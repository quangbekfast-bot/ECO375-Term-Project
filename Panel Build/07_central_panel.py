"""Step 7: central panels (news + prices), Mar 2018 - Feb 2020, at daily, weekly (7-day) and monthly (30-day) frequency.

Inputs : data/news_daily_{raw,filtered}_2018-03_2020-02.csv   (step 5b; sparse ticker x trading-day article counts)
         data/news_ticker_day.csv                              (step 1; all years, used only for each ticker's
                                                                first/last article date = coverage window)
         ../News Data Set/full_history.zip                     (daily prices)
Outputs: data/panel_daily_{raw,filtered}_2018-03_2020-02.csv
         data/panel_weekly_{raw,filtered}_2018-03_2020-02.csv
         data/panel_monthly_{raw,filtered}_2018-03_2020-02.csv
         raw = all matched articles; filtered = price-report headlines removed. Price columns are identical.

Rows: every trading day (or block) on which the ticker has a price, for the 5,513 tickers in the news panel.
  n_articles = articles that day/block; 0 on no-news days INSIDE the ticker's coverage window, blank outside it.
  covered    = 1 if the day lies between the ticker's first and last article in the whole news history
               (DATASET_ISSUES #4: outside that window the scraper didn't collect news, so 'no article' isn't 0).
Daily price columns: open, high, low, close, adj_close, volume, ret (close-to-close on adj_close, previous trading
  day), bad_px (1 if |ret| > 100%: broken split adjustment, DATASET_ISSUES #12).
Blocks (fixed, consecutive calendar days from Saturday 2018-03-03; complete blocks only; weeks run Sat-Fri):
  ret = compounded daily returns in the block (= last close of previous block -> last close of this block),
  open_start (open on the block's first trading day), high (block max), low (block min), close_end, adj_close_end, volume (sum), dollar_volume (sum of close x volume), n_days (trading days),
  n_zero_vol, bad_px (any day), covered (1 only if every trading day in the block is covered), n_articles
  (sum; blank unless covered = 1).

Run in batches (each ~1 min), then merge:
    python 07_central_panel.py 0 3 ; python 07_central_panel.py 1 3 ; python 07_central_panel.py 2 3
    python 07_central_panel.py merge          # or, in two shorter steps: merge daily ; merge blocks
"""
import sys, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
PARTS = DATA / "_07_parts"; PARTS.mkdir(exist_ok=True)
ZIP = HERE.parent / "News Data Set" / "full_history.zip"
START, END = "2018-03-01", "2020-02-28"
ANCHOR, LAST_DAY = pd.Timestamp("2018-03-03"), pd.Timestamp("2020-02-29")
TAG = "2018-03_2020-02"

def write(df, path):
    try:
        df.to_csv(path, index=False, float_format="%.10g")
    except PermissionError:                      # file open elsewhere (e.g. Excel)
        alt = path.with_name(path.stem + "_NEW.csv")
        df.to_csv(alt, index=False, float_format="%.10g")
        print(f"  !! {path.name} is locked (open in another program?) -> wrote {alt.name} instead")
        return alt
    return path

if sys.argv[1:2] != ["merge"]:
    b, nb = int(sys.argv[1]), int(sys.argv[2])
    nraw = pd.read_csv(DATA / f"news_daily_raw_{TAG}.csv", keep_default_na=False)
    nfil = pd.read_csv(DATA / f"news_daily_filtered_{TAG}.csv", keep_default_na=False)
    allnews = pd.read_csv(DATA / "news_ticker_day.csv", usecols=["ticker", "price_date"], keep_default_na=False)
    span = allnews.groupby("ticker")["price_date"].agg(["min", "max"])
    tickers = sorted(nraw.ticker.unique())[b::nb]
    nraw, nfil = (x.set_index(["ticker", "date"])["n_articles"] for x in (nraw, nfil))
    z = zipfile.ZipFile(ZIP)
    files = {Path(n).stem.upper(): n for n in z.namelist()
             if n.startswith("full_history/") and n.endswith(".csv") and "__MACOSX" not in n}
    out = []
    for t in tickers:
        px = (pd.read_csv(z.open(files[t])).rename(columns={"adj close": "adj_close"})
                .drop_duplicates("date").sort_values("date"))
        px = px[(px.date >= "2018-01-01") & (px.date <= END)].copy()
        px["ret"] = px["adj_close"].pct_change(fill_method=None)
        px = px[px.date >= START]
        if px.empty:
            continue
        px.insert(0, "ticker", t)
        px["bad_px"] = (px["ret"].abs() > 1).astype(int)
        lo, hi = span.loc[t, "min"], span.loc[t, "max"]
        px["covered"] = ((px.date >= lo) & (px.date <= hi)).astype(int)
        key = pd.MultiIndex.from_arrays([px.ticker, px.date])
        for col, s in (("n_raw", nraw), ("n_filt", nfil)):
            v = s.reindex(key).to_numpy()
            v = np.where(np.isnan(v), 0, v)
            px[col] = np.where(px["covered"] == 1, v, np.nan)
        out.append(px[["ticker", "date", "open", "high", "low", "close", "adj_close", "volume", "ret",
                       "bad_px", "covered", "n_raw", "n_filt"]])
    pd.concat(out).to_csv(PARTS / f"part_{b:02d}.csv", index=False, float_format="%.10g")
    print(f"batch {b}: {len(tickers)} tickers, {sum(len(o) for o in out):,} ticker-days")
    sys.exit()

# ---------------- merge ----------------
d = pd.concat([pd.read_csv(p, keep_default_na=False, na_values=[""]) for p in sorted(PARTS.glob("part_*.csv"))],
              ignore_index=True)
d = d.sort_values(["ticker", "date"]).reset_index(drop=True)
STAGE = sys.argv[2] if len(sys.argv) > 2 else "all"      # 'merge daily' / 'merge blocks' / 'merge' (both)
# sanity: every news ticker-day must land on a price row
for kind, col in (("raw", "n_raw"), ("filtered", "n_filt")):
    n_news = pd.read_csv(DATA / f"news_daily_{kind}_{TAG}.csv", keep_default_na=False).n_articles.sum()
    print(f"{kind}: articles in news panel {n_news:,} | on price rows {int(d[col].sum()):,}")
price_cols = ["open", "high", "low", "close", "adj_close", "volume", "ret", "bad_px", "covered"]
for kind, col in (("raw", "n_raw"), ("filtered", "n_filt")):
    if STAGE == "blocks":
        break
    f = write(d[["ticker", "date"] + price_cols + [col]].rename(columns={col: "n_articles"}),
              DATA / f"panel_daily_{kind}_{TAG}.csv")
    print(f"wrote {f.name}: {len(d):,} ticker-days, {d.ticker.nunique():,} tickers")
if STAGE == "daily":
    sys.exit()

d["date"] = pd.to_datetime(d["date"])
d["lr"] = np.log1p(d["ret"].clip(lower=-0.999999))
d["dv"] = d["close"] * d["volume"]
d["zv"] = (d["volume"] == 0).astype(int)
for name, L in (("weekly", 7), ("monthly", 30)):
    n_blocks = ((LAST_DAY - ANCHOR).days + 1) // L
    x = d[d.date >= ANCHOR].copy()
    x["block"] = (x.date - ANCHOR).dt.days // L + 1
    x = x[x.block <= n_blocks]
    g = x.groupby(["ticker", "block"])
    blk = pd.DataFrame({
        "ret": np.expm1(g["lr"].sum(min_count=1)),
        "open_start": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
        "close_end": g["close"].last(), "adj_close_end": g["adj_close"].last(),
        "volume": g["volume"].sum(), "dollar_volume": g["dv"].sum(),
        "n_days": g.size(), "n_zero_vol": g["zv"].sum(), "bad_px": g["bad_px"].max(),
        "covered": g["covered"].min(),
        "n_raw": g["n_raw"].sum(min_count=1), "n_filt": g["n_filt"].sum(min_count=1),
    }).reset_index()
    for c in ("n_raw", "n_filt"):
        blk.loc[blk.covered == 0, c] = np.nan
    blk.insert(2, "block_start", (ANCHOR + pd.to_timedelta((blk.block - 1) * L, unit="D")).dt.strftime("%Y-%m-%d"))
    blk.insert(3, "block_end", (ANCHOR + pd.to_timedelta(blk.block * L - 1, unit="D")).dt.strftime("%Y-%m-%d"))
    base = ["ticker", "block", "block_start", "block_end", "ret", "open_start", "high", "low", "close_end", "adj_close_end", "volume",
            "dollar_volume", "n_days", "n_zero_vol", "bad_px", "covered"]
    for kind, col in (("raw", "n_raw"), ("filtered", "n_filt")):
        f = write(blk[base + [col]].rename(columns={col: "n_articles"}), DATA / f"panel_{name}_{kind}_{TAG}.csv")
        print(f"wrote {f.name}: {n_blocks} blocks, {len(blk):,} ticker-blocks, covered {blk.covered.mean():.1%}")

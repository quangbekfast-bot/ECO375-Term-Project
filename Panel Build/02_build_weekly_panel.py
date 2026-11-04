"""Step 2: ticker x week panel (weeks end Friday) built only from files already in the project.

Inputs : data/news_ticker_day.csv (step 1), ../News Data Set/full_history.zip (daily prices)
Output : data/panel_weekly_base.csv

Price side (from full_history.zip):
  ret_w       weekly return = compounded daily close-to-close returns on adj close
  dvol_w      dollar volume = sum over the week of close x volume
  n_days      trading days in the week; n_zero_vol = days with volume 0
  bad_px      1 if any daily |return| > 100% that week (bad split adjustment, see DATASET_ISSUES #12)
  mkt_ret_w   SPY weekly return (same construction), merged on week
Attention side (from news):
  n_news, n_own   articles that week (all / headline names the ticker in parentheses)
  covered         1 between the ticker's first and last news week; zeros are filled only here
  in_gap          1 if the week sits in a run of >= 13 straight zero-news weeks (likely scraper gap, issue #4)
  abn_attn        Ver1: 1 if n_news > average of the previous 4 weeks (~20 trading sessions)
  n_news_lag1     last week's n_news
"""
import time, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ZIP = HERE.parent / "News Data Set" / "full_history.zip"
import sys
OUT = HERE / "data" / "panel_weekly_base.csv"
PARTS = HERE / "data" / "parts"; PARTS.mkdir(exist_ok=True)
if sys.argv[1:] == ["merge"]:
    fs = sorted(PARTS.glob("part_*.csv"))
    pd.concat([pd.read_csv(f, keep_default_na=False, na_values=[""]) for f in fs]).to_csv(OUT, index=False, float_format="%.6g")
    print(f"merged {len(fs)} parts -> {OUT.name}"); sys.exit()
BATCH, NB = int(sys.argv[1]), int(sys.argv[2])
START, END = "2009-06-01", "2023-12-29"
GAP_WEEKS = 13

def weekly_prices(px):
    px = px.rename(columns={"adj close": "adj_close"}).drop_duplicates("date").sort_values("date")
    px = px[(px["date"] >= START) & (px["date"] <= END)]
    r = px["adj_close"].pct_change(fill_method=None)
    px = px.assign(r=r, lr=np.log1p(r.clip(lower=-0.999999)), dv=px["close"] * px["volume"], zv=px["volume"].eq(0), bad=r.abs() > 1,
                   week=px["date"].dt.to_period("W-FRI"))
    g = px.groupby("week")
    return pd.DataFrame({
        "ret_w": np.expm1(g["lr"].sum(min_count=1)),
        "dvol_w": g["dv"].sum(), "close_w": g["close"].last(),
        "n_days": g.size(), "n_zero_vol": g["zv"].sum(), "bad_px": g["bad"].any().astype(int),
    })

t0 = time.time()
news = pd.read_csv(HERE / "data" / "news_ticker_day.csv", keep_default_na=False, parse_dates=["price_date"])
news["week"] = news["price_date"].dt.to_period("W-FRI")
news_w = news.groupby(["ticker", "week"])[["n_news", "n_own"]].sum()
tickers = news_w.index.get_level_values(0).unique()
tickers = tickers[BATCH::NB]
OUT = PARTS / f"part_{BATCH:02d}.csv"

with zipfile.ZipFile(ZIP) as z:
    files = {Path(n).stem.upper(): n for n in z.namelist()
             if n.startswith("full_history/") and n.endswith(".csv") and "__MACOSX" not in n}
    rd = lambda t: pd.read_csv(z.open(files[t]), parse_dates=["date"])
    mkt = weekly_prices(rd("SPY"))["ret_w"].rename("mkt_ret_w")
    first = True
    for i, t in enumerate(tickers):
        if t not in files:
            continue
        w = weekly_prices(rd(t))
        if w.empty:
            continue
        nw = news_w.loc[t].reindex(w.index)
        wk = w.index
        nwk = news_w.loc[t].index
        covered = (wk >= nwk.min()) & (wk <= nwk.max())
        n = nw["n_news"].where(~covered | nw["n_news"].notna(), 0).where(covered)
        # length of the zero-news run each week belongs to
        z0 = n.eq(0)
        run_id = (z0 != z0.shift()).cumsum()
        run_len = z0.groupby(run_id).transform("sum")
        out = w.assign(
            ticker=t,
            n_news=n, n_own=nw["n_own"].where(covered).fillna(0).where(covered),
            covered=covered.astype(int), in_gap=(z0 & (run_len >= GAP_WEEKS)).astype(int),
        )
        trail = out["n_news"].shift(1).rolling(4, min_periods=4).mean()
        out["abn_attn"] = np.where(trail.notna() & out["n_news"].notna(), (out["n_news"] > trail).astype(float), np.nan)
        out["n_news_lag1"] = out["n_news"].shift(1)
        out = out.join(mkt).reset_index()
        out["week_end"] = out["week"].dt.end_time.dt.strftime("%Y-%m-%d")
        out = out.drop(columns="week")
        cols = ["ticker", "week_end", "ret_w", "mkt_ret_w", "dvol_w", "close_w", "n_days", "n_zero_vol", "bad_px",
                "n_news", "n_own", "n_news_lag1", "abn_attn", "covered", "in_gap"]
        out[cols].to_csv(OUT, mode="w" if first else "a", header=first, index=False, float_format="%.6g")
        first = False
        if i % 500 == 0:
            print(f"{i:,}/{len(tickers):,} tickers ({time.time()-t0:,.0f}s)", flush=True)
print(f"done ({time.time()-t0:,.0f}s)", flush=True)

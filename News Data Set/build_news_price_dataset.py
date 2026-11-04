# %% [markdown]
# # ECO375 – Build the news × price dataset
#
# One row per (ticker, article), matched to that ticker's daily price on the
# publication date. Output: ./news_price_matched.csv
#
# Matching rule: the article's publication date (UTC calendar date, as in the raw
# files) is matched to the first trading day ON OR AFTER it, at most 5 days later.
# `same_day` is True when the article came out on a trading day; weekend/holiday
# news is matched to the next session (e.g. Saturday -> Monday).
#
# Cleaning (same rules as Step 11 of news_preliminary_analysis.py):
#   * rows without a ticker are dropped (Reuters/Bloomberg/lenta.ru general news)
#   * dates outside 2009-01-01 .. last price date are dropped (1969 placeholder dates)
#   * each (ticker, article URL) is kept once; the Nasdaq copy wins over Benzinga
#   * tickers tagged by the 30 Nov–16 Dec 2023 scraping batch are dropped
#
# Needs ./cache/*_meta.pkl from news_preliminary_analysis.py (Step 1). The cache rows
# are in raw-file order, so matching is done on the cache and the raw CSVs are only
# streamed once more to pick up the headline, URL, publisher and author.

# %% Setup
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).parent if "__file__" in globals() else Path.cwd()
SOURCES = {
    "nasdaq": HERE / "nasdaq_exteral_data.csv",   # (sic) file name as downloaded
    "benzinga": HERE / "All_external.csv",
}
PRICE_ZIP = HERE / "full_history.zip"
CACHE_DIR = HERE / "cache"
OUT_PATH = HERE / "news_price_matched.csv"

CHUNKSIZE = 25_000      # must match the chunked read that built the cache
MAX_GAP_DAYS = 5        # longest wait for the next trading day (covers long weekends + holidays)
START = pd.Timestamp("2009-01-01")
PRICE_COLS = ["open", "high", "low", "close", "adj_close", "volume", "ret"]

# %% Step 1 – ticker-tagged, de-duplicated article list from the cache
t0 = time.time()
parts = []
for name in SOURCES:
    m = pd.read_pickle(CACHE_DIR / f"{name}_meta.pkl")
    keep = m["ticker"].notna().to_numpy()
    parts.append(pd.DataFrame({
        "source": name,
        "row": np.flatnonzero(keep),     # row position in the raw CSV
        "published_utc": m["date"].to_numpy()[keep],
        "ticker": m["ticker"].astype(str).to_numpy()[keep],
        "url_hash": m["url_hash"].to_numpy()[keep],
        "has_article_text": m["article_len"].notna().to_numpy()[keep],
    }))
    del m
news = pd.concat(parts, ignore_index=True)   # Nasdaq first, so its copy wins the de-dup
del parts
news["ticker"] = news["ticker"].astype("category")
news["pub_date"] = news["published_utc"].dt.normalize()
print(f"{len(news):,} ticker-tagged rows ({time.time() - t0:,.0f}s)")

with zipfile.ZipFile(PRICE_ZIP) as z:
    price_files = {
        Path(n).stem.upper(): n for n in z.namelist()
        if n.startswith("full_history/") and n.endswith(".csv") and "__MACOSX" not in n
    }
    last_price_date = pd.to_datetime(pd.read_csv(z.open(price_files["AAPL"]), usecols=["date"])["date"]).max()

news = news[(news["pub_date"] >= START) & (news["pub_date"] <= last_price_date)]

EMPTY_URL = pd.util.hash_pandas_object(pd.Series([""]), index=False).iloc[0]
dup = news.duplicated(["ticker", "url_hash"]) & (news["url_hash"] != EMPTY_URL)
print(f"dropping {dup.sum():,} repeated (ticker, article) rows")
news = news[~dup]

per_ticker = news["ticker"].value_counts()
in_burst = news.loc[news["pub_date"].between("2023-11-30", "2023-12-16"), "ticker"].value_counts()
burst_share = in_burst.reindex(per_ticker.index, fill_value=0) / per_ticker
artifact = per_ticker.index[(per_ticker >= 1000) & (burst_share > 0.5)]
print(f"dropping {len(artifact)} tickers tagged by the Dec-2023 batch ({news['ticker'].isin(artifact).sum():,} rows)")
news = news[~news["ticker"].isin(artifact)]
print(f"{len(news):,} unique (ticker, article) rows to match")

# %% Step 2 – attach the daily price, ticker by ticker
t0, matched = time.time(), []
no_file = 0
with zipfile.ZipFile(PRICE_ZIP) as z:
    for i, (ticker, g) in enumerate(news.groupby("ticker", observed=True)):
        if ticker not in price_files:
            no_file += len(g)
            continue
        px = (pd.read_csv(z.open(price_files[ticker]), parse_dates=["date"])
                .rename(columns={"adj close": "adj_close"})
                .astype({"date": "datetime64[ns]"})            # same resolution as the cache dates
                .drop_duplicates("date")
                .sort_values("date"))
        px["ret"] = px["adj_close"].pct_change(fill_method=None)   # close-to-close, prior trading day
        px = px.rename(columns={"date": "price_date"})
        matched.append(pd.merge_asof(
            g.sort_values("pub_date"), px, left_on="pub_date", right_on="price_date",
            direction="forward", tolerance=pd.Timedelta(days=MAX_GAP_DAYS),
        ))
        if i % 1000 == 0:
            print(f"  {i:,} tickers matched ({time.time() - t0:,.0f}s)")
matched = pd.concat(matched, ignore_index=True)
no_price = matched["price_date"].isna()
print(f"no price file for ticker: {no_file:,} rows | no trading day within {MAX_GAP_DAYS} days: {no_price.sum():,} rows")
matched = matched[~no_price]
matched["same_day"] = matched["price_date"] == matched["pub_date"]
matched["volume"] = matched["volume"].round().astype("Int64")
matched[["open", "high", "low", "close", "adj_close"]] = matched[["open", "high", "low", "close", "adj_close"]].round(4)
matched["ret"] = matched["ret"].round(6)
print(f"{len(matched):,} rows matched; {matched['same_day'].mean():.1%} on the publication date itself")

# %% Step 3 – stream the raw CSVs once more for the text fields and write the output
OUT_COLS = ["source", "ticker", "published_utc", "pub_date", "price_date", "same_day",
            "title", "url", "publisher", "author", "has_article_text"] + PRICE_COLS
OUT_PATH.unlink(missing_ok=True)
t0, written = time.time(), 0
for name, path in SOURCES.items():
    want = matched[matched["source"] == name].sort_values("row").set_index("row")
    reader = pd.read_csv(
        path, chunksize=CHUNKSIZE, dtype=str,
        keep_default_na=False, na_values=[""],          # same parsing as the cache build
        usecols=["Article_title", "Url", "Publisher", "Author"],
    )
    start = 0
    for j, ch in enumerate(reader):
        rows = want.index[(want.index >= start) & (want.index < start + len(ch))]
        if len(rows):
            sel = ch.iloc[rows - start]
            h = pd.util.hash_pandas_object(sel["Url"].fillna(""), index=False).to_numpy()
            assert (h == want.loc[rows, "url_hash"].to_numpy()).all(), f"{name}: raw rows out of sync with cache near row {start:,}"
            out = want.loc[rows].assign(
                title=sel["Article_title"].to_numpy(), url=sel["Url"].to_numpy(),
                publisher=sel["Publisher"].to_numpy(), author=sel["Author"].to_numpy(),
            )[OUT_COLS]
            out["pub_date"] = out["pub_date"].dt.strftime("%Y-%m-%d")
            out["price_date"] = out["price_date"].dt.strftime("%Y-%m-%d")
            out.to_csv(OUT_PATH, mode="a", header=written == 0, index=False, date_format="%Y-%m-%d %H:%M:%S")
            written += len(out)
        start += len(ch)
        if j % 100 == 0:
            print(f"  {name}: {start:,} raw rows read, {written:,} written ({time.time() - t0:,.0f}s)")
print(f"done: {written:,} rows -> {OUT_PATH.name} ({OUT_PATH.stat().st_size / 1e9:.2f} GB, {time.time() - t0:,.0f}s)")

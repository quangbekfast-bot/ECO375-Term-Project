"""Step 5b: firm x trading-day news panel, Mar 2018 - Feb 2020, aligned with the price panel.

Input : ../News Data Set/news_price_matched.csv   (built by build_news_price_dataset.py: one row per
        ticker-article, each matched to the first trading day on/after its publication date; already
        de-duplicated, untagged news and the Dec-2023 batch removed, tickers without prices dropped)
        headline_classifier.py
Output: data/news_daily_raw_2018-03_2020-02.csv       ticker, date, n_articles   (all matched articles)
        data/news_daily_filtered_2018-03_2020-02.csv  ticker, date, n_articles   (price-report headlines removed)

  * date = price_date, the matched TRADING day (weekend/holiday articles sit on the next session), so the
           panel lines up with the daily price files.
  * window: trading days 2018-03-01 .. 2020-02-28.
  * filter: drop 'price_report' headlines; keep 'event_plus_price' and 'no_price'.
  * sparse: a ticker-day appears only if it had at least one article.
Supersedes 05_news_daily_panel.py (built from the raw Nasdaq file on calendar dates); those outputs are in
data/_superseded_rawfile/.
"""
import sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from headline_classifier import classify

SRC = HERE.parent / "News Data Set" / "news_price_matched.csv"
DATA = HERE / "data"
START, END = "2018-03-01", "2020-02-28"

parts = []
for ch in pd.read_csv(SRC, usecols=["ticker", "price_date", "title"], dtype=str,
                      keep_default_na=False, na_values=[""], chunksize=1_000_000):
    parts.append(ch[(ch["price_date"] >= START) & (ch["price_date"] <= END)])
rows = pd.concat(parts, ignore_index=True).rename(columns={"price_date": "date"})
rows["cat"] = classify(rows["title"].fillna("").to_numpy())
print(f"matched articles in window: {len(rows):,} | classes: {rows['cat'].value_counts().to_dict()}")

raw = rows.groupby(["ticker", "date"]).size().rename("n_articles").reset_index()
filt = rows[rows["cat"] != "price_report"].groupby(["ticker", "date"]).size().rename("n_articles").reset_index()
for df, name in [(raw, "raw"), (filt, "filtered")]:
    f = DATA / f"news_daily_{name}_2018-03_2020-02.csv"
    df.to_csv(f, index=False)
    print(f"wrote {f.name}: {len(df):,} ticker-days, {df.ticker.nunique():,} tickers, {df.n_articles.sum():,} articles, "
          f"{df.date.nunique()} trading days ({df.date.min()} .. {df.date.max()})")

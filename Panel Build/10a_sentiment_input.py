"""Step 10a: input file for headline sentiment (FinBERT, run in Google Colab).

Input : ../News Data Set/news_price_matched.csv, headline_classifier.py
Output: data/_10_work/finbert_input_headlines.csv.gz   one row per DISTINCT filtered headline:
            headline_id, title, n_rows (how many ticker-article rows use it), first_date
        data/_10_work/article_headline_map.csv.gz      one row per filtered ticker-article row:
            ticker, date (matched trading day), headline_id
Same window and filter as the weekly panel (05b): trading days 2017-02-01 .. 2020-02-28, price-report
headlines removed. A headline tagged to several tickers is scored once and its label is copied to every row.
Upload finbert_input_headlines.csv.gz to Colab (finbert_colab.ipynb); merge the result with 10b.
"""
import sys
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from headline_classifier import classify

SRC = HERE.parent / "News Data Set" / "news_price_matched.csv"
OUT = HERE / "data" / "_10_work"; OUT.mkdir(parents=True, exist_ok=True)
START, END = "2017-02-01", "2020-02-28"

parts = []
for ch in pd.read_csv(SRC, usecols=["ticker", "price_date", "title"], dtype=str,
                      keep_default_na=False, na_values=[""], chunksize=1_000_000):
    parts.append(ch[(ch["price_date"] >= START) & (ch["price_date"] <= END)])
rows = pd.concat(parts, ignore_index=True).rename(columns={"price_date": "date"})
rows["title"] = rows["title"].fillna("")
rows = rows[classify(rows["title"].to_numpy()) != "price_report"].copy()

heads = (rows.groupby("title", sort=False)
             .agg(n_rows=("ticker", "size"), first_date=("date", "min"))
             .reset_index()
             .sort_values(["first_date", "title"])
             .reset_index(drop=True))
heads.insert(0, "headline_id", range(1, len(heads) + 1))
rows = rows.merge(heads[["headline_id", "title"]], on="title", how="left")
assert rows.headline_id.notna().all()

heads[["headline_id", "title", "n_rows", "first_date"]].to_csv(OUT / "finbert_input_headlines.csv.gz", index=False)
rows[["ticker", "date", "headline_id"]].sort_values(["date", "ticker"]).to_csv(
    OUT / "article_headline_map.csv.gz", index=False)
print(f"filtered ticker-article rows: {len(rows):,} | distinct headlines: {len(heads):,} "
      f"({(heads.first_date >= '2018-03-03').sum():,} first seen in the sample period)")

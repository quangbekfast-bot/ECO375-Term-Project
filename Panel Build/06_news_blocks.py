"""Step 6: weekly (7-day) and monthly (30-day) sub-panels from the daily news panels of step 5.

Inputs : data/news_daily_raw_2018-03_2020-02.csv, data/news_daily_filtered_2018-03_2020-02.csv
Outputs: data/news_weekly_{raw,filtered}_2018-03_2020-02.csv
         data/news_monthly_{raw,filtered}_2018-03_2020-02.csv
         columns: ticker, block, block_start, block_end, n_articles

Blocks are fixed, non-overlapping runs of consecutive calendar days:
  * week  = 7 days, month = 30 days
  * both start on ANCHOR = Saturday 2018-03-03, so each week runs Saturday-Friday. That matches weekly returns
    measured Friday close to Friday close: weekend articles count toward the following trading week.
  * only complete blocks are kept: 104 weeks (2018-03-03 .. 2020-02-28) and 24 months (2018-03-03 .. 2020-02-20).
    Days outside complete blocks are dropped (weeks: 1-2 Mar 2018 and 29 Feb 2020; months: 1-2 Mar 2018
    and 21-29 Feb 2020).
  * like the daily panel, rows exist only for ticker-blocks with at least one article; zero-fill later,
    inside each ticker's covered period only.
"""
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
ANCHOR = pd.Timestamp("2018-03-03")          # Saturday
LAST_DAY = pd.Timestamp("2020-02-29")

for kind in ["raw", "filtered"]:
    d = pd.read_csv(DATA / f"news_daily_{kind}_2018-03_2020-02.csv", keep_default_na=False, parse_dates=["date"])
    for name, L in [("weekly", 7), ("monthly", 30)]:
        n_blocks = ((LAST_DAY - ANCHOR).days + 1) // L          # complete blocks only
        x = d[d["date"] >= ANCHOR].copy()
        x["block"] = (x["date"] - ANCHOR).dt.days // L + 1     # 1, 2, ...
        x = x[x["block"] <= n_blocks]
        out = x.groupby(["ticker", "block"])["n_articles"].sum().reset_index()
        out["block_start"] = (ANCHOR + pd.to_timedelta((out["block"] - 1) * L, unit="D")).dt.strftime("%Y-%m-%d")
        out["block_end"] = (ANCHOR + pd.to_timedelta(out["block"] * L - 1, unit="D")).dt.strftime("%Y-%m-%d")
        out = out[["ticker", "block", "block_start", "block_end", "n_articles"]]
        f = DATA / f"news_{name}_{kind}_2018-03_2020-02.csv"
        out.to_csv(f, index=False)
        print(f"{f.name}: {n_blocks} blocks ({out.block_start.min()} .. {out.block_end.max()}), "
              f"{len(out):,} ticker-blocks, {out.ticker.nunique():,} tickers, {out.n_articles.sum():,} articles "
              f"(daily file: {d.n_articles.sum():,}; dropped outside complete blocks: {d.n_articles.sum()-out.n_articles.sum():,})")

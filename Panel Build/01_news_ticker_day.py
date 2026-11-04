"""Step 1: collapse news_price_matched.csv (one row per ticker-article) to ticker x trading-day counts.
Columns: n_news (all articles), n_own (headline names the ticker in parentheses, e.g. 'Agilent (A)'),
n_same_day (published on a trading day). Reads in chunks, so it fits in ~3 GB RAM."""
import re, time
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "News Data Set" / "news_price_matched.csv"
OUT = HERE / "data" / "news_ticker_day.csv"

t0, parts = time.time(), []
reader = pd.read_csv(SRC, usecols=["ticker", "price_date", "same_day", "title"], dtype=str,
                     keep_default_na=False, chunksize=500_000)
for i, ch in enumerate(reader):
    tk, ti = ch["ticker"].to_numpy(), ch["title"].fillna("").to_numpy()
    ch["own"] = [f"({t})" in s or f"({t}." in s or f":{t})" in s for t, s in zip(tk, ti)]  # (A), (NYSE:A)
    ch["sd"] = ch["same_day"].eq("True")
    parts.append(ch.groupby(["ticker", "price_date"]).agg(n_news=("own", "size"), n_own=("own", "sum"), n_same_day=("sd", "sum")))
    print(f"chunk {i}: {time.time()-t0:,.0f}s", flush=True)
out = pd.concat(parts).groupby(level=[0, 1]).sum().reset_index()
out.to_csv(OUT, index=False)
print(out.shape, out[["n_news", "n_own"]].sum().to_dict(), f"{time.time()-t0:,.0f}s")

"""Reconcile prices across the three sources and look for missing open prices.

Sources compared (trading days 2018-03-01 .. 2020-02-28):
  A. ../News Data Set/full_history.zip          original daily price files
  B. ../News Data Set/news_price_matched.csv    news rows with the price of their matched trading day
  C. data/panel_daily_raw_2018-03_2020-02.csv   central daily panel (step 7)
Also checks which price columns the weekly/monthly panels carry.
Writes analysis_report.txt next to this script.

    python analysis.py            # A is checked on a random sample of tickers (default 400)
    python analysis.py --all      # check every ticker against A (slower)
"""
import sys, zipfile, random
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
NEWS = HERE.parent / "News Data Set"
DATA = HERE / "data"
TAG = "2018-03_2020-02"
START, END = "2018-03-01", "2020-02-28"
COLS = ["open", "high", "low", "close", "adj_close", "volume"]
lines = []
def say(s=""):
    print(s); lines.append(s)

# ---------- C: central daily panel ----------
C = pd.read_csv(DATA / f"panel_daily_raw_{TAG}.csv", usecols=["ticker", "date"] + COLS,
                keep_default_na=False, na_values=[""])
say(f"C panel_daily: {len(C):,} ticker-days, {C.ticker.nunique():,} tickers")
say("  missing values per column: " + str(C[COLS].isna().sum().to_dict()))
say(f"  open == 0: {(C.open == 0).sum():,} | open missing but close present: {(C.open.isna() & C.close.notna()).sum():,}")
miss = C[C[COLS].isna().all(axis=1)]
say(f"  rows with ALL prices missing: {len(miss):,} (tickers: {sorted(miss.ticker.unique())[:15]})")

# ---------- B: news_price_matched ----------
parts = []
for ch in pd.read_csv(NEWS / "news_price_matched.csv", usecols=["ticker", "price_date"] + COLS, dtype={"ticker": str},
                      keep_default_na=False, na_values=[""], chunksize=1_000_000):
    parts.append(ch[(ch.price_date >= START) & (ch.price_date <= END)])
B = pd.concat(parts).rename(columns={"price_date": "date"}).drop_duplicates(["ticker", "date"])
say(f"\nB news_price_matched (one row per ticker-day with news): {len(B):,} ticker-days")
say("  missing values per column: " + str(B[COLS].isna().sum().to_dict()))
j = B.merge(C, on=["ticker", "date"], suffixes=("_B", "_C"), how="left", indicator=True)
say(f"  ticker-days of B found in C: {(j._merge == 'both').mean():.4%}")
for c in COLS:
    a, b = j[c + "_B"], j[c + "_C"]
    ok = a.notna() & b.notna()
    same = (np.isclose(a[ok], b[ok], rtol=1e-4, atol=1e-4)).mean()
    say(f"  {c:9s} B vs C identical (to 4 dp): {same:.4%} of {ok.sum():,}")

# ---------- A: original price files ----------
z = zipfile.ZipFile(NEWS / "full_history.zip")
files = {Path(n).stem.upper(): n for n in z.namelist()
         if n.startswith("full_history/") and n.endswith(".csv") and "__MACOSX" not in n}
tick = sorted(C.ticker.unique())
if "--all" not in sys.argv:
    random.seed(0); tick = sorted(random.sample(tick, min(400, len(tick))))
A = []
for t in tick:
    px = pd.read_csv(z.open(files[t])).rename(columns={"adj close": "adj_close"})
    px = px[(px.date >= START) & (px.date <= END)].assign(ticker=t)
    A.append(px)
A = pd.concat(A)
say(f"\nA original price files: {len(tick):,} tickers checked, {len(A):,} ticker-days")
say("  missing values per column: " + str(A[COLS].isna().sum().to_dict()))
say(f"  open == 0: {(A.open == 0).sum():,} | duplicated dates: {A.duplicated(['ticker','date']).sum():,}")
j = A.merge(C[C.ticker.isin(tick)], on=["ticker", "date"], suffixes=("_A", "_C"), how="outer", indicator=True)
say(f"  rows only in A: {(j._merge=='left_only').sum():,} | only in C: {(j._merge=='right_only').sum():,}")
for c in COLS:
    a, b = j[c + "_A"], j[c + "_C"]
    ok = a.notna() & b.notna()
    say(f"  {c:9s} A vs C identical (to 4 dp): {np.isclose(a[ok], b[ok], rtol=1e-4, atol=1e-4).mean():.4%}")
if len(miss):
    m = miss[miss.ticker.isin(tick)]
    say(f"  the all-missing C rows for sampled tickers: {len(m)}; in A they are: "
        + str(A.merge(m[['ticker','date']], on=['ticker','date'])[COLS].isna().all(axis=1).value_counts().to_dict()))

# ---------- block panels ----------
say("")
for f in ("weekly", "monthly"):
    cols = pd.read_csv(DATA / f"panel_{f}_raw_{TAG}.csv", nrows=1).columns.tolist()
    say(f"panel_{f}: price columns = {[c for c in cols if c in ('open_start','high','low','close_end','adj_close_end','volume','dollar_volume','ret')]}"
        f" | has an open column: {any(c.startswith('open') for c in cols)}")

(HERE / "analysis_report.txt").write_text("\n".join(lines) + "\n")
print("\nreport -> analysis_report.txt")

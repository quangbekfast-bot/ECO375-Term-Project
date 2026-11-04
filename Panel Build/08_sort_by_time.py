"""Step 8: re-sort the central panels by time first, then ticker, so each day / week / month forms one
contiguous cross-section (all firms for that period together). Files are overwritten in place; values are
read and written as text, so nothing is reformatted.

    python 08_sort_by_time.py                 # all six panels
    python 08_sort_by_time.py panel_daily_raw_2018-03_2020-02.csv   # one file
"""
import sys
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
TAG = "2018-03_2020-02"
names = sys.argv[1:] or [f"panel_{f}_{k}_{TAG}.csv" for f in ("daily", "weekly", "monthly") for k in ("raw", "filtered")]
for name in names:
    path = DATA / name
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if "date" in df:
        df = df.sort_values(["date", "ticker"], kind="mergesort")
        t, n_t = "date", df["date"].nunique()
    else:
        df = df.assign(_b=df["block"].astype(int)).sort_values(["_b", "ticker"], kind="mergesort").drop(columns="_b")
        t, n_t = "block", df["block"].nunique()
    sizes = df.groupby(t, sort=False).size()
    df.to_csv(path, index=False)
    print(f"{name}: {len(df):,} rows sorted by {t}, ticker -> {n_t} cross-sections "
          f"(firms per cross-section: min {sizes.min():,}, median {int(sizes.median()):,}, max {sizes.max():,})")

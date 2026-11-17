"""Step 10b: add headline-sentiment counts to the filtered weekly panel.

Inputs : data/_10_work/finbert_labels.csv.gz         (from finbert_colab.ipynb: headline_id, label, p_*)
         data/_10_work/article_headline_map.csv.gz    (from 10a: ticker, date, headline_id; one row per article)
         data/panel_weekly_filtered_2018-03_2020-02.csv
Output : the same weekly panel with four new columns (file rewritten in place, plus a fresh .csv.gz):
           agg_positive, agg_negative, agg_neutral   articles in the ticker-week with that label
           agg_unscored                              articles whose headline has no label (should be 0)
         Blank wherever n_articles is blank (block outside the ticker's news coverage).
Check  : agg_positive + agg_negative + agg_neutral + agg_unscored == n_articles in every row with news coverage.

    python 10b_merge_sentiment.py                       # default files
    python 10b_merge_sentiment.py --labels other.csv.gz --out test.csv   # e.g. a test run
"""
import argparse, gzip, shutil
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
W = DATA / "_10_work"
ANCHOR, L = pd.Timestamp("2018-03-03"), 7          # same weekly blocks as step 7

ap = argparse.ArgumentParser()
ap.add_argument("--labels", default=str(W / "finbert_labels.csv.gz"))
ap.add_argument("--panel", default=str(DATA / "panel_weekly_filtered_2018-03_2020-02.csv"))
ap.add_argument("--out", default=None)
a = ap.parse_args()
out = Path(a.out) if a.out else Path(a.panel)

lab = pd.read_csv(a.labels, usecols=["headline_id", "label"])
art = pd.read_csv(W / "article_headline_map.csv.gz")
art = art.merge(lab, on="headline_id", how="left")
art["label"] = art["label"].fillna("unscored")
art["block"] = (pd.to_datetime(art["date"]) - ANCHOR).dt.days // L + 1

cnt = (art.groupby(["ticker", "block", "label"]).size().unstack(fill_value=0)
          .reindex(columns=["positive", "negative", "neutral", "unscored"], fill_value=0)
          .add_prefix("agg_").reset_index())

p = pd.read_csv(a.panel, keep_default_na=False, na_values=[""], dtype={"ticker": str})
p = p.drop(columns=[c for c in p.columns if c.startswith("agg_")])      # re-runs replace old columns
p = p.merge(cnt, on=["ticker", "block"], how="left")
cols = ["agg_positive", "agg_negative", "agg_neutral", "agg_unscored"]
has = p["n_articles"].notna()
p.loc[has, cols] = p.loc[has, cols].fillna(0)
p.loc[~has, cols] = np.nan

tot = p.loc[has, cols].sum(axis=1)
bad = (tot != p.loc[has, "n_articles"]).sum()
print(f"rows with coverage: {has.sum():,} | rows where the four counts != n_articles: {bad}")
assert bad == 0, "sentiment counts do not add up to n_articles"
s = p.loc[has & (p.pre_sample == 0), cols].sum()
print("sample-period articles by label:", {k: int(v) for k, v in s.items()},
      "| shares:", (s / s.sum()).round(3).to_dict())

p.to_csv(out, index=False, float_format="%.10g")
with open(out, "rb") as fi, gzip.open(str(out) + ".gz", "wb", compresslevel=6) as fo:
    shutil.copyfileobj(fi, fo)
print(f"wrote {out.name} (+ .gz): {len(p):,} rows")

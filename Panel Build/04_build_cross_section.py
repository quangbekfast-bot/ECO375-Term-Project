"""Step 4 (cross-sectional version): one row per stock for a single year.

Input : data/panel_weekly_base.csv (step 2); optional raw/F-F_Research_Data_Factors_weekly.csv for rf
Output: data/cross_section_<YEAR>.csv

  ret_y        annual return = compounded weekly returns over the year's 52 weeks
  rf_y         annual risk-free = compounded Ken French weekly RF (if the file is in raw/)
  exret_y      ret_y - rf_y
  n_news_y     total articles in the year; n_own_y = headline names the ticker
  hi_attn      1 if n_news_y > mean of n_news_y across all stocks in the sample, else 0
  n_news_prev  total articles in the previous year (lagged attention)
  log_dvol_prev log of average weekly dollar volume in the previous year (size/liquidity proxy we already have)
Sample: stocks with all weeks of the year covered by the news scraper, no 13-week scraper gap, no broken prices,
and a full year of returns.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
YEAR = int(sys.argv[1]) if len(sys.argv) > 1 else 2019

p = pd.read_csv(HERE / "data" / "panel_weekly_base.csv", keep_default_na=False, na_values=[""],
                parse_dates=["week_end"],
                usecols=["ticker", "week_end", "ret_w", "dvol_w", "bad_px", "n_news", "n_own", "covered", "in_gap"])
p["year"] = p["week_end"].dt.year
cur, prev = p[p["year"] == YEAR], p[p["year"] == YEAR - 1]
nweeks = cur["week_end"].nunique()

g = cur.groupby("ticker")
cs = pd.DataFrame({
    "weeks": g["ret_w"].count(),
    "ret_y": np.expm1(np.log1p(cur["ret_w"].clip(lower=-0.999999)).groupby(cur["ticker"]).sum()),
    "n_news_y": g["n_news"].sum(min_count=1), "n_own_y": g["n_own"].sum(min_count=1),
    "cov_weeks": g["covered"].sum(), "gap_weeks": g["in_gap"].sum(), "bad_weeks": g["bad_px"].sum(),
})
gp = prev.groupby("ticker")
cs = cs.join(pd.DataFrame({"n_news_prev": gp["n_news"].sum(min_count=1), "prev_cov": gp["covered"].sum(),
                           "log_dvol_prev": np.log(gp["dvol_w"].mean().where(lambda s: s > 0))}))
keep = (cs["weeks"] == nweeks) & (cs["cov_weeks"] == nweeks) & (cs["gap_weeks"] == 0) & (cs["bad_weeks"] == 0)
cs = cs[keep].copy()
cs.loc[cs["prev_cov"] < prev["week_end"].nunique(), "n_news_prev"] = np.nan   # previous year not fully covered
cs["hi_attn"] = (cs["n_news_y"] > cs["n_news_y"].mean()).astype(int)

f = HERE / "raw" / "F-F_Research_Data_Factors_weekly.csv"
if f.exists():
    lines = [l for l in f.read_text().splitlines() if l[:8].strip().isdigit()]
    ff = pd.DataFrame([l.split(",")[:5] for l in lines], columns=["d", "m", "s", "h", "rf"])
    ff["d"] = pd.to_datetime(ff["d"].str.strip(), format="%Y%m%d")
    rf = ff.loc[ff["d"].dt.to_period("W-FRI").dt.end_time.dt.year == YEAR, "rf"].astype(float) / 100
    cs["rf_y"] = np.prod(1 + rf) - 1
    cs["exret_y"] = cs["ret_y"] - cs["rf_y"]

cols = [c for c in ["ret_y", "rf_y", "exret_y", "n_news_y", "n_own_y", "hi_attn", "n_news_prev", "log_dvol_prev"] if c in cs]
cs[cols].reset_index().to_csv(HERE / "data" / f"cross_section_{YEAR}.csv", index=False, float_format="%.6g")
print(f"{YEAR}: {len(cs):,} stocks written")

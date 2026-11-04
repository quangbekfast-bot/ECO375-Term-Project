"""Step 3: add the controls you download yourself (put the files in raw/) to the weekly panel.

Each block runs only if its file is in raw/, so you can add sources one at a time.
Output: data/panel_weekly_full.csv  (restricted to YEARS below)

raw/F-F_Research_Data_Factors_weekly.csv   Ken French Data Library, "Fama/French 3 Factors [Weekly]" (unzip it)
    -> rf_w (weekly 1-month T-bill), mkt_rf_w (market excess return), smb_w, hml_w; also exret_w = ret_w - rf_w
raw/crsp_daily.csv                          WRDS > CRSP > Daily Stock File: PERMNO, date, TICKER, PRC, VOL, SHROUT
    -> permno, mktcap (|PRC| x SHROUT x 1000 at week end), log_size, turnover (week VOL / shares out)
raw/ccm_fundq.csv                           WRDS > CRSP/Compustat Merged > Fundamentals Quarterly:
                                            LPERMNO, datadate, rdq, ceqq, epspxq
    -> bm (latest announced book equity / mktcap), earn_wk (1 in the week of the earnings release, rdq),
       sue (seasonal-random-walk surprise: (EPS_q - EPS_q-4) / price, set in the announcement week)
raw/ibes_numest.csv + raw/ibes_crsp_link.csv WRDS > IBES > Summary History (EPS, FPI=1) : TICKER, STATPERS, NUMEST
                                            WRDS > Linking Suite > IBES-CRSP link : TICKER, PERMNO, SCORE
    -> numest (analysts covering, latest monthly snapshot)
Not built here: InstHold (13F) - see the tracker, section 'Controls'.
"""
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW, DATA = HERE / "raw", HERE / "data"
YEARS = (2018, 2019)   # change once the sample period is fixed

def wk(s):  # any date -> the Friday ending its week
    return pd.to_datetime(s).dt.to_period("W-FRI").dt.end_time.dt.normalize()

def low(df):
    df.columns = [c.lower() for c in df.columns]
    return df

p = pd.read_csv(DATA / "panel_weekly_base.csv", keep_default_na=False, na_values=[""], parse_dates=["week_end"])
p = p[p["week_end"].dt.year.between(*YEARS)].copy()
print(f"base: {len(p):,} rows, {p.ticker.nunique():,} tickers")

# --- Ken French weekly factors ------------------------------------------------------------
f = RAW / "F-F_Research_Data_Factors_weekly.csv"
if f.exists():
    lines = [l for l in f.read_text().splitlines() if l[:8].strip().isdigit()]
    ff = pd.DataFrame([l.split(",") for l in lines]).iloc[:, :5]
    ff.columns = ["date", "mkt_rf_w", "smb_w", "hml_w", "rf_w"]
    ff["week_end"] = wk(pd.to_datetime(ff["date"].str.strip(), format="%Y%m%d"))
    ff[["mkt_rf_w", "smb_w", "hml_w", "rf_w"]] = ff[["mkt_rf_w", "smb_w", "hml_w", "rf_w"]].astype(float) / 100
    p = p.merge(ff.drop(columns="date"), on="week_end", how="left")
    p["exret_w"] = p["ret_w"] - p["rf_w"]
    print("added Ken French factors; weeks unmatched:", p["rf_w"].isna().sum())

# --- CRSP daily: size and turnover ----------------------------------------------------------
f = RAW / "crsp_daily.csv"
if f.exists():
    c = low(pd.read_csv(f, usecols=lambda x: x.lower() in {"permno", "date", "ticker", "prc", "vol", "shrout"}))
    c["week_end"] = wk(c["date"])
    c = c.sort_values(["permno", "date"])
    g = c.groupby(["permno", "week_end"])
    cw = pd.DataFrame({"ticker": g["ticker"].last(), "prc": g["prc"].last().abs(), "shrout": g["shrout"].last(),
                       "vol": g["vol"].sum()}).reset_index()
    cw["mktcap"] = cw["prc"] * cw["shrout"] * 1000
    cw["turnover"] = cw["vol"] / (cw["shrout"] * 1000)
    # one permno per (ticker, week): keep the largest share class
    cw = cw.sort_values("mktcap", ascending=False).drop_duplicates(["ticker", "week_end"])
    p = p.merge(cw[["ticker", "week_end", "permno", "mktcap", "turnover"]], on=["ticker", "week_end"], how="left")
    p["log_size"] = np.log(p["mktcap"])
    p["permno"] = p["permno"].astype(float)
    print("added CRSP size/turnover; rows matched:", p["permno"].notna().mean().round(3))

# --- Compustat quarterly via CCM: book-to-market, earnings week, SUE -----------------------
f = RAW / "ccm_fundq.csv"
if f.exists() and "permno" in p:
    q = low(pd.read_csv(f)).rename(columns={"lpermno": "permno"})
    q["permno"] = q["permno"].astype(float)
    q = q.dropna(subset=["rdq"]).sort_values(["permno", "datadate"])
    q["eps_lag4"] = q.groupby("permno")["epspxq"].shift(4)
    q["week_end"] = wk(q["rdq"])
    q = q.drop_duplicates(["permno", "week_end"], keep="last")
    p = p.sort_values("week_end")
    p = pd.merge_asof(p, q[["permno", "week_end", "ceqq", "epspxq", "eps_lag4"]].sort_values("week_end"),
                      on="week_end", by="permno", direction="backward")   # latest release on or before the week
    p["bm"] = p["ceqq"] * 1e6 / p["mktcap"]
    ann = q[["permno", "week_end"]].assign(earn_wk=1)
    p = p.merge(ann, on=["permno", "week_end"], how="left")
    p["earn_wk"] = p["earn_wk"].fillna(0).astype(int)
    p["sue"] = np.where(p["earn_wk"] == 1, (p["epspxq"] - p["eps_lag4"]) / p["close_w"], 0.0)
    print("added BM, earn_wk, SUE")

# --- IBES analyst coverage --------------------------------------------------------------------
f, fl = RAW / "ibes_numest.csv", RAW / "ibes_crsp_link.csv"
if f.exists() and fl.exists() and "permno" in p:
    i = low(pd.read_csv(f))
    lk = low(pd.read_csv(fl)).sort_values("score").drop_duplicates("ticker")   # best-quality link (score 1 = best)
    i = i.merge(lk[["ticker", "permno"]], on="ticker")
    i["permno"] = i["permno"].astype(float)
    i["week_end"] = wk(i["statpers"])
    i = i.sort_values("week_end").drop_duplicates(["permno", "week_end"], keep="last")
    p = pd.merge_asof(p.sort_values("week_end"), i[["permno", "week_end", "numest"]], on="week_end",
                      by="permno", direction="backward")
    p["numest"] = p["numest"].fillna(0)
    print("added NumEst")

p = p.sort_values(["ticker", "week_end"])
p.to_csv(DATA / "panel_weekly_full.csv", index=False, float_format="%.6g")
print(f"wrote panel_weekly_full.csv: {len(p):,} rows, columns: {list(p.columns)}")

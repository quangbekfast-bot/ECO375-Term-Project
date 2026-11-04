"""Step 5: firm x day news-coverage panel from the RAW Nasdaq news file, Mar 2018 - Feb 2020.

Input : ../News Data Set/nasdaq_exteral_data.csv   (raw, ~23 GB; file name misspelled as downloaded)
        headline_classifier.py                      (dictionary rules for price-report headlines)
Output: data/news_daily_raw_2018-03_2020-02.csv       ticker, date, n_articles   (all ticker-tagged articles)
        data/news_daily_filtered_2018-03_2020-02.csv  ticker, date, n_articles   (price-report headlines removed)

Rules
  * date   = calendar date of the article's timestamp (the raw 'Date' field, labelled UTC). Weekends are kept;
             99% of timestamps are 00:00:00 placeholders, so only the date is real (DATASET_ISSUES #3, #8).
  * kept   = rows with a ticker (Stock_symbol), dated 2018-03-01 .. 2020-02-29.
  * de-dup = each (ticker, article URL) counted once (DATASET_ISSUES #11). Rows with no URL are all kept.
  * one article tagged to several tickers counts once for each ticker.
  * filter = drop headlines classified 'price_report' (pure price/technical reports with no stated cause).
             'event_plus_price' and 'no_price' headlines are kept.
  * panel is sparse: a ticker-day appears only if it had at least one article. Zero-filling should be done
             later, and only inside each ticker's covered period (DATASET_ISSUES #4).

The raw file has line breaks inside quoted article text, so it is read with Python's csv module (same quoting
rules as pandas). Progress (byte position at a record boundary) is saved every ~20 s, so the script can be
stopped and re-run and it resumes where it left off:
    python 05_news_daily_panel.py                    # run to the end
    python 05_news_daily_panel.py --max-seconds 150  # run at most ~150 s, then save and stop
    python 05_news_daily_panel.py --reset            # start over
"""
import argparse, csv, json, sys, time
from pathlib import Path
import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from headline_classifier import classify

SRC = HERE.parent / "News Data Set" / "nasdaq_exteral_data.csv"
DATA = HERE / "data"
WORK = DATA / "_05_work"
STATE = WORK / "state.json"
START, END = b"2018-03-01", b"2020-02-29"
OUT_RAW = DATA / "news_daily_raw_2018-03_2020-02.csv"
OUT_FILT = DATA / "news_daily_filtered_2018-03_2020-02.csv"

ap = argparse.ArgumentParser()
ap.add_argument("--max-seconds", type=float, default=0)
ap.add_argument("--reset", action="store_true")
args = ap.parse_args()

WORK.mkdir(parents=True, exist_ok=True)
if args.reset and STATE.exists():
    STATE.write_text(json.dumps({"offset": None}))
st = json.loads(STATE.read_text()) if STATE.exists() else {"offset": None}

with open(SRC, "rb") as f:
    header = f.readline()
    hdr_end = f.tell()
size = SRC.stat().st_size
if st.get("offset") is None:
    for old in WORK.glob("part_*.csv"):
        old.write_text("")                       # can't delete in this folder; empty old parts instead
    st = {"offset": hdr_end, "records": 0, "kept_in_window": 0, "part": 0, "done": False}

t0 = time.time()
csv.field_size_limit(sys.maxsize)
COLS = header.decode().strip().split(",")
I_DATE, I_TITLE, I_TK, I_URL = (COLS.index(c) for c in ("Date", "Article_title", "Stock_symbol", "Url"))

def save_part(buf):
    if not buf:
        return 0
    df = pd.DataFrame(buf, columns=["ticker", "date", "url", "title"])
    df["cat"] = classify(df["title"].to_numpy())
    df.drop(columns="title").to_csv(WORK / f"part_{st['part']:05d}.csv", index=False)
    st["part"] += 1
    return len(df)

if not st.get("done"):
    with open(SRC, "rb") as f:
        f.seek(st["offset"])
        pos = [st["offset"]]
        def lines():                                   # yields text lines and tracks the byte position
            for ln in f:
                pos[0] += len(ln)
                yield ln.decode("utf-8", "replace")
        reader = csv.reader(lines())                   # same quoting rules as pandas (stray quotes inside
        buf, last_save = [], time.time()               # unquoted fields are kept as text)
        for row in reader:
            st["records"] += 1
            if len(row) > I_URL:
                d = row[I_DATE][:10]
                tk = row[I_TK].strip().upper()
                if tk and "2018-03-01" <= d <= "2020-02-29":
                    buf.append((tk, d, row[I_URL], row[I_TITLE]))
            if time.time() - last_save > 20:           # checkpoint at a record boundary
                st["kept_in_window"] += save_part(buf); buf = []
                st["offset"] = pos[0]
                STATE.write_text(json.dumps(st))
                last_save = time.time()
                pct = (pos[0] - hdr_end) / (size - hdr_end) * 100
                print(f"{pct:5.1f}% | records {st['records']:,} | in-window tagged rows {st['kept_in_window']:,} | {time.time()-t0:,.0f}s", flush=True)
                if args.max_seconds and time.time() - t0 > args.max_seconds:
                    print("time limit reached; progress saved, re-run to continue")
                    sys.exit(0)
        st["kept_in_window"] += save_part(buf)
        st["offset"] = pos[0]
        st["done"] = True
        STATE.write_text(json.dumps(st))

# ---- all records read: combine, de-duplicate, aggregate ----
parts = [p for p in sorted(WORK.glob("part_*.csv")) if p.stat().st_size > 0]
rows = pd.concat([pd.read_csv(p, dtype=str, keep_default_na=False, na_values=[""]) for p in parts], ignore_index=True)
rows["url"] = rows["url"].fillna("")
n0 = len(rows)
dup = rows.duplicated(["ticker", "url"]) & (rows["url"] != "")
rows = rows[~dup]
print(f"raw records read: {st['records']:,} | ticker-tagged rows in window: {n0:,} | repeats dropped: {dup.sum():,} | kept: {len(rows):,}")
print("headline classes:", rows["cat"].value_counts().to_dict())

raw = rows.groupby(["ticker", "date"]).size().rename("n_articles").reset_index()
filt = rows[rows["cat"] != "price_report"].groupby(["ticker", "date"]).size().rename("n_articles").reset_index()
raw.to_csv(OUT_RAW, index=False)
filt.to_csv(OUT_FILT, index=False)
print(f"wrote {OUT_RAW.name}: {len(raw):,} ticker-days, {raw.ticker.nunique():,} tickers, {raw.n_articles.sum():,} articles")
print(f"wrote {OUT_FILT.name}: {len(filt):,} ticker-days, {filt.ticker.nunique():,} tickers, {filt.n_articles.sum():,} articles")

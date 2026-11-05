"""Step 9: book equity, market equity and earnings-announcement flags from SEC bulk data, per weekly / monthly block.

Inputs (in the project folder "SEC DATA/"):
  companyfacts.zip      https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip
  submissions.zip       https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip
  company_tickers.json  https://www.sec.gov/files/company_tickers.json
  data/panel_{weekly,monthly}_raw_2018-03_2020-02.csv   (step 7: ticker, block, block_end, close_end)
Outputs:
  data/sec_controls_{weekly,monthly}_2018-03_2020-02.csv   one row per ticker-block in the panel:
    cik, book_equity, be_period_end, be_filed, shares_out, shares_filed, split_factor, market_equity,
    earn_8k (1 if an 8-K with Item 2.02 'Results of Operations' was filed in the block),
    filing_10qk (1 if a 10-Q or 10-K was filed in the block), sec_matched
  Merge onto the panels in Stata by ticker + block. BM = book_equity / market_equity.

Point-in-time rules (only information public by the block's last day):
  book_equity  = us-gaap StockholdersEquity (fallback: ...IncludingPortionAttributableToNoncontrollingInterest)
                 from the most recent balance sheet whose filing date <= block_end
  shares_out   = dei EntityCommonStockSharesOutstanding (cover page; share classes summed;
                 fallback us-gaap CommonStockSharesOutstanding), latest filed <= block_end
  market_equity= shares_out x split_factor x close_end

Split correction: the FNSPID price files before 2020-07-06 are adjusted for splits up to about July 2020 but
SEC share counts are as reported at the time. split_factor = product of split ratios for splits detected
that happened after the share count was filed and before 2020-07-05. Splits are detected from restated
share counts (a later filing reports the same period's WeightedAverageNumberOfSharesOutstandingBasic at ~2x,
3x, 0.1x ... the earlier value) and dated at the first cover page whose share count jumps by that ratio.
split_approx = 1 where no such jump was found and the restating filing's date was used instead.

Ticker -> CIK uses the SEC's CURRENT ticker list (plus each company's ticker list in submissions), so firms
delisted or renamed since 2020 may not match; a CIK whose first filing is after 2020-02 is rejected
(ticker re-used by a newer company).

Runs in batches so each step stays short:
    python 09_sec_controls.py index          # ticker -> CIK map, list of CIKs needed
    python 09_sec_controls.py facts 0 4 ... facts 3 4     # read companyfacts for a quarter of the CIKs each
    python 09_sec_controls.py subs 0 4  ... subs 3 4      # read submissions
    python 09_sec_controls.py names 0 4 ... names 3 4     # SEC names + former names (for the second pass)
    python 09_sec_controls.py match          # second pass: match remaining tickers by company name in headlines
    python 09_sec_controls.py facts 0 2 new ; subs 0 2 new ...   # read only the newly matched CIKs
    python 09_sec_controls.py build          # assemble the block-level files
"""
import json, re, sys, zipfile
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
RAW, DATA = HERE.parent / "SEC DATA", HERE / "data"
WORK = DATA / "_09_work"; WORK.mkdir(parents=True, exist_ok=True)
TAG = "2018-03_2020-02"
SNAPSHOT = "2020-07-05"           # price files are adjusted for splits up to about here
WIN_LO, WIN_HI = "2016-01-01", "2020-07-05"   # facts needed: balance sheets before the sample + split detection
SPLIT_RATIOS = [1.25, 4 / 3, 1.5, 2, 2.5, 3, 4, 5, 6, 7, 8, 10, 12, 15, 20, 25, 30, 40, 50, 100]

def cik10(c):
    return f"{int(c):010d}"

stage = sys.argv[1]

# ------------------------------------------------------------------ index
if stage == "index":
    tick = set()
    for f in ("weekly", "monthly"):
        tick |= set(pd.read_csv(DATA / f"panel_{f}_raw_{TAG}.csv", usecols=["ticker"], keep_default_na=False).ticker)
    ct = json.loads((RAW / "company_tickers.json").read_text())
    m = pd.DataFrame(ct.values()).rename(columns={"cik_str": "cik"})
    m["ticker"] = m["ticker"].str.upper().str.replace("-", ".", regex=False)
    m = m[m.ticker.isin(tick)].drop_duplicates("ticker")
    # tickers not in the current list: look through submissions' own ticker lists
    missing = tick - set(m.ticker)
    extra = []
    if missing and "--scan-submissions" in sys.argv and (RAW / "submissions.zip").exists():   # slow: ~1M files
        with zipfile.ZipFile(RAW / "submissions.zip") as z:
            for n in z.namelist():
                if not re.fullmatch(r"CIK\d{10}\.json", n):
                    continue
                s = json.loads(z.read(n))
                for t in s.get("tickers", []) or []:
                    t = str(t).upper().replace("-", ".")
                    if t in missing:
                        extra.append({"ticker": t, "cik": int(s["cik"]), "title": s.get("name", "")})
                        missing.discard(t)
                if not missing:
                    break
    m = pd.concat([m, pd.DataFrame(extra)], ignore_index=True) if extra else m
    m[["ticker", "cik", "title"]].to_csv(WORK / "ticker_cik.csv", index=False)
    print(f"tickers in panels: {len(tick):,} | matched to a CIK: {len(m):,} ({len(m)/len(tick):.1%}) | unmatched: {len(tick)-len(m):,}")
    sys.exit()


# ------------------------------------------------------------------ names (for the second matching pass)
if stage == "names":
    b, nb = int(sys.argv[2]), int(sys.argv[3])
    with zipfile.ZipFile(RAW / "companyfacts.zip") as z:
        cf = sorted(n for n in z.namelist() if re.fullmatch(r"CIK\d{10}\.json", n))[b::nb]
    out = []
    with zipfile.ZipFile(RAW / "submissions.zip") as z:
        have = set(z.namelist())
        for n in cf:
            if n not in have:
                continue
            s = json.loads(z.read(n))
            c = int(s["cik"])
            out.append((c, s.get("name", ""), "", ""))
            for f in s.get("formerNames", []) or []:
                out.append((c, f.get("name", ""), f.get("from", "")[:10], f.get("to", "")[:10]))
    pd.DataFrame(out, columns=["cik", "name", "from", "to"]).to_csv(WORK / f"names_{b:02d}.csv", index=False)
    print(f"names batch {b}: {len(cf):,} companies, {len(out):,} names")
    sys.exit()

# ------------------------------------------------------------------ match (second pass: names from news headlines)
SUFFIX = {"inc", "corp", "corporation", "co", "company", "ltd", "limited", "plc", "holdings", "holding", "group",
          "the", "sa", "nv", "ag", "lp", "llc", "incorporated", "trust", "de", "new", "cl", "class", "a", "common", "stock"}
def norm(x):
    t = re.sub(r"[^a-z0-9 ]", " ", str(x).lower().replace("&", " and ")).split()
    while t and t[-1] in SUFFIX:
        t.pop()
    while t and t[0] == "the":
        t.pop(0)
    return " ".join(t)

if stage == "match":
    names = pd.concat([pd.read_csv(p, keep_default_na=False) for p in sorted(WORK.glob("names_*.csv"))])
    # date each name: a former name has from/to; the current name starts where the last former name ended.
    # keep only names in use at some point during Jun 2017 - Feb 2020 (so "Coherent Corp", the 2022 renaming of
    # II-VI, does not compete with Coherent Inc)
    lastto = names[names["to"] != ""].groupby("cik")["to"].max()
    cur = names["to"] == ""
    names.loc[cur, "from"] = names.loc[cur, "cik"].map(lastto).fillna("")
    names = names[((names["to"] == "") | (names["to"] >= "2017-06-01")) & ((names["from"] == "") | (names["from"] <= "2020-02-29"))]
    names["key"] = names["name"].map(norm)
    names = names[names.key.str.len() >= 4]
    cik2keys = names.groupby("cik").key.agg(lambda x: {k.replace(" ", "") for k in x})
    key2cik = names.groupby("key").cik.agg(lambda x: sorted(set(x)))
    key2cik = key2cik[key2cik.map(len) == 1].map(lambda x: x[0])               # unambiguous names only
    first = pd.concat([pd.read_csv(p, keep_default_na=False) for p in sorted(WORK.glob("first_*.csv"))]) \
        if list(WORK.glob("first_*.csv")) else pd.DataFrame(columns=["cik", "first_filing"])
    late = set(first.loc[first.first_filing > "2020-02-29", "cik"])
    tick = set()
    for f in ("weekly", "monthly"):
        tick |= set(pd.read_csv(DATA / f"panel_{f}_raw_{TAG}.csv", usecols=["ticker"], keep_default_na=False).ticker)
    # always start from the untouched SEC-list mapping (saved once), so reruns of this stage are repeatable
    base = WORK / "ticker_cik_seclist.csv"
    if not base.exists():
        tm = pd.read_csv(WORK / "ticker_cik.csv", keep_default_na=False)
        if "method" not in tm:
            tm["method"] = "sec_ticker_list"
        tm[tm.method == "sec_ticker_list"].to_csv(base, index=False)
    tm = pd.read_csv(base, keep_default_na=False)
    need = tick                                    # check every ticker, including ones the SEC list maps
    # headlines: "Company Name (TICKER)" or "(NYSE: TICKER)" / "(NASDAQ: TICKER)"
    votes, phrases = {}, {}
    for ch in pd.read_csv(HERE.parent / "News Data Set" / "news_price_matched.csv", usecols=["ticker", "price_date", "title"],
                          dtype=str, keep_default_na=False, chunksize=1_000_000):
        ch = ch[(ch.price_date >= "2017-06-01") & (ch.price_date <= "2020-06-30") & ch.ticker.isin(need)]
        for t, title in zip(ch.ticker, ch.title):
            mt = re.search(r"([^:|\-–—(]{3,80}?)\s*\((?:NYSE|NASDAQ|NYSEAMERICAN|AMEX|NYSEMKT)?\s*:?\s*" + re.escape(t) + r"\)", title)
            if not mt:
                continue
            toks = norm(mt.group(1)).split()
            phrases.setdefault(t, []).append("".join(toks))
            for L in range(min(6, len(toks)), 0, -1):                          # longest trailing phrase that is a known name
                k = " ".join(toks[-L:])
                if (L >= 2 or len(k) >= 5) and k in key2cik.index:
                    votes.setdefault(t, []).append(key2cik[k]); break
    def consistent(ph, keys):                     # share of headline names matching one of the company's names
        keys = [k for k in keys if len(k) >= 4]
        ph = [x for x in ph if len(x) >= 4]
        if not ph or not keys:
            return 0.0
        return float(np.mean([any(k in x or x in k for k in keys) for x in ph]))
    rows = []
    listed = dict(zip(tm.ticker, tm.cik))
    gap = set(tm.loc[tm.cik.isin(late), "ticker"]) | (tick - set(tm.ticker))
    for t, v in votes.items():
        vc = pd.Series(v).value_counts()
        top, sup, share = int(vc.index[0]), int(vc.iloc[0]), vc.iloc[0] / len(v)
        if top in late:
            continue
        if t in gap and sup >= 2 and share >= 0.6:                               # fill a missing / re-used ticker
            rows.append({"ticker": t, "cik": top, "title": "", "method": "headline_name", "support": sup, "of": len(v)})
        elif t in listed and top != listed[t] and sup >= 5 and share >= 0.8 and \
                consistent(phrases.get(t, []), cik2keys.get(listed[t], set())) < 0.2:
            # SEC list points at a different company: the headlines' name for this ticker (almost) never matches
            # any name the listed company used during 2017-2020
            rows.append({"ticker": t, "cik": top, "title": "", "method": "headline_override", "support": sup, "of": len(v)})
    add = pd.DataFrame(rows)
    tm = tm[~tm.ticker.isin(add.ticker)] if len(add) else tm
    out = pd.concat([tm, add], ignore_index=True)
    out.to_csv(WORK / "ticker_cik.csv", index=False)
    print(f"needed a second-pass match: {len(need):,} tickers | headline-name matches: {len(add):,} | "
          f"total matched now {len(out):,} of {len(tick):,} ({len(out)/len(tick):.1%})")
    if len(add):
        ov = add[add.method == "headline_override"]
        print(f"of which overrides of the SEC ticker list: {len(ov):,}")
        print(ov.assign(old_cik=ov.ticker.map(listed)).sort_values("support", ascending=False).head(40).to_string(index=False))
    sys.exit()

tmap = pd.read_csv(WORK / "ticker_cik.csv", keep_default_na=False)
ciks = sorted(tmap.cik.unique())
if len(sys.argv) > 4 and sys.argv[4] == "new":            # only CIKs not yet read (after the second matching pass)
    done = set()
    for p in WORK.glob("facts_*.csv" if stage == "facts" else "first_*.csv"):   # each stage checks its own outputs
        if p.stat().st_size > 0:
            done |= set(pd.read_csv(p, usecols=["cik"]).cik)
    ciks = [c for c in ciks if c not in done]

# ------------------------------------------------------------------ facts
if stage == "facts":
    b, nb = int(sys.argv[2]), int(sys.argv[3])
    want = ciks[b::nb]
    rows, splits = [], []
    with zipfile.ZipFile(RAW / "companyfacts.zip") as z:
        names = set(z.namelist())
        for c in want:
            n = f"CIK{cik10(c)}.json"
            if n not in names:
                continue
            facts = json.loads(z.read(n)).get("facts", {})
            def get(tax, tag, unit):
                return facts.get(tax, {}).get(tag, {}).get("units", {}).get(unit, [])
            for kind, tax, tag, unit in (("be", "us-gaap", "StockholdersEquity", "USD"),
                                         ("be_nci", "us-gaap", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest", "USD"),
                                         ("sh_dei", "dei", "EntityCommonStockSharesOutstanding", "shares"),
                                         ("sh_gaap", "us-gaap", "CommonStockSharesOutstanding", "shares"),
                                         ("sh_wa", "us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic", "shares")):
                for x in get(tax, tag, unit):
                    if WIN_LO <= x.get("filed", "") <= "2020-07-31":     # through the price snapshot, for split dating
                        rows.append((c, kind, x["end"], x["filed"], x.get("form", ""), x["val"]))
            # split detection from restated weighted-average shares (same period, different filings)
            w = pd.DataFrame(get("us-gaap", "WeightedAverageNumberOfSharesOutstandingBasic", "shares"))
            if not w.empty and {"start", "end", "filed", "val"} <= set(w.columns):
                w = w[(w.end >= "2015-01-01") & (w.val > 0)]
                for _, g in w.groupby(["start", "end"]):
                    g = g.sort_values("filed")
                    first = g.iloc[0]
                    for _, later in g.iloc[1:].iterrows():
                        r = later.val / first.val
                        for k in SPLIT_RATIOS:
                            for kk in (k, 1 / k):
                                if abs(r / kk - 1) < 0.02:
                                    splits.append((c, later.filed, first.filed, kk))
    sfx = "n" if (len(sys.argv) > 4 and sys.argv[4] == "new") else ""
    pd.DataFrame(rows, columns=["cik", "kind", "end", "filed", "form", "val"]).to_csv(WORK / f"facts_{sfx}{b:02d}.csv", index=False)
    pd.DataFrame(splits, columns=["cik", "restated_filed", "orig_filed", "ratio"]).to_csv(WORK / f"splits_{sfx}{b:02d}.csv", index=False)
    print(f"facts batch {b}: {len(want):,} CIKs, {len(rows):,} facts, {len(splits):,} split signals")
    sys.exit()

# ------------------------------------------------------------------ submissions
if stage == "subs":
    b, nb = int(sys.argv[2]), int(sys.argv[3])
    want = ciks[b::nb]
    out, first_filing = [], []
    with zipfile.ZipFile(RAW / "submissions.zip") as z:
        names = set(z.namelist())
        for c in want:
            n = f"CIK{cik10(c)}.json"
            if n not in names:
                continue
            s = json.loads(z.read(n))
            blocks = [s["filings"]["recent"]]
            for extra in s["filings"].get("files", []):        # older filings live in extra pages
                if extra["name"] in names:
                    blocks.append(json.loads(z.read(extra["name"])))
            dates = []
            for f in blocks:
                df = pd.DataFrame({"form": f["form"], "date": f["filingDate"],
                                   "items": f.get("items", [""] * len(f["form"]))})
                dates.extend(df.date.tolist())
                df = df[(df.date >= "2017-11-01") & (df.date <= "2020-03-31")]
                e = df[df.form.isin(["8-K", "8-K/A"]) & df["items"].fillna("").str.contains(r"2\.02")]
                q = df[df.form.isin(["10-Q", "10-K", "10-KT"])]
                out += [(c, d, "earn_8k") for d in e.date] + [(c, d, "filing_10qk") for d in q.date]
            first_filing.append((c, min(dates) if dates else ""))
    sfx = "n" if (len(sys.argv) > 4 and sys.argv[4] == "new") else ""
    pd.DataFrame(out, columns=["cik", "date", "kind"]).drop_duplicates().to_csv(WORK / f"subs_{sfx}{b:02d}.csv", index=False)
    pd.DataFrame(first_filing, columns=["cik", "first_filing"]).to_csv(WORK / f"first_{sfx}{b:02d}.csv", index=False)
    print(f"subs batch {b}: {len(want):,} CIKs, {len(out):,} filing events")
    sys.exit()

# ------------------------------------------------------------------ build
if stage == "build":
    rd = lambda pat: pd.concat([pd.read_csv(p, keep_default_na=False, na_values=[""]) for p in sorted(WORK.glob(pat))
                                if p.stat().st_size > 0], ignore_index=True)
    facts, splits, subs, first = rd("facts_*.csv"), rd("splits_*.csv"), rd("subs_*.csv"), rd("first_*.csv")
    # reject CIKs that only started filing after the sample ends (ticker re-used by a newer company)
    late = set(first.loc[first.first_filing > "2020-02-29", "cik"])
    tmap = tmap[~tmap.cik.isin(late)].drop_duplicates("ticker")
    print(f"CIKs rejected as later re-use of the ticker: {len(late):,}")

    # cover-page share counts: share classes are summed within one form; a form and its amendment (10-Q and
    # 10-Q/A) filed the same day are not added together (take the larger of the two sums)
    deiv = (facts[facts.kind == "sh_dei"].drop_duplicates(["cik", "filed", "end", "form", "val"])
            .groupby(["cik", "filed", "end", "form"])["val"].sum().reset_index()
            .groupby(["cik", "filed", "end"])["val"].max().reset_index())
    dei = deiv.groupby(["cik", "filed"])["val"].max().reset_index().sort_values(["cik", "filed"])
    # foreign filers (20-F / 40-F): cover-page shares are ordinary shares, which may not be 1:1 with the US-listed ADR
    foreign = set(facts.loc[facts.form.fillna("").str.match(r"^(20-F|40-F)"), "cik"])
    # split events. A restatement signal (same period's shares re-reported at ratio k in a later filing) says a
    # k-for-1 split happened between the two filings. Date it at the first cover page that shows the jump
    # (consecutive cover-page counts with ratio within 15% of k); that filing is the first post-split count.
    # If no such jump is found, fall back to the restating filing's date (flagged).
    evs = []
    for (c, k), g in splits.groupby(["cik", splits.ratio.round(4)]):
        lo, hi = g.orig_filed.min(), g.restated_filed.max()
        d = dei[(dei.cik == c) & (dei.filed >= lo) & (dei.filed <= hi)]
        v = d.val.to_numpy(dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            r = v[1:] / v[:-1] if len(v) > 1 else np.array([])
        dist = np.abs(np.log(np.where(r > 0, r, np.nan) / k)) if len(r) else np.array([])
        if len(dist) and np.nanmin(dist) < np.log(1.5):
            i = int(np.nanargmin(dist))
            evs.append((c, k, d.filed.iloc[i + 1], 0))
        else:
            evs.append((c, k, g.restated_filed.min(), 1))
    ev = pd.DataFrame(evs, columns=["cik", "ratio", "event_filed", "approx_date"]).drop_duplicates(["cik", "event_filed"])
    ev = ev[(ev.event_filed > "2017-06-01") & (ev.event_filed <= SNAPSHOT)]
    ev.to_csv(WORK / "split_events.csv", index=False)
    print(f"split events used: {len(ev):,} ({int(ev.approx_date.sum())} dated approximately)")

    # book equity: prefer StockholdersEquity, else the NCI-inclusive tag, per (cik, end, filed)
    be = facts[facts.kind.isin(["be", "be_nci"])].copy()
    be["pref"] = (be.kind == "be_nci").astype(int)
    be = be.sort_values(["cik", "filed", "end", "pref"]).drop_duplicates(["cik", "end", "filed"])
    # shares: dei cover-page value summed over share classes, else us-gaap balance-sheet value
    sh = deiv.copy()
    shg = facts[facts.kind == "sh_gaap"].groupby(["cik", "filed", "end"])["val"].max().reset_index()
    shw = (facts[facts.kind == "sh_wa"].sort_values("end").groupby(["cik", "filed"]).tail(1)[["cik", "filed", "end", "val"]])
    sh = pd.concat([sh.assign(pref=0), shg.assign(pref=1), shw.assign(pref=2)])
    sh = sh[sh.val > 0].sort_values(["cik", "filed", "pref", "end"], ascending=[True, True, True, False]).drop_duplicates(["cik", "filed"])
    # fallback tags (balance-sheet / weighted-average) are only trusted if close to the firm's nearest cover-page
    # count; e.g. one firm tags shares ISSUED (incl. treasury) as outstanding
    fb = sh[sh.pref > 0].copy()
    if len(fb) and len(dei):
        fb["_f"] = pd.to_datetime(fb.filed); d2 = dei.rename(columns={"val": "_dei"}).copy(); d2["_f"] = pd.to_datetime(d2.filed)
        fb = pd.merge_asof(fb.sort_values("_f"), d2[["cik", "_f", "_dei"]].sort_values("_f"), on="_f", by="cik", direction="nearest")
        r = fb.val / fb._dei
        drop = fb[fb._dei.notna() & ((r > 1.5) | (r < 1 / 1.5))][["cik", "filed", "pref"]]
        print(f"fallback share counts dropped (inconsistent with cover page): {len(drop):,}")
        sh = sh.merge(drop.assign(_x=1), on=["cik", "filed", "pref"], how="left")
        sh = sh[sh._x.isna()].drop(columns="_x")
    # scale errors (e.g. a filing reporting shares x 1,000,000): drop values > 200x away from the firm's median
    med = sh.groupby("cik").val.transform("median")
    bad = (sh.val / med > 200) | (med / sh.val > 200)
    print(f"share counts dropped as scale errors: {int(bad.sum()):,}")
    sh = sh[~bad]
    medb = be.groupby("cik").val.transform(lambda x: x.abs().median())
    badb = (be.val.abs() / medb > 200) | ((medb / be.val.abs().replace(0, np.nan)) > 200)
    print(f"book-equity values dropped as scale errors: {int(badb.sum()):,}")
    be = be[~badb]
    sh = sh[sh.filed <= "2020-03-31"]
    be = be[be.filed <= "2020-03-31"]
    # stale restatements: a later filing (often an 8-K recasting old years) that only re-reports an OLDER period
    # than one already public must not replace the newer number. Keep the latest period per filing, then drop
    # filings whose period end is earlier than the latest period already filed.
    def fresh(d):
        d = d.sort_values(["cik", "filed", "end"]).drop_duplicates(["cik", "filed"], keep="last")
        e = pd.to_datetime(d["end"], errors="coerce")
        prev = e.groupby(d["cik"]).transform(lambda x: x.cummax().shift())
        keep = prev.isna() | (e >= prev)
        return d[keep], int((~keep).sum())
    sh, n1 = fresh(sh); be, n2 = fresh(be)
    print(f"stale restated values dropped: shares {n1:,}, book equity {n2:,}")

    for freq in ("weekly", "monthly"):
        p = pd.read_csv(DATA / f"panel_{freq}_raw_{TAG}.csv", usecols=["ticker", "block", "block_start", "block_end", "close_end"],
                        keep_default_na=False, na_values=[""])
        p = p.merge(tmap[["ticker", "cik"]], on="ticker", how="left")
        p["sec_matched"] = p.cik.notna().astype(int)
        q = p[p.cik.notna()].copy()
        q["cik"] = q.cik.astype(int)
        q["block_end"] = pd.to_datetime(q.block_end); q["block_start"] = pd.to_datetime(q.block_start)
        q = q.sort_values("block_end")
        # latest balance sheet filed on/before block end; among same filing date take the latest period end
        b2 = be.sort_values(["filed", "end"]).rename(columns={"filed": "be_filed", "end": "be_period_end", "val": "book_equity"})
        b2 = b2.drop_duplicates(["cik", "be_filed"], keep="last")
        b2["be_filed"] = pd.to_datetime(b2.be_filed)
        q = pd.merge_asof(q, b2[["cik", "be_filed", "be_period_end", "book_equity"]].sort_values("be_filed"),
                          left_on="block_end", right_on="be_filed", by="cik", direction="backward")
        s2 = sh.rename(columns={"filed": "shares_filed", "val": "shares_out"})[["cik", "shares_filed", "shares_out"]].copy()
        s2["shares_filed"] = pd.to_datetime(s2.shares_filed)
        q = pd.merge_asof(q.sort_values("block_end"), s2.sort_values("shares_filed"),
                          left_on="block_end", right_on="shares_filed", by="cik", direction="backward")
        # split factor: prices are on the split basis of ~July 2020, so a share count reported BEFORE a split that
        # happened before the snapshot must be scaled by that split's ratio. (Depends on when the share count was
        # filed, not on the block date.)
        q["split_factor"] = 1.0
        q["split_approx"] = 0
        for _, e in ev.iterrows():
            mask = (q.cik == e.cik) & (q.shares_filed < pd.Timestamp(e.event_filed))
            q.loc[mask, "split_factor"] *= e.ratio
            q.loc[mask, "split_approx"] |= int(e.approx_date)
        q["market_equity"] = q.shares_out * q.split_factor * q.close_end
        q["foreign_filer"] = q.cik.isin(foreign).astype(int)
        # several tickers on one CIK (mostly ETF trusts filing for many funds): shares are the trust total
        q["cik_shared"] = q.cik.map(tmap.groupby("cik").ticker.nunique()).gt(1).astype(int)
        # earnings / filing flags per block
        for kind in ("earn_8k", "filing_10qk"):
            ev2 = subs[subs.kind == kind][["cik", "date"]].copy()
            ev2["date"] = pd.to_datetime(ev2.date)
            hit = q[["cik", "block", "block_start", "block_end"]].merge(ev2, on="cik")
            hit = hit[(hit.date >= hit.block_start) & (hit.date <= hit.block_end)].drop_duplicates(["cik", "block"])
            q = q.merge(hit[["cik", "block"]].assign(**{kind: 1}), on=["cik", "block"], how="left")
            q[kind] = q[kind].fillna(0).astype(int)
        for c in ("be_filed", "shares_filed"):
            q[c] = q[c].dt.strftime("%Y-%m-%d")
        cols = ["ticker", "block", "cik", "book_equity", "be_period_end", "be_filed", "shares_out", "shares_filed",
                "split_factor", "split_approx", "market_equity", "foreign_filer", "cik_shared", "earn_8k", "filing_10qk"]
        out = p[["ticker", "block", "sec_matched"]].merge(q[cols], on=["ticker", "block"], how="left")
        out = out.sort_values(["block", "ticker"])
        f = DATA / f"sec_controls_{freq}_{TAG}.csv"
        out.to_csv(f, index=False, float_format="%.10g")
        n = len(out)
        print(f"{f.name}: {n:,} ticker-blocks | matched {out.sec_matched.mean():.1%} | book equity {out.book_equity.notna().mean():.1%} "
              f"| market equity {out.market_equity.notna().mean():.1%} | split-corrected rows {(out.split_factor.fillna(1) != 1).sum():,} "
              f"| earnings-week share {out.earn_8k.mean():.1%}")

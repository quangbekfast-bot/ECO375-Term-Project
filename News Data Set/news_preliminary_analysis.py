# %% [markdown]
# # ECO375 – News Data Set: Preliminary Data Analysis
#
# Files in this folder (this is the FNSPID financial-news dataset):
#   * nasdaq_exteral_data.csv  (~23 GB)  – Nasdaq.com articles WITH full text + 4 auto-summaries
#   * All_external.csv         (~5.7 GB) – mostly Benzinga headlines (no article text)
#   * full_history.zip         (~0.6 GB) – one daily OHLCV price file per ticker
#
# The news files are far too big to load into memory at once, so the first cell
# streams each file in chunks ONCE and saves a slim "metadata" version
# (date, ticker, publisher, text lengths, URL hash) to ./cache/.
# Every later run reads the cache in seconds.
#
# How to run in VS Code: open this file and use "Run Cell" (Interactive Window),
# or run the whole file. Charts are also saved to ./figures/.

# %% Setup
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pandas.api.types import union_categoricals

pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 200)

HERE = Path(__file__).parent if "__file__" in globals() else Path.cwd()
SOURCES = {
    "nasdaq": HERE / "nasdaq_exteral_data.csv",   # (sic) file name as downloaded
    "benzinga": HERE / "All_external.csv",
}
PRICE_ZIP = HERE / "full_history.zip"
CACHE_DIR = HERE / "cache"
FIG_DIR = HERE / "figures"
CACHE_DIR.mkdir(exist_ok=True)
FIG_DIR.mkdir(exist_ok=True)

CHUNKSIZE = 25_000      # rows per chunk; Nasdaq rows are ~10 KB each, so keep this modest
MAX_CHUNKS = None       # set to e.g. 4 for a quick test run (cache is NOT saved in test mode)
REBUILD_CACHE = False   # set True to re-read the raw CSVs

TEXT_COLS = ["Article", "Lsa_summary", "Luhn_summary", "Textrank_summary", "Lexrank_summary"]
COLORS = {"nasdaq": "#1f77b4", "benzinga": "#ff7f0e"}


def save_show(fig, name):
    fig.tight_layout()
    fig.savefig(FIG_DIR / f"{name}.png", dpi=150)
    plt.show()


# %% Step 1 – stream the raw CSVs once and build a slim cache
def to_cat(s):
    """Categorical with object-dtype categories (so chunks can be stacked safely)."""
    s = s.astype("object")
    return pd.Categorical(s, categories=pd.Index(pd.unique(s.dropna()), dtype="object"))


def slim_chunk(ch):
    out = pd.DataFrame({
        # Dates look like "2020-06-05 06:30:54 UTC"
        "date": pd.to_datetime(ch["Date"].str.replace(" UTC", "", regex=False),
                               format="%Y-%m-%d %H:%M:%S", errors="coerce"),
        "ticker": to_cat(ch["Stock_symbol"].str.strip().str.upper()),
        "publisher": to_cat(ch["Publisher"]),
        "title_len": ch["Article_title"].str.len().astype("float32"),
        "article_len": ch["Article"].str.len().astype("float32"),
        "has_summary": ch[TEXT_COLS[1:]].notna().any(axis=1).to_numpy(),
        "url_hash": pd.util.hash_pandas_object(ch["Url"].fillna(""), index=False).to_numpy(),
    })
    return out


def stack(parts):
    cols = {}
    for c in parts[0].columns:
        if isinstance(parts[0][c].dtype, pd.CategoricalDtype):
            cols[c] = union_categoricals([p[c] for p in parts], ignore_order=True)
        else:
            cols[c] = np.concatenate([p[c].to_numpy() for p in parts])
    return pd.DataFrame(cols)


def build_cache(name, path):
    t0, parts, missing, n_raw = time.time(), [], None, 0
    reader = pd.read_csv(
        path, chunksize=CHUNKSIZE, dtype=str,
        keep_default_na=False, na_values=[""],          # keeps tickers like "NA" as text
        usecols=lambda c: not c.startswith("Unnamed"),  # drop the stray index column
    )
    for i, ch in enumerate(reader):
        n_raw += len(ch)
        miss = ch.isna().sum()
        missing = miss if missing is None else missing.add(miss, fill_value=0)
        parts.append(slim_chunk(ch))
        if i % 20 == 0:
            print(f"  {name}: {n_raw:,} rows read ({time.time() - t0:,.0f}s)")
        if MAX_CHUNKS and i + 1 >= MAX_CHUNKS:
            break
    df = stack(parts)
    missing_pct = (missing / n_raw * 100).round(2).rename("missing_%")
    print(f"  {name}: done, {n_raw:,} rows in {time.time() - t0:,.0f}s")
    if not MAX_CHUNKS:
        df.to_pickle(CACHE_DIR / f"{name}_meta.pkl")
        missing_pct.to_pickle(CACHE_DIR / f"{name}_missing.pkl")
    return df, missing_pct


news, missing = {}, {}
for name, path in SOURCES.items():
    cache = CACHE_DIR / f"{name}_meta.pkl"
    if cache.exists() and not REBUILD_CACHE and not MAX_CHUNKS:
        news[name] = pd.read_pickle(cache)
        missing[name] = pd.read_pickle(CACHE_DIR / f"{name}_missing.pkl")
        print(f"{name}: loaded cache ({len(news[name]):,} rows)")
    else:
        print(f"{name}: building cache from {path.name} (first run only, takes a while)...")
        news[name], missing[name] = build_cache(name, path)

# %% Step 2 – Overview: size, coverage, data quality
def overview(df):
    d = df["date"]
    midnight = (d.dt.hour == 0) & (d.dt.minute == 0) & (d.dt.second == 0)
    return pd.Series({
        "rows": len(df),
        "unique tickers": df["ticker"].nunique(),
        "unique URLs (articles)": pd.Series(df["url_hash"]).nunique(),
        "rows per article (ticker tags)": len(df) / pd.Series(df["url_hash"]).nunique(),
        "exact duplicate rows (same URL + ticker)": df.duplicated(["url_hash", "ticker"]).sum(),
        "unparseable dates": d.isna().sum(),
        "first date": d.min(),
        "last date": d.max(),
        "% timestamps exactly 00:00:00 (time likely unknown)": midnight.mean() * 100,
        "% rows with full article text": df["article_len"].notna().mean() * 100,
        "% rows with a summary": df["has_summary"].mean() * 100,
        "% rows with publisher filled": df["publisher"].notna().mean() * 100,
    })


overview_tbl = pd.DataFrame({k: overview(v) for k, v in news.items()})
print(overview_tbl.to_string())

print("\nMissing values by raw column (%):")
print(pd.DataFrame(missing).to_string())

# %% Step 3 – How much news is there over time?
fig, ax = plt.subplots(figsize=(11, 4.5))
for name, df in news.items():
    monthly = df.dropna(subset=["date"]).set_index("date").resample("MS").size()
    ax.plot(monthly.index, monthly.values, label=name, color=COLORS[name])
ax.set_yscale("log")
ax.set_title("News rows per month (log scale)")
ax.set_ylabel("rows (article × ticker)")
ax.legend()
ax.grid(alpha=0.3)
save_show(fig, "01_news_per_month")

yearly = pd.DataFrame({k: v["date"].dt.year.value_counts().sort_index() for k, v in news.items()})
print("Rows per year:")
print(yearly.fillna(0).astype(int).to_string())

# %% Step 4 – How concentrated is coverage across tickers?
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
for name, df in news.items():
    per_ticker = df["ticker"].value_counts()
    per_ticker = per_ticker[per_ticker > 0]
    bins = np.logspace(0, np.log10(per_ticker.max() + 1), 40)
    axes[0].hist(per_ticker, bins=bins, alpha=0.6, label=name, color=COLORS[name])
    top10 = per_ticker.head(int(np.ceil(len(per_ticker) * 0.10))).sum() / per_ticker.sum()
    print(f"{name}: {len(per_ticker):,} tickers | median {per_ticker.median():,.0f} rows/ticker | "
          f"top 10% of tickers = {top10:.0%} of rows")
axes[0].set_xscale("log")
axes[0].set_title("Rows per ticker (distribution)")
axes[0].set_xlabel("rows per ticker (log)")
axes[0].set_ylabel("number of tickers")
axes[0].legend()

top = pd.DataFrame({k: v["ticker"].value_counts().head(20) for k, v in news.items()}).fillna(0)
top = top.loc[top.sum(axis=1).sort_values().index]
top.plot.barh(ax=axes[1], color=[COLORS[c] for c in top.columns], width=0.8)
axes[1].set_title("Top tickers by news rows")
axes[1].set_xlabel("rows")
save_show(fig, "02_ticker_coverage")

# %% Step 5 – Who writes the news?
# NOTE: in All_external.csv the "Publisher" column holds AUTHOR names (Benzinga staff),
# and in the Nasdaq file "Publisher"/"Author" are (almost) empty.
for name, df in news.items():
    vc = df["publisher"].value_counts()
    vc = vc[vc > 0]
    if vc.empty:
        print(f"{name}: publisher field is empty – nothing to plot")
        continue
    fig, ax = plt.subplots(figsize=(9, 5))
    vc.head(15).sort_values().plot.barh(ax=ax, color=COLORS[name])
    ax.set_title(f"{name}: top 15 'Publisher' values ({vc.size:,} distinct)")
    ax.set_xlabel("rows")
    save_show(fig, f"03_publishers_{name}")
    print(f"{name}: top 15 'publishers' account for {vc.head(15).sum() / vc.sum():.0%} of rows")

# %% Step 6 – When is news published? (matters for aligning news to trading days)
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
dow_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
width = 0.4
for j, (name, df) in enumerate(news.items()):
    d = df["date"].dropna()
    dow = d.dt.dayofweek.value_counts(normalize=True).reindex(range(7), fill_value=0)
    axes[0].bar(np.arange(7) + (j - 0.5) * width, dow.values * 100, width, label=name, color=COLORS[name])
    has_time = ~((d.dt.hour == 0) & (d.dt.minute == 0) & (d.dt.second == 0))
    hour = d[has_time].dt.hour.value_counts(normalize=True).reindex(range(24), fill_value=0)
    axes[1].plot(hour.index, hour.values * 100, marker="o", label=name, color=COLORS[name])
    print(f"{name}: weekend share {dow.loc[[5, 6]].sum():.1%}; "
          f"{(~has_time).mean():.1%} of timestamps are exactly midnight (excluded from hour chart)")
axes[0].set_xticks(range(7), dow_names)
axes[0].set_title("Day of week (% of rows)")
axes[0].legend()
axes[1].set_title("Hour of day, UTC (% of rows with a real time)")
axes[1].set_xlabel("hour (UTC); US market open 13:30/14:30 UTC")
axes[1].set_xticks(range(0, 24, 2))
axes[1].legend()
save_show(fig, "04_publication_timing")

# %% Step 7 – Text length
fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
for name, df in news.items():
    tl = df["title_len"].dropna()
    axes[0].hist(tl.clip(upper=tl.quantile(0.99)), bins=60, alpha=0.6, density=True,
                 label=f"{name} (median {tl.median():.0f})", color=COLORS[name])
axes[0].set_title("Headline length (characters)")
axes[0].legend()

al = news["nasdaq"]["article_len"].dropna()
axes[1].hist(al.clip(upper=al.quantile(0.99)), bins=60, color=COLORS["nasdaq"])
axes[1].set_title(f"Nasdaq article length (chars, median {al.median():,.0f})")
save_show(fig, "05_text_length")
print(news["nasdaq"]["article_len"].describe(percentiles=[0.01, 0.25, 0.5, 0.75, 0.99]).round(0))

# %% Step 8 – Do the news tickers line up with each other and with the price files?
with zipfile.ZipFile(PRICE_ZIP) as z:
    price_tickers = {
        Path(n).stem.upper() for n in z.namelist()
        if n.startswith("full_history/") and n.endswith(".csv") and "__MACOSX" not in n
    }

t_nas = set(news["nasdaq"]["ticker"].dropna().unique())
t_bz = set(news["benzinga"]["ticker"].dropna().unique())
overlap = pd.Series({
    "tickers in Nasdaq news": len(t_nas),
    "tickers in Benzinga news": len(t_bz),
    "in both news files": len(t_nas & t_bz),
    "price files in full_history.zip": len(price_tickers),
    "Nasdaq-news tickers with a price file": len(t_nas & price_tickers),
    "Benzinga-news tickers with a price file": len(t_bz & price_tickers),
})
print(overlap.to_string())
for name, df in news.items():
    print(f"{name}: {df['ticker'].isin(price_tickers).mean():.1%} of news ROWS have a matching price file")

# %% Step 9 – Ticker-day panel (the unit you'd regress on)
# Calendar date in UTC. Caveat: news after the US close (~20:00–21:00 UTC) really
# belongs to the NEXT trading day – handle that before any regression.
daily = []
for name, df in news.items():
    g = (df.dropna(subset=["date", "ticker"])
           .assign(day=lambda x: x["date"].dt.normalize())
           .groupby(["ticker", "day"], observed=True).size().rename(f"n_{name}"))
    daily.append(g)
panel = pd.concat(daily, axis=1).fillna(0).astype(int).reset_index()
panel["n_total"] = panel.filter(like="n_").sum(axis=1)
panel.to_csv(CACHE_DIR / "news_counts_by_ticker_day.csv", index=False)
print(f"{len(panel):,} ticker-days with at least one news row (saved to cache/news_counts_by_ticker_day.csv)")
print(panel["n_total"].describe(percentiles=[0.5, 0.9, 0.99]).round(1))

fig, ax = plt.subplots(figsize=(8, 4))
ax.hist(panel["n_total"].clip(upper=20), bins=np.arange(1, 22) - 0.5, color="#555")
ax.set_yscale("log")
ax.set_title("News rows per ticker-day (days with ≥1 story; 20 = 20+)")
ax.set_xlabel("rows on that ticker-day")
ax.set_ylabel("ticker-days (log)")
save_show(fig, "06_news_per_ticker_day")

# %% Step 10 – First look: one well-covered ticker, news days vs. price moves
# Purely descriptive – this is NOT evidence that news causes returns.
covered = panel.groupby("ticker")["n_total"].sum().sort_values(ascending=False)
example = next(t for t in covered.index if t in price_tickers)
with zipfile.ZipFile(PRICE_ZIP) as z:
    px = pd.read_csv(z.open(f"full_history/{example}.csv"), parse_dates=["date"])
px = px.sort_values("date").set_index("date")
px["ret"] = px["adj close"].pct_change()
nd = panel.loc[panel["ticker"] == example].set_index("day")["n_total"]
px["n_news"] = nd.reindex(px.index).fillna(0)
px = px.loc[nd.index.min():nd.index.max()]

px["news_day"] = np.where(px["n_news"] > 0, "news day", "no news")
summary = px.groupby("news_day")["ret"].agg(
    days="count", mean_abs_return=lambda r: r.abs().mean(), std="std")
print(f"Example ticker: {example}")
print(summary.round(4))

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 6), sharex=True)
ax1.plot(px.index, px["adj close"], color="black", lw=0.8)
ax1.set_title(f"{example}: adjusted close and daily news count")
ax1.set_ylabel("adj close")
ax2.bar(px.index, px["n_news"], width=1.0, color=COLORS["nasdaq"])
ax2.set_ylabel("news rows")
save_show(fig, "07_example_ticker")

# %% Step 11 – News volume over time for the 15 most-covered tickers
# The two files share ~1.8M ticker-tagged URLs, so stack them and count each
# (ticker, article) pair once. Rows with no URL can't be matched, so all are kept.
# Rows without a ticker (Reuters/Bloomberg/lenta.ru general news) are left out.
EMPTY_URL = pd.util.hash_pandas_object(pd.Series([""]), index=False).iloc[0]
tagged = pd.concat(
    [df.loc[df["ticker"].notna(), ["date", "ticker", "url_hash"]].assign(ticker=lambda x: x["ticker"].astype(str))
     for df in news.values()],
    ignore_index=True,
)
# 2009+ drops the 1969-12-31 placeholder dates; Jan 2024 is a partial month (9 days)
tagged = tagged[(tagged["date"] >= "2009-01-01") & (tagged["date"] < "2024-01-01")]
dup = tagged.duplicated(["ticker", "url_hash"]) & (tagged["url_hash"] != EMPTY_URL)
print(f"{dup.sum():,} of {len(tagged):,} ticker-tagged rows repeat a (ticker, article) pair – dropped")
tagged = tagged[~dup]

# Scraping artifact: between 30 Nov and 16 Dec 2023 the same ~10k Nasdaq articles were tagged to
# ~50 obscure symbols (warrants, preferreds, units, e.g. BROGW, BPYPO, BHFAL). Drop any ticker with
# 1,000+ articles of which more than half fall in that window.
per_ticker = tagged["ticker"].value_counts()
in_burst = tagged.loc[tagged["date"].between("2023-11-30", "2023-12-17"), "ticker"].value_counts()
burst_share = in_burst.reindex(per_ticker.index, fill_value=0) / per_ticker
artifact = per_ticker.index[(per_ticker >= 1000) & (burst_share > 0.5)]
print(f"Dropping {len(artifact)} tickers tagged by the Dec-2023 batch: {', '.join(artifact[:10])}, ...")
tagged = tagged[~tagged["ticker"].isin(artifact)]

top15 = tagged["ticker"].value_counts().head(15)
months = pd.date_range("2009-01-01", "2023-12-01", freq="MS")
monthly = (tagged[tagged["ticker"].isin(top15.index)]
           .groupby(["ticker", pd.Grouper(key="date", freq="MS")]).size()
           .unstack("ticker", fill_value=0)
           .reindex(index=months, columns=top15.index, fill_value=0))
print("Top 15 tickers by unique articles, 2009–2023:")
print(top15.to_string())

BENZINGA_END = pd.Timestamp("2020-06-11")   # last date in All_external.csv
fig, axes = plt.subplots(5, 3, figsize=(13, 12), sharex=True, sharey=True)
for ax, t in zip(axes.flat, top15.index):
    for other in top15.index.drop(t):
        ax.plot(monthly.index, monthly[other], color="#dcdbd7", lw=0.6, zorder=1)
    ax.plot(monthly.index, monthly[t], color="#2a78d6", lw=1.5, zorder=3)
    ax.axvline(BENZINGA_END, color="#8a8984", lw=0.8, ls="--", zorder=2)
    ax.set_title(f"{t}  ·  {top15[t]:,} articles", loc="left", fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    ax.spines[["top", "right"]].set_visible(False)
for ax in axes[:, 0]:
    ax.set_ylabel("articles / month")
axes[0, 0].annotate("Benzinga file ends", xy=(BENZINGA_END, 0.97), xycoords=("data", "axes fraction"),
                    xytext=(-4, 0), textcoords="offset points", ha="right", va="top",
                    fontsize=8, color="#52514e")
fig.suptitle("Monthly news volume, 15 most-covered tickers (Nasdaq + Benzinga, unique articles, 2009–2023)\n"
             "grey = the other 14 tickers, for comparison", x=0.01, ha="left", fontsize=12)
save_show(fig, "08_top15_news_volume")

# %% [markdown]
# ## Key findings (from the full run)
# Filled in after the first full run – see bottom of file.

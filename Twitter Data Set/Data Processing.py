# %% [markdown]
# # ECO375 – Tweet Sentiment & Stock Returns: Data Loading
# Source: full_dataset-release.csv (862,231 tweets, 101 firms, 121 dates)
#
# NOTE: the raw CSV contains ~4.2M bare carriage returns (\r) inside unquoted
# tweet text, which breaks pd.read_csv. We strip them before parsing.

# %%
import io
from pathlib import Path

import numpy as np
import pandas as pd

pd.set_option("display.max_columns", 30)
pd.set_option("display.width", 200)
pd.set_option("display.max_colwidth", 80)

DATA_PATH = Path(__file__).parent / "full_dataset-release.csv" if "__file__" in globals() else Path("full_dataset-release.csv")


def load_tweets(path=DATA_PATH):
    raw = path.read_bytes()
    raw = raw.replace(b"\r\n", b"\n").replace(b"\r", b" ")
    df = pd.read_csv(io.BytesIO(raw), index_col=0)
    df["DATE"] = pd.to_datetime(df["DATE"], format="%d/%m/%Y")
    df["WEEKDAY"] = df["DATE"].dt.day_name()
    df["IS_WEEKEND"] = df["DATE"].dt.dayofweek >= 5
    return df


df = load_tweets()
assert len(df) == 862_231, f"unexpected row count {len(df)}"
print(df.shape)

# %% Quick look
df.head(10)

# %% Structure
df.info()

# %% Summary stats
df.describe().T

# %% Firms ranked by mentions
firm_rank = (
    df.groupby("STOCK")
    .agg(mentions=("TWEET", "size"), unique_tweets=("TWEET", "nunique"), days=("DATE", "nunique"))
    .sort_values("mentions", ascending=False)
)
firm_rank["share_pct"] = (firm_rank["mentions"] / firm_rank["mentions"].sum() * 100).round(2)
firm_rank

# %% Recomputed daily price change
# The dataset's k_DAY_RETURN columns are P(t-k)/P(t) - 1 (backward-looking, inverted),
# not forward returns. Rebuild the true close-to-close change and reconcile it.
# Prices are calendar-day: weekends carry Friday's close, so weekend changes are 0.

# Implied close on t-1 (calendar day), recovered from the dataset's own 1_DAY_RETURN
df["PREV_CLOSE"] = df["LAST_PRICE"] * (1 + df["1_DAY_RETURN"])
# True daily price change, close(t-1) -> close(t)
df["DAILY_PRICE_CHG"] = df["LAST_PRICE"] / df["PREV_CLOSE"] - 1

# Independent check: the firm's observed LAST_PRICE on t-1, where that date is in the data
closes = df.groupby(["STOCK", "DATE"])["LAST_PRICE"].first()
prev_key = pd.MultiIndex.from_arrays([df["STOCK"], df["DATE"] - pd.Timedelta(days=1)])
df["DAILY_PRICE_CHG_OBS"] = df["LAST_PRICE"] / closes.reindex(prev_key).to_numpy() - 1
df["RECON_DIFF"] = df["DAILY_PRICE_CHG"] - df["DAILY_PRICE_CHG_OBS"]

# Next-trading-day change, close(t) -> close(next weekday); weekend tweets map to Monday
next_bday = {d: d + pd.offsets.BDay(1) for d in pd.DatetimeIndex(df["DATE"].unique())}
daily_chg = df.groupby(["STOCK", "DATE"])["DAILY_PRICE_CHG"].first()
next_key = pd.MultiIndex.from_arrays([df["STOCK"], df["DATE"].map(next_bday)])
df["NEXT_DAY_PRICE_CHG"] = daily_chg.reindex(next_key).to_numpy()

recon = df["RECON_DIFF"].dropna()
print(f"Reconciled rows: {len(recon):,} | max |diff|: {recon.abs().max():.2e} | "
      f"match within 1e-9: {(recon.abs() < 1e-9).mean():.1%}")
print("Coverage by year:")
print(df.groupby(df["DATE"].dt.year)[["DAILY_PRICE_CHG", "DAILY_PRICE_CHG_OBS", "NEXT_DAY_PRICE_CHG"]]
      .apply(lambda g: g.notna().mean().round(3)))
df[["STOCK", "DATE", "WEEKDAY", "LAST_PRICE", "PREV_CLOSE", "1_DAY_RETURN",
    "DAILY_PRICE_CHG", "DAILY_PRICE_CHG_OBS", "NEXT_DAY_PRICE_CHG"]].drop_duplicates(["STOCK", "DATE"]).query(
    "STOCK == 'Apple' and DATE >= '2018-09-06'").head(10)

# %% Firm-day panel (returns/price are constant within firm-day, so aggregate here)
panel = (
    df.groupby(["STOCK", "DATE"])
    .agg(
        n_tweets=("TWEET", "size"),
        lstm_mean=("LSTM_POLARITY", "mean"),
        textblob_mean=("TEXTBLOB_POLARITY", "mean"),
        last_price=("LAST_PRICE", "first"),
        ret_1d=("1_DAY_RETURN", "first"),
        ret_2d=("2_DAY_RETURN", "first"),
        ret_3d=("3_DAY_RETURN", "first"),
        ret_7d=("7_DAY_RETURN", "first"),
        prev_close=("PREV_CLOSE", "first"),
        daily_price_chg=("DAILY_PRICE_CHG", "first"),
        next_day_price_chg=("NEXT_DAY_PRICE_CHG", "first"),
        volume=("PX_VOLUME", "first"),
        vol_10d=("VOLATILITY_10D", "first"),
        vol_30d=("VOLATILITY_30D", "first"),
        is_weekend=("IS_WEEKEND", "first"),
    )
    .reset_index()
)
print(panel.shape)
panel.head(10)

# %% Firms per day
firms_per_day = df.groupby("DATE")["STOCK"].nunique()
firms_per_day.describe()

# %% Figure: tweet volume over time (A) and daily return by firm (B)
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

INK, INK_2, MUTED, GRID, AXIS = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"]  # categorical slots 1-5, fixed order
plt.rcParams.update({
    "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "DejaVu Sans"],
    "axes.edgecolor": AXIS, "axes.labelcolor": INK_2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True, "grid.color": GRID,
    "grid.linewidth": 0.6, "axes.axisbelow": True, "figure.facecolor": "white", "axes.facecolor": "white",
})

daily = panel[panel["DATE"] >= "2018-07-11"]               # daily window; 2017 is month-end only
vol = daily.pivot(index="DATE", columns="STOCK", values="n_tweets").asfreq("D")  # missing dates -> line gaps
top_firms = firm_rank.index[:5].tolist()
top25 = firm_rank.index[:25].tolist()

fig, (ax_a, ax_b) = plt.subplots(2, 1, figsize=(12, 10), sharex=True, gridspec_kw={"hspace": 0.3})

# Panel A — context firms in gray, top 5 highlighted and direct-labelled
for firm in vol.columns.difference(top_firms):
    ax_a.plot(vol.index, vol[firm], color=AXIS, linewidth=0.6, alpha=0.6, zorder=1)
label_y = {}
for firm, color in zip(top_firms, SERIES):
    s = vol[firm]
    ax_a.plot(s.index, s, color=color, linewidth=2, label=firm, zorder=3)
    label_y[firm] = np.log10(s.dropna().iloc[-1])
# Spread end labels so they don't collide (min gap in log10 units)
prev = None
for firm in sorted(label_y, key=label_y.get, reverse=True):
    if prev is not None and prev - label_y[firm] < 0.17:
        label_y[firm] = prev - 0.17
    prev = label_y[firm]
    ax_a.annotate(firm, (vol.index[-1], 10 ** label_y[firm]), xytext=(6, 0), textcoords="offset points",
                  va="center", fontsize=9, color=INK_2)
ax_a.set_yscale("log")
ax_a.set_ylabel("Tweets per day (log scale)")
ax_a.xaxis.set_major_locator(mdates.MonthLocator())
ax_a.xaxis.set_minor_locator(mdates.WeekdayLocator(byweekday=mdates.MO))
ax_a.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
ax_a.set_xlim(vol.index.min(), vol.index.max() + pd.Timedelta(days=9))
ax_a.legend(loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, ncol=5, fontsize=9, labelcolor=INK_2)
ax_a.set_title("A. Daily tweet volume by firm, 11 Jul – 31 Oct 2018 (top 5 highlighted; other 96 firms in gray;\n"
               "    breaks = dates missing from the dataset)", loc="left", fontsize=11, color=INK, pad=28)

# Panel B — daily close-to-close return over time, same firms/colors as A.
# Weekdays only (weekend returns are 0 by construction); missing dates -> line gaps.
ret = (daily[~daily["is_weekend"]]
       .pivot(index="DATE", columns="STOCK", values="daily_price_chg").asfreq("B") * 100)
for firm in ret.columns.difference(top_firms):
    ax_b.plot(ret.index, ret[firm], color=AXIS, linewidth=0.6, alpha=0.5, zorder=1)
for firm, color in zip(top_firms, SERIES):
    ax_b.plot(ret.index, ret[firm], color=color, linewidth=1.6, label=firm, zorder=3)
ax_b.axhline(0, color=MUTED, linewidth=1, zorder=2)
ax_b.set_ylabel("Daily return, close-to-close (%)")
ax_b.legend(loc="lower left", bbox_to_anchor=(0, 1.0), frameon=False, ncol=5, fontsize=9, labelcolor=INK_2)
ax_b.set_title("B. Daily stock return by firm, weekdays 11 Jul – 31 Oct 2018 (same firms highlighted; others in gray)",
               loc="left", fontsize=11, color=INK, pad=28)
ax_b.tick_params(axis="x", labelbottom=True)

fig.savefig("fig_volume_and_returns.png", dpi=200, bbox_inches="tight")
plt.show()

# V4b weekly (same-week return, Fama–MacBeth): results

*ECO375 term project · run 2026-11-16 · do-file [v4b_weekly_same_week.do](../v4/v4b_weekly_same_week.do) · next-week version in [v4_weekly_three_regressions.md](v4_weekly_three_regressions.md)*

## Model

One cross-sectional OLS per week *t*, across stocks, then the coefficients are averaged over weeks:

$$r_{i,t} = \alpha_t + \lambda^A_t\,\text{AbnAttn}_{i,t} + \gamma^S_t\,\text{Size}_{i,t-1} + \gamma^V_t\,\text{Risk}_{i,t-1} + \gamma^B_t\,\text{BM}_{i,t-1} + \gamma^M_t\,\text{Mom}_{i,t-2} + \gamma^R_t\,r_{i,t-1} + \gamma^E_t\,\text{Earn}_{i,t} + \epsilon_{i,t}$$

| Term | Variable | Definition |
|---|---|---|
| Outcome | `ret_w` | **This week's** return, winsorized 1/99 |
| AbnAttn (V4-I) | `abn_i` | 1 if this week's articles (price reports removed) > the stock's own 4-week average |
| AbnAttn (V4-C) | `abn_c` | ln(1 + articles) − ln(1 + 4-week average) |
| Size | `size_r` | log average weekly dollar volume, weeks t−52..t−1 |
| Risk | `risk_r` | 52-week daily volatility as of last week |
| BM | `bm_r` | log(book / market equity) as of last week |
| Mom | `mom_r` | cumulative return, weeks t−52..t−2 |
| Reversal | `ret_lag_r` | last week's return |
| Earn | `earn_8k` | 1 if earnings are released this week |

All controls end **before** week *t*, so none moves mechanically with this week's return. `_r` = within-week percentile rank (0 = lowest stock, 1 = highest).

**Sample:** 103 weeks (blocks 2–104), 275,505 stock-weeks, about 2,675 stocks per week.

## Results

| Variable | V4-I coef. | t | p | V4-C coef. | t | p |
|---|---:|---:|---:|---:|---:|---:|
| **AbnAttn** | **0.00214** | **6.41** | **0.000** | **0.00190** | **7.60** | **0.000** |
| size_r | −0.00007 | −0.04 | 0.970 | 0.00072 | 0.38 | 0.706 |
| risk_r | −0.00458 | −1.93 | 0.057 | −0.00461 | −1.94 | 0.056 |
| bm_r | −0.00060 | −0.45 | 0.652 | −0.00052 | −0.40 | 0.694 |
| mom_r | 0.00229 | 1.36 | 0.176 | 0.00238 | 1.42 | 0.159 |
| **ret_lag_r** | **−0.00494** | **−4.26** | **0.000** | −0.00496 | −4.29 | 0.000 |
| earn_8k | −0.00307 | −1.95 | 0.054 | −0.00430 | −2.66 | 0.009 |
| cons | 0.00249 | 1.36 | 0.179 | 0.00297 | 1.61 | 0.111 |
| F(7, 95) | 14.58 (p = 0.000) | | | 15.82 (p = 0.000) | | |
| avg. R² | 0.051 | | | 0.052 | | |

The Newey–West run (regression 3) wasn't shared. The Python run of the same model without `ret_lag_r` gave NW t = 6.2 for `abn_i`, so autocorrelation isn't a concern here.

## Interpretation

- **Strong same-week link.** In a week when a stock's coverage is above its own 4-week norm, its return is about **0.21 pp higher** than other stocks' that week, holding the controls fixed (t = 6.4). The continuous measure agrees: doubling coverage relative to the norm (+0.69 log points) goes with about 0.13 pp higher return (0.0019 × 0.69, t = 7.6). Unlike the next-week test, **both** attention measures are highly significant.
- **Same size as the two-way FE estimate.** The weekly firm + week FE model gave +0.23 pp (t = 9.3). Two quite different designs (within-stock over time vs. across stocks within a week) give almost the same number.
- **Contemporaneous, not predictive.** The same attention measure predicts only +0.04 pp *next* week (t = 2.0, and the continuous version isn't significant). About 80% of the association is in the same week. That fits news arriving with, or reacting to, price moves, rather than attention driving future prices.
- **Reversal:** stocks that did best last week do about 0.49 pp worse this week (t = −4.3), the same size as in the next-week model, as expected.
- **Earnings week:** returns are slightly *lower* in an earnings week once attention is controlled for (−0.3 to −0.4 pp, t between −2.0 and −2.7). Earnings weeks also bring above-normal coverage, so the attention dummy picks up the news part, and what's left is slightly negative.
- **Risk** is borderline negative (low-volatility pattern). Size, value and momentum aren't significant.

## Caveats

1. **Direction of causality:** the same-week design can't tell whether news moves prices or prices generate news. The next-week result (small, fragile) suggests most of the link is news *about* price moves. The tracker's price-report filter already removes headlines that explicitly report price moves, and the link survives that.
2. **SEC data quality:** some market-equity values are wrong (bad share counts), which affects BM. Ranking limits the damage.
3. **Short history early on:** 52-week windows are shorter during the first year of the sample.

## All runs so far

| Model | Horizon | AbnAttn (indicator) | t | AbnAttn (continuous) | t |
|---|---|---:|---:|---:|---:|
| Weekly TWFE | same week | +0.0023 | 9.31 | — | — |
| **V4b weekly (FMB)** | **same week** | **+0.0021** | **6.41** | **+0.0019** | **7.60** |
| Weekly TWFE | next week | +0.0003 | 1.47 | — | — |
| V4 weekly (FMB) | next week | +0.0004 | 2.03 | +0.0002 | 1.28 |
| V4 monthly (FMB) | next month | −0.0008 | −0.91 | — | — |

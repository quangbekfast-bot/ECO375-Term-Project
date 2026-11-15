# Weekly two-way FE regression: next-week return (timing check)

*ECO375 term project · run 2026-11-15 · follows [weekly_twfe_results.md](weekly_twfe_results.md)*

## Why this regression

In the first run, attention and returns were measured in the **same** week, so a positive coefficient could mean either that attention moves prices or that news reacts to a price move. This run keeps this week's attention and last week's controls on the right-hand side but puts **next week's** return on the left. Attention is then measured strictly before the return, so the regression asks whether a news spike *predicts* returns.

## Specification

$$\text{ret}_{i,t+1} = \beta_1\,\text{AbnAttn}_{it} + \gamma'X_{i,t-1} + \delta\,\text{Earn}_{i,t+1} + a_i + \lambda_t + u_{i,t+1}$$

- **Outcome:** `ret_next = F.ret_w`, next week's return winsorized at 1/99.
- **AbnAttn, controls, sample, FE and clustering:** same as the first run (firm FE, week FE, SEs clustered by firm).
- **Earnings dummy:** moved to the return week (`earn_next = F.earn_8k`). Earnings dates are scheduled in advance, so this isn't caused by the return.
- **Last week:** block 104 drops out because it has no following week.

```stata
xtset firm_id block
gen ret_next  = F.ret_w
gen earn_next = F.earn_8k
areg ret_next abn_attn n_news_lag1 log_dvol_lag log_size_lag bm_lag turnover_lag earn_next i.block, ///
    absorb(firm_id) vce(cluster firm_id)
```

## Results

N = 275,079 stock-weeks · 2,869 firms · R² = 0.188 · Root MSE = 0.050

| Variable | Coef. | SE | t | p |
|---|---:|---:|---:|---:|
| **abn_attn** | **0.00032** | 0.00022 | **1.47** | **0.142** |
| n_news_lag1 | 0.00002 | 0.00002 | 1.07 | 0.286 |
| log_dvol_lag | −0.00132 | 0.00025 | −5.36 | 0.000 |
| log_size_lag | −0.01260 | 0.00085 | −14.89 | 0.000 |
| bm_lag | 1.42e-10 | 1.23e-11 | 11.53 | 0.000 |
| turnover_lag | 1.33e-09 | 1.74e-10 | 7.60 | 0.000 |
| earn_next | 0.00145 | 0.00060 | 2.40 | 0.016 |

The week dummies are omitted. Each one is now keyed to the attention week, so block 103's −0.10 is the return in the following week, the Feb 24–28, 2020 COVID crash.

## Same week vs. next week

| | Same-week return | Next-week return |
|---|---:|---:|
| abn_attn coefficient | 0.00228 (0.23 pp) | 0.00032 (0.03 pp) |
| t-stat | 9.31 | 1.47 |
| p-value | 0.000 | 0.142 |
| N | 277,990 | 275,079 |

## Interpretation

- **Attention does not predict next week's return.** The coefficient falls from 0.23 pp to 0.03 pp, about one-seventh as large, and is no longer statistically different from zero.
- **The same-week effect is mostly contemporaneous.** Coverage spikes coincide with good returns but don't lead them, which is consistent with news reacting to (or arriving with) price moves in the same week.
- **No reversal either.** The coefficient isn't negative, so the spike-week gain doesn't unwind the following week. The same-week return looks like a permanent price move rather than temporary attention-driven buying pressure.
- **Earnings week matters for the next return:** stocks reporting earnings next week earn about 0.14 pp more that week (p = 0.016), a standard earnings-announcement premium.
- **Size and dollar volume** stay negative, with the same short-term reversal reading as before.

## Caveats and next steps

1. **`bm_lag` and `turnover_lag` still have broken scales** (coefficients around 1e-10). Fix them (`ln(bm_lag)`, winsorize turnover) and rerun both regressions.
2. **Run the lean version** (`areg ret_next abn_attn n_news_lag1 log_dvol_lag i.block, absorb(firm_id) vce(cluster firm_id)`). It uses the full covered sample without the SEC match, to check that the null result isn't a sample-size issue.
3. **Separate the channels in the same week.** Rerun the same-week model with price-report headlines kept versus removed, as the tracker suggests. If the same-week effect is driven by headlines written *about* price moves, that supports reverse causality.
4. **Model choice.** The tracker's monthly V4 (attention at month *t* → return at *t+1*) is the monthly version of this test. A null here makes it worth checking whether a longer horizon shows anything.

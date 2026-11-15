# Weekly two-way FE regression: first results

*ECO375 term project · run 2026-11-15*

## Data

`panel_weekly_merged.dta` is one row per stock per week (Sat–Fri `block` weeks), built from three files merged on `ticker` and `block`:

| Source | Contents |
|---|---|
| `panel_weekly_filtered_2018-03_2020-02.csv` | Weekly return `ret`, volume, dollar volume, `n_articles` (price-report headlines removed), flags `covered`, `bad_px`, `pre_sample` |
| `sec_controls_weekly_2018-03_2020-02.csv` | `book_equity`, `market_equity`, `shares_out`, `earn_8k` (earnings-release week); about 69% of rows match |
| Ken French 3 factors (weekly, compounded from daily) | `rf`, `mkt_rf`, `smb`, `hml` as decimals |

The full file has 574,195 rows and 5,521 tickers. Blocks 1–104 cover Mar 2018 to Feb 2020, and blocks −2 to 0 are kept only to build lags.

## Specification

$$\text{ret}_{it} = \beta_1\,\text{AbnAttn}_{it} + \gamma'X_{i,t-1} + a_i + \lambda_t + u_{it}$$

- **Outcome:** `ret_w`, the weekly return winsorized at 1/99. Week FE absorb RF and the market, so the excess return gives the same β₁.
- **AbnAttn:** 1 if this week's articles exceed the stock's mean over the previous 4 weeks (at least 3 lags required).
- **Controls (last week):** articles, log dollar volume, log market equity, B/M, turnover, plus same-week `earn_8k`.
- **Fixed effects:** firm (`a_i`) and week (`λ_t`). Standard errors are clustered by firm.
- **Sample:** `pre_sample = 0`, `covered = 1`, `bad_px = 0`.

```stata
areg ret_w abn_attn n_news_lag1 log_dvol_lag log_size_lag bm_lag turnover_lag earn_8k i.block, ///
    absorb(firm_id) vce(cluster firm_id)
```

## Results

N = 277,990 stock-weeks · 2,875 firms · R² = 0.191 · Root MSE = 0.050

| Variable | Coef. | SE | t | p |
|---|---:|---:|---:|---:|
| **abn_attn** | **0.00228** | 0.00025 | **9.31** | 0.000 |
| n_news_lag1 | 0.00002 | 0.00002 | 0.75 | 0.454 |
| log_dvol_lag | −0.00147 | 0.00029 | −5.13 | 0.000 |
| log_size_lag | −0.01389 | 0.00097 | −14.38 | 0.000 |
| bm_lag | 1.28e-10 | 1.35e-11 | 9.46 | 0.000 |
| turnover_lag | 7.65e-10 | 1.90e-10 | 4.03 | 0.000 |
| earn_8k | 0.00007 | 0.00062 | 0.11 | 0.909 |

The 103 week dummies are omitted from the table. They capture each week's common market move relative to block 1. Block 104 (Feb 24–28, 2020, the COVID crash) is −0.14. The week dummies explain most of the R². The F-statistic is missing because the model has more parameters than Stata can test with 2,875 clusters, which is normal here.

## Interpretation

- **Main result:** in weeks when a stock's coverage is above its own 4-week average, its return is about **0.23 percentage points higher**. That compares the stock with its own normal weeks and with other stocks that same week, holding the controls fixed. The effect is small next to the typical 5% weekly swing but very precisely estimated (t = 9.3).
- **Lagged attention:** last week's coverage level adds nothing once the spike indicator is in.
- **Size and dollar volume:** both are negative. With firm FE, these say that a stock whose price or trading rose last week does slightly worse this week. That's short-term reversal, not a cross-stock size premium.
- **Earnings week:** no detectable effect.

## Caveats and next steps

1. **Fix `bm_lag` and `turnover_lag`.** Coefficients around 1e-10 mean some values are in the hundreds of millions, probably from tiny or mis-scaled market equity or share counts. Check with `summ bm_lag turnover_lag, detail`, use `ln(bm_lag)`, and winsorize turnover. The coefficients aren't reportable until this is done.
2. **Timing check.** Attention and return are in the same week, so news may be reacting to price moves. Rerun with next week's return (`gen ret_next = F.ret_w`, run before the `keep` step). If `abn_attn` stays positive, attention predicts returns.
3. **Sample selection.** The SEC controls cut the sample roughly in half (277,990 of about 535k covered rows). Report the lean model (`abn_attn n_news_lag1 log_dvol_lag` only) alongside this one.
4. **Robustness from the TWFE write-up.** Run two-way clustering (firm and week), and add a stock-specific slope on Ken French `mkt_rf` (`reghdfe ..., absorb(firm_id block firm_id#c.mkt_rf)`).
5. **Model choice.** The newest tracker version (V4) is monthly Fama–MacBeth cross-sections with attention at *t* and return at *t+1*. The group still needs to decide which spec is the main one.
6. **Still missing:** institutional holdings, analyst count and earnings surprise (WRDS).

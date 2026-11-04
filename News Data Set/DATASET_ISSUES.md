# FNSPID News + Price Data: Known Problems

Problems found while exploring the data in `News Data Set/`, with counts and what was done about each.

- **Fixed** means `build_news_price_dataset.py` handles it, so `news_price_matched.csv` is already clean of it.
- **Open** means it is still in the data and has to be handled in the analysis.

Files covered:

| File | Contents |
|---|---|
| `nasdaq_exteral_data.csv` | Nasdaq.com news, 15,549,299 rows, ~23 GB |
| `All_external.csv` | Benzinga and other sources, 13,057,514 rows, ~5.7 GB |
| `full_history.zip` | 7,693 daily price files |
| `news_price_matched.csv` | Merged output, 4,450,364 rows |

## Summary

| # | Problem | Severity | Status |
|---|---|---|---|
| 1 | Most news rows have no ticker; they are general news (Reuters, Bloomberg, Russian lenta.ru) | High | Fixed (dropped) |
| 2 | The ticker-tagged Benzinga rows are all already in the Nasdaq file | High | Fixed (de-duplicated) |
| 3 | 99.1% of timestamps are exactly 00:00:00, so time of day is unknown | High | **Open** |
| 4 | Ticker coverage starts and stops over time (e.g. no AAPL news before 2020) | High | **Open** |
| 5 | Scraping batch in Dec 2023 tagged the same ~10k articles to 49 obscure symbols | High | Fixed (dropped) |
| 6 | Junk dates (1914-09-16, 1969-12-31) | Medium | Fixed (kept 2009+ only) |
| 7 | Many headlines are roundups that only mention the company | Medium | **Open** |
| 8 | Unclear whether dates are US or UTC calendar days | Medium | **Open** |
| 9 | News rows with no matching price | Medium | Fixed (dropped), but adds selection bias |
| 10 | Publisher, author, text and summary fields are mostly empty | Low–Medium | **Open** |
| 11 | Repeated (ticker, article) rows inside the Nasdaq file | Low | Fixed (de-duplicated) |
| 12 | Price data quirks: impossible returns (e.g. +8,902,516% in a day), zero-volume days, split-adjusted levels, end dates | **High** | **Open** |
| 13 | Raw-file formatting quirks | Low | Fixed (handled when reading) |
| 14 | Older outputs built before these fixes | Medium | **Open** |

---

## 1. Most news rows have no ticker

- **9,804,627 rows in each news file have an empty `Stock_symbol`.** That is 63.1% of the Nasdaq file and 75.1% of the Benzinga file.
- It is **the same block of articles in both files**: all 9,791,999 unique URLs in it appear in both.
- By source website (counted in `All_external.csv`):

  | Source | Rows |
  |---|---|
  | reuters.com | 8,556,310 |
  | lenta.ru (Russian-language general news) | 800,975 |
  | bloomberg.com | 446,656 |
  | no URL | 686 |

- The content is general news, not company news (e.g. "Moose attacks helicopter in Alaska").
- These rows are mostly dated 2008–2016 and stop entirely after 2019.
- **Impact:** any count over *all* rows is inflated, especially for 2008–2016. That includes `figures/01_news_per_month.png`.
- **Status:** Fixed. Untagged rows are excluded from the merged dataset.

## 2. Benzinga file is redundant for ticker-level work

- All **3,241,268** ticker-tagged (ticker, article) pairs in `All_external.csv` also appear in the Nasdaq file.
- For ticker-level analysis the Benzinga file therefore adds no new articles, and every row in `news_price_matched.csv` has `source = nasdaq`.
- The Benzinga file also ends on **2020-06-11**, while the Nasdaq file runs to 2024-01-09.
- **Impact:** adding the two files together (the `n_total` column in `cache/news_counts_by_ticker_day.csv`) double-counts most articles before mid-2020. Any combined series also jumps or drops at June 2020 for that reason alone.
- **Status:** Fixed in the merged dataset (each ticker-article pair kept once; the Nasdaq copy wins). `news_counts_by_ticker_day.csv` has not been rebuilt (see #14).

## 3. Timestamps have no real time of day

- **99.1%** of merged rows (4,410,986 of 4,450,364) are timestamped exactly `00:00:00`.
- It is 100% in 2009–2010 and 2021–2022, and the lowest is 92.2% in 2020.
- The time field is a placeholder: only the **date** is real.
- **Impact:**
  - You can't tell whether an article came out before the market opened, during trading, or after the close. News released after the close shows up in the *next* day's return.
  - The hour-of-day chart in `figures/04_publication_timing.png` rests on the remaining ~0.9% of rows that have a time, a small and unusual subset. Don't use it to describe the dataset.
- **Status:** Open. Suggested approach: measure the reaction over a window of days *t* to *t*+1, or report both the day-*t* and the *t*–*t*+1 results.

## 4. Ticker coverage starts and stops over time

- The scraper clearly did not collect every ticker for the whole period. Among the 15 most-covered tickers (`figures/08_top15_news_volume.png`):
  - **AAPL**: no articles before 2020, and none again from mid-2020 to 2022.
  - **TSLA, NVDA**: zero articles from mid-2020 to 2022.
  - **INTC** starts in 2018; **GOOG** starts in 2019.
- Total ticker-tagged volume also drops in 2021–2022: 181,623 and 280,354 rows, against 954,117 in 2023.
- **Impact:** a ticker-day with no news in the data does **not** mean no news was published. Treating gaps as zero-news days creates false "quiet" periods, and changes in news volume over time partly reflect how the data was collected.
- **Status:** Open. Suggested approach: for each ticker, keep only the period where it is actually covered, and include ticker and time (e.g. month) fixed effects.

## 5. December 2023 scraping batch

- Between **30 Nov and 16 Dec 2023**, the same ~10,000 Nasdaq articles were tagged to dozens of obscure securities: warrants, preferred shares, notes, units and share classes (e.g. BROGW, BPYPO, BHFAL, ACGLO, GTN-A).
- For these symbols nearly all of their articles fall in that window. BROGW and BPYPO share 9,821 identical article URLs.
- **Impact:** before the fix, BROGW, BPYPO and BHFAL ranked among the 15 "most-covered" tickers, with about 10,000 articles each in a single month.
- **Status:** Fixed. Rule used: drop any ticker with ≥1,000 articles of which more than 50% fall in the window. This dropped **49 tickers (350,064 rows)**. Smaller tickers caught up in the same batch, with fewer than 1,000 articles, are *not* removed by this rule.

## 6. Junk dates

- The earliest date in both raw news files is **1914-09-16**. It has not been checked whether these rows all sit in the untagged block from #1.
- The ticker-tagged data contains **1969-12-31**, an "epoch zero" placeholder date (2 ticker-days in the old panel).
- **Status:** Fixed. The merged dataset keeps publication dates from 2009-01-01 to the last price date (2023-12-28). January 2024 is excluded: it is only 9 days and has no prices.

## 7. Headlines that only mention the company

- Many articles are market roundups or lists that mention the company in passing. Examples tagged to `A` (Agilent):
  - "Pre-Market Most Active for Dec 7, 2023 : SQQQ, PLTR, TQQQ, …"
  - "The Zacks Analyst Blog Highlights Visa, Marriott International, Parker-Hannifin, FedEx and Agilent Technologies"
- Some are written *after* a price move and describe it. For example, "Tuesday Sector Leaders: Healthcare, Consumer Products" on a day Agilent rose 8.7%.
- **Impact:** news-volume counts mix company-specific news with incidental mentions, and some articles follow the price move rather than cause it (reverse causality).
- **Status:** Open. Possible filter: keep articles whose title contains the company name, or the ticker in parentheses, e.g. "(A)".
  - Matching the bare ticker fails for one-letter tickers such as A (Agilent), T (AT&T), F (Ford), C (Citigroup) and V (Visa), because they match ordinary words.

## 8. Unclear whether dates are US or UTC

- Raw dates carry a `UTC` label, but because the time is a placeholder (#3), it is unclear whether the date is the US Eastern day or the UTC day.
- Evening US news (after about 8 pm ET) falls on the next UTC day.
- **Status:** Open. Another reason to use a two-day (*t*, *t*+1) window.

## 9. News rows with no matching price

Of 5,379,694 cleaned (ticker, article) rows:

| Outcome | Rows |
|---|---|
| Matched to a price | 4,450,364 |
| Ticker has no price file in `full_history.zip` | 787,901 |
| No trading day within 5 days of publication (e.g. after delisting) | 141,429 |

- The news covers 8,552 tickers, but only 5,987 end up in the merged file.
- Matching rule: each article gets the first trading day on or after its publication date. **94.7%** match on the same day; weekend and holiday news moves to the next session.
- **Impact:** possible selection bias. Unmatched tickers are likely delisted, renamed or non-US securities, so the merged sample leans toward stocks that survived.
- **Status:** Fixed (dropped), but the bias should be acknowledged.

## 10. Mostly empty fields

Share of rows missing each field in the raw files:

| Field | Nasdaq file | Benzinga file |
|---|---|---|
| Publisher | 74.1% | 69.2% |
| Author | 92.4% | 90.9% |
| Article text | 76.0% | 90.4% |
| The four summary columns | 84.0% | 100% |

- In the Benzinga file, `Publisher` actually holds **author names** (Benzinga staff), not outlets.
- In the merged dataset `publisher` and `author` are essentially empty.
- Both files report exactly **1,142** distinct publishers. That looks like an artifact of how the analysis script merges category lists across chunks (`union_categoricals`); it has not been checked.
- **Status:** Open. Don't use publisher as a variable without re-checking it. `has_article_text` in the merged file flags which rows have full text, which can be joined back by `url`.

## 11. Repeated (ticker, article) rows inside the Nasdaq file

- The Nasdaq file has 5,744,672 ticker-tagged rows but only 5,729,843 unique (ticker, URL) pairs, so **14,829** rows are repeats.
- One article tagged to several tickers is legitimate: it appears once per ticker. As a result, rows count (article × ticker) pairs, not distinct articles.
- **Status:** Fixed. Repeats were dropped, and articles tagged to several tickers keep one row per ticker.

## 12. Price data quirks

- **Impossible returns:** **2,529** merged rows have |`ret`| > 100% and 122 have |`ret`| > 1,000%. Example: EFOI shows a daily return of +8,902,516% on 2019-06-17, and a close of $1,283,593.75 on 2015-09-11. These are errors in the price files, most likely bad reverse-split adjustments.
  - A few such rows dominate any mean: the mean |`ret`| across merged rows is about 22%, against a median of about 1.2%.
  - Winsorize returns, or drop |`ret`| above a sensible cap, and prefer medians when describing the data.
- **Zero-volume / stale days:** some rows have `volume = 0` with open = high = low = close. Example: DJCB on 2023-09-12, a thinly traded ETF. These returns are stale prices, not real trading.
- **Split-adjusted price levels:** levels can look odd after reverse splits (e.g. BIOL trading near $441 in 2022). Use `adj_close` / `ret` for returns, not price levels.
- **End-date mismatch:** price files end around **2023-12-28**, while news runs to 2024-01-09.
- **Row order:** price files are sorted newest first, and so are the raw news rows within each ticker. Sort by `ticker` and `price_date` before computing anything that depends on order (lags, rolling windows).
- **Status:** Open. Consider excluding zero-volume days and very illiquid tickers.

## 13. Raw-file formatting quirks (handled when reading)

- The Nasdaq file name is misspelled: `nasdaq_exteral_data.csv`.
- The Nasdaq file has a stray `Unnamed: 0` index column (stored as float).
- Tickers such as `NA` would be read as missing values by pandas' default settings. The scripts read with `keep_default_na=False`.
- The zip contains `__MACOSX/` metadata entries, which are not data. 259 of the 7,693 price files have lowercase names (e.g. `spxu.csv`); tickers are matched case-insensitively.
- The Nasdaq articles contain line breaks inside quoted fields, so the file must be read with a proper CSV parser, not line by line.

## 14. Older outputs built before these fixes

- `cache/news_counts_by_ticker_day.csv` and `figures/01`–`07` from `news_preliminary_analysis.py` were built **before** the fixes above. They:
  - double-count articles found in both files (#2),
  - include the December 2023 batch (#5),
  - and figures 01, 03, 04 and 05 also include the untagged general news (#1).
- **Status:** Open. Rebuild any ticker-day panel from `news_price_matched.csv` by grouping on `ticker` and `price_date`. Use `figures/08_top15_news_volume.png`, which applies the fixes.

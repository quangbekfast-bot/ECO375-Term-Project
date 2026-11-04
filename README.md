# ECO375 Term Project: News Attention and Stock Returns

Does abnormal news attention to a stock go with higher (excess) returns? US equities, FNSPID news + daily prices.

## Model documents
| File | What it is |
|---|---|
| `eco375_tracker.tex/.pdf` | Main tracker: panel model, variables, data issues, open questions |
| `eco375_model_alt_twfe.tex/.pdf` | Alternative panel spec: firm + week fixed effects |
| `eco375_tracker_cross_section.tex/.pdf` | Cross-sectional formulations V1-V4 (Fama-MacBeth) with version log |

## Data pipeline (`Panel Build/`)
Run from inside `Panel Build/`, in order:

| Step | Script | Output (in `Panel Build/data/`) |
|---|---|---|
| 1 | `01_news_ticker_day.py` | `news_ticker_day.csv`: articles per ticker per trading day, all years |
| 2 | `02_build_weekly_panel.py` (batches, then `merge`) | `panel_weekly_base.csv`: weekly returns + attention, 2009-2023 |
| 4 | `04_build_cross_section.py <year>` | `cross_section_<year>.csv`: annual cross-section (V1; superseded, outputs not kept) |
| 5b | `05b_news_daily_panel_matched.py` | daily article counts on matched trading days, Mar 2018 - Feb 2020 |
| 7 | `07_central_panel.py` (batches `0 3`, `1 3`, `2 3`, then `merge`) | `panel_{daily,weekly,monthly}_{raw,filtered}_2018-03_2020-02.csv`: central panels, news + prices |
| 8 | `08_sort_by_time.py` | same files, sorted by time then ticker (one cross-section per period) |
| check | `analysis.py` | `analysis_report.txt`: price reconciliation across sources |

Also: `headline_classifier.py` (keyword rules that flag price-report headlines), `03_merge_controls.py` (merges WRDS / Ken French controls once downloaded into `raw/`).
`05_news_daily_panel.py` and `06_news_blocks.py` are superseded by 5b and 7.

`raw` panels count all articles; `filtered` panels drop price-report headlines. Weekly = 7-day blocks (Sat-Fri), monthly = 30-day blocks, both starting 3 Mar 2018.

## Data in this repo (`Panel Build/data/`)
Central panels, Mar 2018 - Feb 2020, news counts + prices, sorted by time then ticker (one cross-section per period):
- `panel_daily_{raw,filtered}_2018-03_2020-02.csv.gz`: compressed; unzip (7-Zip, or `pandas.read_csv` reads .gz directly)
- `panel_weekly_{raw,filtered}_2018-03_2020-02.csv`
- `panel_monthly_{raw,filtered}_2018-03_2020-02.csv`

## Data not in this repo
GitHub limits files to 100 MB, so these stay local (shared separately, e.g. via cloud drive):
- `News Data Set/`: `nasdaq_exteral_data.csv` (~23 GB), `All_external.csv` (~5.7 GB), `news_price_matched.csv` (~1.3 GB), `full_history.zip` (price files), `cache/`
- `Twitter Data Set/full_dataset-release.csv`
- Intermediate outputs: `panel_weekly_base.csv`, `news_ticker_day.csv`, the news-only `news_*` files. Rebuild them with the scripts above.

Known data problems and fixes: `News Data Set/DATASET_ISSUES.md`.

## Working together (GitHub Desktop)
- **Before you start:** Fetch / Pull to get groupmates' changes.
- **When something is ready:** write a short summary, Commit, then Push.
- Avoid editing the same file at the same time; if a conflict appears, GitHub Desktop walks you through it.

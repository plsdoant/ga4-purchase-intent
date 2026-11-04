# GA4 Purchase Intent

How early in a shopping session can we tell whether it will end in a purchase, and do intent signals shift between pre-holiday, peak and post-holiday shopping?

## Question

- **Task A, early intent:** predict a purchase from the first *k* events of a session, before any cart activity.
- **Task B, cart rescue:** for sessions with an add-to-cart, predict whether a purchase follows.
- **Unit of analysis:** one session.

## Data

Google Analytics 4 obfuscated sample export from the Google Merchandise Store, queried through the free BigQuery sandbox.

| Item | Detail |
| --- | --- |
| Dataset | `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*` |
| Window | Nov 1, 2020 – Jan 31, 2021 (`events_20201101` – `events_20210131`) |
| Events | 4,295,584 |
| Users | 270,154 |
| Days | 92 |
| Known limits | Obfuscated: some fields hold placeholders (`<Other>`, `NULL`, `''`) and internal consistency is limited |

Counts come from [`sql/00_count_check.sql`](sql/00_count_check.sql). Docs: [dataset](https://developers.google.com/analytics/bigquery/web-ecommerce-demo-dataset), [export schema](https://support.google.com/analytics/answer/7029846).

## Setup

Requires Python 3.14 (3.12 and 3.13 also work), the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) and a [BigQuery sandbox](https://cloud.google.com/bigquery/docs/sandbox) project. On macOS, LightGBM needs OpenMP: `brew install libomp`.

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
gcloud auth application-default login
```

Pass your own project ID when creating the client: `bigquery.Client(project="your-project-id")`.

## Repository structure

```text
├── data/                # gitignored
│   ├── raw/             # Parquet extracts from BigQuery
│   └── processed/       # session, prefix and feature tables
├── sql/                 # every BigQuery query run
├── notebooks/           # 01_extract.ipynb … 06_drift.ipynb
├── src/                 # reusable code: sessionize, features, evaluate
├── reports/figures/     # final charts
├── requirements.txt
└── README.md
```

## Key dates, 2020–21 season

| Date | Event |
| --- | --- |
| Nov 1, 2020 | Data starts |
| Nov 26, 2020 | US Thanksgiving |
| Nov 27, 2020 | Black Friday |
| Nov 30, 2020 | Cyber Monday |
| Mid-December | Holiday shipping cutoffs (exact drop found in Phase 2) |
| Dec 25, 2020 | Christmas |
| Jan 1, 2021 | New Year's Day |
| Jan 31, 2021 | Data ends |

## Ground rules

- One random seed everywhere: `42`.
- The test period stays locked until the final step of Phase 5.
- Every query is saved in `sql/`; every final figure in `reports/figures/`.
- Time convention: `event_timestamp` is UTC microseconds; `event_date` is in the property's own time zone.

## Decisions log

Every exclusion, threshold and definition, with its reason.

| Date | Phase | Decision | Reason |
| --- | --- | --- | --- |
| 2026-11-04 | 0 | Random seed fixed at 42 | Reproducibility |
| 2026-11-04 | 0 | Intermediate results stored locally as Parquet, not in BigQuery | Sandbox has 10 GiB lifetime storage and 60-day table expiry |

## Results

To come.

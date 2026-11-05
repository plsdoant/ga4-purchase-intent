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
| Sessions (after cleaning) | 359,848 |
| Converted sessions | 4,672 (1.30%) |
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

## Data quality

Sessions are rebuilt from 4,295,584 events into 360,129 sessions (`src/sessionize.py`), then checked (`src/quality.py`). Full log with converter counts: [`reports/data_quality_log.csv`](reports/data_quality_log.csv).

| Check | Sessions affected | Share of all sessions | Converted sessions affected | Decision |
| --- | ---: | ---: | ---: | --- |
| Missing session ID | 0 | 0.00% | 0 | Drop (none found) |
| No `session_start` | 5,272 | 1.46% | 103 | Keep, flag |
| Window start edge (first 30 min, no `session_start`) | 3 | <0.01% | 0 | Drop |
| Window end edge (last 30 min) | 77 | 0.02% | 1 | Drop |
| Purchase with no earlier `view_item` or `add_to_cart` | 175 | 0.05% | 175 | Drop |
| Purchase with no earlier `add_to_cart` | 2,031 | 0.56% | 2,031 | Keep, flag (Task B scope) |
| Purchase with zero or missing revenue | 411 | 0.11% | 411 | Keep label, flag revenue |
| Purchase with `(not set)` transaction ID | 813 | 0.23% | 813 | Keep, flag |
| More than one purchase | 552 | 0.15% | 552 | Keep label, dedupe revenue |
| Placeholder device, OS, country or medium | 84,108 | 23.36% | 1,342 | Map to `unknown` |
| Gap over 30 min between events | 224 | 0.06% | 5 | Keep, flag |
| Duration over 4 hours | 26 | 0.01% | 0 | Drop |
| Over 500 events | 17 | <0.01% | 11 | Keep |
| No shopper actions | 24,883 | 6.91% | 0 | Keep |

Dropping 281 sessions (0.08%, 176 of them converters) leaves **359,848 sessions, 4,672 converted, a 1.30% conversion rate**. Clean tables: `data/processed/sessions.parquet`, `events_clean.parquet`, `items_clean.parquet`.

## Decisions log

Every exclusion, threshold and definition, with its reason.

| Date | Phase | Decision | Reason |
| --- | --- | --- | --- |
| 2026-11-04 | 0 | Random seed fixed at 42 | Reproducibility |
| 2026-11-04 | 0 | Intermediate results stored locally as Parquet, not in BigQuery | Sandbox has 10 GiB lifetime storage and 60-day table expiry |
| 2026-11-04 | 1 | Extract all 17 event types | BigQuery bills by columns scanned, not rows, so filtering events saves nothing |
| 2026-11-04 | 1 | `session_start`, `first_visit` and `user_engagement` do not count toward the *k*-event prefix; they are used only as feature sources | They fire automatically, not from shopper actions, and make up ~39% of events; counting them would make small *k* uninformative |
| 2026-11-04 | 1 | `view_item_list` not used as a feature | Only 71 events against 31,007 `select_item`, an obfuscation gap |
| 2026-11-04 | 1 | Extraction adds `event_date`, `page_location` and `page_title` to the master-sheet query | Page fields feed "distinct pages viewed" in Phase 4 |
| 2026-11-04 | 1 | Time convention: UTC, from `event_timestamp` | In this export `event_date` matches the UTC date of `event_timestamp` for 100% of events, so the two agree |
| 2026-11-04 | 1 | Events sharing a timestamp within a session are ordered by funnel stage (`EVENT_ORDER` in `src/sessionize.py`), then extract order | 57% of events and 99.7% of sessions have a tie; 43% of shopper actions tie with another action, mostly events fired together on one page load (`page_view` + `view_item`, `page_view` + `scroll`). `purchase` never ties, so label timing is unaffected |
| 2026-11-04 | 1 | Drop sessions at the window edges: starting in the first 30 min without `session_start` (3), or ending in the last 30 min (77) | Their start or outcome may fall outside the data; 30 min is GA4's session timeout |
| 2026-11-04 | 1 | Drop sessions whose purchase has no earlier `view_item` or `add_to_cart` (175) | A purchase with no product interaction is likely an obfuscation artifact and adds noise to Task A positives |
| 2026-11-04 | 1 | Drop sessions longer than 4 hours (26) | None converted; likely tracking errors |
| 2026-11-04 | 1 | Keep sessions with zero or missing purchase revenue as converted; flag them (`dq_bad_revenue`) | The purchase event exists, only its revenue is unreliable; exclude these from revenue analyses |
| 2026-11-04 | 1 | Keep multi-purchase sessions; count revenue once per (session, transaction ID, revenue) | 330 of 552 repeat a transaction ID, i.e. a double-fired purchase; the label is unaffected |
| 2026-11-04 | 1 | Map placeholders (`<Other>`, `(not set)`, `(data deleted)`, `''`, `NULL`) to `unknown` in context and item fields | Makes missingness an explicit category; first-touch medium is most affected (20.7% of sessions) |
| 2026-11-04 | 1 | Keep and flag sessions with no `session_start` (1.46%) and sessions with an internal gap over 30 min (0.06%) | Otherwise normal; too small or too unclear to justify dropping |
| 2026-11-04 | 1 | Open issue for Phase 3: 42% of converting sessions have no `add_to_cart` before the purchase | Most still reach `begin_checkout`, so their cart likely came from an earlier session; Task B as defined covers only ~60% of buyers. Consider a `begin_checkout` variant |
| 2026-11-04 | 1 | Item prices come from `item.price`, not `item.price_in_usd` | `price_in_usd` is filled only on purchases; `price` covers 97–100% of view, cart and checkout rows and equals `price_in_usd` on all 15,555 purchase rows that have both |
| 2026-11-04 | 1 | Open issue for Phase 4: item lists on `view_item`, `add_to_cart` and `select_item` are unreliable | 91% of `view_item` events carry exactly 12 items (only 48% of those from a single category); `add_to_cart` and `select_item` also carry a median of 12. Item-level "what was viewed or added" can't be taken at face value |

## Results

To come.

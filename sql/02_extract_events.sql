-- Phase 1, step 2: one row per event, all 17 event types, Nov 1, 2020 – Jan 31, 2021.
-- Extends the master-sheet query with event_date, page_location and page_title
-- (page fields feed "distinct pages viewed" in Phase 4).
SELECT
  CONCAT(user_pseudo_id, '-', CAST(
    (SELECT value.int_value FROM UNNEST(event_params)
     WHERE key = 'ga_session_id') AS STRING)) AS session_id,
  user_pseudo_id,
  event_date,
  event_timestamp,
  event_name,
  (SELECT value.int_value FROM UNNEST(event_params)
   WHERE key = 'ga_session_number') AS session_number,
  (SELECT value.int_value FROM UNNEST(event_params)
   WHERE key = 'engagement_time_msec') AS engagement_time_msec,
  (SELECT value.string_value FROM UNNEST(event_params)
   WHERE key = 'page_location') AS page_location,
  (SELECT value.string_value FROM UNNEST(event_params)
   WHERE key = 'page_title') AS page_title,
  device.category AS device,
  device.operating_system AS os,
  geo.country AS country,
  traffic_source.medium AS first_touch_medium,
  ecommerce.purchase_revenue_in_usd AS revenue,
  ecommerce.transaction_id
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'

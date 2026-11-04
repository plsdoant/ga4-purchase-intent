-- Phase 0 sanity check: events, users and days in the study window.
-- Processes ~132 MB. Result (2026-11-04): 4,295,584 events, 270,154 users, 92 days.
SELECT
  COUNT(*) AS event_count,
  COUNT(DISTINCT user_pseudo_id) AS user_count,
  COUNT(DISTINCT event_date) AS day_count
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'

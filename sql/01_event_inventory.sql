-- Phase 1, step 1: inventory of event types in the study window.
SELECT
  event_name,
  COUNT(*) AS n
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'
GROUP BY 1
ORDER BY 2 DESC

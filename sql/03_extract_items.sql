-- Phase 1, step 3: one row per item attached to an event (UNNEST(items)).
-- Join back to events on session_id, event_timestamp and event_name.
-- Extends the master-sheet field list with item_name, price and quantity.
-- price_in_usd is populated only on purchase events; price (store currency, USD)
-- covers view, cart and checkout events too.
SELECT
  CONCAT(user_pseudo_id, '-', CAST(
    (SELECT value.int_value FROM UNNEST(event_params)
     WHERE key = 'ga_session_id') AS STRING)) AS session_id,
  event_timestamp,
  event_name,
  item.item_id,
  item.item_name,
  item.item_category,
  item.price,
  item.price_in_usd,
  item.quantity
FROM `bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*`,
  UNNEST(items) AS item
WHERE _TABLE_SUFFIX BETWEEN '20201101' AND '20210131'

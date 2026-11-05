"""Session-level data-quality flags for the Phase 1 checks."""

import pandas as pd

WINDOW_START = pd.Timestamp("2020-11-01", tz="UTC")
WINDOW_END = pd.Timestamp("2021-02-01", tz="UTC")
# GA4 ends a session after 30 minutes of inactivity
SESSION_TIMEOUT = pd.Timedelta("30min")
MAX_DURATION = pd.Timedelta("4h")

PLACEHOLDERS = ["<Other>", "(not set)", "(data deleted)", "", "NULL"]
PLACEHOLDER_COLS = ["device", "os", "country", "first_touch_medium"]
ITEM_PLACEHOLDER_COLS = ["item_id", "item_name", "item_category"]
UNKNOWN = "unknown"

# Decision per check, approved 2026-11-04 (README decisions log has the reasons)
DECISIONS = {
    "missing_session_id": "drop (none found)",
    "no_session_start": "keep, flag",
    "window_start_edge": "drop",
    "window_end_edge": "drop",
    "purchase_without_browsing": "drop",
    "purchase_without_cart": "keep, flag (Task B scope)",
    "bad_revenue": "keep label, flag revenue",
    "bad_transaction_id": "keep, flag",
    "duplicate_purchases": "keep label, dedupe revenue",
    "placeholder_context": "map to 'unknown'",
    "gap_over_timeout": "keep, flag",
    "duration_over_4h": "drop",
    "over_500_events": "keep",
    "zero_shopper_actions": "keep",
}
DROP_CHECKS = [check for check, decision in DECISIONS.items() if decision.startswith("drop")]
FLAG_CHECKS = ["no_session_start", "purchase_without_cart", "bad_revenue", "bad_transaction_id",
               "duplicate_purchases", "gap_over_timeout"]


def _first_index(ordered: pd.DataFrame, names: list[str]) -> pd.Series:
    """Position of each session's first event in `names`."""
    return ordered[ordered["event_name"].isin(names)].groupby("session_id")["event_index"].min()


def quality_flags(sessions: pd.DataFrame, ordered: pd.DataFrame) -> pd.DataFrame:
    """One boolean column per check, indexed by session_id.

    `sessions` comes from build_sessions and `ordered` from order_events.
    """
    s = sessions.set_index("session_id")
    flags = pd.DataFrame(index=s.index)

    flags["missing_session_id"] = s.index.isna()
    flags["no_session_start"] = s["n_session_start"].eq(0)

    # A session starting in the first 30 minutes without session_start probably began before the window;
    # one ending in the last 30 minutes may have continued (and purchased) after it.
    flags["window_start_edge"] = s["start_time"].lt(WINDOW_START + SESSION_TIMEOUT) & flags["no_session_start"]
    flags["window_end_edge"] = s["end_time"].gt(WINDOW_END - SESSION_TIMEOUT)

    first_purchase = _first_index(ordered, ["purchase"])
    first_browse = _first_index(ordered, ["view_item", "add_to_cart"]).reindex(first_purchase.index)
    no_browse = first_browse.isna() | first_browse.gt(first_purchase)
    flags["purchase_without_browsing"] = s.index.isin(no_browse[no_browse].index)

    first_cart = _first_index(ordered, ["add_to_cart"]).reindex(first_purchase.index)
    no_cart = first_cart.isna() | first_cart.gt(first_purchase)
    flags["purchase_without_cart"] = s.index.isin(no_cart[no_cart].index)

    purchases = ordered[ordered["event_name"] == "purchase"]
    bad_revenue = purchases["revenue"].isna() | purchases["revenue"].le(0)
    bad_tid = purchases["transaction_id"].isna() | purchases["transaction_id"].isin(PLACEHOLDERS)
    flags["bad_revenue"] = s.index.isin(purchases.loc[bad_revenue, "session_id"])
    flags["bad_transaction_id"] = s.index.isin(purchases.loc[bad_tid, "session_id"])
    flags["duplicate_purchases"] = s["n_purchase"].gt(1)

    flags["placeholder_context"] = s[PLACEHOLDER_COLS].isin(PLACEHOLDERS).any(axis=1)

    gaps = ordered.groupby("session_id")["event_timestamp"].diff()
    max_gap = pd.to_timedelta(gaps.groupby(ordered["session_id"]).max().reindex(s.index), unit="us")
    flags["gap_over_timeout"] = max_gap.gt(SESSION_TIMEOUT)
    flags["duration_over_4h"] = pd.to_timedelta(s["duration_s"], unit="s").gt(MAX_DURATION)
    flags["over_500_events"] = s["n_events"].gt(500)
    flags["zero_shopper_actions"] = s["n_actions"].eq(0)
    return flags


def quality_log(flags: pd.DataFrame, converted: pd.Series) -> pd.DataFrame:
    """Sessions affected per check, overall and among converters."""
    converted = converted.reindex(flags.index).astype(bool)
    return pd.DataFrame({
        "sessions affected": flags.sum(),
        "share of all sessions": flags.mean(),
        "converted sessions affected": flags[converted].sum(),
        "share of converted sessions": flags[converted].mean(),
        "conversion rate in group": flags.apply(lambda col: converted[col].mean() if col.any() else float("nan")),
        "decision": pd.Series(DECISIONS),
    }).rename_axis("check")


def _map_placeholders(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    return df.assign(**{col: df[col].mask(df[col].isin(PLACEHOLDERS), UNKNOWN) for col in cols})


def apply_decisions(
    sessions: pd.DataFrame, ordered: pd.DataFrame, items: pd.DataFrame, flags: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply DECISIONS and return clean (sessions, events, items).

    - drops sessions failing any DROP_CHECKS check
    - maps placeholders to UNKNOWN in context and item fields
    - marks repeated (session, transaction_id, revenue) purchases and recomputes
      session revenue without them
    - adds dq_<check> columns to sessions for the keep-and-flag checks
    - adds event_index to items and keeps `price` (equal to price_in_usd where both exist)
    """
    keep = flags.index[~flags[DROP_CHECKS].any(axis=1)]

    events = ordered[ordered["session_id"].isin(keep)]
    events = _map_placeholders(events, PLACEHOLDER_COLS)
    events = events.reset_index(drop=True)
    is_purchase = events["event_name"].eq("purchase")
    repeated = events[is_purchase].duplicated(["session_id", "transaction_id", "revenue"])
    events["is_duplicate_purchase"] = repeated.reindex(events.index, fill_value=False)

    counted = events[is_purchase & ~events["is_duplicate_purchase"]]
    clean_sessions = sessions[sessions["session_id"].isin(keep)].set_index("session_id")
    clean_sessions = _map_placeholders(clean_sessions, PLACEHOLDER_COLS)
    clean_sessions["revenue"] = counted.groupby("session_id")["revenue"].sum().reindex(
        clean_sessions.index, fill_value=0.0)
    clean_sessions["n_transactions"] = counted.groupby("session_id").size().reindex(
        clean_sessions.index, fill_value=0)
    clean_sessions = clean_sessions.join(flags.loc[keep, FLAG_CHECKS].add_prefix("dq_"))

    key = ["session_id", "event_timestamp", "event_name"]
    clean_items = items[items["session_id"].isin(keep)].drop(columns="price_in_usd")
    clean_items = _map_placeholders(clean_items, ITEM_PLACEHOLDER_COLS)
    clean_items = clean_items.merge(events[key + ["event_index"]], on=key, how="left", validate="many_to_one")

    return clean_sessions.reset_index(), events, clean_items

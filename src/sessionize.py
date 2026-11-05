"""Rebuild ordered sessions from the raw GA4 event extract."""

import pandas as pd

# Fired automatically by GA4, not by a shopper action. Kept as feature sources,
# but excluded from the k-event prefix count (see README decisions log).
AUTO_EVENTS = ["session_start", "first_visit", "user_engagement"]

# Tie-break for events that share a timestamp within a session: earlier funnel
# stages first, so simultaneous events never put a purchase before its cart.
EVENT_ORDER = [
    "session_start",
    "first_visit",
    "page_view",
    "view_promotion",
    "select_promotion",
    "view_item_list",
    "view_search_results",
    "select_item",
    "view_item",
    "scroll",
    "click",
    "user_engagement",
    "add_to_cart",
    "begin_checkout",
    "add_shipping_info",
    "add_payment_info",
    "purchase",
]

CONTEXT_COLS = ["user_pseudo_id", "session_number", "device", "os", "country", "first_touch_medium"]


def order_events(events: pd.DataFrame) -> pd.DataFrame:
    """Sort events within each session and add position columns.

    Order is session_id, event_timestamp, then EVENT_ORDER rank; the sort is
    stable, so exact duplicates keep their extract order.

    Adds:
      event_index   0-based position of the event in its session
      is_auto       event is in AUTO_EVENTS
      action_index  1-based count of shopper actions up to and including this
                    event (non-auto events only; NA for auto events)
      ts_tie        event shares its timestamp with another event in the session
    """
    unknown = set(events["event_name"].unique()) - set(EVENT_ORDER)
    if unknown:
        raise ValueError(f"event names missing from EVENT_ORDER: {sorted(unknown)}")

    out = events.assign(
        event_rank=events["event_name"].map({name: i for i, name in enumerate(EVENT_ORDER)})
    )
    out = out.sort_values(["session_id", "event_timestamp", "event_rank"], kind="stable")
    out = out.drop(columns="event_rank").reset_index(drop=True)

    out["event_index"] = out.groupby("session_id").cumcount()
    out["is_auto"] = out["event_name"].isin(AUTO_EVENTS)
    actions = (~out["is_auto"]).astype(int).groupby(out["session_id"]).cumsum()
    out["action_index"] = actions.where(~out["is_auto"]).astype("Int64")
    out["ts_tie"] = out.duplicated(["session_id", "event_timestamp"], keep=False)
    return out


def tie_stats(ordered: pd.DataFrame) -> pd.Series:
    """How often the timestamp tie-break rule is needed."""
    tied_sessions = ordered.loc[ordered["ts_tie"], "session_id"].nunique()
    tied_actions = ordered[ordered["ts_tie"] & ~ordered["is_auto"]]
    action_ties = tied_actions.duplicated(["session_id", "event_timestamp"], keep=False).sum()
    return pd.Series({
        "events in a timestamp tie": ordered["ts_tie"].mean(),
        "sessions with any tie": tied_sessions / ordered["session_id"].nunique(),
        "shopper actions tied with another shopper action": action_ties / (~ordered["is_auto"]).sum(),
    })


def build_sessions(ordered: pd.DataFrame) -> pd.DataFrame:
    """One row per session from the output of order_events.

    Context columns take the session's first value; context_varies flags
    sessions where any of them changes mid-session.
    """
    g = ordered.groupby("session_id", sort=False)

    sessions = g.agg(
        start_ts=("event_timestamp", "min"),
        end_ts=("event_timestamp", "max"),
        n_events=("event_name", "size"),
        engagement_time_msec=("engagement_time_msec", "sum"),
        revenue=("revenue", "sum"),
        **{col: (col, "first") for col in CONTEXT_COLS},
    )
    sessions["context_varies"] = g[CONTEXT_COLS].nunique(dropna=False).gt(1).any(axis=1)

    counts = pd.crosstab(ordered["session_id"], ordered["event_name"])
    counts = counts.reindex(columns=EVENT_ORDER, fill_value=0).add_prefix("n_")
    sessions = sessions.join(counts)
    sessions.insert(3, "n_actions", sessions["n_events"] - counts[[f"n_{e}" for e in AUTO_EVENTS]].sum(axis=1))

    sessions["start_time"] = pd.to_datetime(sessions["start_ts"], unit="us", utc=True)
    sessions["end_time"] = pd.to_datetime(sessions["end_ts"], unit="us", utc=True)
    sessions["duration_s"] = (sessions["end_ts"] - sessions["start_ts"]) / 1e6
    sessions["converted"] = (sessions["n_purchase"] > 0).astype(int)
    return sessions.reset_index()

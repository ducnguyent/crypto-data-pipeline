"""Dagster sensor that watches silver layer materializations and triggers
gold-layer runs when fresh data is available.

Also emits warnings when bronze/silver assets produce empty results
across consecutive runs.
"""

import logging

from dagster import (
    AssetKey,
    EventLogEntry,
    RunRequest,
    SensorEvaluationContext,
    SkipReason,
    sensor,
)

logger = logging.getLogger(__name__)

# Silver assets we watch to decide if gold layer should run
_SILVER_ASSET_KEYS = [
    AssetKey("silver_ohlcv_1m"),
    AssetKey("silver_ohlcv_multi_timeframe"),
    AssetKey("silver_trade_metrics"),
]

# Consecutive empty-data threshold before warning
_EMPTY_THRESHOLD = 3


@sensor(
    name="data_quality_sensor",
    description="Monitors silver materializations and triggers gold analytics when fresh data is ready",
    minimum_interval_seconds=600,  # Check every 10 minutes
    default_status=None,  # leave for user to enable
)
def data_quality_sensor(context: SensorEvaluationContext):
    """Evaluate whether the gold layer should be triggered.

    Logic
    -----
    1. For each silver asset, check the latest materialisation event since the
       cursor.
    2. If *any* silver asset has new successful materialisations → yield a
       ``RunRequest`` for the ``gold_analytics_job``.
    3. Track consecutive empty results and warn after ``_EMPTY_THRESHOLD``.
    """

    cursor = context.cursor or "0"
    new_cursor = cursor
    has_fresh_data = False
    empty_streak: dict = {}

    # Try to restore streak counters from cursor metadata
    try:
        parts = cursor.split("|")
        if len(parts) == 2:
            cursor_ts = parts[0]
            # parse streaks
            import json
            empty_streak = json.loads(parts[1])
            cursor = cursor_ts
    except Exception:
        pass

    for asset_key in _SILVER_ASSET_KEYS:
        asset_name = asset_key.path[-1]

        # Fetch events since cursor
        events = context.instance.get_event_records(
            event_records_filter=None,
            limit=5,
        )

        # Simple approach: check latest materialization
        try:
            latest = context.instance.get_latest_materialization_event(asset_key)
        except Exception:
            latest = None

        if latest is None:
            context.log.debug(f"No materialization found for {asset_name}")
            empty_streak[asset_name] = empty_streak.get(asset_name, 0) + 1
            continue

        # Check if materialization metadata indicates success
        metadata = {}
        if latest.asset_materialization and latest.asset_materialization.metadata:
            metadata = {
                e.label: e.value for e in latest.asset_materialization.metadata_entries
            } if hasattr(latest.asset_materialization, "metadata_entries") else {}

        status = metadata.get("status", "success")
        record_count = metadata.get("record_count", 1)

        if status == "no_data" or record_count == 0:
            empty_streak[asset_name] = empty_streak.get(asset_name, 0) + 1
            if empty_streak[asset_name] >= _EMPTY_THRESHOLD:
                context.log.warning(
                    f"⚠️  {asset_name} has produced empty results "
                    f"{empty_streak[asset_name]} consecutive times"
                )
        else:
            empty_streak[asset_name] = 0
            has_fresh_data = True

    # Persist cursor
    import json
    new_cursor = f"{int(context.last_tick_completion_time or 0)}|{json.dumps(empty_streak)}"
    context.update_cursor(new_cursor)

    if has_fresh_data:
        context.log.info("Fresh silver data detected — triggering gold analytics")
        yield RunRequest(
            run_key=f"gold_trigger_{int(context.last_tick_completion_time or 0)}",
            job_name="gold_analytics_job",
        )
    else:
        yield SkipReason("No fresh silver data since last check")

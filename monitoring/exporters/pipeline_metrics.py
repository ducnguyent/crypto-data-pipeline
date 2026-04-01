"""Custom Prometheus metrics exporter for the crypto data pipeline.

Exposes key pipeline health metrics on port 8000 for Prometheus scraping.
Reads from Hudi table metadata and optional Dagster event log.
"""

import logging
import os
import time
from http.server import HTTPServer

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    generate_latest,
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    start_http_server,
)

logger = logging.getLogger(__name__)

# ============================================================
# Metrics definitions
# ============================================================

REGISTRY = CollectorRegistry()

RECORDS_PROCESSED = Counter(
    "pipeline_records_processed_total",
    "Total records processed by the pipeline",
    ["layer", "asset", "symbol"],
    registry=REGISTRY,
)

LAST_RUN_TS = Gauge(
    "pipeline_last_run_timestamp",
    "Unix timestamp of last successful asset run",
    ["layer", "asset"],
    registry=REGISTRY,
)

QUALITY_SCORE = Gauge(
    "pipeline_data_quality_score",
    "Average data quality score",
    ["layer", "symbol"],
    registry=REGISTRY,
)

PROCESSING_DURATION = Histogram(
    "pipeline_processing_duration_seconds",
    "Duration of asset processing in seconds",
    ["asset"],
    buckets=[5, 15, 30, 60, 120, 300, 600],
    registry=REGISTRY,
)

ERRORS_TOTAL = Counter(
    "pipeline_errors_total",
    "Total pipeline errors",
    ["asset", "error_type"],
    registry=REGISTRY,
)

# Gold-layer specific gauges
GOLD_SHARPE = Gauge(
    "pipeline_gold_sharpe_ratio",
    "Latest Sharpe ratio",
    ["symbol"],
    registry=REGISTRY,
)

GOLD_MAX_DRAWDOWN = Gauge(
    "pipeline_gold_max_drawdown",
    "Latest max drawdown",
    ["symbol"],
    registry=REGISTRY,
)

GOLD_VAR95 = Gauge(
    "pipeline_gold_var_95",
    "Latest 95% VaR",
    ["symbol"],
    registry=REGISTRY,
)

GOLD_SIGNAL_SCORE = Gauge(
    "pipeline_gold_signal_score",
    "Latest composite signal score",
    ["symbol"],
    registry=REGISTRY,
)

GOLD_SIGNAL_COUNT = Gauge(
    "pipeline_gold_signal_count",
    "Count of latest signals by type",
    ["signal"],
    registry=REGISTRY,
)

GOLD_CORRELATION = Gauge(
    "pipeline_gold_correlation",
    "Pairwise correlation coefficient",
    ["symbol_1", "symbol_2"],
    registry=REGISTRY,
)

GOLD_VOLATILITY = Gauge(
    "pipeline_gold_realised_volatility",
    "Realised annualised volatility",
    ["symbol"],
    registry=REGISTRY,
)


# ============================================================
# Metric update helpers (called by Dagster assets or cron)
# ============================================================

def record_asset_run(
    layer: str,
    asset: str,
    symbol: str,
    record_count: int,
    duration_seconds: float,
    quality_score: float = 1.0,
):
    """Record a successful asset run."""
    RECORDS_PROCESSED.labels(layer=layer, asset=asset, symbol=symbol).inc(record_count)
    LAST_RUN_TS.labels(layer=layer, asset=asset).set(time.time())
    QUALITY_SCORE.labels(layer=layer, symbol=symbol).set(quality_score)
    PROCESSING_DURATION.labels(asset=asset).observe(duration_seconds)


def record_error(asset: str, error_type: str):
    """Increment an error counter."""
    ERRORS_TOTAL.labels(asset=asset, error_type=error_type).inc()


def update_gold_metrics(
    symbol: str,
    sharpe: float = None,
    max_drawdown: float = None,
    var_95: float = None,
    signal_score: float = None,
    volatility: float = None,
):
    """Push gold-layer analytics values."""
    if sharpe is not None:
        GOLD_SHARPE.labels(symbol=symbol).set(sharpe)
    if max_drawdown is not None:
        GOLD_MAX_DRAWDOWN.labels(symbol=symbol).set(max_drawdown)
    if var_95 is not None:
        GOLD_VAR95.labels(symbol=symbol).set(var_95)
    if signal_score is not None:
        GOLD_SIGNAL_SCORE.labels(symbol=symbol).set(signal_score)
    if volatility is not None:
        GOLD_VOLATILITY.labels(symbol=symbol).set(volatility)


def update_correlation(symbol_1: str, symbol_2: str, value: float):
    """Push a pairwise correlation value."""
    GOLD_CORRELATION.labels(symbol_1=symbol_1, symbol_2=symbol_2).set(value)


# ============================================================
# Standalone server
# ============================================================

def main():
    """Run a standalone HTTP metrics server on port 8000."""
    port = int(os.getenv("METRICS_PORT", "8000"))
    logger.info("Starting pipeline metrics exporter on port %d", port)

    start_http_server(port, registry=REGISTRY)

    # Keep alive — metrics are pushed in-process by Dagster assets
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        logger.info("Exporter shutting down")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

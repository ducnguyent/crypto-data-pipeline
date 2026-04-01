import logging
from dagster import (
    Definitions,
    ScheduleDefinition,
    define_asset_job,
    AssetSelection
)

from .assets.bronze_assets import (
    bronze_trade_data,
    bronze_ticker_data,
    bronze_kline_data,
    bronze_depth_data,
)
from .assets.silver_assets import (
    silver_ohlcv_1m,
    silver_ohlcv_multi_timeframe,
    silver_trade_metrics,
)
from .assets.gold_assets import (
    gold_portfolio_metrics,
    gold_market_correlation,
    gold_trading_signals,
    gold_risk_metrics,
)
from .assets.quality_assets import data_quality_report
from .sensors.data_quality_sensor import data_quality_sensor

logger = logging.getLogger(__name__)

# ========================================
# Jobs
# ========================================

bronze_ingestion_job = define_asset_job(
    name="bronze_ingestion_job",
    description="Ingest raw data from Kafka to bronze Hudi tables",
    selection=AssetSelection.groups("bronze_layer")
)

silver_processing_job = define_asset_job(
    name="silver_processing_job",
    description="Process bronze data into clean silver layer with indicators",
    selection=AssetSelection.groups("silver_layer")
)

gold_analytics_job = define_asset_job(
    name="gold_analytics_job",
    description="Generate analytics and business insights from silver data",
    selection=AssetSelection.groups("gold_layer")
)

quality_report_job = define_asset_job(
    name="quality_report_job",
    description="Run cross-layer data quality checks",
    selection=AssetSelection.groups("quality_layer")
)

# ========================================
# Schedules
# ========================================

bronze_schedule = ScheduleDefinition(
    job=bronze_ingestion_job,
    cron_schedule="*/10 * * * *",  # Every 10 minutes
    name="bronze_ingestion_schedule"
)

silver_schedule = ScheduleDefinition(
    job=silver_processing_job,
    cron_schedule="*/30 * * * *",  # Every 30 minutes
    name="silver_processing_schedule"
)

gold_schedule = ScheduleDefinition(
    job=gold_analytics_job,
    cron_schedule="0 */6 * * *",  # Every 6 hours
    name="gold_analytics_schedule"
)

gold_correlation_schedule = ScheduleDefinition(
    job=gold_analytics_job,
    cron_schedule="0 3 * * 0",  # Weekly on Sunday at 3 AM
    name="gold_correlation_weekly_schedule"
)

quality_schedule = ScheduleDefinition(
    job=quality_report_job,
    cron_schedule="0 */4 * * *",  # Every 4 hours
    name="quality_report_schedule"
)

# ========================================
# Definitions
# ========================================

defs = Definitions(
    assets=[
        # Bronze layer
        bronze_trade_data,
        bronze_ticker_data,
        bronze_kline_data,
        bronze_depth_data,
        # Silver layer
        silver_ohlcv_1m,
        silver_ohlcv_multi_timeframe,
        silver_trade_metrics,
        # Gold layer
        gold_portfolio_metrics,
        gold_market_correlation,
        gold_trading_signals,
        gold_risk_metrics,
        # Quality layer
        data_quality_report,
    ],
    jobs=[
        bronze_ingestion_job,
        silver_processing_job,
        gold_analytics_job,
        quality_report_job,
    ],
    schedules=[
        bronze_schedule,
        silver_schedule,
        gold_schedule,
        gold_correlation_schedule,
        quality_schedule,
    ],
    sensors=[
        data_quality_sensor,
    ],
)

import logging
from dagster import (
    Definitions,
    ScheduleDefinition,
    DefaultSensorStatus,
    define_asset_job,
    AssetSelection
)

from .assets.bronze_assets import bronze_trade_data, bronze_ticker_data, bronze_kline_data
from .assets.silver_assets import silver_ohlcv_1m, silver_trade_metrics
from .assets.gold_assets import gold_portfolio_metrics, gold_bigquery_sync

logger = logging.getLogger(__name__)

# Define asset jobs
bronze_ingestion_job = define_asset_job(
    name="bronze_ingestion_job",
    description="Ingest raw data from Kafka to bronze Hudi tables",
    selection=AssetSelection.groups("bronze_layer")
)

silver_processing_job = define_asset_job(
    name="silver_processing_job",
    description="Process bronze data into clean silver layer",
    selection=AssetSelection.groups("silver_layer")
)

gold_analytics_job = define_asset_job(
    name="gold_analytics_job",
    description="Generate analytics and business insights",
    selection=AssetSelection.groups("gold_layer")
)

# Define schedules
bronze_schedule = ScheduleDefinition(
    job=bronze_ingestion_job,
    cron_schedule="*/10 * * * *",  # Every 10 minutes
    name="bronze_ingestion_schedule"
)

silver_schedule = ScheduleDefinition(
    job=silver_processing_job,
    cron_schedule="0 */6 * * *",  # Every 6 hours
    name="silver_processing_schedule"
)

gold_schedule = ScheduleDefinition(
    job=gold_analytics_job,
    cron_schedule="0 2 * * *",  # Daily at 2 AM
    name="gold_analytics_schedule"
)

# Main definitions
defs = Definitions(
    assets=[
        # Bronze layer
        bronze_trade_data,
        bronze_ticker_data,
        bronze_kline_data,
        # Silver layer (placeholders)
        silver_ohlcv_1m,
        silver_trade_metrics,
        # Gold layer (placeholders)
        gold_portfolio_metrics,
        gold_bigquery_sync
    ],
    jobs=[
        bronze_ingestion_job,
        silver_processing_job,
        gold_analytics_job
    ],
    schedules=[
        bronze_schedule,
        silver_schedule,
        gold_schedule
    ]
)

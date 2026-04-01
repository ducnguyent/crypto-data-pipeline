import logging
from dagster import asset, Config, OpExecutionContext
from pyspark.sql import DataFrame
from pyspark.sql.functions import *
from pyspark.sql.types import *

from ..utils.spark_utils import get_spark_session, get_hudi_write_config

logger = logging.getLogger(__name__)


class BronzeAssetConfig(Config):
    """Configuration for bronze layer assets"""
    symbol: str = "BTCUSDT"
    batch_size: int = 1000


# ========================================
# Schemas
# ========================================

def get_bronze_trade_schema() -> StructType:
    """Define schema for bronze trade data"""
    return StructType([
        StructField("record_id", StringType(), False),
        StructField("symbol", StringType(), False),
        StructField("stream_type", StringType(), False),
        StructField("event_time", LongType(), False),
        StructField("received_time", LongType(), False),
        StructField("date", StringType(), False),
        StructField("raw_data", StringType(), True),
        StructField("data_quality_score", DoubleType(), True),
        StructField("price", DoubleType(), True),
        StructField("quantity", DoubleType(), True),
        StructField("trade_id", LongType(), True),
        StructField("is_buyer_maker", BooleanType(), True),
    ])


def get_bronze_ticker_schema() -> StructType:
    """Define schema for bronze ticker data"""
    return StructType([
        StructField("record_id", StringType(), False),
        StructField("symbol", StringType(), False),
        StructField("stream_type", StringType(), False),
        StructField("event_time", LongType(), False),
        StructField("received_time", LongType(), False),
        StructField("date", StringType(), False),
        StructField("raw_data", StringType(), True),
        StructField("data_quality_score", DoubleType(), True),
        StructField("price_change", DoubleType(), True),
        StructField("price_change_percent", DoubleType(), True),
        StructField("last_price", DoubleType(), True),
        StructField("volume", DoubleType(), True),
        StructField("quote_volume", DoubleType(), True),
    ])


def get_bronze_kline_schema() -> StructType:
    """Define schema for bronze kline (candlestick) data"""
    return StructType([
        StructField("record_id", StringType(), False),
        StructField("symbol", StringType(), False),
        StructField("stream_type", StringType(), False),
        StructField("event_time", LongType(), False),
        StructField("received_time", LongType(), False),
        StructField("date", StringType(), False),
        StructField("raw_data", StringType(), True),
        StructField("data_quality_score", DoubleType(), True),
        StructField("interval", StringType(), True),
        StructField("open", DoubleType(), True),
        StructField("high", DoubleType(), True),
        StructField("low", DoubleType(), True),
        StructField("close", DoubleType(), True),
        StructField("volume", DoubleType(), True),
        StructField("is_closed", BooleanType(), True),
    ])


def get_bronze_depth_schema() -> StructType:
    """Define schema for bronze depth (order book) data"""
    return StructType([
        StructField("record_id", StringType(), False),
        StructField("symbol", StringType(), False),
        StructField("stream_type", StringType(), False),
        StructField("event_time", LongType(), False),
        StructField("received_time", LongType(), False),
        StructField("date", StringType(), False),
        StructField("raw_data", StringType(), True),
        StructField("data_quality_score", DoubleType(), True),
        StructField("bids", StringType(), True),
        StructField("asks", StringType(), True),
        StructField("bid_count", IntegerType(), True),
        StructField("ask_count", IntegerType(), True),
        StructField("best_bid", DoubleType(), True),
        StructField("best_ask", DoubleType(), True),
        StructField("spread", DoubleType(), True),
    ])


# ========================================
# Shared helpers
# ========================================

def _ingest_from_kafka(
    context: OpExecutionContext,
    config: BronzeAssetConfig,
    topic_suffix: str,
    schema: StructType,
    table_prefix: str,
) -> dict:
    """Generic Kafka → Hudi ingestion for bronze layer.

    Returns a metadata dict with status, table_name and record_count.
    """
    spark = get_spark_session(f"Bronze{table_prefix.title()}Ingestion")

    try:
        topic = f"crypto_raw_{config.symbol.lower()}_{topic_suffix}"
        context.log.info(f"Reading from topic {topic}")

        df = (
            spark.read
            .format("kafka")
            .option("kafka.bootstrap.servers", "kafka:29092")
            .option("subscribe", topic)
            .option("startingOffsets", "earliest")
            .option("endingOffsets", "latest")
            .load()
        )

        if df.count() == 0:
            context.log.info(f"No new data found in topic {topic}")
            return {"status": "no_data", "topic": topic}

        # Parse Kafka value as JSON with the provided schema
        parsed_df = df.select(
            from_json(col("value").cast("string"), schema).alias("data"),
            col("timestamp").alias("kafka_timestamp"),
        ).select("data.*", "kafka_timestamp")

        # Filter out null records from parse failures
        parsed_df = parsed_df.filter(col("record_id").isNotNull())

        # Add time-based partitioning columns
        enriched_df = (
            parsed_df
            .withColumn("year", year(from_unixtime(col("event_time") / 1000)))
            .withColumn("month", month(from_unixtime(col("event_time") / 1000)))
            .withColumn("day", dayofmonth(from_unixtime(col("event_time") / 1000)))
        )

        # Write to Hudi
        table_name = f"bronze_{table_prefix}_{config.symbol.lower()}"
        table_path = f"s3a://datalake/bronze/{table_name}"

        hudi_options = get_hudi_write_config(table_name, "upsert")

        enriched_df.write \
            .format("hudi") \
            .options(**hudi_options) \
            .mode("append") \
            .save(table_path)

        record_count = enriched_df.count()
        context.log.info(f"Wrote {record_count} records to {table_name}")

        return {
            "status": "success",
            "table_name": table_name,
            "record_count": record_count,
            "symbol": config.symbol,
        }

    except Exception as e:
        context.log.error(f"Error processing bronze {table_prefix} data: {e}")
        raise
    finally:
        spark.stop()


# ========================================
# Assets
# ========================================

@asset(
    name="bronze_trade_data",
    description="Raw trade data from Kafka streams ingested into bronze Hudi tables",
    group_name="bronze_layer",
    compute_kind="spark",
)
def bronze_trade_data(context: OpExecutionContext, config: BronzeAssetConfig):
    """Ingest trade data from Kafka to bronze Hudi tables"""
    return _ingest_from_kafka(
        context, config,
        topic_suffix="trade",
        schema=get_bronze_trade_schema(),
        table_prefix="trade",
    )


@asset(
    name="bronze_ticker_data",
    description="Raw 24hr ticker data from Kafka streams ingested into bronze Hudi tables",
    group_name="bronze_layer",
    compute_kind="spark",
)
def bronze_ticker_data(context: OpExecutionContext, config: BronzeAssetConfig):
    """Ingest ticker data from Kafka to bronze Hudi tables"""
    return _ingest_from_kafka(
        context, config,
        topic_suffix="24hrTicker",
        schema=get_bronze_ticker_schema(),
        table_prefix="ticker",
    )


@asset(
    name="bronze_kline_data",
    description="Raw kline (candlestick) data from Kafka streams ingested into bronze Hudi tables",
    group_name="bronze_layer",
    compute_kind="spark",
)
def bronze_kline_data(context: OpExecutionContext, config: BronzeAssetConfig):
    """Ingest kline data from Kafka to bronze Hudi tables"""
    return _ingest_from_kafka(
        context, config,
        topic_suffix="kline",
        schema=get_bronze_kline_schema(),
        table_prefix="kline",
    )


@asset(
    name="bronze_depth_data",
    description="Raw order-book depth snapshots from Kafka streams ingested into bronze Hudi tables",
    group_name="bronze_layer",
    compute_kind="spark",
)
def bronze_depth_data(context: OpExecutionContext, config: BronzeAssetConfig):
    """Ingest depth data from Kafka to bronze Hudi tables"""
    return _ingest_from_kafka(
        context, config,
        topic_suffix="depthUpdate",
        schema=get_bronze_depth_schema(),
        table_prefix="depth",
    )

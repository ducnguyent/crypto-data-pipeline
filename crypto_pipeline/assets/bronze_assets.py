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


def get_bronze_schema() -> StructType:
    """Define schema for bronze layer data"""
    return StructType([
        StructField("record_id", StringType(), False),
        StructField("symbol", StringType(), False),
        StructField("stream_type", StringType(), False),
        StructField("event_time", LongType(), False),
        StructField("received_time", LongType(), False),
        StructField("date", StringType(), False),
        StructField("raw_data", StringType(), True),
        StructField("data_quality_score", DoubleType(), True)
    ])


@asset(
    name="bronze_trade_data",
    description="Raw trade data from Kafka streams ingested into bronze Hudi tables",
    group_name="bronze_layer",
    compute_kind="spark"
)
def bronze_trade_data(context: OpExecutionContext, config: BronzeAssetConfig):
    """Ingest trade data from Kafka to bronze Hudi tables"""

    spark = get_spark_session("BronzeTradeIngestion")

    try:
        context.log.info(f"Processing bronze trade data for {config.symbol}")

        # Read from Kafka (batch processing for now)
        topic = f"crypto_raw_{config.symbol.lower()}_trade"

        df = spark \
            .read \
            .format("kafka") \
            .option("kafka.bootstrap.servers", "kafka:29092") \
            .option("subscribe", topic) \
            .option("startingOffsets", "earliest") \
            .option("endingOffsets", "latest") \
            .load()

        if df.count() == 0:
            context.log.info(f"No new data found in topic {topic}")
            return {"status": "no_data", "topic": topic}

        # Parse Kafka messages
        parsed_df = df.select(
            from_json(col("value").cast("string"),
                      get_bronze_schema()).alias("data"),
            col("timestamp").alias("kafka_timestamp")
        ).select("data.*", "kafka_timestamp")

        # Add partitioning columns
        enriched_df = parsed_df \
            .withColumn("year", year(from_unixtime(col("event_time") / 1000))) \
            .withColumn("month", month(from_unixtime(col("event_time") / 1000))) \
            .withColumn("day", dayofmonth(from_unixtime(col("event_time") / 1000)))

        # Write to Hudi table
        table_name = f"bronze_trade_{config.symbol.lower()}"
        table_path = f"s3a://datalake/bronze/{table_name}"

        hudi_options = get_hudi_write_config(table_name, "upsert")

        enriched_df.write \
            .format("hudi") \
            .options(**hudi_options) \
            .mode("append") \
            .save(table_path)

        record_count = enriched_df.count()
        context.log.info(
            f"Successfully wrote {record_count} records to {table_name}")

        return {
            "status": "success",
            "table_name": table_name,
            "record_count": record_count,
            "symbol": config.symbol
        }

    except Exception as e:
        context.log.error(f"Error processing bronze trade data: {e}")
        raise
    finally:
        spark.stop()


@asset(
    name="bronze_ticker_data",
    description="Raw ticker data from Kafka streams",
    group_name="bronze_layer",
    compute_kind="spark"
)
def bronze_ticker_data(context: OpExecutionContext, config: BronzeAssetConfig):
    """Ingest ticker data from Kafka to bronze Hudi tables"""

    context.log.info(f"Processing bronze ticker data for {config.symbol}")

    # Similar implementation to bronze_trade_data but for ticker stream
    # This is a placeholder - full implementation would be similar to above

    return {
        "status": "placeholder",
        "table_name": f"bronze_ticker_{config.symbol.lower()}",
        "symbol": config.symbol,
        "stream_type": "ticker"
    }


@asset(
    name="bronze_kline_data",
    description="Raw kline data from Kafka streams",
    group_name="bronze_layer",
    compute_kind="spark"
)
def bronze_kline_data(context: OpExecutionContext, config: BronzeAssetConfig):
    """Ingest kline data from Kafka to bronze Hudi tables"""

    context.log.info(f"Processing bronze kline data for {config.symbol}")

    # Placeholder for kline data processing
    return {
        "status": "placeholder",
        "table_name": f"bronze_kline_{config.symbol.lower()}",
        "symbol": config.symbol,
        "stream_type": "kline_1m"
    }

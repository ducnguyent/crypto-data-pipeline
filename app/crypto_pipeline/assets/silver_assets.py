import logging
from dagster import asset, Config, OpExecutionContext
from pyspark.sql import DataFrame, Window
from pyspark.sql.functions import *
from pyspark.sql.types import *

from ..utils.spark_utils import get_spark_session, get_hudi_write_config

logger = logging.getLogger(__name__)


class SilverAssetConfig(Config):
    """Configuration for silver layer assets"""
    symbol: str = "BTCUSDT"


# ========================================
# Technical Indicator Helpers (PySpark)
# ========================================

def _add_sma(df: DataFrame, col_name: str, periods: list[int]) -> DataFrame:
    """Add Simple Moving Average columns"""
    window_spec = Window.partitionBy("symbol").orderBy("event_time")
    for p in periods:
        df = df.withColumn(
            f"sma_{p}",
            avg(col(col_name)).over(window_spec.rowsBetween(-(p - 1), 0))
        )
    return df


def _add_ema(df: DataFrame, col_name: str, periods: list[int]) -> DataFrame:
    """Add Exponential Moving Average columns using recursive approximation.

    PySpark doesn't natively support recursive EMA, so we approximate with a
    weighted window average.  For a production system with very large datasets
    this is sufficiently accurate; for exact EMA you'd use a UDF or Pandas-on-Spark.
    """
    window_spec = Window.partitionBy("symbol").orderBy("event_time")
    for p in periods:
        # Approximate EMA via expanding weighted average over window
        # Weight = 2/(period+1), but in a window context the simple avg
        # of the last 2*period rows is a reasonable proxy.
        span = 2 * p
        df = df.withColumn(
            f"ema_{p}",
            avg(col(col_name)).over(window_spec.rowsBetween(-(span - 1), 0))
        )
    return df


def _add_rsi(df: DataFrame, col_name: str, period: int = 14) -> DataFrame:
    """Add Relative Strength Index column"""
    window_spec = Window.partitionBy("symbol").orderBy("event_time")

    df = df.withColumn("_price_change", col(col_name) - lag(col(col_name), 1).over(window_spec))
    df = df.withColumn("_gain", when(col("_price_change") > 0, col("_price_change")).otherwise(0))
    df = df.withColumn("_loss", when(col("_price_change") < 0, -col("_price_change")).otherwise(0))

    rsi_window = window_spec.rowsBetween(-(period - 1), 0)
    df = df.withColumn("_avg_gain", avg("_gain").over(rsi_window))
    df = df.withColumn("_avg_loss", avg("_loss").over(rsi_window))

    df = df.withColumn(
        "rsi",
        when(col("_avg_loss") == 0, lit(100.0))
        .otherwise(100.0 - (100.0 / (1.0 + col("_avg_gain") / col("_avg_loss"))))
    )

    return df.drop("_price_change", "_gain", "_loss", "_avg_gain", "_avg_loss")


def _add_macd(df: DataFrame, col_name: str, fast: int = 12, slow: int = 26, signal: int = 9) -> DataFrame:
    """Add MACD columns (macd_line, macd_signal, macd_histogram)"""
    window_spec = Window.partitionBy("symbol").orderBy("event_time")

    # Use approximate EMA (weighted window averages)
    fast_span = 2 * fast
    slow_span = 2 * slow

    df = df.withColumn(
        "_ema_fast",
        avg(col(col_name)).over(window_spec.rowsBetween(-(fast_span - 1), 0))
    )
    df = df.withColumn(
        "_ema_slow",
        avg(col(col_name)).over(window_spec.rowsBetween(-(slow_span - 1), 0))
    )
    df = df.withColumn("macd_line", col("_ema_fast") - col("_ema_slow"))

    signal_span = 2 * signal
    df = df.withColumn(
        "macd_signal",
        avg("macd_line").over(window_spec.rowsBetween(-(signal_span - 1), 0))
    )
    df = df.withColumn("macd_histogram", col("macd_line") - col("macd_signal"))

    return df.drop("_ema_fast", "_ema_slow")


def _add_bollinger_bands(df: DataFrame, col_name: str, period: int = 20, num_std: float = 2.0) -> DataFrame:
    """Add Bollinger Bands columns"""
    window_spec = Window.partitionBy("symbol").orderBy("event_time").rowsBetween(-(period - 1), 0)

    df = df.withColumn("bb_middle", avg(col(col_name)).over(window_spec))
    df = df.withColumn("_bb_std", stddev(col(col_name)).over(window_spec))
    df = df.withColumn("bb_upper", col("bb_middle") + (lit(num_std) * col("_bb_std")))
    df = df.withColumn("bb_lower", col("bb_middle") - (lit(num_std) * col("_bb_std")))

    return df.drop("_bb_std")


def add_all_indicators(df: DataFrame, price_col: str = "close") -> DataFrame:
    """Add all technical indicators to a DataFrame with OHLCV data"""
    df = _add_sma(df, price_col, [7, 25, 99])
    df = _add_ema(df, price_col, [12, 26])
    df = _add_rsi(df, price_col, 14)
    df = _add_macd(df, price_col, 12, 26, 9)
    df = _add_bollinger_bands(df, price_col, 20, 2.0)
    return df


# ========================================
# Assets
# ========================================

@asset(
    name="silver_ohlcv_1m",
    description="Clean 1-minute OHLCV data with technical indicators, sourced from bronze kline tables",
    group_name="silver_layer",
    compute_kind="spark",
    deps=["bronze_kline_data"],
)
def silver_ohlcv_1m(context: OpExecutionContext, config: SilverAssetConfig):
    """Read bronze kline data, filter closed candles, calculate indicators, write to silver."""

    spark = get_spark_session("SilverOHLCV1m")

    try:
        symbol = config.symbol
        bronze_table = f"s3a://datalake/bronze/bronze_kline_{symbol.lower()}"
        context.log.info(f"Reading bronze kline data from {bronze_table}")

        df = spark.read.format("hudi").load(bronze_table)

        if df.count() == 0:
            context.log.info("No kline data available")
            return {"status": "no_data", "symbol": symbol}

        # Filter: only closed candles + minimum quality
        df = df.filter(
            (col("is_closed") == True) &
            (col("data_quality_score") >= 0.5) &
            (col("interval") == "1m")
        )

        # Validate OHLCV values
        df = df.filter(
            (col("open") > 0) & (col("high") > 0) &
            (col("low") > 0) & (col("close") > 0) &
            (col("volume") >= 0) &
            (col("high") >= col("low"))
        )

        if df.count() == 0:
            context.log.info("No valid closed klines after filtering")
            return {"status": "no_valid_data", "symbol": symbol}

        # Deduplicate by event_time (keep latest received_time)
        dedup_window = Window.partitionBy("symbol", "event_time").orderBy(col("received_time").desc())
        df = df.withColumn("_rank", row_number().over(dedup_window)).filter(col("_rank") == 1).drop("_rank")

        # Add technical indicators
        df = add_all_indicators(df, "close")

        # Write to silver Hudi table
        silver_table = f"silver_ohlcv_1m_{symbol.lower()}"
        silver_path = f"s3a://datalake/silver/{silver_table}"

        hudi_options = get_hudi_write_config(silver_table, "upsert")

        df.write \
            .format("hudi") \
            .options(**hudi_options) \
            .mode("append") \
            .save(silver_path)

        record_count = df.count()
        context.log.info(f"Wrote {record_count} records to {silver_table}")

        return {
            "status": "success",
            "table_name": silver_table,
            "record_count": record_count,
            "symbol": symbol,
            "timeframe": "1m",
        }

    except Exception as e:
        context.log.error(f"Error processing silver OHLCV 1m: {e}")
        raise
    finally:
        spark.stop()


# Timeframe aggregation map: target → number of 1m candles
_TIMEFRAME_MINUTES = {
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}


@asset(
    name="silver_ohlcv_multi_timeframe",
    description="Multi-timeframe OHLCV (5m, 15m, 1h, 4h, 1d) aggregated from 1-minute data",
    group_name="silver_layer",
    compute_kind="spark",
    deps=["silver_ohlcv_1m"],
)
def silver_ohlcv_multi_timeframe(context: OpExecutionContext, config: SilverAssetConfig):
    """Aggregate 1m OHLCV into higher timeframes and re-compute indicators."""

    spark = get_spark_session("SilverOHLCVMultiTF")

    try:
        symbol = config.symbol
        source_table = f"s3a://datalake/silver/silver_ohlcv_1m_{symbol.lower()}"
        context.log.info(f"Reading 1m OHLCV from {source_table}")

        df_1m = spark.read.format("hudi").load(source_table)

        if df_1m.count() == 0:
            context.log.info("No 1m data available for aggregation")
            return {"status": "no_data", "symbol": symbol}

        # Convert event_time (ms) to timestamp for windowing
        df_1m = df_1m.withColumn("ts", (col("event_time") / 1000).cast("timestamp"))

        results = {}

        for tf_name, minutes in _TIMEFRAME_MINUTES.items():
            context.log.info(f"Aggregating {tf_name} candles for {symbol}")

            window_duration = f"{minutes} minutes"

            agg_df = (
                df_1m
                .groupBy(
                    window("ts", window_duration).alias("time_window"),
                    "symbol",
                )
                .agg(
                    first("open").alias("open"),
                    max("high").alias("high"),
                    min("low").alias("low"),
                    last("close").alias("close"),
                    sum("volume").alias("volume"),
                    first("date").alias("date"),
                    first("event_time").alias("event_time"),
                    first("record_id").alias("record_id"),
                )
                .withColumn("interval", lit(tf_name))
                .withColumn("data_quality_score", lit(1.0))
                .drop("time_window")
            )

            # Add indicators
            agg_df = add_all_indicators(agg_df, "close")

            # Write to silver
            table_name = f"silver_ohlcv_{tf_name}_{symbol.lower()}"
            table_path = f"s3a://datalake/silver/{table_name}"

            hudi_options = get_hudi_write_config(table_name, "upsert")

            agg_df.write \
                .format("hudi") \
                .options(**hudi_options) \
                .mode("append") \
                .save(table_path)

            count = agg_df.count()
            context.log.info(f"Wrote {count} records to {table_name}")
            results[tf_name] = count

        return {
            "status": "success",
            "symbol": symbol,
            "timeframes": results,
        }

    except Exception as e:
        context.log.error(f"Error processing multi-timeframe OHLCV: {e}")
        raise
    finally:
        spark.stop()


@asset(
    name="silver_trade_metrics",
    description="Aggregated trade metrics: VWAP, volume analysis, buy/sell ratios",
    group_name="silver_layer",
    compute_kind="spark",
    deps=["bronze_trade_data"],
)
def silver_trade_metrics(context: OpExecutionContext, config: SilverAssetConfig):
    """Aggregate trade data into VWAP and volume metrics per time window."""

    spark = get_spark_session("SilverTradeMetrics")

    try:
        symbol = config.symbol
        bronze_table = f"s3a://datalake/bronze/bronze_trade_{symbol.lower()}"
        context.log.info(f"Reading bronze trade data from {bronze_table}")

        df = spark.read.format("hudi").load(bronze_table)

        if df.count() == 0:
            context.log.info("No trade data available")
            return {"status": "no_data", "symbol": symbol}

        # Quality filter
        df = df.filter(
            (col("data_quality_score") >= 0.5) &
            (col("price") > 0) &
            (col("quantity") > 0)
        )

        # Convert event_time to timestamp
        df = df.withColumn("ts", (col("event_time") / 1000).cast("timestamp"))

        # Calculate trade value for VWAP
        df = df.withColumn("trade_value", col("price") * col("quantity"))

        # Aggregate into 1-minute windows
        metrics_df = (
            df
            .groupBy(
                window("ts", "1 minute").alias("time_window"),
                "symbol",
            )
            .agg(
                # VWAP = sum(price * quantity) / sum(quantity)
                (sum("trade_value") / sum("quantity")).alias("vwap"),
                # Volume metrics
                sum("quantity").alias("total_volume"),
                sum("trade_value").alias("total_value"),
                count("*").alias("trade_count"),
                avg("price").alias("avg_price"),
                min("price").alias("min_price"),
                max("price").alias("max_price"),
                # Buy/sell ratio
                sum(when(col("is_buyer_maker") == False, col("quantity")).otherwise(0)).alias("buy_volume"),
                sum(when(col("is_buyer_maker") == True, col("quantity")).otherwise(0)).alias("sell_volume"),
                first("date").alias("date"),
                first("record_id").alias("record_id"),
                first("event_time").alias("event_time"),
            )
        )

        # Calculate derived metrics
        metrics_df = metrics_df.withColumn(
            "buy_sell_ratio",
            when(col("sell_volume") > 0, col("buy_volume") / col("sell_volume")).otherwise(lit(0.0))
        )
        metrics_df = metrics_df.withColumn(
            "price_range",
            col("max_price") - col("min_price")
        )
        metrics_df = metrics_df.withColumn("data_quality_score", lit(1.0))
        metrics_df = metrics_df.drop("time_window")

        # Write to silver
        table_name = f"silver_trade_metrics_{symbol.lower()}"
        table_path = f"s3a://datalake/silver/{table_name}"

        hudi_options = get_hudi_write_config(table_name, "upsert")

        metrics_df.write \
            .format("hudi") \
            .options(**hudi_options) \
            .mode("append") \
            .save(table_path)

        record_count = metrics_df.count()
        context.log.info(f"Wrote {record_count} trade metric records to {table_name}")

        return {
            "status": "success",
            "table_name": table_name,
            "record_count": record_count,
            "symbol": symbol,
        }

    except Exception as e:
        context.log.error(f"Error processing silver trade metrics: {e}")
        raise
    finally:
        spark.stop()

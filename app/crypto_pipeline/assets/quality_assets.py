"""Data quality assets — cross-layer quality reporting.

Produces a quality report that scores completeness, freshness, validity,
and cross-stream consistency for every configured symbol.
"""

import logging
import time
from typing import Dict, List

from dagster import asset, Config, OpExecutionContext
from pyspark.sql import DataFrame
from pyspark.sql.functions import (
    avg,
    col,
    count,
    lit,
    max as spark_max,
    min as spark_min,
    when,
)

from ..utils.spark_utils import get_spark_session, get_hudi_write_config
from ..utils.gold_utils import read_silver_table

logger = logging.getLogger(__name__)


class QualityAssetConfig(Config):
    """Configuration for data quality reports"""
    symbols: str = "BTCUSDT,ETHUSDT"
    quality_threshold: float = 0.5  # minimum acceptable quality score

    @property
    def symbol_list(self) -> List[str]:
        return [s.strip().upper() for s in self.symbols.split(",") if s.strip()]


# Bronze table prefixes we expect per symbol
_BRONZE_TABLES = ["bronze_trade", "bronze_kline", "bronze_ticker", "bronze_depth"]
# Silver table prefixes we expect per symbol
_SILVER_TABLES = ["silver_ohlcv_1m", "silver_trade_metrics"]


def _check_table(
    spark,
    table_prefix: str,
    symbol: str,
    layer: str,
) -> Dict:
    """Read a Hudi table and return quality stats."""
    path = f"s3a://datalake/{layer}/{table_prefix}_{symbol.lower()}"
    now_ms = int(time.time() * 1000)

    try:
        df = spark.read.format("hudi").load(path)
        total = df.count()
        if total == 0:
            return {
                "table": table_prefix,
                "symbol": symbol,
                "record_count": 0,
                "completeness": 0.0,
                "freshness_ms": None,
                "avg_quality_score": 0.0,
                "valid_pct": 0.0,
                "status": "empty",
            }

        stats = df.select(
            count("*").alias("total"),
            spark_max("event_time").alias("latest_event"),
            avg("data_quality_score").alias("avg_qs"),
            count(when(col("data_quality_score") >= 0.5, True)).alias("valid_count"),
        ).first()

        latest_event = int(stats["latest_event"]) if stats["latest_event"] else 0
        freshness_ms = now_ms - latest_event if latest_event > 0 else None
        total_count = int(stats["total"])
        avg_qs = float(stats["avg_qs"]) if stats["avg_qs"] is not None else 0.0
        valid_count = int(stats["valid_count"])

        return {
            "table": table_prefix,
            "symbol": symbol,
            "record_count": total_count,
            "completeness": 1.0 if total_count > 0 else 0.0,
            "freshness_ms": freshness_ms,
            "avg_quality_score": round(avg_qs, 4),
            "valid_pct": round(valid_count / total_count, 4) if total_count > 0 else 0.0,
            "status": "ok",
        }

    except Exception as exc:
        logger.warning("Could not check %s: %s", path, exc)
        return {
            "table": table_prefix,
            "symbol": symbol,
            "record_count": 0,
            "completeness": 0.0,
            "freshness_ms": None,
            "avg_quality_score": 0.0,
            "valid_pct": 0.0,
            "status": f"error: {exc}",
        }


def _cross_stream_check(spark, symbol: str) -> Dict:
    """Validate that trade prices fall within kline OHLC range.

    Returns a consistency score between 0 and 1.
    """
    trade_df = read_silver_table(spark, "silver_trade_metrics", symbol)
    kline_df = read_silver_table(spark, "silver_ohlcv_1m", symbol)

    if trade_df is None or kline_df is None:
        return {"symbol": symbol, "cross_stream_consistency": None, "status": "insufficient_data"}

    # Join on closest event_time
    trades = trade_df.select(
        col("event_time").alias("t_et"),
        col("avg_price"),
    )
    klines = kline_df.select(
        col("event_time").alias("k_et"),
        col("high"),
        col("low"),
    )

    # Simple: join where trade event_time == kline event_time
    joined = trades.join(klines, trades["t_et"] == klines["k_et"], "inner")
    if joined.count() == 0:
        return {"symbol": symbol, "cross_stream_consistency": None, "status": "no_overlap"}

    consistent = joined.filter(
        (col("avg_price") >= col("low")) & (col("avg_price") <= col("high"))
    ).count()
    total = joined.count()

    return {
        "symbol": symbol,
        "cross_stream_consistency": round(consistent / total, 4) if total > 0 else 0.0,
        "status": "ok",
    }


@asset(
    name="data_quality_report",
    description="Cross-layer data quality report: completeness, freshness, validity, consistency",
    group_name="quality_layer",
    compute_kind="spark",
    deps=[
        "bronze_trade_data",
        "bronze_kline_data",
        "bronze_ticker_data",
        "bronze_depth_data",
        "silver_ohlcv_1m",
        "silver_trade_metrics",
    ],
)
def data_quality_report(context: OpExecutionContext, config: QualityAssetConfig):
    """Generate a comprehensive data quality report."""

    spark = get_spark_session("DataQualityReport")

    try:
        rows = []

        for symbol in config.symbol_list:
            context.log.info(f"Checking quality for {symbol}")

            # Bronze checks
            for table_prefix in _BRONZE_TABLES:
                result = _check_table(spark, table_prefix, symbol, "bronze")
                rows.append(result)

            # Silver checks
            for table_prefix in _SILVER_TABLES:
                result = _check_table(spark, table_prefix, symbol, "silver")
                rows.append(result)

            # Cross-stream consistency
            consistency = _cross_stream_check(spark, symbol)
            context.log.info(
                f"{symbol} cross-stream consistency: {consistency.get('cross_stream_consistency')}"
            )

        if not rows:
            return {"status": "no_data"}

        report_df = spark.createDataFrame(rows)

        table_name = "data_quality_report"
        table_path = f"s3a://datalake/quality/{table_name}"
        hudi_opts = get_hudi_write_config(table_name, "upsert")
        hudi_opts["hoodie.datasource.write.recordkey.field"] = "table,symbol"
        hudi_opts["hoodie.datasource.write.partitionpath.field"] = "symbol"
        hudi_opts["hoodie.datasource.write.precombine.field"] = "record_count"

        report_df.write.format("hudi").options(**hudi_opts).mode("overwrite").save(table_path)

        record_count = report_df.count()
        context.log.info(f"Quality report: {record_count} checks written")

        # Log summary
        issues = [r for r in rows if r.get("status") != "ok"]
        if issues:
            context.log.warning(f"Quality issues found in {len(issues)} tables")
            for issue in issues:
                context.log.warning(f"  {issue['table']}_{issue['symbol']}: {issue['status']}")

        return {
            "status": "success",
            "table_name": table_name,
            "record_count": record_count,
            "symbols": config.symbol_list,
            "issues_found": len(issues),
        }

    except Exception as e:
        context.log.error(f"Error generating quality report: {e}")
        raise
    finally:
        spark.stop()

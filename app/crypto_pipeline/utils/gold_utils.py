"""Gold layer shared utility functions.

Provides reusable PySpark helpers for portfolio analytics, risk
calculations, signal scoring, and standardised silver-table reading.
"""

import logging
from typing import Dict, Optional

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql.functions import (
    avg,
    col,
    count,
    lit,
    max as spark_max,
    min as spark_min,
    percentile_approx,
    sqrt,
    stddev,
    sum as spark_sum,
    when,
)

logger = logging.getLogger(__name__)


# ============================================================
# Silver table reader
# ============================================================

def read_silver_table(
    spark: SparkSession,
    table_name: str,
    symbol: str,
) -> Optional[DataFrame]:
    """Read a silver Hudi table for a given symbol.

    Returns ``None`` when the table is empty or does not exist.
    """
    path = f"s3a://datalake/silver/{table_name}_{symbol.lower()}"
    try:
        df = spark.read.format("hudi").load(path)
        if df.count() == 0:
            logger.info("Table %s is empty", path)
            return None
        return df
    except Exception as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None


# ============================================================
# Portfolio helpers
# ============================================================

def calculate_daily_returns(df: DataFrame, price_col: str = "close") -> DataFrame:
    """Add a ``daily_return`` column as fractional change of *price_col*."""
    w = Window.partitionBy("symbol").orderBy("event_time")
    prev = col(price_col)  # alias for readability
    return df.withColumn(
        "daily_return",
        (col(price_col) - lag_col(prev, w)) / lag_col(prev, w),
    )


def lag_col(c, window_spec):
    """Convenience: lag(column, 1) over the given window."""
    from pyspark.sql.functions import lag
    return lag(c, 1).over(window_spec)


def calculate_sharpe_ratio(
    returns_df: DataFrame,
    return_col: str = "daily_return",
    risk_free_rate: float = 0.0,
    annualisation_factor: float = 365.0,
) -> float:
    """Compute annualised Sharpe ratio from a column of returns.

    Returns 0.0 when standard deviation is zero (no variability).
    """
    stats = returns_df.select(
        avg(col(return_col)).alias("mean"),
        stddev(col(return_col)).alias("std"),
    ).first()

    if stats is None or stats["std"] is None or stats["std"] == 0:
        return 0.0

    daily_rf = risk_free_rate / annualisation_factor
    excess = stats["mean"] - daily_rf
    return float(excess / stats["std"] * (annualisation_factor ** 0.5))


def calculate_max_drawdown(df: DataFrame, price_col: str = "close") -> DataFrame:
    """Add ``cumulative_max`` and ``drawdown`` columns.

    ``drawdown`` is expressed as a negative fraction (0 = no drawdown).
    """
    w = Window.partitionBy("symbol").orderBy("event_time").rowsBetween(
        Window.unboundedPreceding, Window.currentRow
    )
    df = df.withColumn("cumulative_max", spark_max(col(price_col)).over(w))
    df = df.withColumn(
        "drawdown",
        (col(price_col) - col("cumulative_max")) / col("cumulative_max"),
    )
    return df


# ============================================================
# Risk helpers
# ============================================================

def calculate_var(
    returns_df: DataFrame,
    return_col: str = "daily_return",
    confidence: float = 0.95,
) -> float:
    """Historical Value-at-Risk at the given confidence level.

    Returns the loss threshold (as a positive number) such that losses
    exceed this value only (1 - confidence)% of the time.
    """
    quantile = 1.0 - confidence  # e.g. 0.05 for 95 %
    row = returns_df.select(
        percentile_approx(col(return_col), quantile).alias("var")
    ).first()

    if row is None or row["var"] is None:
        return 0.0

    # Return as positive loss magnitude
    return float(abs(row["var"]))


def calculate_volatility(
    returns_df: DataFrame,
    return_col: str = "daily_return",
    window_size: int = 30,
) -> DataFrame:
    """Add ``rolling_volatility`` (annualised) over *window_size* rows."""
    w = (
        Window.partitionBy("symbol")
        .orderBy("event_time")
        .rowsBetween(-(window_size - 1), 0)
    )
    return returns_df.withColumn(
        "rolling_volatility",
        stddev(col(return_col)).over(w) * sqrt(lit(365.0)),
    )


# ============================================================
# Signal scoring
# ============================================================

# Default weights for composite signal score
_DEFAULT_WEIGHTS: Dict[str, float] = {
    "sma_crossover": 0.20,
    "rsi_signal": 0.25,
    "macd_signal": 0.25,
    "bb_signal": 0.15,
    "volume_signal": 0.15,
}


def generate_signal_score(indicator_signals: Dict[str, float]) -> float:
    """Weighted composite score in [0, 100].

    Each value in *indicator_signals* should already be in [0, 100].
    Missing keys receive a neutral 50.
    """
    weights = _DEFAULT_WEIGHTS
    total_weight = 0.0
    weighted_sum = 0.0

    for key, w in weights.items():
        value = indicator_signals.get(key, 50.0)
        # Clamp to valid range
        value = max(0.0, min(100.0, value))
        weighted_sum += value * w
        total_weight += w

    if total_weight == 0:
        return 50.0

    return round(weighted_sum / total_weight, 2)


def classify_signal(score: float) -> str:
    """Map a 0–100 score to BUY / SELL / HOLD."""
    if score >= 65:
        return "BUY"
    elif score <= 35:
        return "SELL"
    return "HOLD"

"""Gold layer assets — business-level analytics.

Assets
------
* ``gold_portfolio_metrics``  – daily portfolio KPIs (Sharpe, drawdown, returns)
* ``gold_market_correlation`` – cross-symbol correlation & beta
* ``gold_trading_signals``    – composite buy/sell/hold signals
* ``gold_risk_metrics``       – VaR, volatility, liquidity scoring
"""

import logging
from typing import List

from dagster import asset, Config, OpExecutionContext
from pyspark.sql import DataFrame, Window
from pyspark.sql.functions import (
    abs as spark_abs,
    avg,
    coalesce,
    col,
    corr,
    count,
    first,
    lag,
    last,
    lit,
    max as spark_max,
    min as spark_min,
    percentile_approx,
    sqrt,
    stddev,
    struct,
    sum as spark_sum,
    udf,
    when,
)
from pyspark.sql.types import DoubleType, StringType

from ..utils.spark_utils import get_spark_session, get_hudi_write_config
from ..utils.gold_utils import (
    calculate_daily_returns,
    calculate_max_drawdown,
    calculate_sharpe_ratio,
    calculate_var,
    calculate_volatility,
    classify_signal,
    generate_signal_score,
    read_silver_table,
)

logger = logging.getLogger(__name__)


# ========================================
# Config
# ========================================

class GoldAssetConfig(Config):
    """Configuration for gold layer assets"""
    symbols: str = "BTCUSDT,ETHUSDT"  # comma-separated

    @property
    def symbol_list(self) -> List[str]:
        return [s.strip().upper() for s in self.symbols.split(",") if s.strip()]


# ========================================
# 1. Portfolio Metrics
# ========================================

@asset(
    name="gold_portfolio_metrics",
    description="Daily portfolio KPIs: returns, Sharpe ratio, max drawdown, Sortino ratio",
    group_name="gold_layer",
    compute_kind="spark",
    deps=["silver_ohlcv_1m", "silver_trade_metrics"],
)
def gold_portfolio_metrics(context: OpExecutionContext, config: GoldAssetConfig):
    """Compute daily portfolio performance metrics per symbol."""

    spark = get_spark_session("GoldPortfolioMetrics")

    try:
        all_results = []

        for symbol in config.symbol_list:
            context.log.info(f"Computing portfolio metrics for {symbol}")

            # Read 1-minute OHLCV (use daily close as proxy for daily price)
            ohlcv = read_silver_table(spark, "silver_ohlcv_1m", symbol)
            if ohlcv is None:
                context.log.info(f"No OHLCV data for {symbol}, skipping")
                continue

            # Compute daily returns from close prices
            w = Window.partitionBy("symbol").orderBy("event_time")
            ohlcv = ohlcv.withColumn("prev_close", lag("close", 1).over(w))
            ohlcv = ohlcv.withColumn(
                "daily_return",
                when(col("prev_close") > 0, (col("close") - col("prev_close")) / col("prev_close"))
                .otherwise(lit(0.0)),
            )

            # Cumulative return
            ohlcv = ohlcv.withColumn(
                "cumulative_return",
                (col("close") / first("close").over(
                    Window.partitionBy("symbol").orderBy("event_time")
                    .rowsBetween(Window.unboundedPreceding, Window.currentRow)
                )) - lit(1.0),
            )

            # Max drawdown
            ohlcv = calculate_max_drawdown(ohlcv, "close")

            # Rolling volatility
            ohlcv = calculate_volatility(ohlcv, "daily_return", 30)

            # Aggregate portfolio-level stats
            sharpe = calculate_sharpe_ratio(ohlcv, "daily_return")
            var_95 = calculate_var(ohlcv, "daily_return", 0.95)

            # Sortino: use downside deviation only
            downside = ohlcv.filter(col("daily_return") < 0)
            sortino_stats = downside.select(stddev("daily_return").alias("ds")).first()
            downside_std = float(sortino_stats["ds"]) if sortino_stats and sortino_stats["ds"] else 0.0

            mean_return = ohlcv.select(avg("daily_return")).first()[0] or 0.0
            sortino = float(mean_return / downside_std * (365 ** 0.5)) if downside_std > 0 else 0.0

            max_dd = ohlcv.select(spark_min("drawdown")).first()[0] or 0.0

            # Build summary row
            summary = spark.createDataFrame([{
                "symbol": symbol,
                "sharpe_ratio": round(sharpe, 4),
                "sortino_ratio": round(sortino, 4),
                "max_drawdown": round(float(max_dd), 4),
                "var_95": round(var_95, 6),
                "mean_daily_return": round(float(mean_return), 6),
                "record_count": ohlcv.count(),
            }])

            all_results.append(summary)

        if not all_results:
            context.log.info("No portfolio data produced")
            return {"status": "no_data"}

        # Union and write
        combined = all_results[0]
        for df in all_results[1:]:
            combined = combined.unionByName(df)

        table_name = "gold_portfolio_metrics"
        table_path = f"s3a://datalake/gold/{table_name}"
        hudi_opts = get_hudi_write_config(table_name, "upsert")
        # Use symbol as record key for portfolio metrics
        hudi_opts["hoodie.datasource.write.recordkey.field"] = "symbol"
        hudi_opts["hoodie.datasource.write.partitionpath.field"] = "symbol"
        hudi_opts["hoodie.datasource.write.precombine.field"] = "record_count"

        combined.write.format("hudi").options(**hudi_opts).mode("append").save(table_path)

        record_count = combined.count()
        context.log.info(f"Wrote {record_count} portfolio metric rows")

        return {
            "status": "success",
            "table_name": table_name,
            "record_count": record_count,
            "symbols": config.symbol_list,
        }

    except Exception as e:
        context.log.error(f"Error computing portfolio metrics: {e}")
        raise
    finally:
        spark.stop()


# ========================================
# 2. Market Correlation
# ========================================

@asset(
    name="gold_market_correlation",
    description="Cross-symbol correlation matrix and beta coefficients (30-day rolling)",
    group_name="gold_layer",
    compute_kind="spark",
    deps=["silver_ohlcv_multi_timeframe"],
)
def gold_market_correlation(context: OpExecutionContext, config: GoldAssetConfig):
    """Build a correlation matrix and beta relative to BTC."""

    spark = get_spark_session("GoldMarketCorrelation")

    try:
        symbols = config.symbol_list
        if len(symbols) < 2:
            context.log.info("Need at least 2 symbols for correlation")
            return {"status": "insufficient_symbols"}

        # Load 1h OHLCV for each symbol and compute returns
        dfs = {}
        for sym in symbols:
            df = read_silver_table(spark, "silver_ohlcv_1h", sym)
            if df is None:
                # Fallback to 1m
                df = read_silver_table(spark, "silver_ohlcv_1m", sym)
            if df is None:
                context.log.warning(f"No data for {sym}, skipping from correlation")
                continue
            w = Window.partitionBy("symbol").orderBy("event_time")
            df = df.withColumn("prev_close", lag("close", 1).over(w))
            df = df.withColumn(
                "ret",
                when(col("prev_close") > 0, (col("close") - col("prev_close")) / col("prev_close"))
                .otherwise(lit(0.0)),
            )
            dfs[sym] = df.select(col("event_time"), col("ret").alias(f"ret_{sym.lower()}"))

        if len(dfs) < 2:
            context.log.info("Not enough symbols with data for correlation")
            return {"status": "insufficient_data"}

        # Join all returns on event_time
        base_sym = list(dfs.keys())[0]
        joined = dfs[base_sym]
        for sym in list(dfs.keys())[1:]:
            joined = joined.join(dfs[sym], on="event_time", how="inner")

        # Compute pairwise correlations
        rows = []
        sym_keys = list(dfs.keys())
        for i, s1 in enumerate(sym_keys):
            for s2 in sym_keys[i:]:
                c1 = f"ret_{s1.lower()}"
                c2 = f"ret_{s2.lower()}"
                corr_val = joined.select(corr(col(c1), col(c2))).first()[0]
                corr_val = round(float(corr_val), 4) if corr_val is not None else 0.0
                rows.append({
                    "symbol_1": s1,
                    "symbol_2": s2,
                    "correlation": corr_val,
                })
                if s1 != s2:
                    rows.append({
                        "symbol_1": s2,
                        "symbol_2": s1,
                        "correlation": corr_val,
                    })

        # Beta relative to BTC
        btc_col = "ret_btcusdt"
        if btc_col in joined.columns:
            for sym in sym_keys:
                if sym == "BTCUSDT":
                    continue
                ret_col = f"ret_{sym.lower()}"
                stats = joined.select(
                    corr(col(ret_col), col(btc_col)).alias("corr_btc"),
                    stddev(col(ret_col)).alias("std_sym"),
                    stddev(col(btc_col)).alias("std_btc"),
                ).first()
                if stats and stats["std_btc"] and stats["std_btc"] > 0:
                    beta = float(stats["corr_btc"] or 0) * float(stats["std_sym"] or 0) / float(stats["std_btc"])
                else:
                    beta = 0.0
                # Attach beta as a special correlation row
                rows.append({
                    "symbol_1": sym,
                    "symbol_2": "BTC_BETA",
                    "correlation": round(beta, 4),
                })

        corr_df = spark.createDataFrame(rows)

        table_name = "gold_market_correlation"
        table_path = f"s3a://datalake/gold/{table_name}"
        hudi_opts = get_hudi_write_config(table_name, "upsert")
        hudi_opts["hoodie.datasource.write.recordkey.field"] = "symbol_1,symbol_2"
        hudi_opts["hoodie.datasource.write.partitionpath.field"] = "symbol_1"
        hudi_opts["hoodie.datasource.write.precombine.field"] = "correlation"

        corr_df.write.format("hudi").options(**hudi_opts).mode("overwrite").save(table_path)

        record_count = corr_df.count()
        context.log.info(f"Wrote {record_count} correlation rows")

        return {
            "status": "success",
            "table_name": table_name,
            "record_count": record_count,
            "symbols": sym_keys,
        }

    except Exception as e:
        context.log.error(f"Error computing market correlation: {e}")
        raise
    finally:
        spark.stop()


# ========================================
# 3. Trading Signals
# ========================================

@asset(
    name="gold_trading_signals",
    description="Composite BUY/SELL/HOLD signals from silver indicators",
    group_name="gold_layer",
    compute_kind="spark",
    deps=["silver_ohlcv_1m", "silver_trade_metrics"],
)
def gold_trading_signals(context: OpExecutionContext, config: GoldAssetConfig):
    """Generate trading signals per symbol from technical indicators."""

    spark = get_spark_session("GoldTradingSignals")

    try:
        all_results = []

        for symbol in config.symbol_list:
            context.log.info(f"Generating signals for {symbol}")

            ohlcv = read_silver_table(spark, "silver_ohlcv_1m", symbol)
            if ohlcv is None:
                continue

            # --- SMA crossover ---
            # Bullish when sma_7 > sma_25, bearish when opposite
            ohlcv = ohlcv.withColumn(
                "sma_crossover_signal",
                when(col("sma_7") > col("sma_25"), lit(80.0))
                .when(col("sma_7") < col("sma_25"), lit(20.0))
                .otherwise(lit(50.0)),
            )

            # --- RSI ---
            ohlcv = ohlcv.withColumn(
                "rsi_signal",
                when(col("rsi") < 30, lit(85.0))       # oversold → buy
                .when(col("rsi") > 70, lit(15.0))       # overbought → sell
                .when(col("rsi") < 40, lit(65.0))
                .when(col("rsi") > 60, lit(35.0))
                .otherwise(lit(50.0)),
            )

            # --- MACD crossover ---
            ohlcv = ohlcv.withColumn(
                "macd_raw_signal",
                when(col("macd_histogram") > 0, lit(75.0))
                .when(col("macd_histogram") < 0, lit(25.0))
                .otherwise(lit(50.0)),
            )

            # --- Bollinger Band squeeze ---
            ohlcv = ohlcv.withColumn(
                "bb_width",
                when(col("bb_middle") > 0, (col("bb_upper") - col("bb_lower")) / col("bb_middle"))
                .otherwise(lit(0.0)),
            )
            ohlcv = ohlcv.withColumn(
                "bb_signal",
                when(col("close") < col("bb_lower"), lit(80.0))   # below lower band → buy
                .when(col("close") > col("bb_upper"), lit(20.0))  # above upper band → sell
                .otherwise(lit(50.0)),
            )

            # Volume signal from trade metrics (optional join)
            trade_metrics = read_silver_table(spark, "silver_trade_metrics", symbol)
            if trade_metrics is not None:
                # Use buy_sell_ratio as a signal
                tm = trade_metrics.select(
                    col("event_time").alias("tm_event_time"),
                    when(col("buy_sell_ratio") > 1.5, lit(75.0))
                    .when(col("buy_sell_ratio") < 0.67, lit(25.0))
                    .otherwise(lit(50.0)).alias("volume_signal"),
                )
                ohlcv = ohlcv.join(
                    tm,
                    ohlcv["event_time"] == tm["tm_event_time"],
                    "left",
                ).drop("tm_event_time")
            else:
                ohlcv = ohlcv.withColumn("volume_signal", lit(50.0))

            # Fill nulls with neutral 50
            for c in ["sma_crossover_signal", "rsi_signal", "macd_raw_signal", "bb_signal", "volume_signal"]:
                ohlcv = ohlcv.withColumn(c, coalesce(col(c), lit(50.0)))

            # --- Composite score ---
            ohlcv = ohlcv.withColumn(
                "signal_score",
                col("sma_crossover_signal") * lit(0.20)
                + col("rsi_signal") * lit(0.25)
                + col("macd_raw_signal") * lit(0.25)
                + col("bb_signal") * lit(0.15)
                + col("volume_signal") * lit(0.15),
            )

            # Classification
            ohlcv = ohlcv.withColumn(
                "signal",
                when(col("signal_score") >= 65, lit("BUY"))
                .when(col("signal_score") <= 35, lit("SELL"))
                .otherwise(lit("HOLD")),
            )

            # Select output columns
            signal_df = ohlcv.select(
                "record_id", "symbol", "event_time", "date", "close",
                "sma_crossover_signal", "rsi_signal", "macd_raw_signal",
                "bb_signal", "volume_signal", "signal_score", "signal",
            )

            all_results.append(signal_df)

        if not all_results:
            context.log.info("No signal data produced")
            return {"status": "no_data"}

        combined = all_results[0]
        for df in all_results[1:]:
            combined = combined.unionByName(df, allowMissingColumns=True)

        table_name = "gold_trading_signals"
        table_path = f"s3a://datalake/gold/{table_name}"
        hudi_opts = get_hudi_write_config(table_name, "upsert")

        combined.write.format("hudi").options(**hudi_opts).mode("append").save(table_path)

        record_count = combined.count()
        context.log.info(f"Wrote {record_count} signal rows")

        return {
            "status": "success",
            "table_name": table_name,
            "record_count": record_count,
            "symbols": config.symbol_list,
        }

    except Exception as e:
        context.log.error(f"Error generating trading signals: {e}")
        raise
    finally:
        spark.stop()


# ========================================
# 4. Risk Metrics
# ========================================

@asset(
    name="gold_risk_metrics",
    description="VaR, volatility, and liquidity scoring per symbol",
    group_name="gold_layer",
    compute_kind="spark",
    deps=["silver_ohlcv_multi_timeframe", "silver_trade_metrics"],
)
def gold_risk_metrics(context: OpExecutionContext, config: GoldAssetConfig):
    """Calculate risk metrics per symbol."""

    spark = get_spark_session("GoldRiskMetrics")

    try:
        all_results = []

        for symbol in config.symbol_list:
            context.log.info(f"Computing risk metrics for {symbol}")

            # Read OHLCV — prefer hourly, fall back to 1m
            ohlcv = read_silver_table(spark, "silver_ohlcv_1h", symbol)
            if ohlcv is None:
                ohlcv = read_silver_table(spark, "silver_ohlcv_1m", symbol)
            if ohlcv is None:
                context.log.info(f"No OHLCV data for {symbol}, skipping")
                continue

            # Compute returns
            w = Window.partitionBy("symbol").orderBy("event_time")
            ohlcv = ohlcv.withColumn("prev_close", lag("close", 1).over(w))
            ohlcv = ohlcv.withColumn(
                "daily_return",
                when(col("prev_close") > 0, (col("close") - col("prev_close")) / col("prev_close"))
                .otherwise(lit(0.0)),
            )

            # VaR
            var_95 = calculate_var(ohlcv, "daily_return", 0.95)
            var_99 = calculate_var(ohlcv, "daily_return", 0.99)

            # Realised volatility (annualised)
            vol_stats = ohlcv.select(stddev("daily_return").alias("std")).first()
            realised_vol = float(vol_stats["std"] or 0) * (365 ** 0.5)

            # Liquidity score from trade metrics
            liquidity_score = 0.5  # neutral default
            trade_metrics = read_silver_table(spark, "silver_trade_metrics", symbol)
            if trade_metrics is not None:
                tm_stats = trade_metrics.select(
                    avg("total_volume").alias("avg_vol"),
                    avg("trade_count").alias("avg_trades"),
                ).first()
                if tm_stats and tm_stats["avg_vol"] is not None:
                    avg_vol = float(tm_stats["avg_vol"])
                    avg_trades = float(tm_stats["avg_trades"] or 0)
                    # Simple liquidity heuristic: normalize on BTC-like volumes
                    liquidity_score = min(1.0, avg_vol / 1000.0) * 0.6 + min(1.0, avg_trades / 500.0) * 0.4

            row = {
                "symbol": symbol,
                "var_95": round(var_95, 6),
                "var_99": round(var_99, 6),
                "realised_volatility": round(realised_vol, 6),
                "liquidity_score": round(liquidity_score, 4),
                "data_points": ohlcv.count(),
            }
            all_results.append(spark.createDataFrame([row]))

        if not all_results:
            context.log.info("No risk data produced")
            return {"status": "no_data"}

        combined = all_results[0]
        for df in all_results[1:]:
            combined = combined.unionByName(df)

        table_name = "gold_risk_metrics"
        table_path = f"s3a://datalake/gold/{table_name}"
        hudi_opts = get_hudi_write_config(table_name, "upsert")
        hudi_opts["hoodie.datasource.write.recordkey.field"] = "symbol"
        hudi_opts["hoodie.datasource.write.partitionpath.field"] = "symbol"
        hudi_opts["hoodie.datasource.write.precombine.field"] = "data_points"

        combined.write.format("hudi").options(**hudi_opts).mode("append").save(table_path)

        record_count = combined.count()
        context.log.info(f"Wrote {record_count} risk metric rows")

        return {
            "status": "success",
            "table_name": table_name,
            "record_count": record_count,
            "symbols": config.symbol_list,
        }

    except Exception as e:
        context.log.error(f"Error computing risk metrics: {e}")
        raise
    finally:
        spark.stop()

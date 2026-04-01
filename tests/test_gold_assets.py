"""Tests for gold layer assets."""

import pytest
from unittest.mock import Mock, patch


class TestGoldAssetConfig:
    """Test gold asset configuration."""

    def test_default_symbols(self):
        from app.crypto_pipeline.assets.gold_assets import GoldAssetConfig
        config = GoldAssetConfig()
        assert config.symbols == "BTCUSDT,ETHUSDT"
        assert config.symbol_list == ["BTCUSDT", "ETHUSDT"]

    def test_custom_symbols(self):
        from app.crypto_pipeline.assets.gold_assets import GoldAssetConfig
        config = GoldAssetConfig(symbols="ADAUSDT,DOTUSDT,BTCUSDT")
        assert config.symbol_list == ["ADAUSDT", "DOTUSDT", "BTCUSDT"]

    def test_single_symbol(self):
        from app.crypto_pipeline.assets.gold_assets import GoldAssetConfig
        config = GoldAssetConfig(symbols="BTCUSDT")
        assert config.symbol_list == ["BTCUSDT"]

    def test_whitespace_handling(self):
        from app.crypto_pipeline.assets.gold_assets import GoldAssetConfig
        config = GoldAssetConfig(symbols=" BTCUSDT , ETHUSDT ")
        assert config.symbol_list == ["BTCUSDT", "ETHUSDT"]


class TestPortfolioMetrics:
    """Test portfolio metrics calculations with PySpark."""

    @pytest.fixture(scope="class")
    def spark(self):
        try:
            from pyspark.sql import SparkSession
            spark = (
                SparkSession.builder
                .master("local[1]")
                .appName("GoldAssetTests")
                .config("spark.driver.memory", "512m")
                .config("spark.ui.enabled", "false")
                .getOrCreate()
            )
            yield spark
            spark.stop()
        except Exception:
            pytest.skip("PySpark not available in test environment")

    def _make_ohlcv(self, spark, n=100):
        rows = []
        for i in range(n):
            rows.append({
                "symbol": "BTCUSDT",
                "event_time": 1640995200000 + i * 60000,
                "close": 50000.0 + (i % 20) * 100 - 1000,
                "open": 50000.0,
                "high": 51000.0,
                "low": 49000.0,
                "volume": 100.0,
                "date": "2022-01-01",
                "record_id": f"r_{i}",
                "data_quality_score": 1.0,
                "sma_7": 50000.0,
                "sma_25": 49500.0,
                "sma_99": 49000.0,
                "ema_12": 50000.0,
                "ema_26": 49800.0,
                "rsi": 55.0,
                "macd_line": 200.0,
                "macd_signal": 150.0,
                "macd_histogram": 50.0,
                "bb_middle": 50000.0,
                "bb_upper": 51000.0,
                "bb_lower": 49000.0,
            })
        return spark.createDataFrame(rows)

    def test_sharpe_computable(self, spark):
        """Portfolio metrics should compute a Sharpe ratio from OHLCV data."""
        from app.crypto_pipeline.utils.gold_utils import (
            calculate_max_drawdown,
            calculate_sharpe_ratio,
        )
        from pyspark.sql import Window
        from pyspark.sql.functions import col, lag, lit, when

        df = self._make_ohlcv(spark, 100)
        w = Window.partitionBy("symbol").orderBy("event_time")
        df = df.withColumn("prev_close", lag("close", 1).over(w))
        df = df.withColumn(
            "daily_return",
            when(col("prev_close") > 0, (col("close") - col("prev_close")) / col("prev_close"))
            .otherwise(lit(0.0)),
        )
        sharpe = calculate_sharpe_ratio(df, "daily_return")
        assert isinstance(sharpe, float)

    def test_drawdown_columns_exist(self, spark):
        from app.crypto_pipeline.utils.gold_utils import calculate_max_drawdown
        df = self._make_ohlcv(spark, 50)
        result = calculate_max_drawdown(df, "close")
        assert "cumulative_max" in result.columns
        assert "drawdown" in result.columns


class TestTradingSignals:
    """Test signal classification logic."""

    def test_buy_signal_above_threshold(self):
        from app.crypto_pipeline.utils.gold_utils import classify_signal
        assert classify_signal(80) == "BUY"

    def test_sell_signal_below_threshold(self):
        from app.crypto_pipeline.utils.gold_utils import classify_signal
        assert classify_signal(20) == "SELL"

    def test_hold_in_neutral_range(self):
        from app.crypto_pipeline.utils.gold_utils import classify_signal
        assert classify_signal(50) == "HOLD"


class TestCorrelation:
    """Test correlation matrix logic."""

    @pytest.fixture(scope="class")
    def spark(self):
        try:
            from pyspark.sql import SparkSession
            spark = (
                SparkSession.builder
                .master("local[1]")
                .appName("CorrelationTests")
                .config("spark.driver.memory", "512m")
                .config("spark.ui.enabled", "false")
                .getOrCreate()
            )
            yield spark
            spark.stop()
        except Exception:
            pytest.skip("PySpark not available in test environment")

    def test_self_correlation_is_one(self, spark):
        from pyspark.sql.functions import corr, col
        rows = [{"a": float(i), "b": float(i)} for i in range(50)]
        df = spark.createDataFrame(rows)
        result = df.select(corr("a", "b")).first()[0]
        assert result == pytest.approx(1.0, abs=1e-6)

    def test_negative_correlation(self, spark):
        from pyspark.sql.functions import corr
        rows = [{"a": float(i), "b": float(-i)} for i in range(50)]
        df = spark.createDataFrame(rows)
        result = df.select(corr("a", "b")).first()[0]
        assert result == pytest.approx(-1.0, abs=1e-6)


class TestRiskMetrics:
    """Test risk metric calculations."""

    @pytest.fixture(scope="class")
    def spark(self):
        try:
            from pyspark.sql import SparkSession
            spark = (
                SparkSession.builder
                .master("local[1]")
                .appName("RiskTests")
                .config("spark.driver.memory", "512m")
                .config("spark.ui.enabled", "false")
                .getOrCreate()
            )
            yield spark
            spark.stop()
        except Exception:
            pytest.skip("PySpark not available in test environment")

    def test_var_bounds(self, spark):
        from app.crypto_pipeline.utils.gold_utils import calculate_var
        values = [0.01, -0.02, 0.005, -0.03, 0.02, -0.01, 0.015, -0.005]
        df = spark.createDataFrame([{"daily_return": v} for v in values])
        var_95 = calculate_var(df, "daily_return", 0.95)
        var_99 = calculate_var(df, "daily_return", 0.99)
        assert var_95 >= 0
        assert var_99 >= 0

    def test_volatility_column_created(self, spark):
        from app.crypto_pipeline.utils.gold_utils import calculate_volatility
        rows = [
            {"symbol": "TEST", "event_time": 1000 + i, "daily_return": 0.01 * ((-1) ** i)}
            for i in range(30)
        ]
        df = spark.createDataFrame(rows)
        result = calculate_volatility(df, "daily_return", 10)
        assert "rolling_volatility" in result.columns


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

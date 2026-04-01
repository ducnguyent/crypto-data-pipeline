"""Tests for silver layer technical indicator helpers"""

import pytest
from unittest.mock import Mock, patch


class TestSilverAssetConfig:
    """Test silver config"""

    def test_default_config(self):
        from app.crypto_pipeline.assets.silver_assets import SilverAssetConfig
        config = SilverAssetConfig()
        assert config.symbol == "BTCUSDT"

    def test_custom_symbol(self):
        from app.crypto_pipeline.assets.silver_assets import SilverAssetConfig
        config = SilverAssetConfig(symbol="ETHUSDT")
        assert config.symbol == "ETHUSDT"


class TestTimeframeConstants:
    """Validate multi-timeframe configuration"""

    def test_timeframe_minutes_mapping(self):
        from app.crypto_pipeline.assets.silver_assets import _TIMEFRAME_MINUTES
        assert _TIMEFRAME_MINUTES["5m"] == 5
        assert _TIMEFRAME_MINUTES["15m"] == 15
        assert _TIMEFRAME_MINUTES["1h"] == 60
        assert _TIMEFRAME_MINUTES["4h"] == 240
        assert _TIMEFRAME_MINUTES["1d"] == 1440

    def test_all_expected_timeframes_present(self):
        from app.crypto_pipeline.assets.silver_assets import _TIMEFRAME_MINUTES
        expected = {"5m", "15m", "1h", "4h", "1d"}
        assert set(_TIMEFRAME_MINUTES.keys()) == expected


class TestIndicatorFunctions:
    """Test technical indicator helpers with a local PySpark session.

    These tests create minimal DataFrames to verify the indicator
    functions produce the expected columns.  They require PySpark
    to be installed in the test environment.
    """

    @pytest.fixture(scope="class")
    def spark(self):
        """Shared local Spark session for indicator tests"""
        try:
            from pyspark.sql import SparkSession
            spark = (
                SparkSession.builder
                .master("local[1]")
                .appName("SilverIndicatorTests")
                .config("spark.driver.memory", "512m")
                .config("spark.ui.enabled", "false")
                .getOrCreate()
            )
            yield spark
            spark.stop()
        except Exception:
            pytest.skip("PySpark not available in test environment")

    def _make_ohlcv_df(self, spark, n_rows: int = 100):
        """Create a minimal OHLCV DataFrame for testing"""
        from pyspark.sql.types import (
            StructType, StructField, StringType, DoubleType, LongType
        )

        rows = []
        base_time = 1640995200000
        for i in range(n_rows):
            rows.append({
                "symbol": "BTCUSDT",
                "event_time": base_time + i * 60000,
                "open": 50000.0 + i,
                "high": 50010.0 + i,
                "low": 49990.0 + i,
                "close": 50005.0 + i,
                "volume": 100.0 + i,
            })

        return spark.createDataFrame(rows)

    def test_add_sma_creates_columns(self, spark):
        from app.crypto_pipeline.assets.silver_assets import _add_sma
        df = self._make_ohlcv_df(spark, 30)
        result = _add_sma(df, "close", [7, 25])
        columns = result.columns
        assert "sma_7" in columns
        assert "sma_25" in columns
        assert result.count() == 30

    def test_add_ema_creates_columns(self, spark):
        from app.crypto_pipeline.assets.silver_assets import _add_ema
        df = self._make_ohlcv_df(spark, 30)
        result = _add_ema(df, "close", [12, 26])
        columns = result.columns
        assert "ema_12" in columns
        assert "ema_26" in columns

    def test_add_rsi_creates_column(self, spark):
        from app.crypto_pipeline.assets.silver_assets import _add_rsi
        df = self._make_ohlcv_df(spark, 30)
        result = _add_rsi(df, "close", 14)
        assert "rsi" in result.columns
        # RSI should be between 0 and 100
        rsi_values = [row.rsi for row in result.collect() if row.rsi is not None]
        for v in rsi_values:
            assert 0 <= v <= 100, f"RSI out of range: {v}"

    def test_add_macd_creates_columns(self, spark):
        from app.crypto_pipeline.assets.silver_assets import _add_macd
        df = self._make_ohlcv_df(spark, 60)
        result = _add_macd(df, "close")
        columns = result.columns
        assert "macd_line" in columns
        assert "macd_signal" in columns
        assert "macd_histogram" in columns

    def test_add_bollinger_bands_creates_columns(self, spark):
        from app.crypto_pipeline.assets.silver_assets import _add_bollinger_bands
        df = self._make_ohlcv_df(spark, 30)
        result = _add_bollinger_bands(df, "close", 20, 2.0)
        columns = result.columns
        assert "bb_middle" in columns
        assert "bb_upper" in columns
        assert "bb_lower" in columns

    def test_add_all_indicators(self, spark):
        from app.crypto_pipeline.assets.silver_assets import add_all_indicators
        df = self._make_ohlcv_df(spark, 100)
        result = add_all_indicators(df, "close")
        columns = result.columns
        expected = [
            "sma_7", "sma_25", "sma_99",
            "ema_12", "ema_26",
            "rsi",
            "macd_line", "macd_signal", "macd_histogram",
            "bb_middle", "bb_upper", "bb_lower",
        ]
        for col_name in expected:
            assert col_name in columns, f"Missing indicator column: {col_name}"

    def test_bollinger_upper_greater_than_lower(self, spark):
        from app.crypto_pipeline.assets.silver_assets import _add_bollinger_bands
        df = self._make_ohlcv_df(spark, 30)
        result = _add_bollinger_bands(df, "close", 20, 2.0)
        rows = result.filter("bb_upper IS NOT NULL AND bb_lower IS NOT NULL").collect()
        for row in rows:
            assert row.bb_upper >= row.bb_lower, "BB upper should be >= lower"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

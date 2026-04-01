"""Tests for data quality assets."""

import pytest
from unittest.mock import Mock, patch


class TestQualityAssetConfig:
    """Test quality config."""

    def test_default_config(self):
        from app.crypto_pipeline.assets.quality_assets import QualityAssetConfig
        config = QualityAssetConfig()
        assert config.symbols == "BTCUSDT,ETHUSDT"
        assert config.quality_threshold == 0.5
        assert config.symbol_list == ["BTCUSDT", "ETHUSDT"]

    def test_custom_threshold(self):
        from app.crypto_pipeline.assets.quality_assets import QualityAssetConfig
        config = QualityAssetConfig(quality_threshold=0.8)
        assert config.quality_threshold == 0.8


class TestBronzeTableConstants:
    """Validate expected table lists."""

    def test_bronze_tables_defined(self):
        from app.crypto_pipeline.assets.quality_assets import _BRONZE_TABLES
        assert "bronze_trade" in _BRONZE_TABLES
        assert "bronze_kline" in _BRONZE_TABLES
        assert "bronze_ticker" in _BRONZE_TABLES
        assert "bronze_depth" in _BRONZE_TABLES

    def test_silver_tables_defined(self):
        from app.crypto_pipeline.assets.quality_assets import _SILVER_TABLES
        assert "silver_ohlcv_1m" in _SILVER_TABLES
        assert "silver_trade_metrics" in _SILVER_TABLES


class TestCheckTable:
    """Test the _check_table helper."""

    @pytest.fixture(scope="class")
    def spark(self):
        try:
            from pyspark.sql import SparkSession
            spark = (
                SparkSession.builder
                .master("local[1]")
                .appName("QualityTests")
                .config("spark.driver.memory", "512m")
                .config("spark.ui.enabled", "false")
                .getOrCreate()
            )
            yield spark
            spark.stop()
        except Exception:
            pytest.skip("PySpark not available in test environment")

    def test_missing_table_returns_error(self, spark):
        """When a table doesn't exist, should return error status."""
        from app.crypto_pipeline.assets.quality_assets import _check_table
        result = _check_table(spark, "nonexistent_table", "BTCUSDT", "bronze")
        assert result["status"].startswith("error")
        assert result["record_count"] == 0
        assert result["completeness"] == 0.0


class TestCrossStreamCheck:
    """Test cross-stream consistency validation."""

    @pytest.fixture(scope="class")
    def spark(self):
        try:
            from pyspark.sql import SparkSession
            spark = (
                SparkSession.builder
                .master("local[1]")
                .appName("CrossStreamTests")
                .config("spark.driver.memory", "512m")
                .config("spark.ui.enabled", "false")
                .getOrCreate()
            )
            yield spark
            spark.stop()
        except Exception:
            pytest.skip("PySpark not available in test environment")

    @patch("app.crypto_pipeline.assets.quality_assets.read_silver_table")
    def test_insufficient_data(self, mock_read, spark):
        """When either table is missing, should return insufficient_data."""
        from app.crypto_pipeline.assets.quality_assets import _cross_stream_check
        mock_read.return_value = None
        result = _cross_stream_check(spark, "BTCUSDT")
        assert result["status"] == "insufficient_data"

    @patch("app.crypto_pipeline.assets.quality_assets.read_silver_table")
    def test_consistent_data(self, mock_read, spark):
        """When trade prices are within kline range, consistency should be 1.0."""
        from app.crypto_pipeline.assets.quality_assets import _cross_stream_check

        # Mock trade metrics
        trade_df = spark.createDataFrame([
            {"event_time": 1000, "avg_price": 50000.0},
            {"event_time": 2000, "avg_price": 50500.0},
        ])
        # Mock kline data
        kline_df = spark.createDataFrame([
            {"event_time": 1000, "high": 51000.0, "low": 49000.0},
            {"event_time": 2000, "high": 51000.0, "low": 50000.0},
        ])

        def side_effect(spark, table_name, symbol):
            if "trade_metrics" in table_name:
                return trade_df
            return kline_df

        mock_read.side_effect = side_effect
        result = _cross_stream_check(spark, "BTCUSDT")
        assert result["status"] == "ok"
        assert result["cross_stream_consistency"] == 1.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

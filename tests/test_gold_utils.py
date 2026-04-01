"""Tests for gold_utils helper functions."""

import pytest


class TestGenerateSignalScore:
    """Test the composite signal scoring function."""

    def test_all_bullish_signals(self):
        from app.crypto_pipeline.utils.gold_utils import generate_signal_score
        signals = {
            "sma_crossover": 90.0,
            "rsi_signal": 85.0,
            "macd_signal": 80.0,
            "bb_signal": 75.0,
            "volume_signal": 70.0,
        }
        score = generate_signal_score(signals)
        assert 70 <= score <= 100

    def test_all_bearish_signals(self):
        from app.crypto_pipeline.utils.gold_utils import generate_signal_score
        signals = {
            "sma_crossover": 10.0,
            "rsi_signal": 15.0,
            "macd_signal": 20.0,
            "bb_signal": 25.0,
            "volume_signal": 30.0,
        }
        score = generate_signal_score(signals)
        assert 0 <= score <= 30

    def test_neutral_when_empty(self):
        from app.crypto_pipeline.utils.gold_utils import generate_signal_score
        score = generate_signal_score({})
        assert score == 50.0

    def test_missing_keys_default_to_neutral(self):
        from app.crypto_pipeline.utils.gold_utils import generate_signal_score
        signals = {"sma_crossover": 100.0}
        score = generate_signal_score(signals)
        # Only sma_crossover is non-neutral; rest are 50
        # sma_crossover=100 (weight 0.20) + four neutral 50 → 100*0.2 + 50*0.8 = 60.0
        assert 50 < score <= 60

    def test_score_in_range(self):
        from app.crypto_pipeline.utils.gold_utils import generate_signal_score
        signals = {
            "sma_crossover": 0.0,
            "rsi_signal": 0.0,
            "macd_signal": 0.0,
            "bb_signal": 0.0,
            "volume_signal": 0.0,
        }
        score = generate_signal_score(signals)
        assert 0 <= score <= 100

    def test_values_clamped_to_range(self):
        from app.crypto_pipeline.utils.gold_utils import generate_signal_score
        signals = {
            "sma_crossover": 200.0,   # Above 100 → clamped to 100
            "rsi_signal": -50.0,       # Below 0 → clamped to 0
        }
        score = generate_signal_score(signals)
        assert 0 <= score <= 100


class TestClassifySignal:
    """Test signal classification."""

    def test_buy(self):
        from app.crypto_pipeline.utils.gold_utils import classify_signal
        assert classify_signal(80) == "BUY"
        assert classify_signal(65) == "BUY"

    def test_sell(self):
        from app.crypto_pipeline.utils.gold_utils import classify_signal
        assert classify_signal(20) == "SELL"
        assert classify_signal(35) == "SELL"

    def test_hold(self):
        from app.crypto_pipeline.utils.gold_utils import classify_signal
        assert classify_signal(50) == "HOLD"
        assert classify_signal(36) == "HOLD"
        assert classify_signal(64) == "HOLD"


class TestSharpeRatio:
    """Test Sharpe ratio calculation with PySpark."""

    @pytest.fixture(scope="class")
    def spark(self):
        try:
            from pyspark.sql import SparkSession
            spark = (
                SparkSession.builder
                .master("local[1]")
                .appName("GoldUtilsTests")
                .config("spark.driver.memory", "512m")
                .config("spark.ui.enabled", "false")
                .getOrCreate()
            )
            yield spark
            spark.stop()
        except Exception:
            pytest.skip("PySpark not available in test environment")

    def _make_returns_df(self, spark, values):
        return spark.createDataFrame(
            [{"daily_return": v} for v in values]
        )

    def test_sharpe_zero_std(self, spark):
        from app.crypto_pipeline.utils.gold_utils import calculate_sharpe_ratio
        df = self._make_returns_df(spark, [0.01, 0.01, 0.01])
        result = calculate_sharpe_ratio(df, "daily_return")
        assert result == 0.0  # zero std → returns 0

    def test_sharpe_positive_returns(self, spark):
        from app.crypto_pipeline.utils.gold_utils import calculate_sharpe_ratio
        values = [0.02, 0.01, 0.03, 0.015, 0.025]
        df = self._make_returns_df(spark, values)
        result = calculate_sharpe_ratio(df, "daily_return")
        assert result > 0  # positive mean, should be positive Sharpe

    def test_sharpe_negative_returns(self, spark):
        from app.crypto_pipeline.utils.gold_utils import calculate_sharpe_ratio
        values = [-0.02, -0.01, -0.03, -0.015, -0.025]
        df = self._make_returns_df(spark, values)
        result = calculate_sharpe_ratio(df, "daily_return")
        assert result < 0


class TestVaR:
    """Test Value at Risk calculation."""

    @pytest.fixture(scope="class")
    def spark(self):
        try:
            from pyspark.sql import SparkSession
            spark = (
                SparkSession.builder
                .master("local[1]")
                .appName("VaRTests")
                .config("spark.driver.memory", "512m")
                .config("spark.ui.enabled", "false")
                .getOrCreate()
            )
            yield spark
            spark.stop()
        except Exception:
            pytest.skip("PySpark not available in test environment")

    def test_var_95_is_positive(self, spark):
        from app.crypto_pipeline.utils.gold_utils import calculate_var
        values = [0.01, -0.02, 0.005, -0.03, 0.02, -0.01, 0.0]
        df = spark.createDataFrame([{"daily_return": v} for v in values])
        result = calculate_var(df, "daily_return", 0.95)
        assert result >= 0  # VaR returned as positive magnitude

    def test_var_all_positive_returns(self, spark):
        from app.crypto_pipeline.utils.gold_utils import calculate_var
        values = [0.01, 0.02, 0.03, 0.04, 0.05]
        df = spark.createDataFrame([{"daily_return": v} for v in values])
        result = calculate_var(df, "daily_return", 0.95)
        assert result >= 0


class TestMaxDrawdown:
    """Test max drawdown calculation."""

    @pytest.fixture(scope="class")
    def spark(self):
        try:
            from pyspark.sql import SparkSession
            spark = (
                SparkSession.builder
                .master("local[1]")
                .appName("DrawdownTests")
                .config("spark.driver.memory", "512m")
                .config("spark.ui.enabled", "false")
                .getOrCreate()
            )
            yield spark
            spark.stop()
        except Exception:
            pytest.skip("PySpark not available in test environment")

    def test_monotonic_increase_has_zero_drawdown(self, spark):
        from app.crypto_pipeline.utils.gold_utils import calculate_max_drawdown
        rows = [
            {"symbol": "TEST", "event_time": 1000 + i, "close": 100.0 + i}
            for i in range(10)
        ]
        df = spark.createDataFrame(rows)
        result = calculate_max_drawdown(df, "close")
        min_dd = result.select("drawdown").agg({"drawdown": "min"}).first()[0]
        assert min_dd == pytest.approx(0.0)

    def test_drawdown_is_negative_on_decline(self, spark):
        from app.crypto_pipeline.utils.gold_utils import calculate_max_drawdown
        prices = [100, 110, 105, 95, 90, 100]
        rows = [
            {"symbol": "TEST", "event_time": 1000 + i, "close": float(p)}
            for i, p in enumerate(prices)
        ]
        df = spark.createDataFrame(rows)
        result = calculate_max_drawdown(df, "close")
        min_dd = result.select("drawdown").agg({"drawdown": "min"}).first()[0]
        assert min_dd < 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

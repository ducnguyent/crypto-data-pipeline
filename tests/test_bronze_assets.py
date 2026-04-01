"""Tests for bronze layer assets"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from app.crypto_pipeline.assets.bronze_assets import (
    get_bronze_trade_schema,
    get_bronze_ticker_schema,
    get_bronze_kline_schema,
    get_bronze_depth_schema,
    BronzeAssetConfig,
)


class TestBronzeSchemas:
    """Validate schema definitions for each stream type"""

    def test_trade_schema_has_required_fields(self):
        schema = get_bronze_trade_schema()
        field_names = [f.name for f in schema.fields]
        required = [
            "record_id", "symbol", "stream_type", "event_time",
            "received_time", "date", "raw_data", "data_quality_score",
            "price", "quantity", "trade_id", "is_buyer_maker",
        ]
        for field in required:
            assert field in field_names, f"Missing field: {field}"

    def test_ticker_schema_has_required_fields(self):
        schema = get_bronze_ticker_schema()
        field_names = [f.name for f in schema.fields]
        required = [
            "record_id", "symbol", "stream_type", "event_time",
            "price_change", "price_change_percent", "last_price",
            "volume", "quote_volume",
        ]
        for field in required:
            assert field in field_names, f"Missing field: {field}"

    def test_kline_schema_has_required_fields(self):
        schema = get_bronze_kline_schema()
        field_names = [f.name for f in schema.fields]
        required = [
            "record_id", "symbol", "stream_type", "event_time",
            "interval", "open", "high", "low", "close", "volume", "is_closed",
        ]
        for field in required:
            assert field in field_names, f"Missing field: {field}"

    def test_depth_schema_has_required_fields(self):
        schema = get_bronze_depth_schema()
        field_names = [f.name for f in schema.fields]
        required = [
            "record_id", "symbol", "stream_type", "event_time",
            "bids", "asks", "bid_count", "ask_count",
            "best_bid", "best_ask", "spread",
        ]
        for field in required:
            assert field in field_names, f"Missing field: {field}"

    def test_trade_schema_record_id_not_nullable(self):
        schema = get_bronze_trade_schema()
        record_id = [f for f in schema.fields if f.name == "record_id"][0]
        assert record_id.nullable is False

    def test_kline_schema_volume_is_double(self):
        from pyspark.sql.types import DoubleType
        schema = get_bronze_kline_schema()
        vol_field = [f for f in schema.fields if f.name == "volume"][0]
        assert isinstance(vol_field.dataType, DoubleType)


class TestBronzeAssetConfig:
    """Test the config dataclass"""

    def test_default_config_values(self):
        config = BronzeAssetConfig()
        assert config.symbol == "BTCUSDT"
        assert config.batch_size == 1000

    def test_custom_config_values(self):
        config = BronzeAssetConfig(symbol="ETHUSDT", batch_size=500)
        assert config.symbol == "ETHUSDT"
        assert config.batch_size == 500


class TestDepthStreamProcessing:
    """Test depth stream processing in the WebSocket client"""

    def test_depth_message_processing(self):
        from streaming.core.binance_websocket import BinanceWebSocketClient

        config = Mock()
        config.binance_base_url = "wss://stream.binance.com:9443/ws/"
        config.stream_definitions = {
            "trade": "trade",
            "depth5": "depth5@100ms",
        }

        client = BinanceWebSocketClient(
            ["BTCUSDT"], ["depth5"], Mock(), config
        )

        message = json.dumps({
            "stream": "btcusdt@depth5@100ms",
            "data": {
                "E": 1640995200000,
                "s": "BTCUSDT",
                "bids": [["49999.00", "1.00"], ["49998.00", "2.00"]],
                "asks": [["50001.00", "1.00"], ["50002.00", "2.00"]],
            }
        })

        result = client._process_message(message)

        assert result["symbol"] == "BTCUSDT"
        assert result["bid_count"] == 2
        assert result["ask_count"] == 2
        assert result["best_bid"] == 49999.00
        assert result["best_ask"] == 50001.00
        assert result["spread"] == 2.00

    def test_depth_quality_score_full(self):
        from streaming.core.binance_websocket import BinanceWebSocketClient

        config = Mock()
        config.stream_definitions = {}
        client = BinanceWebSocketClient([], [], Mock(), config)

        data = {
            "E": 1640995200000,
            "s": "BTCUSDT",
            "bids": [["49999.00", "1.00"]],
            "asks": [["50001.00", "1.00"]],
        }
        score = client._calculate_quality_score(data, "depthUpdate")
        assert score == 1.0

    def test_depth_quality_score_missing_bids(self):
        from streaming.core.binance_websocket import BinanceWebSocketClient

        config = Mock()
        config.stream_definitions = {}
        client = BinanceWebSocketClient([], [], Mock(), config)

        data = {
            "E": 1640995200000,
            "s": "BTCUSDT",
            "asks": [["50001.00", "1.00"]],
        }
        score = client._calculate_quality_score(data, "depthUpdate")
        assert score == 0.7  # -0.3 for missing bids

    def test_depth_quality_score_empty_both(self):
        from streaming.core.binance_websocket import BinanceWebSocketClient

        config = Mock()
        config.stream_definitions = {}
        client = BinanceWebSocketClient([], [], Mock(), config)

        data = {"E": 1640995200000, "s": "BTCUSDT"}
        score = client._calculate_quality_score(data, "depthUpdate")
        assert score == pytest.approx(0.4)  # -0.3 bids, -0.3 asks


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

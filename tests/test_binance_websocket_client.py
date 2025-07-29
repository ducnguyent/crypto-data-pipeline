import pytest
import asyncio
import json
import uuid
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime
import websockets
from typing import Dict, Any, List

# Import the class to test
from streaming.binance_websocket import BinanceWebSocketClient


@pytest.fixture
def mock_config():
    """Mock configuration object"""
    config = Mock()
    config.binance_base_url = "wss://stream.binance.com:9443/ws/"
    config.max_reconnect_attempts = 3
    config.ping_interval = 20
    config.ping_timeout = 10
    config.reconnect_interval = 5
    return config


@pytest.fixture
def symbols():
    """Test symbols"""
    return ["BTCUSDT", "ETHUSDT"]


@pytest.fixture
def streams():
    """Test streams"""
    return ["trade", "ticker", "kline_1m", "depth5"]


@pytest.fixture
def mock_callback():
    """Mock callback function"""
    return Mock()


@pytest.fixture
def ws_client(symbols, streams, mock_callback, mock_config):
    """WebSocket client fixture"""
    return BinanceWebSocketClient(symbols, streams, mock_callback, mock_config)


class TestBinanceWebSocketClientInitialization:
    """Test client initialization"""

    def test_initialization_success(self, symbols, streams, mock_callback, mock_config):
        """Test successful client initialization"""
        client = BinanceWebSocketClient(
            symbols, streams, mock_callback, mock_config)

        assert client.symbols == symbols
        assert client.streams == streams
        assert client.callback == mock_callback
        assert client.config == mock_config
        assert client.websocket is None
        assert client.running is False

    def test_initialization_with_empty_symbols(self, streams, mock_callback, mock_config):
        """Test initialization with empty symbols list"""
        client = BinanceWebSocketClient(
            [], streams, mock_callback, mock_config)
        assert client.symbols == []

    def test_initialization_with_empty_streams(self, symbols, mock_callback, mock_config):
        """Test initialization with empty streams list"""
        client = BinanceWebSocketClient(
            symbols, [], mock_callback, mock_config)
        assert client.streams == []


class TestStreamURLBuilding:
    """Test WebSocket stream URL building"""

    def test_build_stream_url_single_symbol_single_stream(self, mock_callback, mock_config):
        """Test URL building with single symbol and single stream"""
        client = BinanceWebSocketClient(
            ["BTCUSDT"], ["trade"], mock_callback, mock_config)
        url = client._build_stream_url()

        expected_url = "wss://stream.binance.com:9443/ws/btcusdt@trade"
        assert url == expected_url

    def test_build_stream_url_multiple_symbols_multiple_streams(self, ws_client):
        """Test URL building with multiple symbols and streams"""
        url = ws_client._build_stream_url()

        # Check that URL contains all expected streams
        assert "btcusdt@trade" in url
        assert "ethusdt@trade" in url
        assert "btcusdt@ticker" in url
        assert "ethusdt@ticker" in url
        assert "btcusdt@kline_1m" in url
        assert "ethusdt@kline_1m" in url
        assert "btcusdt@depth5@100ms" in url
        assert "ethusdt@depth5@100ms" in url

    def test_build_stream_url_depth_stream_formatting(self, mock_callback, mock_config):
        """Test that depth stream is formatted correctly"""
        client = BinanceWebSocketClient(
            ["BTCUSDT"], ["depth5"], mock_callback, mock_config)
        url = client._build_stream_url()

        assert "btcusdt@depth5@100ms" in url

    def test_build_stream_url_empty_streams_raises_error(self, mock_callback, mock_config):
        """Test that empty streams raises ValueError"""
        client = BinanceWebSocketClient(
            ["BTCUSDT"], [], mock_callback, mock_config)

        with pytest.raises(ValueError, match="No valid streams configured"):
            client._build_stream_url()

    def test_build_stream_url_invalid_stream_ignored(self, mock_callback, mock_config):
        """Test that invalid streams are ignored"""
        client = BinanceWebSocketClient(
            ["BTCUSDT"], ["invalid_stream"], mock_callback, mock_config)

        with pytest.raises(ValueError, match="No valid streams configured"):
            client._build_stream_url()


class TestDataQualityScoring:
    """Test data quality scoring functionality"""

    def test_quality_score_perfect_trade_message(self, ws_client):
        """Test quality score for perfect trade message"""
        data = {
            "E": 1640995200000,
            "s": "BTCUSDT",
            "p": "50000.00",
            "q": "0.001"
        }

        score = ws_client._calculate_quality_score(data, "trade")
        assert score == 1.0

    def test_quality_score_missing_event_time(self, ws_client):
        """Test quality score with missing event time"""
        data = {
            "s": "BTCUSDT",
            "p": "50000.00",
            "q": "0.001"
        }

        score = ws_client._calculate_quality_score(data, "trade")
        assert score == 0.7  # 1.0 - 0.3 for missing event time

    def test_quality_score_missing_symbol(self, ws_client):
        """Test quality score with missing symbol"""
        data = {
            "E": 1640995200000,
            "p": "50000.00",
            "q": "0.001"
        }

        score = ws_client._calculate_quality_score(data, "trade")
        assert score == 0.8  # 1.0 - 0.2 for missing symbol

    def test_quality_score_missing_price(self, ws_client):
        """Test quality score with missing price"""
        data = {
            "E": 1640995200000,
            "s": "BTCUSDT",
            "q": "0.001"
        }

        score = ws_client._calculate_quality_score(data, "trade")
        assert round(score, 1) == 0.6  # 1.0 - 0.2 for missing price - 0.2 for zero price

    def test_quality_score_zero_price(self, ws_client):
        """Test quality score with zero price"""
        data = {
            "E": 1640995200000,
            "s": "BTCUSDT",
            "p": "0.00",
            "q": "0.001"
        }

        score = ws_client._calculate_quality_score(data, "trade")
        assert score == 0.8  # 1.0 - 0.2 for zero price

    def test_quality_score_invalid_price_format(self, ws_client):
        """Test quality score with invalid price format"""
        data = {
            "E": 1640995200000,
            "s": "BTCUSDT",
            "p": "invalid_price",
            "q": "0.001"
        }

        score = ws_client._calculate_quality_score(data, "trade")
        assert score == 0.7  # 1.0 - 0.3 for invalid price format

    def test_quality_score_non_trade_stream(self, ws_client):
        """Test quality score for non-trade stream"""
        data = {
            "E": 1640995200000,
            "s": "BTCUSDT",
            "c": "50000.00"
        }

        score = ws_client._calculate_quality_score(data, "ticker")
        assert score == 1.0  # Only basic validation for non-trade streams

    def test_quality_score_minimum_zero(self, ws_client):
        """Test that quality score never goes below zero"""
        data = {}  # Empty data should result in very low score

        score = ws_client._calculate_quality_score(data, "trade")
        assert score >= 0.0


class TestWebSocketConnection:
    """Test WebSocket connection functionality"""

    @pytest.mark.asyncio
    async def test_connect_max_reconnection_attempts(self, ws_client):
        """Test that connection fails after max reconnection attempts"""
        with patch('websockets.connect', side_effect=Exception("Connection failed")):
            with patch('asyncio.sleep'):
                with pytest.raises(Exception, match="Connection failed"):
                    await ws_client.connect()

    @pytest.mark.asyncio
    async def test_disconnect(self, ws_client):
        """Test WebSocket disconnection"""
        mock_websocket = AsyncMock()
        ws_client.websocket = mock_websocket
        ws_client.running = True

        await ws_client.disconnect()

        assert ws_client.running is False
        mock_websocket.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_no_websocket(self, ws_client):
        """Test disconnection when no WebSocket exists"""
        ws_client.websocket = None
        ws_client.running = True

        # Should not raise exception
        await ws_client.disconnect()
        assert ws_client.running is False


class TestWebSocketListener:
    """Test WebSocket message listening functionality"""

    @pytest.mark.asyncio
    async def test_listen_processes_messages(self, ws_client):
        """Test that listener processes messages correctly"""
        # Mock messages
        messages = [
            json.dumps({
                "stream": "btcusdt@trade",
                "data": {"E": 1640995200000, "s": "BTCUSDT", "p": "50000", "q": "0.001"}
            }),
            json.dumps({
                "stream": "ethusdt@trade",
                "data": {"E": 1640995200001, "s": "ETHUSDT", "p": "4000", "q": "0.1"}
            })
        ]

        mock_websocket = AsyncMock()
        mock_websocket.__aiter__.return_value = iter(messages)
        ws_client.websocket = mock_websocket
        ws_client.running = True

        with patch.object(ws_client, '_process_message', side_effect=ws_client._process_message) as mock_process:
            await ws_client._listen()

            assert mock_process.call_count == 2
            assert ws_client.callback.call_count == 2

    @pytest.mark.asyncio
    async def test_listen_handles_callback_exception(self, ws_client):
        """Test that listener handles callback exceptions gracefully"""
        message = json.dumps({
            "stream": "btcusdt@trade",
            "data": {"E": 1640995200000, "s": "BTCUSDT", "p": "50000", "q": "0.001"}
        })

        mock_websocket = AsyncMock()
        mock_websocket.__aiter__.return_value = iter([message])
        ws_client.websocket = mock_websocket
        ws_client.running = True

        # Make callback raise exception
        ws_client.callback.side_effect = Exception("Callback error")

        # Should not raise exception, just log error
        await ws_client._listen()

    @pytest.mark.asyncio
    async def test_listen_handles_connection_closed(self, ws_client):
        """Test listener handles connection closed exception"""
        mock_websocket = AsyncMock()
        mock_websocket.__aiter__.side_effect = websockets.exceptions.ConnectionClosed(
            None, None)
        ws_client.websocket = mock_websocket
        ws_client.running = True

        with patch.object(ws_client, 'connect') as mock_connect:
            with patch('asyncio.sleep'):
                await ws_client._listen()
                mock_connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_listen_stops_when_not_running(self, ws_client):
        """Test that listener stops when running is False"""
        messages = ["message1", "message2"]

        mock_websocket = AsyncMock()
        ws_client.websocket = mock_websocket
        ws_client.running = False  # Set to False

        # Create an async iterator that yields messages
        async def async_iter():
            for msg in messages:
                yield msg

        mock_websocket.__aiter__ = async_iter

        await ws_client._listen()

        # Callback should not be called since running is False
        ws_client.callback.assert_not_called()


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_uuid_generation_uniqueness(self, ws_client):
        """Test that record IDs are unique"""
        message = json.dumps({
            "stream": "btcusdt@trade",
            "data": {"E": 1640995200000, "s": "BTCUSDT", "p": "50000", "q": "0.001"}
        })

        result1 = ws_client._process_message(message)
        result2 = ws_client._process_message(message)

        assert result1['record_id'] != result2['record_id']

    def test_message_processing_with_null_data(self, ws_client):
        """Test processing message with null data fields"""
        message = json.dumps({
            "stream": "btcusdt@trade",
            "data": {
                "E": None,
                "s": None,
                "p": None,
                "q": None
            }
        })

        result = ws_client._process_message(message)

        assert 'record_id' in result

    def test_extremely_long_message_truncation(self, ws_client):
        """Test that extremely long error messages are truncated"""
        very_long_message = "x" * 1000  # Very long invalid message

        result = ws_client._process_message(very_long_message)

        assert 'error' in result
        assert len(result['raw_message']) <= 500

    @pytest.mark.asyncio
    async def test_concurrent_disconnect_calls(self, ws_client):
        """Test multiple concurrent disconnect calls"""
        mock_websocket = AsyncMock()
        ws_client.websocket = mock_websocket
        ws_client.running = True

        # Call disconnect multiple times concurrently
        tasks = [ws_client.disconnect() for _ in range(3)]
        await asyncio.gather(*tasks)

        # Should not raise exception and websocket.close should be called at least once
        assert mock_websocket.close.call_count >= 1
        assert ws_client.running is False


# Performance and stress tests
class TestPerformance:
    """Performance and stress tests"""

    def test_message_processing_performance(self, ws_client):
        """Test message processing performance with many messages"""
        import time

        message = json.dumps({
            "stream": "btcusdt@trade",
            "data": {"E": 1640995200000, "s": "BTCUSDT", "p": "50000", "q": "0.001"}
        })

        start_time = time.time()

        # Process 1000 messages
        for _ in range(1000):
            ws_client._process_message(message)

        end_time = time.time()
        processing_time = end_time - start_time

        # Should process 1000 messages in less than 1 second
        assert processing_time < 1.0

        # Calculate messages per second
        messages_per_second = 1000 / processing_time
        print(f"Processed {messages_per_second:.0f} messages per second")

    def test_url_building_with_many_symbols(self, mock_callback, mock_config):
        """Test URL building performance with many symbols"""
        # Test with 100 symbols
        symbols = [f"SYMBOL{i}USDT" for i in range(100)]
        streams = ["trade", "ticker"]

        client = BinanceWebSocketClient(
            symbols, streams, mock_callback, mock_config)

        import time
        start_time = time.time()
        url = client._build_stream_url()
        end_time = time.time()

        # Should build URL quickly even with many symbols
        assert (end_time - start_time) < 0.1
        assert len(url) > 1000  # Should be a long URL


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])

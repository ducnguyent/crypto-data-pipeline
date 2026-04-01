"""Tests for the StreamingService orchestrator"""

import pytest
import asyncio
import json
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime


class TestStreamingServiceInit:
    """Test StreamingService initialization"""

    @patch("streaming.service.setup_logging")
    @patch("streaming.service.StreamingConfig")
    def test_service_creates_config(self, mock_config_cls, mock_logging):
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_config.environment = "development"
        mock_config.active_symbols = ["BTCUSDT"]
        mock_config.kafka_servers = "localhost:9092"
        mock_config_cls.load_from_env.return_value = mock_config

        from streaming.service import StreamingService
        service = StreamingService()

        assert service.config == mock_config
        assert service.producer is None
        assert service.websocket_client is None
        assert service.running is False

    @patch("streaming.service.setup_logging")
    @patch("streaming.service.StreamingConfig")
    def test_service_sets_up_logging(self, mock_config_cls, mock_logging):
        mock_config = Mock()
        mock_config.log_level = "DEBUG"
        mock_config.environment = "test"
        mock_config.active_symbols = []
        mock_config.kafka_servers = "localhost:9092"
        mock_config_cls.load_from_env.return_value = mock_config

        from streaming.service import StreamingService
        StreamingService()

        mock_logging.assert_called_once_with(
            level="DEBUG", service_name="streaming-service"
        )


class TestMessageCallback:
    """Test message routing from WebSocket to Kafka"""

    @patch("streaming.service.setup_logging")
    @patch("streaming.service.StreamingConfig")
    def test_callback_sends_to_producer(self, mock_config_cls, mock_logging):
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_config.environment = "test"
        mock_config.active_symbols = []
        mock_config.kafka_servers = "localhost:9092"
        mock_config_cls.load_from_env.return_value = mock_config

        from streaming.service import StreamingService
        service = StreamingService()
        service.producer = Mock()

        message = {"symbol": "BTCUSDT", "stream_type": "trade", "price": 50000.0}
        service.message_callback(message)

        service.producer.send_to_bronze_layer.assert_called_once_with(message)

    @patch("streaming.service.setup_logging")
    @patch("streaming.service.StreamingConfig")
    def test_callback_handles_no_producer(self, mock_config_cls, mock_logging):
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_config.environment = "test"
        mock_config.active_symbols = []
        mock_config.kafka_servers = "localhost:9092"
        mock_config_cls.load_from_env.return_value = mock_config

        from streaming.service import StreamingService
        service = StreamingService()
        service.producer = None

        # Should not raise
        message = {"symbol": "BTCUSDT"}
        service.message_callback(message)

    @patch("streaming.service.setup_logging")
    @patch("streaming.service.StreamingConfig")
    def test_callback_handles_producer_error(self, mock_config_cls, mock_logging):
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_config.environment = "test"
        mock_config.active_symbols = []
        mock_config.kafka_servers = "localhost:9092"
        mock_config_cls.load_from_env.return_value = mock_config

        from streaming.service import StreamingService
        service = StreamingService()
        service.producer = Mock()
        service.producer.send_to_bronze_layer.side_effect = Exception("Kafka error")

        # Should not raise — errors are caught
        message = {"symbol": "BTCUSDT"}
        service.message_callback(message)


class TestGracefulShutdown:
    """Test stop/disconnect behavior"""

    @pytest.mark.asyncio
    @patch("streaming.service.setup_logging")
    @patch("streaming.service.StreamingConfig")
    async def test_stop_disconnects_websocket(self, mock_config_cls, mock_logging):
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_config.environment = "test"
        mock_config.active_symbols = []
        mock_config.kafka_servers = "localhost:9092"
        mock_config_cls.load_from_env.return_value = mock_config

        from streaming.service import StreamingService
        service = StreamingService()
        service.websocket_client = AsyncMock()
        service.producer = Mock()
        service.running = True

        await service.stop()

        assert service.running is False
        service.websocket_client.disconnect.assert_called_once()
        service.producer.close.assert_called_once()

    @pytest.mark.asyncio
    @patch("streaming.service.setup_logging")
    @patch("streaming.service.StreamingConfig")
    async def test_stop_handles_no_clients(self, mock_config_cls, mock_logging):
        mock_config = Mock()
        mock_config.log_level = "INFO"
        mock_config.environment = "test"
        mock_config.active_symbols = []
        mock_config.kafka_servers = "localhost:9092"
        mock_config_cls.load_from_env.return_value = mock_config

        from streaming.service import StreamingService
        service = StreamingService()

        # Should not raise when clients are None
        await service.stop()
        assert service.running is False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

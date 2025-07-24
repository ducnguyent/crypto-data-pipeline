import pytest
import asyncio
import json
import uuid
from unittest.mock import Mock, AsyncMock, MagicMock
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
import websockets


# ========================================
# Pytest Configuration
# ========================================

def pytest_configure(config):
    """Configure pytest with custom markers and settings"""
    config.addinivalue_line(
        "markers", "unit: Unit tests that don't require external dependencies"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests that may require external services"
    )
    config.addinivalue_line(
        "markers", "performance: Performance and load tests"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take longer to run"
    )
    config.addinivalue_line(
        "markers", "asyncio: Async tests"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers automatically"""
    for item in items:
        # Add asyncio marker to async test functions
        if asyncio.iscoroutinefunction(item.function):
            item.add_marker(pytest.mark.asyncio)

        # Add unit marker to most tests by default
        if not any(mark.name in ['integration', 'performance'] for mark in item.iter_markers()):
            item.add_marker(pytest.mark.unit)


# ========================================
# Event Loop and Async Fixtures
# ========================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the session"""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def async_context():
    """Provide async context for tests"""
    yield
    # Cleanup any pending tasks
    tasks = [task for task in asyncio.all_tasks() if not task.done()]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


# ========================================
# Configuration Fixtures
# ========================================

@pytest.fixture
def base_config():
    """Base configuration object"""
    config = Mock()
    config.binance_base_url = "wss://stream.binance.com:9443/ws/"
    config.max_reconnect_attempts = 3
    config.ping_interval = 20
    config.ping_timeout = 10
    config.reconnect_interval = 5
    config.message_batch_size = 100
    config.quality_threshold = 0.8
    return config


@pytest.fixture
def test_config(base_config):
    """Test-specific configuration with faster timeouts"""
    base_config.max_reconnect_attempts = 2
    base_config.ping_interval = 5
    base_config.ping_timeout = 3
    base_config.reconnect_interval = 1
    return base_config


@pytest.fixture
def production_config(base_config):
    """Production-like configuration"""
    base_config.max_reconnect_attempts = 10
    base_config.ping_interval = 30
    base_config.ping_timeout = 15
    base_config.reconnect_interval = 10
    base_config.message_batch_size = 1000
    return base_config


# ========================================
# Symbol and Stream Fixtures
# ========================================

@pytest.fixture
def single_symbol():
    """Single symbol for testing"""
    return ["BTCUSDT"]


@pytest.fixture
def multiple_symbols():
    """Multiple symbols for testing"""
    return ["BTCUSDT", "ETHUSDT", "ADAUSDT"]


@pytest.fixture
def many_symbols():
    """Many symbols for performance testing"""
    return [f"SYMBOL{i}USDT" for i in range(50)]


@pytest.fixture
def single_stream():
    """Single stream for testing"""
    return ["trade"]


@pytest.fixture
def multiple_streams():
    """Multiple streams for testing"""
    return ["trade", "ticker", "kline_1m", "depth5"]


@pytest.fixture
def all_streams():
    """All available streams"""
    return ["trade", "ticker", "kline_1m", "depth5", "depth10", "depth20"]


# ========================================
# Mock Objects and Services
# ========================================

@pytest.fixture
def mock_callback():
    """Mock callback function with tracking"""
    callback = Mock()
    callback.call_history = []

    def side_effect(data):
        callback.call_history.append({
            'timestamp': datetime.now(),
            'data': data.copy() if isinstance(data, dict) else data
        })
        return data

    callback.side_effect = side_effect
    return callback


@pytest.fixture
def mock_logger():
    """Mock logger for testing logging behavior"""
    logger = Mock(spec=logging.Logger)
    logger.info = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    logger.debug = Mock()
    return logger


@pytest.fixture
def mock_websocket():
    """Basic mock WebSocket connection"""
    websocket = AsyncMock()
    websocket.ping = AsyncMock()
    websocket.pong = AsyncMock()
    websocket.close = AsyncMock()
    websocket.closed = False
    return websocket


@pytest.fixture
def mock_websocket_with_messages():
    """Mock WebSocket that yields test messages"""
    def create_websocket(messages: List[str]):
        websocket = AsyncMock()
        websocket.__aiter__ = lambda: iter(messages).__aiter__()
        websocket.close = AsyncMock()
        websocket.closed = False
        return websocket
    return create_websocket


# ========================================
# Test Data Fixtures
# ========================================

@pytest.fixture
def sample_trade_data():
    """Sample trade message data"""
    return {
        "E": int(datetime.now().timestamp() * 1000),  # Event time
        "s": "BTCUSDT",                               # Symbol
        "t": 12345,                                   # Trade ID
        "p": "50000.00",                             # Price
        "q": "0.001",                                # Quantity
        "b": 88,                                     # Buyer order ID
        "a": 50,                                     # Seller order ID
        "T": int(datetime.now().timestamp() * 1000),  # Trade time
        "m": False,                                  # Is buyer maker
        "M": True                                    # Ignore
    }


@pytest.fixture
def sample_ticker_data():
    """Sample ticker message data"""
    return {
        "E": int(datetime.now().timestamp() * 1000),  # Event time
        "s": "BTCUSDT",                               # Symbol
        "c": "50000.00",                             # Close price
        "o": "49900.00",                             # Open price
        "h": "50100.00",                             # High price
        "l": "49800.00",                             # Low price
        "v": "1000.00",                              # Volume
        "q": "50000000.00",                          # Quote volume
        # Open time
        "O": int((datetime.now() - timedelta(hours=24)).timestamp() * 1000),
        "C": int(datetime.now().timestamp() * 1000),  # Close time
        "F": 0,                                      # First trade ID
        "L": 18150,                                  # Last trade ID
        "n": 18151                                   # Count
    }


@pytest.fixture
def sample_kline_data():
    """Sample kline message data"""
    return {
        "E": int(datetime.now().timestamp() * 1000),  # Event time
        "s": "BTCUSDT",                               # Symbol
        "k": {
            "t": int(datetime.now().timestamp() * 1000),  # Kline start time
            "T": int(datetime.now().timestamp() * 1000),  # Kline close time
            "s": "BTCUSDT",                               # Symbol
            "i": "1m",                                    # Interval
            "f": 100,                                     # First trade ID
            "L": 200,                                     # Last trade ID
            "o": "49999.00",                             # Open price
            "c": "50000.00",                             # Close price
            "h": "50001.00",                             # High price
            "l": "49998.00",                             # Low price
            "v": "100.00",                               # Volume
            "n": 101,                                    # Number of trades
            "x": False,                                  # Is kline closed
            "q": "5000000.00",                           # Quote asset volume
            "V": "50.00",                                # Taker buy base volume
            "Q": "2500000.00",                           # Taker buy quote volume
            "B": "123456"                                # Ignore
        }
    }


@pytest.fixture
def sample_depth_data():
    """Sample depth message data"""
    return {
        "E": int(datetime.now().timestamp() * 1000),  # Event time
        "s": "BTCUSDT",                               # Symbol
        "bids": [                                     # Bids
            ["49999.00", "1.00"],
            ["49998.00", "2.00"],
            ["49997.00", "3.00"],
            ["49996.00", "4.00"],
            ["49995.00", "5.00"]
        ],
        "asks": [                                     # Asks
            ["50001.00", "1.00"],
            ["50002.00", "2.00"],
            ["50003.00", "3.00"],
            ["50004.00", "4.00"],
            ["50005.00", "5.00"]
        ]
    }


@pytest.fixture
def sample_messages(sample_trade_data, sample_ticker_data, sample_kline_data, sample_depth_data):
    """Collection of sample WebSocket messages"""
    return {
        "trade": json.dumps({
            "stream": "btcusdt@trade",
            "data": sample_trade_data
        }),
        "ticker": json.dumps({
            "stream": "btcusdt@ticker",
            "data": sample_ticker_data
        }),
        "kline": json.dumps({
            "stream": "btcusdt@kline_1m",
            "data": sample_kline_data
        }),
        "depth": json.dumps({
            "stream": "btcusdt@depth5@100ms",
            "data": sample_depth_data
        })
    }


@pytest.fixture
def invalid_messages():
    """Collection of invalid messages for testing error handling"""
    return {
        "invalid_json": "invalid json string {{{",
        "missing_stream": json.dumps({
            "data": {"E": 123456, "s": "BTCUSDT"}
        }),
        "missing_data": json.dumps({
            "stream": "btcusdt@trade"
        }),
        "empty_data": json.dumps({
            "stream": "btcusdt@trade",
            "data": {}
        }),
        "null_fields": json.dumps({
            "stream": "btcusdt@trade",
            "data": {
                "E": None,
                "s": None,
                "p": None,
                "q": None
            }
        }),
        "invalid_price": json.dumps({
            "stream": "btcusdt@trade",
            "data": {
                "E": 123456,
                "s": "BTCUSDT",
                "p": "invalid_price",
                "q": "0.001"
            }
        })
    }


# ========================================
# WebSocket Client Fixtures
# ========================================

@pytest.fixture
def ws_client_factory():
    """Factory for creating WebSocket clients with different configurations"""
    def create_client(symbols=None, streams=None, callback=None, config=None):
        from binance_websocket_client import BinanceWebSocketClient

        if symbols is None:
            symbols = ["BTCUSDT", "ETHUSDT"]
        if streams is None:
            streams = ["trade", "ticker"]
        if callback is None:
            callback = Mock()
        if config is None:
            config = Mock()
            config.binance_base_url = "wss://stream.binance.com:9443/ws/"
            config.max_reconnect_attempts = 3
            config.ping_interval = 20
            config.ping_timeout = 10
            config.reconnect_interval = 5

        return BinanceWebSocketClient(symbols, streams, callback, config)

    return create_client


@pytest.fixture
def basic_ws_client(multiple_symbols, multiple_streams, mock_callback, test_config):
    """Basic WebSocket client for most tests"""
    from binance_websocket_client import BinanceWebSocketClient
    return BinanceWebSocketClient(multiple_symbols, multiple_streams, mock_callback, test_config)


@pytest.fixture
def single_symbol_ws_client(single_symbol, single_stream, mock_callback, test_config):
    """WebSocket client with single symbol and stream"""
    from binance_websocket_client import BinanceWebSocketClient
    return BinanceWebSocketClient(single_symbol, single_stream, mock_callback, test_config)


# ========================================
# Test Utilities and Helpers
# ========================================

@pytest.fixture
def message_generator():
    """Utility to generate test messages"""
    def generate(message_type: str, symbol: str = "BTCUSDT", **kwargs):
        base_data = {
            "E": int(datetime.now().timestamp() * 1000),
            "s": symbol
        }

        if message_type == "trade":
            base_data.update({
                "p": kwargs.get("price", "50000.00"),
                "q": kwargs.get("quantity", "0.001"),
                "t": kwargs.get("trade_id", 12345)
            })
            stream = f"{symbol.lower()}@trade"
        elif message_type == "ticker":
            base_data.update({
                "c": kwargs.get("close", "50000.00"),
                "o": kwargs.get("open", "49900.00"),
                "v": kwargs.get("volume", "1000.00")
            })
            stream = f"{symbol.lower()}@ticker"
        elif message_type == "kline":
            base_data["k"] = {
                "o": kwargs.get("open", "49999.00"),
                "c": kwargs.get("close", "50000.00"),
                "h": kwargs.get("high", "50001.00"),
                "l": kwargs.get("low", "49998.00"),
                "v": kwargs.get("volume", "100.00")
            }
            stream = f"{symbol.lower()}@kline_1m"
        elif message_type == "depth":
            base_data.update({
                "bids": kwargs.get("bids", [["49999.00", "1.00"]]),
                "asks": kwargs.get("asks", [["50001.00", "1.00"]])
            })
            stream = f"{symbol.lower()}@depth5@100ms"
        else:
            raise ValueError(f"Unknown message type: {message_type}")

        return json.dumps({
            "stream": stream,
            "data": base_data
        })

    return generate


@pytest.fixture
def quality_scorer():
    """Utility for testing data quality scoring"""
    def score_data(data: Dict[str, Any], stream_type: str):
        """Calculate expected quality score for test data"""
        score = 1.0

        # Basic validation
        if 'E' not in data or data['E'] is None:
            score -= 0.3
        if 's' not in data or data['s'] is None:
            score -= 0.2

        # Stream-specific validation
        if stream_type == "trade":
            required_fields = ['p', 'q']
            for field in required_fields:
                if field not in data or data[field] is None:
                    score -= 0.2

            try:
                if float(data.get('p', 0)) <= 0:
                    score -= 0.2
            except (ValueError, TypeError):
                score -= 0.3

        return max(0.0, score)

    return score_data


@pytest.fixture
def connection_simulator():
    """Simulate various WebSocket connection scenarios"""
    class ConnectionSimulator:
        def __init__(self):
            self.connection_attempts = 0
            self.fail_count = 0
            self.messages = []

        def set_failure_count(self, count: int):
            """Set how many times connection should fail before succeeding"""
            self.fail_count = count

        def set_messages(self, messages: List[str]):
            """Set messages to be returned after successful connection"""
            self.messages = messages

        async def simulate_connect(self, *args, **kwargs):
            """Simulate WebSocket connection with controlled failures"""
            self.connection_attempts += 1

            if self.connection_attempts <= self.fail_count:
                raise Exception(
                    f"Simulated connection failure #{self.connection_attempts}")

            # Create mock websocket that returns our messages
            websocket = AsyncMock()
            websocket.__aiter__ = lambda: iter(self.messages).__aiter__()
            websocket.close = AsyncMock()
            websocket.closed = False
            return websocket

        def reset(self):
            """Reset simulator state"""
            self.connection_attempts = 0
            self.fail_count = 0
            self.messages = []

    return ConnectionSimulator()


@pytest.fixture
def performance_monitor():
    """Monitor performance metrics during tests"""
    class PerformanceMonitor:
        def __init__(self):
            self.metrics = {}

        def start_timer(self, name: str):
            """Start timing an operation"""
            self.metrics[name] = {
                'start': datetime.now(),
                'end': None,
                'duration': None
            }

        def end_timer(self, name: str):
            """End timing an operation"""
            if name in self.metrics:
                self.metrics[name]['end'] = datetime.now()
                self.metrics[name]['duration'] = (
                    self.metrics[name]['end'] - self.metrics[name]['start']
                ).total_seconds()

        def get_duration(self, name: str) -> Optional[float]:
            """Get duration of an operation in seconds"""
            return self.metrics.get(name, {}).get('duration')

        def assert_duration_under(self, name: str, max_seconds: float):
            """Assert that operation completed under specified time"""
            duration = self.get_duration(name)
            assert duration is not None, f"Timer '{name}' was not started/ended"
            assert duration < max_seconds, f"Operation '{name}' took {duration}s, expected < {max_seconds}s"

    return PerformanceMonitor()


# ========================================
# Test Environment Setup
# ========================================

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Setup test environment (runs once per test session)"""
    # Configure logging for tests
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Disable some noisy loggers during testing
    logging.getLogger('websockets').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)

    yield

    # Cleanup after all tests
    pass


@pytest.fixture(autouse=True)
def setup_test_isolation():
    """Setup for each individual test (isolation)"""
    # Reset any global state if needed
    yield

    # Cleanup after each test
    # Cancel any remaining async tasks
    loop = None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        pass

    if loop:
        tasks = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in tasks:
            task.cancel()


# ========================================
# Custom Pytest Markers and Fixtures
# ========================================

@pytest.fixture
def skip_if_no_network():
    """Skip test if no network connection available"""
    import socket
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=3)
        return False
    except OSError:
        pytest.skip("No network connection available")


@pytest.fixture
def temp_log_file(tmp_path):
    """Create temporary log file for tests"""
    log_file = tmp_path / "test.log"
    yield str(log_file)
    # Cleanup happens automatically with tmp_path


# ========================================
# Parametrized Test Data
# ========================================

@pytest.fixture(params=[
    ["BTCUSDT"],
    ["BTCUSDT", "ETHUSDT"],
    ["BTCUSDT", "ETHUSDT", "ADAUSDT", "DOTUSDT"]
])
def various_symbol_lists(request):
    """Various symbol list configurations for parametrized tests"""
    return request.param


@pytest.fixture(params=[
    ["trade"],
    ["trade", "ticker"],
    ["trade", "ticker", "kline_1m"],
    ["trade", "ticker", "kline_1m", "depth5"]
])
def various_stream_lists(request):
    """Various stream list configurations for parametrized tests"""
    return request.param


@pytest.fixture(params=[
    (1, 0.1),  # 1 second timeout, 0.1 second interval
    (5, 0.5),  # 5 second timeout, 0.5 second interval
    (10, 1.0)  # 10 second timeout, 1 second interval
])
def timeout_configurations(request):
    """Various timeout configurations for testing"""
    timeout, interval = request.param
    return {"timeout": timeout, "interval": interval}

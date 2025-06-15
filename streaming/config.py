from shared.settings import BaseConfig
import os
from typing import List
from dataclasses import dataclass, field
import sys
from pathlib import Path

# Add shared to path
sys.path.append(str(Path(__file__).parent.parent))


@dataclass
class StreamingConfig(BaseConfig):
    """Configuration specific to streaming service"""

    # Kafka configuration
    kafka_servers: str = field(default_factory=lambda: os.getenv(
        "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"))
    kafka_topic_prefix: str = "crypto_raw_"
    kafka_batch_size: int = 16384
    kafka_linger_ms: int = 10

    # Binance WebSocket configuration
    binance_base_url: str = "wss://stream.binance.com:9443/ws/"
    reconnect_interval: int = field(
        default_factory=lambda: int(os.getenv("RECONNECT_INTERVAL", "5")))
    ping_interval: int = field(default_factory=lambda: int(
        os.getenv("PING_INTERVAL", "20")))
    ping_timeout: int = 10
    max_reconnect_attempts: int = 10

    def __post_init__(self):
        """Initialize symbol configuration after creation"""
        self._load_symbols_from_yaml()

    @classmethod
    def load_from_env(cls) -> "StreamingConfig":
        """Load configuration from environment variables"""
        return cls()

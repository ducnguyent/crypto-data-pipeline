import os
from typing import List, Dict
from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class SymbolConfig:
    """Configuration for a single trading symbol"""
    symbol: str
    name: str
    priority: int = 2
    enabled: bool = True
    streams: List[str] = field(default_factory=lambda: [
                               "trade", "ticker", "kline_1m"])


@dataclass
class BaseConfig:
    """Base configuration shared across services"""

    # Environment
    environment: str = field(
        default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    # Symbol configuration
    _symbol_configs: Dict[str, SymbolConfig] = field(default_factory=dict)
    _stream_definitions: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        self._load_symbols_from_yaml()

    @property
    def stream_definitions(self) -> Dict[str, str]:
        """Get stream definitions"""
        return self._stream_definitions

    @property
    def active_symbols(self) -> List[str]:
        """Get list of active symbols based on environment"""
        if env_override := os.getenv("ACTIVE_SYMBOLS"):
            return [s.strip().upper() for s in env_override.split(",")]

        # Filter symbols based on environment and priority
        active = []
        max_priority = 1 if self.environment == "development" else 3

        for symbol, config in self._symbol_configs.items():
            if config.enabled and config.priority <= max_priority:
                active.append(symbol)

        return active or ["BTCUSDT", "ETHUSDT"]  # Fallback

    def get_symbol_config(self, symbol: str) -> SymbolConfig:
        """Get configuration for a specific symbol"""
        return self._symbol_configs.get(symbol.upper())

    def _load_symbols_from_yaml(self) -> None:
        """Load symbols from YAML configuration"""
        # Default stream definitions
        self._stream_definitions = {
            "trade": "trade",
            "ticker": "ticker",
            "kline_1m": "kline_1m",
            "depth5": "depth5@100ms"
        }

        try:
            config_path = Path(__file__).parent / ".." / \
                "config" / "symbols.yaml"
            with open(config_path, 'r') as file:
                config = yaml.safe_load(file)

            for symbol, data in config.get("symbols", {}).items():
                if isinstance(data, dict):
                    self._symbol_configs[symbol.upper()] = SymbolConfig(
                        symbol=symbol.upper(),
                        name=data.get("name", symbol),
                        priority=data.get("priority", 2),
                        enabled=data.get("enabled", True),
                        streams=data.get(
                            "streams", ["trade", "ticker", "kline_1m"])
                    )

            # Load stream definitions if present
            stream_defs = config.get("stream_definitions")
            if stream_defs and isinstance(stream_defs, dict):
                self._stream_definitions.update(stream_defs)

        except FileNotFoundError:
            # Default symbols
            self._symbol_configs = {
                "BTCUSDT": SymbolConfig("BTCUSDT", "Bitcoin", 1),
                "ETHUSDT": SymbolConfig("ETHUSDT", "Ethereum", 1)
            }

import json
import logging
import asyncio
import websockets
from typing import Dict, Any, Callable, List
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class BinanceWebSocketClient:
    """Enhanced Binance WebSocket client"""

    def __init__(self, symbols: List[str], streams: List[str], callback: Callable, config):
        self.symbols = symbols
        self.streams = streams
        self.callback = callback
        self.config = config
        self.websocket = None
        self.running = False

        logger.info(f"WebSocket client initialized for {len(symbols)} symbols")

    def _build_stream_url(self) -> str:
        """Build WebSocket URL with multiple streams"""
        stream_list = []

        for symbol in self.symbols:
            symbol_lower = symbol.lower()
            for stream in self.streams:
                if stream == "trade":
                    stream_list.append(f"{symbol_lower}@trade")
                elif stream == "ticker":
                    stream_list.append(f"{symbol_lower}@ticker")
                elif stream == "kline_1m":
                    stream_list.append(f"{symbol_lower}@kline_1m")
                elif stream == "depth5":
                    stream_list.append(f"{symbol_lower}@depth5@100ms")

        if not stream_list:
            raise ValueError("No valid streams configured")

        stream_names = "/".join(stream_list)
        url = f"{self.config.binance_base_url}{stream_names}"

        logger.info(f"WebSocket URL built with {len(stream_list)} streams")
        return url

    def _process_message(self, raw_message: str) -> Dict[str, Any]:
        """Process and enrich raw WebSocket message"""
        try:
            data = json.loads(raw_message)
            stream = data.get('stream', '')
            event_data = data.get('data', data)

            symbol = self._extract_symbol(stream)
            stream_type = self._extract_stream_type(stream)

            processed_message = {
                'record_id': str(uuid.uuid4()),
                'symbol': symbol,
                'stream_type': stream_type,
                'event_time': event_data.get('E', int(datetime.now().timestamp() * 1000)),
                'received_time': int(datetime.now().timestamp() * 1000),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'raw_data': json.dumps(event_data),
                'data_quality_score': self._calculate_quality_score(event_data, stream_type)
            }

            return processed_message

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            return {
                'record_id': str(uuid.uuid4()),
                'error': str(e),
                'raw_message': raw_message[:500],  # Truncate for logging
                'received_time': int(datetime.now().timestamp() * 1000),
                'data_quality_score': 0.0
            }

    def _extract_symbol(self, stream: str) -> str:
        """Extract symbol from stream name"""
        return stream.split('@')[0].upper() if '@' in stream else 'UNKNOWN'

    def _extract_stream_type(self, stream: str) -> str:
        """Extract stream type from stream name"""
        return stream.split('@')[1].split('@')[0] if '@' in stream else 'unknown'

    def _calculate_quality_score(self, data: Dict[str, Any], stream_type: str) -> float:
        """Calculate data quality score"""
        score = 1.0

        # Basic validation
        if 'E' not in data:  # Event time
            score -= 0.3
        if 's' not in data:  # Symbol
            score -= 0.2

        # Stream-specific validation
        if stream_type == "trade":
            required_fields = ['p', 'q']  # price, quantity
            for field in required_fields:
                if field not in data:
                    score -= 0.2
            try:
                if float(data.get('p', 0)) <= 0:
                    score -= 0.2
            except (ValueError, TypeError):
                score -= 0.3

        return max(0.0, score)

    async def connect(self):
        """Connect to WebSocket and start streaming"""
        url = self._build_stream_url()
        reconnect_count = 0

        while reconnect_count < self.config.max_reconnect_attempts:
            try:
                logger.info(
                    f"Connecting to Binance WebSocket (attempt {reconnect_count + 1})")

                self.websocket = await websockets.connect(
                    url,
                    ping_interval=self.config.ping_interval,
                    ping_timeout=self.config.ping_timeout
                )

                self.running = True
                reconnect_count = 0
                logger.info("Successfully connected to Binance WebSocket")

                await self._listen()

            except Exception as e:
                reconnect_count += 1
                logger.error(f"WebSocket connection error: {e}")

                if reconnect_count < self.config.max_reconnect_attempts:
                    await asyncio.sleep(self.config.reconnect_interval * reconnect_count)
                else:
                    logger.error("Max reconnection attempts reached")
                    raise

    async def _listen(self):
        """Listen for WebSocket messages"""
        message_count = 0
        last_log_time = datetime.now()

        try:
            async for message in self.websocket:
                if not self.running:
                    break

                message_count += 1
                processed_message = self._process_message(message)

                try:
                    self.callback(processed_message)
                except Exception as e:
                    logger.error(f"Error in message callback: {e}")

                # Periodic logging
                now = datetime.now()
                if (now - last_log_time).seconds >= 60:
                    logger.info(
                        f"Processed {message_count} messages in last minute")
                    message_count = 0
                    last_log_time = now

        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            if self.running:
                await asyncio.sleep(self.config.reconnect_interval)
                await self.connect()
        except Exception as e:
            logger.error(f"Error in WebSocket listener: {e}")
            if self.running:
                await asyncio.sleep(self.config.reconnect_interval)
                await self.connect()

    async def disconnect(self):
        """Disconnect from WebSocket"""
        self.running = False
        if self.websocket:
            await self.websocket.close()
            logger.info("Disconnected from Binance WebSocket")

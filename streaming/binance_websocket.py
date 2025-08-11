import json
import logging
import asyncio
import websockets
from typing import Dict, Any, Callable, List
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class BinanceWebSocketClient:
    """Enhanced Binance WebSocket client with correct stream mappings"""

    def __init__(self, symbols: List[str], streams: List[str], callback: Callable, config):
        self.symbols = symbols
        self.streams = streams
        self.callback = callback
        self.config = config
        self.websocket = None
        self.running = False
        
        # Map internal stream names to Binance stream names
        self.stream_map = {
            'trade': 'trade',
            'ticker': 'ticker',  # Will produce 24hrTicker events
            'kline_1m': 'kline_1m',  # Will produce kline events
            'depth5': 'depth5'
        }

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
                    stream_list.append(f"{symbol_lower}@ticker")  # 24hr ticker
                elif stream == "kline_1m":
                    stream_list.append(f"{symbol_lower}@kline_1m")
                elif stream == "depth5":
                    stream_list.append(f"{symbol_lower}@depth5@100ms")

        if not stream_list:
            raise ValueError("No valid streams configured")

        stream_names = "/".join(stream_list)
        url = f"{self.config.binance_base_url}{stream_names}"

        logger.info(f"WebSocket URL built with {len(stream_list)} streams")
        logger.debug(f"Streams: {stream_list}")
        return url

    def _process_message(self, raw_message: str) -> Dict[str, Any]:
        """Process and enrich raw WebSocket message"""
        try:
            data = json.loads(raw_message)
            
            # Handle both direct messages and wrapped messages
            if 'stream' in data and 'data' in data:
                # Multi-stream format
                stream_name = data['stream']
                event_data = data['data']
            else:
                # Single stream format
                event_data = data
                stream_name = None
            
            # Extract symbol and event type
            symbol = event_data.get('s', "UNKNOWN")
            
            # Get the actual event type from Binance
            # This is what creates your topic names
            stream_type = event_data.get('e', 'unknown')
            
            # Log for debugging
            if stream_type not in ['trade', '24hrTicker', 'kline', 'depthUpdate']:
                logger.warning(f"Unexpected stream type: {stream_type} for symbol {symbol}")

            processed_message = {
                'record_id': str(uuid.uuid4()),
                'symbol': symbol,
                'stream_type': stream_type,  # This becomes part of your topic name!
                'stream_name': stream_name,  # Original stream name if available
                'event_time': event_data.get('E', int(datetime.now().timestamp() * 1000)),
                'received_time': int(datetime.now().timestamp() * 1000),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'raw_data': json.dumps(event_data),  # Store just the event data
                'data_quality_score': self._calculate_quality_score(event_data, stream_type)
            }
            
            # Add specific fields based on stream type
            if stream_type == 'trade':
                processed_message.update({
                    'price': float(event_data.get('p', 0)),
                    'quantity': float(event_data.get('q', 0)),
                    'trade_id': event_data.get('t'),
                    'is_buyer_maker': event_data.get('m', False)
                })
            elif stream_type == '24hrTicker':
                processed_message.update({
                    'price_change': float(event_data.get('p', 0)),
                    'price_change_percent': float(event_data.get('P', 0)),
                    'last_price': float(event_data.get('c', 0)),
                    'volume': float(event_data.get('v', 0)),
                    'quote_volume': float(event_data.get('q', 0))
                })
            elif stream_type == 'kline':
                kline_data = event_data.get('k', {})
                processed_message.update({
                    'interval': kline_data.get('i'),
                    'open': float(kline_data.get('o', 0)),
                    'high': float(kline_data.get('h', 0)),
                    'low': float(kline_data.get('l', 0)),
                    'close': float(kline_data.get('c', 0)),
                    'volume': float(kline_data.get('v', 0)),
                    'is_closed': kline_data.get('x', False)
                })

            return processed_message

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            logger.debug(f"Raw message: {raw_message[:500]}")
            return {
                'record_id': str(uuid.uuid4()),
                'error': str(e),
                'raw_message': raw_message[:500],  # Truncate for logging
                'received_time': int(datetime.now().timestamp() * 1000),
                'data_quality_score': 0.0
            }

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
            required_fields = ['p', 'q', 't']  # price, quantity, trade_id
            for field in required_fields:
                if field not in data:
                    score -= 0.15
            try:
                if float(data.get('p', 0)) <= 0:
                    score -= 0.2
                if float(data.get('q', 0)) <= 0:
                    score -= 0.1
            except (ValueError, TypeError):
                score -= 0.3
                
        elif stream_type == "24hrTicker":
            required_fields = ['c', 'v']  # close price, volume
            for field in required_fields:
                if field not in data:
                    score -= 0.2
                    
        elif stream_type == "kline":
            if 'k' not in data:
                score -= 0.5
            else:
                kline = data['k']
                required_fields = ['o', 'h', 'l', 'c', 'v']
                for field in required_fields:
                    if field not in kline:
                        score -= 0.1

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
                    wait_time = self.config.reconnect_interval * reconnect_count
                    logger.info(f"Waiting {wait_time} seconds before reconnecting...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error("Max reconnection attempts reached")
                    raise

    async def _listen(self):
        """Listen for WebSocket messages"""
        message_count = 0
        last_log_time = datetime.now()
        stream_type_counts = {}

        try:
            async for message in self.websocket:
                if not self.running:
                    break

                message_count += 1
                processed_message = self._process_message(message)
                
                # Track stream types for logging
                stream_type = processed_message.get('stream_type', 'unknown')
                stream_type_counts[stream_type] = stream_type_counts.get(stream_type, 0) + 1

                try:
                    self.callback(processed_message)
                except Exception as e:
                    logger.error(f"Error in message callback: {e}")

                # Periodic logging
                now = datetime.now()
                if (now - last_log_time).seconds >= 60:
                    logger.info(
                        f"Processed {message_count} messages in last minute. "
                        f"Types: {stream_type_counts}"
                    )
                    message_count = 0
                    stream_type_counts = {}
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
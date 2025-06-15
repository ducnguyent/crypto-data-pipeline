from shared.logging_config import setup_logging
from streaming.kafka_producer import StreamingProducer
from streaming.binance_websocket import BinanceWebSocketClient
from streaming.config import StreamingConfig
import asyncio
import logging
import signal
import sys
from pathlib import Path
from typing import Dict, Any

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))


logger = logging.getLogger(__name__)


class StreamingService:
    """Main streaming service orchestrator"""

    def __init__(self):
        self.config = StreamingConfig.load_from_env()
        self.producer = None
        self.websocket_client = None
        self.running = False
        self.shutdown_event = asyncio.Event()

        # Setup logging
        setup_logging(level=self.config.log_level,
                      service_name="streaming-service")

        # Log configuration
        self._log_startup_info()

    def _log_startup_info(self):
        """Log service configuration on startup"""
        logger.info("=== Streaming Service Starting ===")
        logger.info(f"Environment: {self.config.environment}")
        logger.info(f"Active symbols: {self.config.active_symbols}")
        logger.info(f"Kafka servers: {self.config.kafka_servers}")
        logger.info(f"Log level: {self.config.log_level}")
        logger.info("===================================")

    def message_callback(self, message: Dict[str, Any]) -> None:
        """Handle processed WebSocket messages"""
        try:
            if self.producer:
                self.producer.send_to_bronze_layer(message)
        except Exception as e:
            logger.error(f"Error in message callback: {e}")

    async def start(self):
        """Start the streaming service"""
        logger.info("Starting streaming service...")

        try:
            # Validate configuration
            if not self.config.active_symbols:
                raise ValueError("No active symbols configured")

            # Initialize Kafka producer
            self.producer = StreamingProducer(self.config)
            logger.info("Kafka producer initialized")

            # Get symbol configurations and streams
            symbol_configs = {}
            all_streams = set()

            for symbol in self.config.active_symbols:
                config = self.config.get_symbol_config(symbol)
                if config:
                    symbol_configs[symbol] = config
                    all_streams.update(config.streams)
                else:
                    # Fallback to default streams
                    all_streams.update(["trade", "ticker", "kline_1m"])

            # Initialize WebSocket client
            self.websocket_client = BinanceWebSocketClient(
                symbols=self.config.active_symbols,
                streams=list(all_streams),
                callback=self.message_callback,
                config=self.config
            )
            logger.info("WebSocket client initialized")

            self.running = True

            # Start WebSocket connection
            await self.websocket_client.connect()

        except Exception as e:
            logger.error(f"Error starting streaming service: {e}")
            await self.stop()
            raise

    async def stop(self):
        """Stop the streaming service gracefully"""
        logger.info("Stopping streaming service...")
        self.running = False

        # Disconnect WebSocket
        if self.websocket_client:
            try:
                await self.websocket_client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting WebSocket: {e}")

        # Close Kafka producer
        if self.producer:
            try:
                self.producer.close()
            except Exception as e:
                logger.error(f"Error closing Kafka producer: {e}")

        self.shutdown_event.set()
        logger.info("Streaming service stopped")

    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}, shutting down...")
            asyncio.create_task(self.stop())

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

    async def health_check_loop(self):
        """Periodic health checks"""
        while self.running and not self.shutdown_event.is_set():
            try:
                logger.info(
                    f"Health check - "
                    f"WebSocket: {'connected' if self.websocket_client and self.websocket_client.running else 'disconnected'}, "
                    f"Producer: {'active' if self.producer else 'inactive'}"
                )

                try:
                    # 5 minutes
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=300)
                    break
                except asyncio.TimeoutError:
                    continue

            except Exception as e:
                logger.error(f"Error in health check: {e}")
                await asyncio.sleep(60)

    async def run(self):
        """Main run method"""
        self.setup_signal_handlers()

        try:
            await self.start()

            # Start health check loop
            health_task = asyncio.create_task(self.health_check_loop())

            # Wait for shutdown
            await self.shutdown_event.wait()

            # Cancel health check
            health_task.cancel()
            try:
                await health_task
            except asyncio.CancelledError:
                pass

        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Fatal error in streaming service: {e}")
            raise
        finally:
            await self.stop()


async def main():
    """Main entry point"""
    service = StreamingService()

    try:
        await service.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())

import json
import logging
from typing import Dict, Any, Optional
from kafka import KafkaProducer
from kafka.errors import KafkaError

logger = logging.getLogger(__name__)


class StreamingProducer:
    """Kafka producer for cryptocurrency streaming data"""

    def __init__(self, config):
        self.config = config
        self._producer = None
        self._init_producer()

    def _init_producer(self):
        """Initialize Kafka producer"""
        try:
            self._producer = KafkaProducer(
                bootstrap_servers=self.config.kafka_servers,
                value_serializer=lambda x: json.dumps(x).encode('utf-8'),
                key_serializer=lambda x: x.encode('utf-8') if x else None,
                batch_size=self.config.kafka_batch_size,
                linger_ms=self.config.kafka_linger_ms,
                compression_type='gzip',
                acks='all',
                retries=3,
                retry_backoff_ms=1000
            )
            logger.info("Kafka producer initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            raise

    def send_to_bronze_layer(self, message: Dict[str, Any]) -> None:
        """Send message to appropriate Kafka topic for bronze layer"""
        try:
            symbol = message.get('symbol', 'UNKNOWN')
            stream_type = message.get('stream_type', 'unknown')

            # Create topic name
            topic = f"{self.config.kafka_topic_prefix}{symbol.lower()}_{stream_type}"

            # Send message with symbol as key for partitioning
            future = self._producer.send(topic, value=message, key=symbol)
            future.add_callback(self._on_send_success)
            future.add_errback(self._on_send_error)

            logger.debug(f"Sent message to topic {topic} for symbol {symbol}")

        except Exception as e:
            logger.error(f"Error sending message to bronze layer: {e}")
            raise

    def _on_send_success(self, record_metadata):
        """Callback for successful message send"""
        logger.debug(
            f"Message sent to {record_metadata.topic}:{record_metadata.partition}:{record_metadata.offset}")

    def _on_send_error(self, exception):
        """Callback for failed message send"""
        logger.error(f"Failed to send message: {exception}")

    def flush(self):
        """Flush any pending messages"""
        if self._producer:
            self._producer.flush()

    def close(self):
        """Close the producer"""
        if self._producer:
            self._producer.flush()
            self._producer.close()
            logger.info("Kafka producer closed")

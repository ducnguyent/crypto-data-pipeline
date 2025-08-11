#!/usr/bin/env python3
"""
Kafka connectivity and topic debug script
"""

import json
import time
from kafka import KafkaProducer, KafkaConsumer, KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import KafkaError

def test_kafka_connection():
    """Test basic Kafka connectivity"""
    
    # Configuration - adjust these as needed
    KAFKA_SERVERS = ['localhost:9092']  # Change to your Kafka servers
    TEST_TOPIC = 'crypto_raw_ethusdt_trade'
    
    print(f"Testing Kafka connection to {KAFKA_SERVERS}")
    
    # 1. Test admin connection and list topics
    print("\n1. Testing Admin Client...")
    try:
        admin = KafkaAdminClient(
            bootstrap_servers=KAFKA_SERVERS,
            client_id='debug-admin'
        )
        
        # List existing topics
        existing_topics = admin.list_topics()
        print(f"   ✓ Connected to Kafka")
        print(f"   Existing topics: {existing_topics}")
        
        # Check if our topic exists
        if TEST_TOPIC in existing_topics:
            print(f"   ✓ Topic '{TEST_TOPIC}' exists")
        else:
            print(f"   ✗ Topic '{TEST_TOPIC}' does NOT exist")
            
            # Try to create it
            print(f"   Creating topic '{TEST_TOPIC}'...")
            topic = NewTopic(name=TEST_TOPIC, num_partitions=1, replication_factor=1)
            admin.create_topics([topic])
            print(f"   ✓ Topic created")
            
    except Exception as e:
        print(f"   ✗ Admin client error: {e}")
        return False
    
    # 2. Test producer
    print("\n2. Testing Producer...")
    try:
        producer = KafkaProducer(
            bootstrap_servers=KAFKA_SERVERS,
            value_serializer=lambda x: json.dumps(x).encode('utf-8'),
            key_serializer=lambda x: x.encode('utf-8') if x else None
        )
        
        # Send test message
        test_message = {
            'record_id': 'test-123',
            'symbol': 'ADAUSDT',
            'stream_type': 'trade',
            'event_time': int(time.time() * 1000),
            'raw_data': '{"test": true}',
            'data_quality_score': 1.0
        }
        
        future = producer.send(TEST_TOPIC, value=test_message, key='ADAUSDT')
        record_metadata = future.get(timeout=10)
        
        print(f"   ✓ Message sent to {record_metadata.topic}")
        print(f"     Partition: {record_metadata.partition}")
        print(f"     Offset: {record_metadata.offset}")
        
        producer.flush()
        producer.close()
        
    except Exception as e:
        print(f"   ✗ Producer error: {e}")
        return False
    
    # 3. Test consumer
    print("\n3. Testing Consumer...")
    try:
        consumer = KafkaConsumer(
            TEST_TOPIC,
            bootstrap_servers=KAFKA_SERVERS,
            auto_offset_reset='earliest',
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            consumer_timeout_ms=5000  # 5 second timeout
        )
        
        print(f"   Consuming from '{TEST_TOPIC}'...")
        message_count = 0
        
        for message in consumer:
            message_count += 1
            print(f"   ✓ Received message #{message_count}")
            print(f"     Key: {message.key}")
            print(f"     Value: {json.dumps(message.value, indent=2)}")
            print(f"     Partition: {message.partition}")
            print(f"     Offset: {message.offset}")
            
            # Just read a few messages for testing
            if message.key == b'ADAUSDT':
                break
        
        if message_count == 0:
            print(f"   ⚠ No messages found in topic '{TEST_TOPIC}'")
        else:
            print(f"   ✓ Successfully consumed {message_count} messages")
            
        consumer.close()
        
    except Exception as e:
        print(f"   ✗ Consumer error: {e}")
        return False
    
    print("\n✅ All Kafka tests passed!")
    return True


def test_all_crypto_topics():
    """Test all crypto topics"""
    
    KAFKA_SERVERS = ['localhost:9092']
    
    print("\nChecking all crypto topics...")
    
    try:
        admin = KafkaAdminClient(
            bootstrap_servers=KAFKA_SERVERS,
            client_id='topic-scanner'
        )
        
        all_topics = admin.list_topics()
        crypto_topics = [t for t in all_topics if t.startswith('crypto_')]
        
        if not crypto_topics:
            print("   ⚠ No crypto topics found")
            return
        
        print(f"   Found {len(crypto_topics)} crypto topics:")
        
        for topic in sorted(crypto_topics):
            # Try to get message count
            try:
                # Create a fresh consumer for each topic
                consumer = KafkaConsumer(
                    bootstrap_servers=KAFKA_SERVERS,
                    auto_offset_reset='earliest',
                    consumer_timeout_ms=1000
                )
                
                # Get partition info
                partitions = consumer.partitions_for_topic(topic)
                
                # Get the last offset
                from kafka import TopicPartition
                total_messages = 0
                
                if partitions:
                    for partition in partitions:
                        tp = TopicPartition(topic, partition)
                        consumer.assign([tp])
                        consumer.seek_to_end(tp)
                        last_offset = consumer.position(tp)
                        total_messages += last_offset
                
                print(f"     • {topic}: ~{total_messages} messages")
                
                # Sample a message if available
                if total_messages > 0:
                    consumer.seek_to_beginning(tp)
                    for msg in consumer:
                        try:
                            value = json.loads(msg.value.decode('utf-8'))
                            print(f"       Sample: symbol={value.get('symbol')}, stream={value.get('stream_type')}")
                        except:
                            pass
                        break  # Just one sample
                
                consumer.close()
                
            except Exception as e:
                print(f"     • {topic}: Error reading - {e}")
                
    except Exception as e:
        print(f"   ✗ Error scanning topics: {e}")


if __name__ == "__main__":
    print("=" * 60)
    print("KAFKA DEBUG SCRIPT")
    print("=" * 60)
    
    # Run basic connectivity test
    test_kafka_connection()
    
    # Check all crypto topics
    test_all_crypto_topics()
    
    print("\n" + "=" * 60)
    print("Debug script completed")
    print("=" * 60)
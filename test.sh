#!/bin/bash

echo "🧪 Testing Crypto Data Pipeline..."

# Test container health
echo "🐳 Container Health:"
docker-compose ps

# Test Kafka
echo ""
echo "📡 Testing Kafka connectivity..."
if docker exec crypto-kafka kafka-broker-api-versions --bootstrap-server localhost:9092 >/dev/null 2>&1; then
    echo "✅ Kafka is healthy"
else
    echo "❌ Kafka is not responding"
fi

# Test MinIO
echo ""
echo "🗄️ Testing MinIO connectivity..."
if docker exec crypto-minio mc admin info local >/dev/null 2>&1; then
    echo "✅ MinIO is healthy"
else
    echo "❌ MinIO is not responding"
fi

# Test Dagster
echo ""
echo "📊 Testing Dagster API..."
if curl -f -s http://localhost:3000/server_info >/dev/null 2>&1; then
    echo "✅ Dagster UI is healthy"
else
    echo "❌ Dagster UI is not responding"
fi

# Test Spark
echo ""
echo "⚡ Testing Spark Master..."
if curl -f -s http://localhost:8080 >/dev/null 2>&1; then
    echo "✅ Spark Master is healthy"
else
    echo "❌ Spark Master is not responding"
fi

echo ""
echo "🎉 Health check complete!"
#!/bin/bash

set -e

echo "🚀 Deploying Crypto Data Pipeline..."

# Check prerequisites
if ! command -v docker >/dev/null 2>&1; then
    echo "❌ Docker not found. Please install Docker."
    exit 1
fi

if ! command -v docker-compose >/dev/null 2>&1; then
    echo "❌ Docker Compose not found. Please install Docker Compose."
    exit 1
fi

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please review .env file and update passwords!"
fi

# Download Spark jars
echo "📦 Downloading Spark jars..."
chmod +x scripts/download_jars.sh
./scripts/download_jars.sh

# Create necessary directories
mkdir -p logs dagster_home

# Build images
echo "🔨 Building Docker images..."
docker-compose build

# Start infrastructure
echo "🏗️ Starting infrastructure services..."
docker-compose up -d zookeeper kafka minio postgres spark-master spark-worker

# Wait for services
echo "⏳ Waiting for services to be ready..."
sleep 30

# Initialize MinIO
docker-compose up -d minio-init

# Start application services
echo "🚀 Starting application services..."
docker-compose up -d streaming-service dagster-webserver dagster-daemon

echo "✅ Deployment complete!"
echo ""
echo "🌐 Access points:"
echo "   Dagster UI:    http://localhost:3000"
echo "   Spark UI:      http://localhost:8080"
echo "   MinIO Console: http://localhost:9001"
echo ""
echo "📊 Monitor with: ./monitor.sh"
echo "🧪 Test with: ./test.sh"
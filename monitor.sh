#!/bin/bash

# Simple monitoring script
echo "📊 Crypto Data Pipeline Status"
echo "================================"

echo "🐳 Container Status:"
docker-compose ps

echo ""
echo "📈 Streaming Service Logs (last 10 lines):"
docker-compose logs --tail=10 streaming-service

echo ""
echo "📊 Dagster Webserver Logs (last 5 lines):"
docker-compose logs --tail=5 dagster-webserver

echo ""
echo "🔗 Quick Links:"
echo "   Dagster UI:    http://localhost:3000"
echo "   Spark UI:      http://localhost:8080"
echo "   MinIO Console: http://localhost:9001"
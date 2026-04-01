#!/bin/bash

# Comprehensive monitoring script
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
echo "🔍 Monitoring Stack Health:"
# Prometheus
if curl -sf http://localhost:9090/-/healthy > /dev/null 2>&1; then
    echo "   ✅ Prometheus:    http://localhost:9090 (healthy)"
else
    echo "   ❌ Prometheus:    http://localhost:9090 (not reachable)"
fi

# Grafana
if curl -sf http://localhost:3001/api/health > /dev/null 2>&1; then
    echo "   ✅ Grafana:       http://localhost:3001 (healthy)"
else
    echo "   ❌ Grafana:       http://localhost:3001 (not reachable)"
fi

# AlertManager
if curl -sf http://localhost:9093/-/healthy > /dev/null 2>&1; then
    echo "   ✅ AlertManager:  http://localhost:9093 (healthy)"
else
    echo "   ❌ AlertManager:  http://localhost:9093 (not reachable)"
fi

# Metrics exporter
if curl -sf http://localhost:8000/ > /dev/null 2>&1; then
    echo "   ✅ Exporter:      http://localhost:8000 (healthy)"
else
    echo "   ❌ Exporter:      http://localhost:8000 (not reachable)"
fi

echo ""
echo "🔗 Quick Links:"
echo "   Dagster UI:    http://localhost:3000"
echo "   Spark UI:      http://localhost:8080"
echo "   MinIO Console: http://localhost:9001"
echo "   Grafana:       http://localhost:3001"
echo "   Prometheus:    http://localhost:9090"
echo "   AlertManager:  http://localhost:9093"
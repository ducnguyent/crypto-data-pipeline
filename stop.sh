#!/bin/bash

echo "🛑 Stopping Crypto Data Pipeline..."

# Graceful shutdown
docker-compose stop

# Remove containers
docker-compose down

echo "✅ All services stopped"
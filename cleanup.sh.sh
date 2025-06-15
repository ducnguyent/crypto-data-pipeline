#!/bin/bash

echo "🧹 Cleaning up Crypto Data Pipeline..."

# Stop and remove containers
docker-compose down

# Remove volumes (optional)
read -p "Remove data volumes? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker-compose down -v
    echo "✅ Volumes removed"
fi

# Remove images (optional)
read -p "Remove Docker images? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    docker-compose down --rmi all
    echo "✅ Images removed"
fi

echo "🧹 Cleanup complete!"
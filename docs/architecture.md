
# Architecture

```
crypto-data-pipeline/
├── 📁 crypto_pipeline/                    # Main Dagster package
│   ├── __init__.py
│   ├── definitions.py                     # Main Dagster definitions
│   │
│   ├── 📁 assets/                         # Dagster data assets
│   │   ├── __init__.py
│   │   ├── bronze_assets.py              # Bronze layer ingestion (IMPLEMENTED)
│   │   ├── silver_assets.py              # Silver layer processing (PLACEHOLDER)
│   │   └── gold_assets.py                # Gold layer analytics (PLACEHOLDER)
│   │
│   └── 📁 utils/                          # Dagster utilities
│       ├── __init__.py
│       ├── kafka_utils.py                # Kafka client utilities
│       ├── hudi_utils.py                 # Hudi table operations
│       └── spark_utils.py                # Spark session management
│
├── 📁 streaming/                          # Streaming service (SEPARATE CONTAINER)
│   ├── __init__.py
│   ├── service.py                         # Main streaming service entry point
│   ├── binance_websocket.py              # Binance WebSocket client
│   ├── kafka_producer.py                 # Kafka producer
│   └── config.py                         # Streaming configuration
│
├── 📁 shared/                             # Shared utilities
│   ├── __init__.py
│   ├── settings.py                       # Common configuration classes
│   ├── logging_config.py                 # Shared logging setup
│   └── symbol_manager.py                 # Symbol configuration utilities
│
├── 📁 config/                             # Configuration files
│   ├── symbols.yaml                      # Symbol definitions (simplified)
│   └── dagster.yaml                      # Dagster configuration
│
├── 📁 scripts/                            # Management scripts
│   ├── symbol_config_tool.py             # Symbol management CLI
│   └── download_jars.sh                  # Download required Spark jars
│
├── 📁 tests/                              # Test suite
│   ├── __init__.py
│   ├── conftest.py                       # Pytest configuration
│   ├── test_streaming.py                 # Streaming service tests
│   ├── test_bronze_assets.py             # Bronze layer tests
│   └── test_integration.py               # Integration tests
│
├── 📄 Docker Configuration
├── Dockerfile.dagster                     # Dagster services (lightweight client)
├── Dockerfile.streaming                  # Streaming service
├── docker-compose.yml                    # Complete infrastructure
├── requirements-dagster.txt              # Dagster dependencies
├── requirements-streaming.txt            # Streaming dependencies
│
├── 📄 Management Scripts
├── deploy.sh                             # One-command deployment
├── stop.sh                               # Stop all services
├── monitor.sh                            # Monitoring dashboard
├── test.sh                               # Health checks
├── cleanup.sh                            # Environment cleanup
│
├── 📄 Configuration Files
├── .env.example                          # Environment template
├── .gitignore                            # Git ignore rules
├── .dockerignore                         # Docker ignore rules
├── Makefile                              # Common commands
└── README.md                             # Documentation
```
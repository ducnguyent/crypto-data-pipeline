
# Architecture

```
crypto-data-pipeline/
├── 📁 app/crypto_pipeline/                  # Main Dagster package
│   ├── __init__.py
│   ├── definitions.py                       # Main Dagster definitions
│   │
│   ├── 📁 assets/                           # Dagster data assets
│   │   ├── __init__.py
│   │   ├── bronze_assets.py                 # Bronze layer ingestion (IMPLEMENTED)
│   │   ├── silver_assets.py                 # Silver layer processing (IMPLEMENTED)
│   │   ├── gold_assets.py                   # Gold layer analytics (IMPLEMENTED)
│   │   └── quality_assets.py                # Data quality reporting (IMPLEMENTED)
│   │
│   ├── 📁 sensors/                          # Dagster sensors
│   │   └── data_quality_sensor.py           # Triggers gold layer on fresh silver data
│   │
│   └── 📁 utils/                            # Dagster utilities
│       ├── __init__.py
│       ├── kafka_utils.py                   # Kafka client utilities
│       ├── hudi_utils.py                    # Hudi table operations
│       ├── spark_utils.py                   # Spark session management
│       └── gold_utils.py                    # Gold layer calculation helpers
│
├── 📁 streaming/                            # Streaming service (SEPARATE CONTAINER)
│   ├── __init__.py
│   ├── service.py                           # Main streaming service entry point
│   └── 📁 core/
│       ├── binance_websocket.py             # Binance WebSocket client
│       ├── kafka_producer.py                # Kafka producer
│       └── config.py                        # Streaming configuration
│
├── 📁 shared/                               # Shared utilities
│   ├── __init__.py
│   └── 📁 config/
│       ├── settings.py                      # Common configuration classes
│       └── symbols.yaml                     # Symbol definitions
│
├── 📁 monitoring/                           # Observability stack
│   ├── 📁 prometheus/
│   │   └── prometheus.yml                   # Scrape configuration
│   ├── 📁 grafana/
│   │   ├── 📁 provisioning/
│   │   │   ├── 📁 dashboards/
│   │   │   │   └── dashboards.yml           # Auto-provision config
│   │   │   └── 📁 datasources/
│   │   │       └── datasources.yml          # Prometheus datasource
│   │   └── 📁 dashboards/
│   │       ├── pipeline_overview.json        # Main pipeline dashboard
│   │       ├── data_quality.json             # Quality metrics dashboard
│   │       └── gold_analytics.json           # Gold layer results dashboard
│   ├── 📁 alerting/
│   │   ├── alert_rules.yml                  # Prometheus alert rules
│   │   └── alertmanager.yml                 # AlertManager config
│   └── 📁 exporters/
│       └── pipeline_metrics.py              # Custom Prometheus exporter
│
├── 📁 tests/                                # Test suite
│   ├── __init__.py
│   ├── conftest.py                          # Pytest configuration
│   ├── test_streaming.py                    # Streaming service tests
│   ├── test_binance_websocket_client.py     # WebSocket client tests
│   ├── test_kafka.py                        # Kafka producer tests
│   ├── test_bronze_assets.py                # Bronze layer tests
│   ├── test_silver_assets.py                # Silver layer tests
│   ├── test_gold_assets.py                  # Gold layer tests
│   ├── test_gold_utils.py                   # Gold utility tests
│   ├── test_quality_assets.py               # Quality layer tests
│   └── test_integration.py                  # Integration tests
│
├── 📄 Docker Configuration
├── Dockerfile.dagster                       # Dagster services
├── Dockerfile.streaming                     # Streaming service
├── docker-compose.yml                       # Complete infrastructure
├── requirements-dagster.txt                 # Dagster dependencies
├── requirements-streaming.txt               # Streaming dependencies
│
├── 📄 Management Scripts
├── deploy.sh                                # One-command deployment
├── stop.sh                                  # Stop all services
├── monitor.sh                               # Monitoring dashboard
├── test.sh                                  # Health checks
├── cleanup.sh                               # Environment cleanup
│
├── 📄 Configuration Files
├── .env.example                             # Environment template
├── .gitignore                               # Git ignore rules
├── Makefile                                 # Common commands
└── README.md                                # Documentation
```
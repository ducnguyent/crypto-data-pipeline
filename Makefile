.PHONY: help deploy start stop test monitor clean

help:
	@echo "🚀 Crypto Data Pipeline Commands"
	@echo "================================="
	@echo "  make deploy    Deploy the pipeline"
	@echo "  make start     Start services"
	@echo "  make stop      Stop services"
	@echo "  make test      Run health checks"
	@echo "  make monitor   Show status"
	@echo "  make logs      Show logs"
	@echo "  make clean     Cleanup"

deploy:
	./deploy.sh

start:
	docker-compose up -d

stop:
	./stop.sh

test:
	./test.sh

monitor:
	./monitor.sh

logs:
	docker-compose logs -f

clean:
	./cleanup.sh
import logging
import sys
from typing import Optional


def setup_logging(level: str = "INFO", service_name: str = "crypto-pipeline") -> None:
    """Setup logging configuration"""

    format_string = (
        f"%(asctime)s - {service_name} - %(name)s - %(levelname)s - "
        "%(filename)s:%(lineno)d - %(message)s"
    )

    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=format_string,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )

    # Set specific loggers to appropriate levels
    logging.getLogger("kafka").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("websocket").setLevel(logging.INFO)

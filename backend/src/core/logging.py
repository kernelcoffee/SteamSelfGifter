import logging
import sys
from pathlib import Path
import structlog

from core.config import settings


def setup_logging() -> None:
    """Configure structured logging for the application"""

    # Convert log level string to logging constant
    log_level = getattr(logging, settings.log_level.upper())

    # Ensure log directory exists
    Path(settings.log_file).parent.mkdir(parents=True, exist_ok=True)

    # Configure structlog processors
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            # Use JSON in production, console renderer in development
            structlog.processors.JSONRenderer()
            if settings.environment == "production"
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard logging
    logging.basicConfig(
        format="%(message)s",
        level=log_level,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(settings.log_file),
        ],
    )

    # Get logger and log startup message
    logger = structlog.get_logger()
    logger.info(
        "logging_configured",
        log_level=settings.log_level,
        environment=settings.environment,
        log_file=settings.log_file,
    )

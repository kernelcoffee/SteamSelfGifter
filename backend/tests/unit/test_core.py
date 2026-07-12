#!/usr/bin/env python3
"""Quick test script for core modules"""

print("Testing core modules...")
print()

# Test 1: Config
print("1. Testing config...")
from core.config import settings

print(f"   ✓ App: {settings.app_name} v{settings.version}")
print(f"   ✓ Environment: {settings.environment}")
print(f"   ✓ Database: {settings.database_url}")
print()

# Test 2: Logging
print("2. Testing logging...")
import structlog

from core.logging import setup_logging

setup_logging()
logger = structlog.get_logger()
logger.info("test_message", test_key="test_value")
print("   ✓ Logging configured successfully")
print()

# Test 3: Exceptions
print("3. Testing exceptions...")
from core.exceptions import ERROR_CODES, AppError, ConfigurationError

try:
    raise ConfigurationError("Test error", "CONFIG_001")
except AppError as e:
    print(f"   ✓ Exception caught: {e.message} (code: {e.code})")
    print(f"   ✓ Error code description: {ERROR_CODES[e.code]}")
print()

print("✅ All core modules working correctly!")

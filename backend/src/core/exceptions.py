from typing import Any


class AppException(Exception):
    """Base exception for all application errors"""

    def __init__(
        self, message: str, code: str, details: dict[str, Any] | None = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


# Configuration errors
class ConfigurationError(AppException):
    """Configuration related errors"""

    pass


# Resource errors
class ResourceNotFoundError(AppException):
    """Resource not found"""

    pass


# Validation errors
class ValidationError(AppException):
    """Input validation errors"""

    pass


# External API errors
class SteamGiftsError(AppException):
    """SteamGifts API errors"""

    pass


class SteamGiftsAuthError(SteamGiftsError):
    """SteamGifts authentication errors - invalid or missing session"""

    pass


class SteamGiftsSessionExpiredError(SteamGiftsAuthError):
    """SteamGifts session has expired or been invalidated"""

    pass


class SteamGiftsNotConfiguredError(SteamGiftsAuthError):
    """SteamGifts PHPSESSID not configured"""

    pass


class SteamAPIError(AppException):
    """Steam API errors"""

    pass


# Business logic errors
class InsufficientPointsError(AppException):
    """Not enough points for operation"""

    pass


class RateLimitError(AppException):
    """Rate limit exceeded"""

    pass


class SchedulerError(AppException):
    """Scheduler related errors"""

    pass


# Error code constants
ERROR_CODES = {
    "CONFIG_001": "SteamGifts credentials not configured",
    "CONFIG_002": "Invalid configuration",
    "CONFIG_003": "Invalid PHPSESSID",
    "GIVE_001": "Giveaway not found",
    "GIVE_002": "Giveaway already entered",
    "GIVE_003": "Giveaway ended",
    "GIVE_004": "Insufficient points",
    "GIVE_005": "Giveaway is hidden",
    "STEAM_001": "Steam API unavailable",
    "STEAM_002": "Game not found",
    "SG_001": "SteamGifts rate limit",
    "SG_002": "SteamGifts connection failed",
    "SG_003": "Invalid session",
    "SG_004": "Session expired",
    "SG_005": "Not authenticated",
    "SG_006": "PHPSESSID not configured",
    "SCHED_001": "Scheduler already running",
    "SCHED_002": "Scheduler not running",
    "SCHED_003": "Scheduler error",
    "SYS_001": "Internal server error",
    "SYS_002": "Service unavailable",
}

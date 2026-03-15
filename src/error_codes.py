"""
SovereignForge - Structured API Error Codes

Provides consistent error codes for all API error responses.
Each code is a short, machine-readable string that clients can
switch on without parsing human-readable detail messages.
"""

from enum import Enum


class ErrorCode(str, Enum):
    """Structured error codes returned in API error responses."""

    # Authentication / authorisation
    AUTH_FAILED = "AUTH_FAILED"

    # Rate limiting
    RATE_LIMITED = "RATE_LIMITED"

    # Resource not found
    NOT_FOUND = "NOT_FOUND"

    # Client-side validation errors (bad input, unknown strategy, etc.)
    VALIDATION_ERROR = "VALIDATION_ERROR"

    # Unexpected server-side failure
    INTERNAL_ERROR = "INTERNAL_ERROR"

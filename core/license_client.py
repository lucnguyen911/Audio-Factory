"""
core/license_client.py
──────────────────────────────────────────────────────────────────────────────
Supabase-backed license verification and activation client (v3).

All activation logic is executed server-side via a PostgreSQL RPC function
``activate_or_verify_license_v3`` that uses ``SELECT … FOR UPDATE`` to
prevent race conditions.

The client never PATCHes the ``audio_licenses`` table directly.

Network errors are clearly distinguished from device-mismatch errors.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import List, Optional

from core.device_identity import DeviceIdentity

logger = logging.getLogger(__name__)

# ── Status codes ─────────────────────────────────────────────────────────────
# These are stable string codes used by both server and client.

VALID = "VALID"
ACTIVATED = "ACTIVATED"
MIGRATED = "MIGRATED"
LICENSE_NOT_FOUND = "LICENSE_NOT_FOUND"
LICENSE_DISABLED = "LICENSE_DISABLED"
LICENSE_EXPIRED = "LICENSE_EXPIRED"
DEVICE_MISMATCH = "DEVICE_MISMATCH"
DEVICE_LIMIT = "DEVICE_LIMIT"
LEGACY_DEVICE_MISMATCH = "LEGACY_DEVICE_MISMATCH"
DEVICE_ID_UNAVAILABLE = "DEVICE_ID_UNAVAILABLE"
NETWORK_ERROR = "NETWORK_ERROR"
SERVER_ERROR = "SERVER_ERROR"
CLIENT_CONFIG_ERROR = "CLIENT_CONFIG_ERROR"
AUTH_ERROR = "AUTH_ERROR"

# Statuses that count as "license is valid for this device"
SUCCESS_STATUSES = frozenset({VALID, ACTIVATED, MIGRATED})


@dataclass
class LicenseVerificationResult:
    """Structured result from the activation / verification RPC."""
    valid: bool
    status: str
    message: str
    expired_at: Optional[str] = None


# ── Supabase RPC client ─────────────────────────────────────────────────────

def activate_or_verify(
    key: str,
    identity: DeviceIdentity,
    legacy_candidates: List[str],
    supabase_url: str,
    supabase_key: str,
    app_version: str = "",
    timeout: int = 10,
) -> LicenseVerificationResult:
    """
    Call the ``activate_or_verify_license_v3`` Supabase RPC.

    Args:
        key:               License key string.
        identity:          Current device identity (HWID v3).
        legacy_candidates: List of legacy HWID hashes for migration.
        supabase_url:      Supabase project REST URL.
        supabase_key:      Supabase anon key.
        app_version:       Current application version string.
        timeout:           HTTP timeout in seconds.

    Returns:
        LicenseVerificationResult with a stable status code.
    """
    key = key.strip()
    if not key:
        return LicenseVerificationResult(
            valid=False,
            status=LICENSE_NOT_FOUND,
            message="license_empty_key",
        )

    # Build RPC payload
    payload = {
        "p_license_key": key,
        "p_hwid": identity.hwid,
        "p_hwid_version": identity.version,
        "p_legacy_candidates": legacy_candidates,
        "p_app_version": app_version,
    }

    url = f"{supabase_url}/rest/v1/rpc/activate_or_verify_license_v3"
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))

        status = body.get("status", SERVER_ERROR)
        expired_at = body.get("expired_at")

        valid = status in SUCCESS_STATUSES

        # Log masked info
        masked_key = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "****"
        logger.info(
            "[SECURITY] License verification: key=%s, status=%s",
            masked_key,
            status,
        )

        return LicenseVerificationResult(
            valid=valid,
            status=status,
            message=f"license_{status.lower()}",
            expired_at=expired_at,
        )

    except urllib.error.HTTPError as exc:
        # HTTPError is a subclass of URLError — must be caught FIRST.
        # Classify by HTTP status code, NOT as a generic network error.
        http_code = exc.code
        logger.warning(
            "[SECURITY] Verification HTTP status=%d, category=%s",
            http_code,
            _classify_http_error(http_code),
        )
        return _http_error_to_result(http_code)
    except urllib.error.URLError as exc:
        # True network errors: DNS failure, connection refused, timeout, etc.
        logger.warning(
            "[SECURITY] Network error during license verification: %s",
            type(exc).__name__,
        )
        return LicenseVerificationResult(
            valid=False,
            status=NETWORK_ERROR,
            message="license_network_error",
        )
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        logger.error(
            "[SECURITY] Unexpected server response: %s",
            type(exc).__name__,
        )
        return LicenseVerificationResult(
            valid=False,
            status=SERVER_ERROR,
            message="license_server_error",
        )
    except Exception as exc:
        # Catch-all for socket timeouts, SSL errors, etc.
        logger.warning(
            "[SECURITY] Connection error: %s", type(exc).__name__
        )
        return LicenseVerificationResult(
            valid=False,
            status=NETWORK_ERROR,
            message="license_network_error",
        )


def _classify_http_error(code: int) -> str:
    """Classify an HTTP status code into a license error category."""
    if code in (408, 429):
        return SERVER_ERROR
    if code in (401, 403):
        return AUTH_ERROR
    if 400 <= code < 500:
        return CLIENT_CONFIG_ERROR
    if code >= 500:
        return SERVER_ERROR
    return CLIENT_CONFIG_ERROR


def _http_error_to_result(code: int) -> LicenseVerificationResult:
    """Convert an HTTP error code to a LicenseVerificationResult."""
    category = _classify_http_error(code)
    if category == AUTH_ERROR:
        return LicenseVerificationResult(
            valid=False,
            status=AUTH_ERROR,
            message="license_server_error",
        )
    if category == SERVER_ERROR:
        return LicenseVerificationResult(
            valid=False,
            status=SERVER_ERROR,
            message="license_server_error",
        )
    # CLIENT_CONFIG_ERROR: 400, 404, etc.
    return LicenseVerificationResult(
        valid=False,
        status=CLIENT_CONFIG_ERROR,
        message="license_server_error",
    )


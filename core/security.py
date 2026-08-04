"""
core/security.py
──────────────────────────────────────────────────────────────────────────────
Lõi xác thực bản quyền trực tuyến qua Supabase + Khóa mã máy HWID.
Tác giả: Nguyễn Văn Lực (AUDIO FACTORY PREMIUM SUITE)

──────────────────────────────────────────────────────────────────────────────
v3 security:
  - HWID v3 via SMBIOS UUID with MachineGuid fallback
  - DPAPI-protected local license (replaces XOR)
  - Legacy XOR migration on load
  - Supabase RPC-only activation
  - Backward-compatible public API

Public API:
  get_hwid()                         -> str
  verify_license_online(key, hwid)   -> Tuple[bool, str]
  bind_hwid_online(key, hwid)        -> bool
  save_local_license(key)            -> None
  load_local_license()               -> Optional[str]
  check_license_on_startup()         -> Tuple[bool, str]
  SUPABASE_URL                       -> str
  SUPABASE_KEY                       -> str
"""

import base64
import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from core.device_identity import (
    DeviceIdentity,
    DeviceIdentityError,
    get_device_identity,
    get_hwid as _get_hwid_v3,
    get_legacy_hwid_candidates,
)
from core.dpapi_storage import (
    load_protected_json,
    save_protected_json,
)
from core.license_client import (
    ACTIVATED,
    AUTH_ERROR,
    CLIENT_CONFIG_ERROR,
    DEVICE_ID_UNAVAILABLE,
    DEVICE_MISMATCH,
    DEVICE_LIMIT,
    LEGACY_DEVICE_MISMATCH,
    LICENSE_DISABLED,
    LICENSE_EXPIRED,
    LICENSE_NOT_FOUND,
    MIGRATED,
    NETWORK_ERROR,
    SERVER_ERROR,
    VALID,
    LicenseVerificationResult,
    activate_or_verify,
)
from version import APP_DATA_DIRNAME, APP_VERSION

logger = logging.getLogger(__name__)

# ── Supabase credentials (kept here for updater.py / admin_tools compat) ─────
SUPABASE_URL = "https://owskwezrldwlerywsfex.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im93c2t3ZXpybGR3bGVyeXdzZmV4Iiwicm9sZSI6ImFub24i"
    "LCJpYXQiOjE3ODIzMTAxMDMsImV4cCI6MjA5Nzg4NjEwM30."
    "DPmF5hoQl-FhuNhAladxHUmIYctWjb7J1c5YpkHHTLQ"
)

# ── Local license file paths ────────────────────────────────────────────────
_APP_DATA_DIR = Path(os.environ.get("APPDATA", os.path.expanduser("~"))) / APP_DATA_DIRNAME
_LICENSE_FILE_V2 = _APP_DATA_DIR / "license_v2.dat"
_LICENSE_FILE_LEGACY = _APP_DATA_DIR / "license.json"

# License key format: AF-XXXX-XXXX-XXXX-XXXX (basic check)
_LICENSE_KEY_PATTERN = re.compile(r"^[A-Z0-9]{2,4}-[A-Z0-9]{4}-[A-Z0-9]{4}")

# ── Offline grace period ────────────────────────────────────────────────────
# Only applied when:
#   - Local license exists and is DPAPI-protected
#   - License was previously successfully verified online
#   - Error is a genuine network/server outage (NOT 4xx client error)
#   - Cached HWID matches current device HWID v2
#   - Time since last verification < OFFLINE_GRACE_DAYS
OFFLINE_GRACE_DAYS = 3

# Statuses eligible for offline grace (transient server/network issues)
_GRACE_ELIGIBLE_STATUSES = frozenset({NETWORK_ERROR, SERVER_ERROR})

# ── Localized message lookup ────────────────────────────────────────────────
_STATUS_MESSAGES = {
    VALID: "Bản quyền hợp lệ.",
    ACTIVATED: "Kích hoạt bản quyền thành công trên máy này!",
    MIGRATED: "Đã chuyển đổi bản quyền sang hệ thống mới thành công!",
    LICENSE_NOT_FOUND: "Key bản quyền không tồn tại.",
    LICENSE_DISABLED: "Key bản quyền đã bị vô hiệu hóa.",
    LICENSE_EXPIRED: "Mã dùng thử 3 ngày của bạn đã hết hạn! Vui lòng gia hạn gói Premium để tiếp tục sử dụng.",
    DEVICE_MISMATCH: "Key đã được sử dụng ở máy khác!",
    LEGACY_DEVICE_MISMATCH: "Key đã được sử dụng ở máy khác (phiên bản cũ).",
    DEVICE_ID_UNAVAILABLE: "Không thể xác định mã thiết bị ổn định. Vui lòng khởi động lại Windows hoặc liên hệ hỗ trợ.",
    NETWORK_ERROR: "Lỗi kết nối kiểm tra bản quyền. Vui lòng kiểm tra mạng và thử lại.",
    SERVER_ERROR: "Lỗi máy chủ bản quyền. Vui lòng thử lại sau.",
    CLIENT_CONFIG_ERROR: "Lỗi cấu hình máy chủ bản quyền. Vui lòng cập nhật phần mềm hoặc liên hệ hỗ trợ.",
    AUTH_ERROR: "Lỗi xác thực máy chủ bản quyền. Vui lòng liên hệ hỗ trợ.",
}
_STATUS_MESSAGES[DEVICE_LIMIT] = (
    "Key đã đạt số thiết bị tối đa. Vui lòng reset thiết bị trên trang quản trị."
)


def _get_status_message(status: str) -> str:
    """Get localized message for a status code."""
    return _STATUS_MESSAGES.get(status, f"Lỗi không xác định ({status}).")


# ── Public API: get_hwid ────────────────────────────────────────────────────

def get_hwid() -> str:
    """
    Backward-compatible HWID API.
    Now returns the stable HWID v2 (SHA-256 of MachineGuid).
    """
    return _get_hwid_v3()


# ── Public API: verify_license_online ────────────────────────────────────────

def verify_license_online(key: str, hwid: str) -> Tuple[bool, str]:
    """
    Verify a license key online via Supabase.

    Backward-compatible public wrapper over the v3 activation RPC.
    No direct table REST fallback is permitted.

    Returns (is_valid, message_string).
    """
    key = key.strip()
    if not key:
        return False, "Vui lòng nhập Key kích hoạt."

    # Get device identity
    try:
        identity = get_device_identity()
    except DeviceIdentityError:
        return False, _get_status_message(DEVICE_ID_UNAVAILABLE)

    result = _verify_license_with_result(key, identity)
    return result.valid, _get_status_message(result.status)


# ── Public API: bind_hwid_online ────────────────────────────────────────────

def bind_hwid_online(key: str, hwid: str) -> bool:
    """
    Backward-compatible wrapper.

    In v2, binding is handled atomically inside verify_license_online()
    via the RPC.  This function is kept for any code that still calls it
    directly.
    """
    is_valid, _ = verify_license_online(key, hwid)
    return is_valid


# ── Public API: save_local_license ───────────────────────────────────────────

def save_local_license(
    key: str,
    server_status: str = "",
    server_expired_at: Optional[str] = None,
) -> None:
    """
    Save the license key locally with DPAPI protection.

    Only records last_verified_at when server_status is a success status.
    This prevents offline grace from being extended by failed verifications.
    """
    try:
        identity = get_device_identity()
    except DeviceIdentityError:
        logger.error("[SECURITY] Cannot save local license: device identity unavailable.")
        return

    from datetime import timedelta
    now = datetime.now(timezone.utc)

    # Load existing bundle to preserve last_verified_at if not a new success
    existing = load_protected_json(_LICENSE_FILE_V2)
    last_verified = None
    cached_expires = None
    last_status = ""

    if existing and isinstance(existing, dict):
        last_verified = existing.get("last_verified_at")
        cached_expires = existing.get("cached_expires_at")
        last_status = existing.get("last_server_status", "")

    # Only update verification timestamp on actual success
    from core.license_client import SUCCESS_STATUSES
    if server_status in SUCCESS_STATUSES:
        last_verified = now.isoformat()
        cached_expires = (now + timedelta(days=OFFLINE_GRACE_DAYS)).isoformat()
        last_status = server_status
    elif server_status:
        # Persist definitive rejection so a later network outage cannot revive
        # a license that was already seen as revoked/expired/device-limited.
        last_status = server_status

    bundle = {
        "schema_version": 3,
        "license_key": key,
        "hwid_version": identity.version,
        "hwid": identity.hwid,
        "saved_at": now.isoformat(),
        "last_seen_at": now.isoformat(),
        "last_verified_at": last_verified,
        "cached_expires_at": cached_expires,
        "last_server_status": last_status,
        "server_expired_at": server_expired_at or (
            existing.get("server_expired_at") if existing else None
        ),
    }

    try:
        save_protected_json(_LICENSE_FILE_V2, bundle)
        logger.info("[SECURITY] Local license saved (DPAPI v2).")
    except OSError as exc:
        logger.error(
            "[SECURITY] Failed to save local license: %s",
            type(exc).__name__,
        )


# ── Public API: load_local_license ───────────────────────────────────────────

def load_local_license() -> Optional[str]:
    """
    Load the locally cached license key.

    Priority:
      1. DPAPI v2 format (license_v2.dat).
      2. Legacy XOR format (license.json) — automatic migration.

    Returns the license key string or None.
    """
    # Try v2 format first
    key = _load_license_v2()
    if key is not None:
        return key

    # Try legacy migration
    key = _migrate_legacy_license()
    if key is not None:
        return key

    return None


def _load_license_v2() -> Optional[str]:
    """Load license key from DPAPI v2 file."""
    bundle = _load_license_v2_bundle()
    if bundle is None:
        return None
    return bundle.get("license_key") or None


def _load_license_v2_bundle() -> Optional[dict]:
    """Load the full license bundle including verification metadata."""
    data = load_protected_json(_LICENSE_FILE_V2)
    if data is None:
        return None

    schema = data.get("schema_version")
    if schema not in (2, 3):
        return None

    key = data.get("license_key", "")
    if not key:
        return None

    return data


def _migrate_legacy_license() -> Optional[str]:
    """
    Attempt to migrate a legacy XOR-encrypted license.

    Steps:
      1. Read legacy license.json with 'token' field.
      2. Generate legacy HWID candidates.
      3. Try XOR-decrypting with each candidate.
      4. Keep only results that look like valid license keys.
      5. Do NOT re-save yet — that happens after online verification.

    Returns the recovered key or None.
    """
    if not _LICENSE_FILE_LEGACY.exists():
        return None

    try:
        with open(_LICENSE_FILE_LEGACY, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None

    obfuscated_token = data.get("token")
    if not obfuscated_token:
        return None

    try:
        decoded_bytes = base64.b64decode(obfuscated_token.encode("utf-8"))
        decoded_chars = decoded_bytes.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None

    # Try each legacy HWID candidate
    candidates = get_legacy_hwid_candidates()

    for candidate_hwid in candidates:
        try:
            original_chars = []
            for i, char in enumerate(decoded_chars):
                char_c = ord(char)
                hwid_c = ord(candidate_hwid[i % len(candidate_hwid)])
                original_chars.append(chr(char_c ^ hwid_c))
            recovered_key = "".join(original_chars)

            # Validate: must look like a license key
            if _looks_like_license_key(recovered_key):
                logger.info(
                    "[SECURITY] Legacy license migration: "
                    "successfully decoded with candidate."
                )
                return recovered_key
        except Exception:
            continue

    logger.warning(
        "[SECURITY] Legacy license migration: "
        "no candidate could decrypt the stored token."
    )
    return None


def _looks_like_license_key(value: str) -> bool:
    """
    Basic heuristic to check if a string looks like a license key.

    Checks:
      - Reasonable length (8-64 chars).
      - Only printable ASCII (no control chars).
      - Matches the AF-XXXX-XXXX pattern, OR at least contains dashes.
    """
    if not value or len(value) < 8 or len(value) > 64:
        return False

    # Must be printable ASCII
    if not all(32 <= ord(c) < 127 for c in value):
        return False

    # Prefer the known pattern
    if _LICENSE_KEY_PATTERN.match(value):
        return True

    # Fallback: at least has structure (dashes or alphanumeric)
    if "-" in value and value.replace("-", "").isalnum():
        return True

    return False


# ── Public API: get_license_file_path ────────────────────────────────────────

def get_license_file_path() -> str:
    """
    Return the legacy license file path for backward compatibility.
    """
    _APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return str(_LICENSE_FILE_LEGACY)


# ── Public API: check_license_on_startup ─────────────────────────────────────

def check_license_on_startup() -> Tuple[bool, str]:
    """
    Startup license check with strict fail-closed policy.

    Decision tree:
      Case 1: No local license → False (show LicenseDialog).
      Case 2: Corrupt/unreadable license → False.
      Case 3: Online verification succeeds → True, update timestamps.
      Case 4: NETWORK_ERROR or SERVER_ERROR (5xx) with valid grace → True.
      Case 5: HTTP 4xx / AUTH_ERROR / CLIENT_CONFIG_ERROR → False (no grace).
      Case 6: DEVICE_MISMATCH / EXPIRED / DISABLED / NOT_FOUND → False.
    """
    # Step 1: Device identity
    try:
        identity = get_device_identity()
    except DeviceIdentityError:
        logger.warning("[SECURITY] Startup authorization=False (device identity unavailable)")
        return False, ""

    # Step 2: Load local license
    key = load_local_license()
    if not key:
        logger.info("[SECURITY] Local license present=False, startup authorization=False")
        return False, ""

    # Step 3: Online verification
    result = _verify_license_with_result(key, identity)

    logger.info(
        "[SECURITY] Verification category=%s, local license present=True",
        result.status,
    )

    # Case 3: Online success → update timestamps and allow
    if result.valid:
        save_local_license(
            key,
            server_status=result.status,
            server_expired_at=result.expired_at,
        )
        logger.info("[SECURITY] Startup authorization=True (online verified)")
        return True, key

    # Case 4: Grace-eligible error (true network/server outage)
    if result.status in _GRACE_ELIGIBLE_STATUSES:
        grace_ok = _check_offline_grace(identity)
        if grace_ok:
            save_local_license(key)
            logger.info(
                "[SECURITY] Startup authorization=True "
                "(offline grace, status=%s)", result.status
            )
            return True, key
        else:
            logger.warning(
                "[SECURITY] Startup authorization=False "
                "(offline grace expired or never verified, status=%s)",
                result.status,
            )
            return False, ""

    # Cases 5 & 6: Definitive rejection — no grace allowed
    save_local_license(
        key,
        server_status=result.status,
        server_expired_at=result.expired_at,
    )
    logger.warning(
        "[SECURITY] Startup authorization=False (status=%s)",
        result.status,
    )
    return False, ""


def _check_offline_grace(identity: DeviceIdentity) -> bool:
    """
    Check if the cached license qualifies for offline grace.

    Requirements (ALL must be true):
      1. DPAPI v2 bundle exists and is readable.
      2. last_verified_at is present (was previously verified online).
      3. last_server_status was a success status.
      4. Cached HWID matches current device HWID v2.
      5. cached_expires_at has not passed.

    Returns True only if all checks pass.
    """
    bundle = _load_license_v2_bundle()
    if bundle is None:
        logger.info("[SECURITY] Offline grace eligible=False (no v2 bundle)")
        return False

    # Check 1: Was it ever verified successfully?
    last_verified_str = bundle.get("last_verified_at")
    if not last_verified_str:
        logger.info(
            "[SECURITY] Offline grace eligible=False "
            "(never verified online)"
        )
        return False

    # Check 2: Was the last status a success?
    from core.license_client import SUCCESS_STATUSES
    last_status = bundle.get("last_server_status", "")
    if last_status not in SUCCESS_STATUSES:
        logger.info(
            "[SECURITY] Offline grace eligible=False "
            "(last_server_status=%s)", last_status
        )
        return False

    # Check 3: Cached HWID matches current device
    cached_hwid = bundle.get("hwid", "")
    if cached_hwid != identity.hwid:
        logger.info(
            "[SECURITY] Offline grace eligible=False "
            "(HWID mismatch: cached vs current)"
        )
        return False

    # Check 4: Grace period not expired
    cached_expires_str = bundle.get("cached_expires_at")
    if not cached_expires_str:
        logger.info(
            "[SECURITY] Offline grace eligible=False "
            "(no cached_expires_at)"
        )
        return False

    try:
        cached_expires = datetime.fromisoformat(cached_expires_str)
        now = datetime.now(timezone.utc)
        last_seen_str = bundle.get("last_seen_at")
        if last_seen_str and now < datetime.fromisoformat(last_seen_str):
            logger.warning(
                "[SECURITY] Offline grace eligible=False (system clock moved backwards)"
            )
            return False
        server_expired_str = bundle.get("server_expired_at")
        if server_expired_str and now >= datetime.fromisoformat(server_expired_str):
            logger.info(
                "[SECURITY] Offline grace eligible=False (license expired while offline)"
            )
            return False
        if now > cached_expires:
            logger.info(
                "[SECURITY] Offline grace eligible=False "
                "(expired at %s, now %s)",
                cached_expires.isoformat(),
                now.isoformat(),
            )
            return False
    except (ValueError, TypeError):
        logger.warning(
            "[SECURITY] Offline grace eligible=False "
            "(invalid cached_expires_at)"
        )
        return False

    logger.info("[SECURITY] Offline grace eligible=True")
    return True


def _verify_license_with_result(
    key: str,
    identity: DeviceIdentity,
) -> LicenseVerificationResult:
    """
    Internal helper: run verification and return the full result object.
    Only uses RPC v2 (no legacy REST fallback).
    """
    legacy_candidates = get_legacy_hwid_candidates()

    return activate_or_verify(
        key=key,
        identity=identity,
        legacy_candidates=legacy_candidates,
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_KEY,
        app_version=APP_VERSION,
    )

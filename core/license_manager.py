# -*- coding: utf-8 -*-

"""
core/license_manager.py
──────────────────────────────────────────────────────────────────────────────
Quản lý bản quyền — Thin wrapper cung cấp 3 kịch bản xác thực chính:

  1. Kích hoạt lần đầu: HWID cột NULL → ghi đè HWID.
  2. Kiểm tra hàng ngày: so khớp HWID trùng → cho phép sử dụng.
  3. Báo lỗi HWID: HWID không khớp → từ chối.

Module này ủy quyền logic thực tế tới `license_client.py` và `security.py`
để tránh trùng lặp code.

Tác giả: Nguyễn Văn Lực (AUDIO FACTORY PREMIUM SUITE)
──────────────────────────────────────────────────────────────────────────────
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class LicenseStatus(Enum):
    """Trạng thái kết quả kiểm tra bản quyền."""
    VALID = "valid"                       # Key hợp lệ, HWID trùng khớp
    ACTIVATED = "activated"               # Kích hoạt lần đầu thành công
    MIGRATED = "migrated"                 # Chuyển đổi HWID legacy thành công
    EXPIRED = "expired"                   # Key đã hết hạn
    DISABLED = "disabled"                 # Key bị vô hiệu hóa
    NOT_FOUND = "not_found"               # Key không tồn tại
    DEVICE_MISMATCH = "device_mismatch"   # HWID không khớp (đã dùng ở máy khác)
    NETWORK_ERROR = "network_error"       # Lỗi kết nối mạng
    SERVER_ERROR = "server_error"         # Lỗi máy chủ
    NO_KEY = "no_key"                     # Chưa có key cục bộ
    OFFLINE_GRACE = "offline_grace"       # Cho phép dùng offline tạm thời


@dataclass
class LicenseCheckResult:
    """Kết quả kiểm tra bản quyền chi tiết."""
    is_valid: bool
    status: LicenseStatus
    message: str
    license_key: Optional[str] = None


# ── Mapping từ license_client status codes sang LicenseStatus ────────────────

def _map_status(client_status: str) -> LicenseStatus:
    """Ánh xạ status code từ license_client sang LicenseStatus enum."""
    from core.license_client import (
        VALID, ACTIVATED, MIGRATED,
        LICENSE_NOT_FOUND, LICENSE_DISABLED, LICENSE_EXPIRED,
        DEVICE_MISMATCH, LEGACY_DEVICE_MISMATCH,
        NETWORK_ERROR, SERVER_ERROR,
    )

    mapping = {
        VALID: LicenseStatus.VALID,
        ACTIVATED: LicenseStatus.ACTIVATED,
        MIGRATED: LicenseStatus.MIGRATED,
        LICENSE_NOT_FOUND: LicenseStatus.NOT_FOUND,
        LICENSE_DISABLED: LicenseStatus.DISABLED,
        LICENSE_EXPIRED: LicenseStatus.EXPIRED,
        DEVICE_MISMATCH: LicenseStatus.DEVICE_MISMATCH,
        LEGACY_DEVICE_MISMATCH: LicenseStatus.DEVICE_MISMATCH,
        NETWORK_ERROR: LicenseStatus.NETWORK_ERROR,
        SERVER_ERROR: LicenseStatus.SERVER_ERROR,
    }
    return mapping.get(client_status, LicenseStatus.SERVER_ERROR)


# ── Kịch bản 1: Kích hoạt lần đầu ──────────────────────────────────────────

def activate_license(key: str) -> LicenseCheckResult:
    """
    Kích hoạt license key lần đầu trên máy này.

    Quy trình:
      - Gửi key + HWID lên Supabase.
      - Nếu cột hwid đang NULL → server ghi đè HWID → ACTIVATED.
      - Nếu cột hwid trùng → VALID (đã kích hoạt trước đó).
      - Nếu cột hwid khác → DEVICE_MISMATCH.

    Args:
        key: License key cần kích hoạt (dạng AF-XXXX-XXXX-XXXX-XXXX).

    Returns:
        LicenseCheckResult với trạng thái kích hoạt.
    """
    key = key.strip()
    if not key:
        return LicenseCheckResult(
            is_valid=False,
            status=LicenseStatus.NOT_FOUND,
            message="Vui lòng nhập License Key.",
        )

    from core.security import verify_license_online, save_local_license, get_hwid

    hwid = get_hwid()
    is_valid, message = verify_license_online(key, hwid)

    if is_valid:
        # Lưu license cục bộ khi kích hoạt thành công
        save_local_license(key, server_status="ACTIVATED")
        logger.info("[LICENSE_MANAGER] Kích hoạt thành công: key=%s...%s", key[:4], key[-4:])
        return LicenseCheckResult(
            is_valid=True,
            status=LicenseStatus.ACTIVATED,
            message=message,
            license_key=key,
        )

    logger.warning("[LICENSE_MANAGER] Kích hoạt thất bại: %s", message)
    return LicenseCheckResult(
        is_valid=False,
        status=LicenseStatus.NOT_FOUND,
        message=message,
    )


# ── Kịch bản 2: Kiểm tra hàng ngày ─────────────────────────────────────────

def check_license_status() -> LicenseCheckResult:
    """
    Kiểm tra trạng thái bản quyền khi khởi động ứng dụng hàng ngày.

    Quy trình:
      1. Tải license key từ cache cục bộ.
      2. Nếu không có → NO_KEY (cần hiện dialog kích hoạt).
      3. Nếu có → gửi key + HWID lên server xác thực.
      4. HWID trùng khớp → VALID → cho phép sử dụng.
      5. Lỗi mạng + có grace period → OFFLINE_GRACE.
      6. Lỗi khác → trả về trạng thái tương ứng.

    Returns:
        LicenseCheckResult với trạng thái kiểm tra.
    """
    from core.security import check_license_on_startup, load_local_license

    # Kiểm tra key cục bộ trước
    cached_key = load_local_license()
    if not cached_key:
        return LicenseCheckResult(
            is_valid=False,
            status=LicenseStatus.NO_KEY,
            message="Chưa có license key. Vui lòng kích hoạt bản quyền.",
        )

    # Gọi hàm kiểm tra startup (đã xử lý offline grace)
    is_valid, key = check_license_on_startup()

    if is_valid:
        logger.info("[LICENSE_MANAGER] Bản quyền hợp lệ (startup check).")
        return LicenseCheckResult(
            is_valid=True,
            status=LicenseStatus.VALID,
            message="Bản quyền hợp lệ.",
            license_key=key if key else cached_key,
        )

    logger.warning("[LICENSE_MANAGER] Bản quyền không hợp lệ (startup check).")
    return LicenseCheckResult(
        is_valid=False,
        status=LicenseStatus.DEVICE_MISMATCH,
        message="Bản quyền không hợp lệ. Vui lòng kích hoạt lại.",
    )


# ── Kịch bản 3: Kiểm tra nhanh HWID ────────────────────────────────────────

def verify_hwid_match(key: str) -> LicenseCheckResult:
    """
    Xác thực nhanh: key + HWID hiện tại có khớp với server không.

    Dùng khi cần kiểm tra giữa phiên làm việc (không phải startup).

    Args:
        key: License key cần kiểm tra.

    Returns:
        LicenseCheckResult với trạng thái HWID.
    """
    key = key.strip()
    if not key:
        return LicenseCheckResult(
            is_valid=False,
            status=LicenseStatus.NOT_FOUND,
            message="Key rỗng.",
        )

    from core.security import verify_license_online, get_hwid

    hwid = get_hwid()
    is_valid, message = verify_license_online(key, hwid)

    if is_valid:
        return LicenseCheckResult(
            is_valid=True,
            status=LicenseStatus.VALID,
            message=message,
            license_key=key,
        )

    # Use structured status codes from verify_license_online's underlying RPC
    # instead of fragile message string parsing.
    from core.device_identity import DeviceIdentityError, get_device_identity
    from core.license_client import activate_or_verify as _rpc_verify
    from core.security import SUPABASE_KEY, SUPABASE_URL
    from version import APP_VERSION

    try:
        identity = get_device_identity()
        from core.device_identity import get_legacy_hwid_candidates
        result = _rpc_verify(
            key=key,
            identity=identity,
            legacy_candidates=get_legacy_hwid_candidates(),
            supabase_url=SUPABASE_URL,
            supabase_key=SUPABASE_KEY,
            app_version=APP_VERSION,
        )
        status = _map_status(result.status)
    except (DeviceIdentityError, Exception):
        status = LicenseStatus.SERVER_ERROR

    return LicenseCheckResult(
        is_valid=False,
        status=status,
        message=message,
    )


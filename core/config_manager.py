"""
core/config_manager.py
──────────────────────────────────────────────────────────────────────────────
Quản lý file cấu hình config.json tại thư mục gốc của ứng dụng.

Chức năng:
- Load toàn bộ config khi khởi động
- Partial-update (ghi đè từng key) khi người dùng thay đổi cài đặt
- Không bao giờ raise exception ra ngoài — luôn fallback về giá trị mặc định
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

# ── Xác định vị trí config.json ──────────────────────────────────────────────
# Ưu tiên cùng thư mục với executable (khi đóng gói bằng PyInstaller).
# Fallback: thư mục chứa file này (khi chạy từ source).
if getattr(sys, "frozen", False):
    # PyInstaller: sys.executable là đường dẫn đến file .exe
    _APP_ROOT = Path(sys.executable).parent
else:
    # Chạy từ source: lên 1 cấp so với core/
    _APP_ROOT = Path(__file__).parent.parent

CONFIG_PATH: Path = _APP_ROOT / "config.json"

# ── Giá trị mặc định ─────────────────────────────────────────────────────────
_DEFAULTS: Dict[str, Any] = {
    "gemini_api_key":        "",
    "last_selected_engine":  "Google Bypass (Online Free)",
    "last_target_lang":      "Tiếng Việt (vi)",
    "translation_enabled":   False,
    "language":              "vi",
    "max_early_lead_ms":     20,
    "max_advance_ms":        30,
    "max_delay_ms":          200,
    "onset_confidence_threshold": 0.5,
}


def load_config() -> Dict[str, Any]:
    """
    Nạp toàn bộ config từ config.json.

    - Nếu file chưa tồn tại hoặc JSON lỗi: trả về bản sao của _DEFAULTS.
    - Merge thông minh: bổ sung key còn thiếu từ _DEFAULTS để chống
      KeyError khi codebase thêm key mới mà file cũ chưa có.

    Returns:
        dict: Config dictionary sạch, không bao giờ thiếu key bắt buộc.
    """
    merged = dict(_DEFAULTS)
    try:
        if CONFIG_PATH.exists():
            raw = CONFIG_PATH.read_text(encoding="utf-8")
            data = json.loads(raw)
            if isinstance(data, dict):
                merged.update(data)
    except Exception:
        pass  # File lỗi → dùng defaults, không crash app
    return merged


def save_config(updates: Dict[str, Any]) -> None:
    """
    Ghi đè (partial update) một hoặc nhiều key vào config.json.

    Đọc config hiện tại → merge updates → ghi lại toàn bộ.
    An toàn với concurrent writes theo quy trình đơn luồng (Qt main thread).

    Args:
        updates: Dict chứa các key-value cần cập nhật.
    """
    current = load_config()
    current.update(updates)
    try:
        CONFIG_PATH.write_text(
            json.dumps(current, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass  # Ghi thất bại → bỏ qua, không crash app


def get(key: str, default: Any = None) -> Any:
    """
    Tiện ích lấy một key đơn từ config.

    Args:
        key:     Tên key cần lấy.
        default: Giá trị trả về nếu key không tồn tại.

    Returns:
        Giá trị của key, hoặc default nếu không tìm thấy.
    """
    config = load_config()
    return config.get(key, default)

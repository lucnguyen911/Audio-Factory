"""Verified full-installer updater for frozen Audio Factory builds."""

from __future__ import annotations

import hashlib
import html
import http.cookiejar
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QEventLoop, QThread, Signal, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QStyle,
    QVBoxLayout,
)

from core.dpapi_storage import load_protected_json, save_protected_json
from version import APP_DATA_DIRNAME, APP_ID, APP_VERSION

CURRENT_VERSION = APP_VERSION
_UPDATE_DIR = Path(tempfile.gettempdir()) / APP_DATA_DIRNAME / "updates"
_PENDING_UPDATE_FILE = (
    Path(os.environ.get("APPDATA", os.path.expanduser("~")))
    / APP_DATA_DIRNAME
    / "pending_update.dat"
)


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.fullmatch(r"\s*v?(\d+(?:\.\d+)*)\s*", value or "")
    if not match:
        raise ValueError(f"Invalid semantic version: {value!r}")
    return tuple(int(part) for part in match.group(1).split("."))


def version_is_newer(latest: str, current: str) -> bool:
    try:
        left, right = _version_tuple(latest), _version_tuple(current)
        length = max(len(left), len(right))
        return left + (0,) * (length - len(left)) > right + (0,) * (length - len(right))
    except ValueError:
        return False


def _validate_update_metadata(row: dict) -> Dict[str, Any]:
    required = ("latest_version", "download_url", "sha256", "file_size")
    if any(row.get(name) in (None, "") for name in required):
        raise ValueError("Update metadata is incomplete.")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", str(row["sha256"])):
        raise ValueError("Update sha256 is invalid.")
    if str(row.get("package_type", "installer")) not in {"installer", "full"}:
        raise ValueError("Only full installer updates are supported.")
    enforcement = str(row.get("enforcement", "optional")).lower()
    if enforcement not in {"optional", "forced"}:
        raise ValueError("Update enforcement must be optional or forced.")
    result = dict(row)
    result["sha256"] = str(row["sha256"]).lower()
    result["file_size"] = int(row["file_size"])
    result["package_type"] = "installer"
    result["enforcement"] = enforcement
    result["is_forced"] = enforcement == "forced"
    if result["file_size"] <= 0:
        raise ValueError("Update file_size must be positive.")
    return result


def check_for_updates() -> Optional[Dict[str, Any]]:
    """Fetch signed metadata through a read-only SECURITY DEFINER RPC."""
    if not getattr(sys, "frozen", False):
        return None
    from core.security import SUPABASE_KEY, SUPABASE_URL

    url = f"{SUPABASE_URL}/rest/v1/rpc/get_active_app_version_v3"
    request = urllib.request.Request(
        url,
        data=json.dumps({"p_app_id": APP_ID}).encode("utf-8"),
        headers={
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            row = json.loads(response.read().decode("utf-8"))
        if not row:
            return None
        info = _validate_update_metadata(row)
        return info if version_is_newer(info["latest_version"], CURRENT_VERSION) else None
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError) as exc:
        print(
            f"[UPDATER] Update check rejected: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return None


def _google_drive_file_id(url: str) -> Optional[str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname not in {"drive.google.com", "docs.google.com"}:
        return None
    query_id = urllib.parse.parse_qs(parsed.query).get("id", [None])[0]
    if query_id:
        return query_id
    match = re.search(r"/file/d/([A-Za-z0-9_-]+)", parsed.path)
    return match.group(1) if match else None


def _initial_download_url(url: str) -> str:
    file_id = _google_drive_file_id(url)
    if not file_id:
        return url
    return "https://drive.usercontent.google.com/download?" + urllib.parse.urlencode(
        {"id": file_id, "export": "download", "confirm": "t"}
    )


def _extract_drive_confirmation(body: bytes, base_url: str) -> Optional[str]:
    text = html.unescape(body.decode("utf-8", errors="ignore"))
    href = re.search(r'href="([^"]*(?:confirm|download)[^"]*)"', text, re.I)
    if href:
        return urllib.parse.urljoin(base_url, href.group(1))
    form = re.search(r'<form[^>]+action="([^"]+)"[^>]*>(.*?)</form>', text, re.I | re.S)
    if not form:
        return None
    fields = dict(re.findall(r'name="([^"]+)"\s+value="([^"]*)"', form.group(2), re.I))
    return form.group(1) + ("?" + urllib.parse.urlencode(fields) if fields else "")


class DownloadWorker(QThread):
    progress = Signal(int, int)
    finished = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        url: str,
        dest_path: str,
        expected_sha256: str = "",
        expected_size: int = 0,
    ) -> None:
        super().__init__()
        self.url = url
        self.dest_path = dest_path
        self.expected_sha256 = expected_sha256.lower()
        self.expected_size = int(expected_size or 0)
        self._is_cancelled = False

    def run(self) -> None:
        part = Path(self.dest_path + ".part")
        try:
            destination = Path(self.dest_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.parent.resolve() != _UPDATE_DIR.resolve():
                raise ValueError("Updater destination is outside the trusted temp directory.")
            opener = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
            )
            headers = {"User-Agent": "AudioFactory-Updater/3"}
            response = opener.open(
                urllib.request.Request(_initial_download_url(self.url), headers=headers),
                timeout=45,
            )
            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" in content_type:
                body = response.read(2 * 1024 * 1024)
                confirmation = _extract_drive_confirmation(body, response.geturl())
                response.close()
                if not confirmation:
                    raise ValueError("Google Drive returned a confirmation page, not a file.")
                response = opener.open(
                    urllib.request.Request(confirmation, headers=headers), timeout=45
                )

            total_header = int(response.headers.get("Content-Length", 0) or 0)
            digest, downloaded = hashlib.sha256(), 0
            first_bytes = b""
            with response, open(part, "wb") as stream:
                while not self._is_cancelled:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    if not first_bytes:
                        first_bytes = chunk[:2]
                    stream.write(chunk)
                    digest.update(chunk)
                    downloaded += len(chunk)
                    self.progress.emit(downloaded, self.expected_size or total_header)
            if self._is_cancelled:
                raise RuntimeError("cancelled")
            if first_bytes != b"MZ":
                raise ValueError("Downloaded file is not a Windows installer.")
            if self.expected_size and downloaded != self.expected_size:
                raise ValueError("Downloaded installer size does not match metadata.")
            if self.expected_sha256 and digest.hexdigest() != self.expected_sha256:
                raise ValueError("Downloaded installer SHA-256 does not match metadata.")
            os.replace(part, destination)
            self.finished.emit(str(destination))
        except Exception as exc:
            try:
                part.unlink(missing_ok=True)
            except OSError:
                pass
            self.error.emit(str(exc))

    def cancel(self) -> None:
        self._is_cancelled = True


class UpdateCheckerWorker(QThread):
    update_available = Signal(dict)
    finished_checking = Signal()

    def run(self) -> None:
        try:
            info = check_for_updates()
            if info:
                self.update_available.emit(info)
        finally:
            self.finished_checking.emit()


def _download_destination(version: str) -> Path:
    _UPDATE_DIR.mkdir(parents=True, exist_ok=True)
    return _UPDATE_DIR / f"Audio_Factory_Setup_{version}.exe"


class UpdateDialog(QDialog):
    def __init__(self, info: Dict[str, Any], current_version: str, parent=None):
        super().__init__(parent)
        is_forced = info.get("enforcement") == "forced" or info.get("is_forced", False)
        title = "Cập nhật bắt buộc!" if is_forced else "Phiên bản mới khả dụng!"
        self.setWindowTitle(title)
        self.setMinimumWidth(440)
        self.setMaximumWidth(500)
        self.setStyleSheet("""
            QDialog {
                background-color: #f8f9fa;
                color: #212529;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 13px;
            }
            QLabel {
                color: #212529;
                background: transparent;
                font-size: 13px;
            }
            #divider {
                background-color: #dee2e6;
                max-height: 1px;
                min-height: 1px;
                border: none;
            }
            QPushButton {
                background-color: #ffffff;
                color: #212529;
                border: 1px solid #ced4da;
                border-radius: 6px;
                padding: 6px 18px;
                font-size: 13px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #e9ecef;
                border-color: #adb5bd;
            }
            QPushButton:pressed {
                background-color: #dee2e6;
            }
            QPushButton:focus {
                outline: none;
            }
        """)

        if parent and hasattr(parent, "windowIcon") and not parent.windowIcon().isNull():
            self.setWindowIcon(parent.windowIcon())
        else:
            icon_path = Path(__file__).resolve().parent.parent / "assets" / "logo.ico"
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(14)

        # Top Section: Icon on left, Content on right
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(14)

        # Icon Label (Blue Info Circle)
        icon_label = QLabel()
        std_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
        icon_label.setPixmap(std_icon.pixmap(44, 44))
        icon_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        top_layout.addWidget(icon_label, 0, Qt.AlignmentFlag.AlignTop)

        # Content Layout
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        lbl_curr = QLabel(f"Phiên bản hiện tại: &nbsp;<b>v{current_version}</b>")
        lbl_new = QLabel(f"Phiên bản mới: &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<b>v{info['latest_version']}</b>")
        content_layout.addWidget(lbl_curr)
        content_layout.addWidget(lbl_new)

        line1 = QFrame()
        line1.setObjectName("divider")
        line1.setFrameShape(QFrame.Shape.HLine)
        line1.setFrameShadow(QFrame.Shadow.Sunken)
        content_layout.addWidget(line1)

        lbl_log_title = QLabel("<b>Có gì mới:</b>")
        content_layout.addWidget(lbl_log_title)

        changelog_text = info.get("changelog", "Bản cập nhật mới.")
        lbl_changelog = QLabel(changelog_text)
        lbl_changelog.setWordWrap(True)
        content_layout.addWidget(lbl_changelog)

        line2 = QFrame()
        line2.setObjectName("divider")
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        content_layout.addWidget(line2)

        if is_forced:
            lbl_notice = QLabel("⚠️ <b>Đây là bản cập nhật bắt buộc. Bạn cần cập nhật để tiếp tục sử dụng.</b>")
        else:
            lbl_notice = QLabel("Bạn có muốn cập nhật ngay bây giờ không?")
        lbl_notice.setWordWrap(True)
        content_layout.addWidget(lbl_notice)

        top_layout.addLayout(content_layout, 1)
        main_layout.addLayout(top_layout)

        # Button Row
        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 6, 0, 0)
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_ok = QPushButton("Cập nhật ngay")
        self.btn_ok.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ok.setMinimumWidth(110)

        if is_forced:
            self.btn_cancel = QPushButton("Thoát ứng dụng")
        else:
            self.btn_cancel = QPushButton("Bỏ qua")
        self.btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_cancel.setMinimumWidth(110)

        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel.clicked.connect(self.reject)

        btn_layout.addWidget(self.btn_ok)
        btn_layout.addWidget(self.btn_cancel)
        main_layout.addLayout(btn_layout)


def show_update_dialog(info: Dict[str, Any], current_version: str, parent_widget=None) -> bool:
    dialog = UpdateDialog(info, current_version, parent_widget)
    return dialog.exec() == QDialog.DialogCode.Accepted


def run_update_check(parent_widget=None) -> bool:
    """Run after successful license verification; return True when app must exit."""
    info = check_for_updates()
    if not info:
        return False
    forced = info.get("enforcement") == "forced" or info.get("is_forced", False)
    
    user_accepted = show_update_dialog(info, CURRENT_VERSION, parent_widget)
    if not user_accepted:
        return forced

    destination = _download_destination(info["latest_version"])
    progress = QProgressDialog("Đang tải bản cập nhật...", "Hủy", 0, 100, parent_widget)
    progress.setWindowTitle("Tải cập nhật")
    progress.setMinimumDuration(0)

    if parent_widget and hasattr(parent_widget, "windowIcon") and not parent_widget.windowIcon().isNull():
        progress.setWindowIcon(parent_widget.windowIcon())
    else:
        icon_path = Path(__file__).resolve().parent.parent / "assets" / "logo.ico"
        if icon_path.exists():
            progress.setWindowIcon(QIcon(str(icon_path)))

    progress.setStyleSheet("""
        QProgressDialog {
            background-color: #f8f9fa;
            color: #212529;
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 13px;
        }
        QLabel {
            color: #212529;
            background: transparent;
            font-size: 13px;
            font-weight: 500;
        }
        QProgressBar {
            background-color: #e9ecef;
            color: #212529;
            border: 1px solid #ced4da;
            border-radius: 6px;
            text-align: center;
            font-size: 12px;
            font-weight: bold;
            height: 24px;
        }
        QProgressBar::chunk {
            background-color: #0d6efd;
            border-radius: 5px;
        }
        QPushButton {
            background-color: #ffffff;
            color: #212529;
            border: 1px solid #ced4da;
            border-radius: 6px;
            padding: 5px 16px;
            font-size: 13px;
            font-weight: 500;
            min-width: 80px;
        }
        QPushButton:hover {
            background-color: #e9ecef;
            border-color: #adb5bd;
        }
        QPushButton:pressed {
            background-color: #dee2e6;
        }
    """)
    worker = DownloadWorker(
        info["download_url"],
        str(destination),
        info["sha256"],
        info["file_size"],
    )
    loop, result, error = QEventLoop(), [], []
    worker.progress.connect(
        lambda done, total: progress.setValue(int(done * 100 / total) if total else 0)
    )
    worker.finished.connect(lambda path: (result.append(path), loop.quit()))
    worker.error.connect(lambda message: (error.append(message), loop.quit()))
    progress.canceled.connect(worker.cancel)
    worker.start()
    loop.exec()
    worker.wait()
    progress.close()
    if error or not result:
        QMessageBox.critical(parent_widget, "Lỗi cập nhật", error[0] if error else "Tải thất bại.")
        return forced
    launch_silent_installer(result[0], info["latest_version"])
    return True


def write_pending_update_flag(
    installer_path: str,
    target_version: str,
    install_dir: Optional[str] = None,
) -> None:
    install_dir = install_dir or str(Path(sys.executable).resolve().parent)
    save_protected_json(
        _PENDING_UPDATE_FILE,
        {
            "schema_version": 3,
            "status": "pending",
            "source_version": CURRENT_VERSION,
            "target_version": target_version,
            "expected_install_dir": str(Path(install_dir).resolve()),
            "installer_path": str(Path(installer_path).resolve()),
        },
    )


def check_and_clear_pending_update() -> Optional[Dict[str, Any]]:
    if not getattr(sys, "frozen", False):
        return None
    data = load_protected_json(_PENDING_UPDATE_FILE)
    if data is None:
        if _PENDING_UPDATE_FILE.exists():
            try:
                _PENDING_UPDATE_FILE.unlink()
            except OSError:
                pass
        return None
    try:
        expected_dir = Path(str(data["expected_install_dir"])).resolve()
        current_dir = Path(sys.executable).resolve().parent
        success = (
            data.get("schema_version") == 3
            and expected_dir == current_dir
            and not version_is_newer(str(data["target_version"]), CURRENT_VERSION)
        )
        return {
            "success": success,
            "from_version": str(data.get("source_version", "")),
            "to_version": str(data.get("target_version", "")),
        }
    finally:
        try:
            _PENDING_UPDATE_FILE.unlink(missing_ok=True)
        except OSError:
            pass


def launch_silent_installer(installer_path: str, target_version: str) -> None:
    installer = Path(installer_path).resolve()
    try:
        with open(installer, "rb") as stream:
            magic = stream.read(2)
    except OSError:
        magic = b""
    if (
        not getattr(sys, "frozen", False)
        or not installer.is_file()
        or installer.parent != _UPDATE_DIR.resolve()
        or magic != b"MZ"
    ):
        raise ValueError("Refusing to launch an untrusted updater package.")
    install_dir = Path(sys.executable).resolve().parent
    write_pending_update_flag(str(installer), target_version, str(install_dir))
    subprocess.Popen(
        [
            str(installer),
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CLOSEAPPLICATIONS",
            "/FORCECLOSEAPPLICATIONS",
            f'/DIR={install_dir}',
        ],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    os._exit(0)

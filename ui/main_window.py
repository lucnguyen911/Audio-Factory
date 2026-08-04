"""
ui/main_window.py
──────────────────────────────────────────────────────────────────────────────
Audio Factory – Main Window.
Pass 1: Foundation Shell.

Luật Pass 1:
  • Chỉ xây dựng khung giao diện (layout, widget, theme).
  • Không kết nối backend / worker thread.
  • Không fake data phức tạp.
  • Các slot và helper legacy (browse, start_processing…) giữ lại đủ signature
    để các file tests/* import mà không bị ImportError, nhưng body là stub.
"""

from __future__ import annotations

import os
import sys
import subprocess
import ctypes
import platform
from pathlib import Path
from typing import List, Optional, Dict

from core.cuda_runtime import bootstrap_nvidia_dlls

bootstrap_nvidia_dlls()

from PySide6.QtCore import (
    Qt, QThread, Signal, Slot, QSize, QPropertyAnimation,
    QEasingCurve, Property, QPoint, QTimer, QUrl,
)
from PySide6.QtGui import QPainter, QColor, QFont, QIcon, QPixmap, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QComboBox,
    QTextEdit,
    QProgressBar,
    QFileDialog,
    QMessageBox,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
    QFrame,
    QSizePolicy,
    QAbstractButton,
    QSpacerItem,
    QCheckBox,
)

# ── Internal imports ──────────────────────────────────────────────────────────
from ui.theme import APP_STYLESHEET
from ui.widgets import (
    Switch,
    IconBadge,
    FeatureCard,
    SocialOptimizeCard,
    VoiceCleanerCard,
    SectionPanel,
    DragDropTable,
    DropZoneFrame,
    _SUPPORTED_EXTS,
    create_labeled_combo,
    ComboBoxCheckmarkDelegate,
)

# ── Optional backend imports (graceful fallback for Pass-1 shell) ─────────────
try:
    from core.pipeline import (
        run_audio_pipeline,
        run_batch_pipeline,
        PipelineOptions,
        PipelineResult,
        PipelineError,
    )
    from core.importer import get_duration_seconds, MediaImportError
    from core.ffmpeg_runner import kill_active_ffmpeg_processes
    _BACKEND_AVAILABLE = True
except Exception:
    _BACKEND_AVAILABLE = False
    def kill_active_ffmpeg_processes() -> None:  # type: ignore[misc]
        """Stub: backend not available in Pass-1 shell."""
        pass

    # Minimal stubs so the rest of the file parses cleanly
    class PipelineOptions:  # type: ignore[no-redef]
        pass

    class PipelineResult:  # type: ignore[no-redef]
        pass

    class PipelineError(Exception):  # type: ignore[no-redef]
        pass

    def get_duration_seconds(path):  # type: ignore[misc]
        return None

    class MediaImportError(Exception):  # type: ignore[no-redef]
        pass

# ── Tính năng #5: Config Manager & Translator ───────────────────────────────────
# ── Cấu hình & Việt hóa ──────────────────────────────────────────────────────────
try:
    from core.config_manager import load_config, save_config
except Exception:
    def load_config():  # type: ignore[misc]
        return {}
    def save_config(updates):  # type: ignore[misc]
        pass

try:
    from core.localization import get_translation
except Exception:
    def get_translation(lang_code):  # type: ignore[misc]
        return {
            "window_title": "Audio Factory",
            "header_subtitle": "Premium Suite • Created by Lực Nguyễn",
            "footer": "Powered by FFmpeg + Whisper Local + Lực Nguyễn",
            "panel_input": "Đầu Vào",
            "panel_output": "Đầu Ra",
            "panel_processing": "Cấu Hình Xử Lý",
            "panel_subtitles": "Cấu Hình Phụ Đề",
            "panel_log": "Nhật ký xử lý",
            "panel_progress": "Tiến trình",
            "btn_add_files": "＋  Thêm tệp",
            "btn_remove_selected": "🗑  Xóa tất cả",
            "btn_move_up": "↑  Lên",
            "btn_move_down": "↓  Xuống",
            "lbl_sum_count": "📁  Tổng số: {count} tệp",
            "lbl_sum_duration": "⏱  Tổng thời lượng: {duration}",
            "lbl_sum_size": "💾  Tổng kích thước: {size}",
            "lbl_summary": "💡 *Kéo thả tệp âm thanh/video vào bảng trên để bắt đầu nhập*",
            "table_header_stt": "STT",
            "table_header_name": "Tên tệp",
            "table_header_duration": "Thời lượng",
            "table_header_size": "Kích thước",
            "table_header_action": "✕",
            "lbl_out_dir": "Thư mục đầu ra:",
            "placeholder_out_dir": "Chọn thư mục lưu kết quả...",
            "btn_browse_output": "📁  Chọn thư mục",
            "lbl_project_name": "Tên dự án:",
            "lbl_output_format": "Định dạng xuất:",
            "card_merge": "Gộp Audio",
            "card_voice": "Lọc Giọng Nói",
            "card_volume": "Cân Bằng Âm Lượng",
            "card_silence": "Thu Gọn Im Lặng",
            "card_split": "Tách Câu Spoken",
            "lbl_auto_sub": "Tạo phụ đề tự động",
            "lbl_trans_ai": "Dịch Phụ Đề",
            "lbl_lang": "Ngôn ngữ",
            "lbl_model": "Mô hình Whisper",
            "lbl_speed": "Tốc độ ASR",
            "lbl_batch": "Kích thước lô (Batch)",
            "lbl_format": "Khung hình video",
            "lbl_lines": "Số dòng tối đa",
            "lbl_target_lang": "Ngôn ngữ đích",
            "lbl_translate_model": "Model dịch",
            "lbl_google_msg": "✅ Dịch miễn phí qua Google — Không cần API Key",
            "lbl_api_key": "API Key:",
            "btn_clear_log": "🗑  Xóa log",
            "btn_export_log": "💾  Xuất log",
            "lbl_status_title": "Trạng thái:",
            "status_ready": "Sẵn sàng",
            "status_processing": "Đang xử lý...",
            "status_done": "Hoàn thành!",
            "status_translating": "Đang dịch phụ đề...",
            "status_error": "Gặp lỗi trong quá trình xử lý.",
            "status_cancelling": "Đang hủy...",
            "status_cancelled": "Đã hủy dịch thuật.",
            "lbl_elapsed_title": "Thời gian xử lý:",
            "btn_open_folder": "📁  Mở thư mục kết quả",
            "btn_start": "▶  Bắt đầu xử lý",
            "btn_start_processing": "⏳  Đang xử lý...",
            "btn_cancel": "■  Hủy bỏ"
        }

# ── Tính năng #5: Translator ────────────────────────────────────────────────────
try:
    from core.translator import (
        translate_srt_file,
        verify_api_keys,
        TranslationError,
        TranslationQuotaError,
        ENGINES as TRANSLATION_ENGINES,
        TARGET_LANGUAGES as TRANSLATION_TARGET_LANGUAGES,
    )
    _TRANSLATION_AVAILABLE = True
except Exception:
    _TRANSLATION_AVAILABLE = False
    def translate_srt_file(*args, **kwargs):  # type: ignore[misc]
        raise RuntimeError("Translation backend not available")
    def verify_api_keys(raw_keys, engine="gemini"):  # type: ignore[misc]
        return {"valid": 0, "total": 0, "details": ["Translator backend unavailable"]}
    class TranslationError(Exception):  # type: ignore[no-redef]
        pass
    class TranslationQuotaError(Exception):  # type: ignore[no-redef]
        pass
    TRANSLATION_ENGINES = {
        "Google Bypass (Online Free)": "google",
        "Gemini Flash (Tự động xoay Key & Model)": "gemini",
        "DeepSeek V4 Pro (API)": "deepseek",
    }
    TRANSLATION_TARGET_LANGUAGES = {
        "Tiếng Việt (vi)":            "vi",
        "Tiếng Anh (en)":             "en",
        "Tiếng Trung giản thể (zh)": "zh",
        "Tiếng Nhật (ja)":           "ja",
        "Tiếng Hàn (ko)":             "ko",
        "Tiếng Tây Ban Nha (es)":    "es",
        "Tiếng Pháp (fr)":            "fr",
        "Tiếng Nga (ru)":             "ru",
    }


# ── Thread Worker Kiểm tra API Key ─────────────────────────────────────────────
class KeyValidationWorker(QThread):
    finished_signal = Signal(dict)

    def __init__(self, raw_keys: str, engine: str):
        super().__init__()
        self.raw_keys = raw_keys
        self.engine = engine

    def run(self) -> None:
        result = verify_api_keys(self.raw_keys, self.engine)
        self.finished_signal.emit(result)


# ─────────────────────────────────────────────────────────────────────────────
# Custom UX widgets
# ─────────────────────────────────────────────────────────────────────────────

class NoScrollComboBox(QComboBox):
    """
    QComboBox tùy chỉnh: bỏ qua sự kiện cuộn chuột (wheelEvent) để tránh
    thay đổi giá trị ngoài ý muốn khi người dùng cuộn trang.

    Khi chuột lăn trên combo, sự kiện được chuyển tiếp lên widget cha
    (ScrollArea) để trang vẫn cuộn bình thường.
    """

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        # Bỏ qua thay đổi giá trị combo — chuyển sự kiện lên cha để page cuộn
        event.ignore()


class SmoothScrollArea(QScrollArea):
    """
    QScrollArea tùy chỉnh với hiệu ứng cuộn mượt (smooth scroll).

    Thay vì nhảy khấc ngay lập tức, dùng QPropertyAnimation (250ms,
    easing OutCubic) để di chuyển thanh cuộn êm ái như trình duyệt web.
    Hỗ trợ tích lũy target khi người dùng cuộn liên tiếp nhanh.
    """

    _STEP_PX: int = 80   # pixel mỗi notch chuột
    _DURATION: int = 250  # ms cho mỗi animation

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._target_value: int = 0
        self._anim: Optional[QPropertyAnimation] = None

    # Animation được khởi tạo lười (lazy) sau khi scrollbar sẵn sàng
    def _get_anim(self) -> QPropertyAnimation:
        if self._anim is None:
            self._anim = QPropertyAnimation(self.verticalScrollBar(), b"value")
            self._anim.setEasingCurve(QEasingCurve.OutCubic)
            self._anim.setDuration(self._DURATION)
            self._target_value = self.verticalScrollBar().value()
        return self._anim

    def wheelEvent(self, event) -> None:  # type: ignore[override]
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return

        anim = self._get_anim()
        vbar = self.verticalScrollBar()

        # Dừng animation hiện tại; vbar.value() giữ đúng vị trí giữa chừng
        anim.stop()

        # Tính target tích lũy để cuộn liên tiếp nhanh vẫn mượt
        steps = delta / 120.0
        self._target_value = max(
            vbar.minimum(),
            min(
                vbar.maximum(),
                self._target_value - int(steps * self._STEP_PX),
            ),
        )

        anim.setStartValue(vbar.value())
        anim.setEndValue(self._target_value)
        anim.start()
        event.accept()


# ─────────────────────────────────────────────────────────────────────────────
# Utility helpers
# ─────────────────────────────────────────────────────────────────────────────

def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / 1024 ** 3:.2f} GB"
    if size_bytes >= 1024 ** 2:
        return f"{size_bytes / 1024 ** 2:.2f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes} B"


def _format_duration(seconds: float) -> str:
    if seconds < 0:
        return "00:00:00"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


FORMAT_MAP: Dict[str, str] = {
    ".wav (WAV - Không nén)": "wav",
    ".mp3 (MP3 - Nén phổ biến)": "mp3",
    ".m4a (M4A - AAC)": "m4a",
    ".flac (FLAC - Không nén)": "flac",
    ".ogg (OGG - Vorbis)": "ogg",
}

PLATFORM_MAP: Dict[str, str] = {
    "YouTube / Facebook / X": "youtube_facebook_x",
    "TikTok / Instagram Reels": "tiktok_instagram",
    "Podcast / Voice Clean": "podcast_voice",
}

LANGUAGE_MAP: Dict[str, Optional[str]] = {
    "Tự động nhận diện": None,
    "Tiếng Trung (中文)": "zh",
    "Tiếng Anh (English)": "en",
    "Tiếng Việt": "vi",
    "Tiếng Nhật (日本語)": "ja",
    "Tiếng Hàn (한국어)": "ko",
    "Tiếng Nga (Русский)": "ru",
    "Tiếng Pháp (Français)": "fr",
    "Tiếng Tây Ban Nha": "es",
}


# ─────────────────────────────────────────────────────────────────────────────
# Worker thread stub (legacy API kept for tests)
# ─────────────────────────────────────────────────────────────────────────────

class PipelineCancelledError(Exception):
    """Raised when the user requests cancellation."""


class PipelineWorker(QThread):
    """Background worker — full pipeline with kill-switch cancellation support."""

    status_received  = Signal(str)
    finished_success = Signal(object)
    finished_error   = Signal(str)
    # Emitted with path of partially-created output dir that was cleaned up
    cleanup_done     = Signal(str)

    # ── Tín hiệu tiến độ chi tiết (spec Phần 5) ──────────────────────────
    # progress_signal(percent: int, status_text: str)
    #   Phân bổ: Whisper 0→50%  |  Dịch AI 50→95%  |  Xuất file 95→100%
    progress_signal  = Signal(int, str)
    # log_signal(text: str) — append trực tiếp vào ô Nhật ký
    log_signal       = Signal(str)
    # finished_signal(success: bool, message: str)
    finished_signal  = Signal(bool, str)

    def __init__(
        self,
        input_paths: List[Path],
        output_dir: Path,
        options: PipelineOptions,
        is_batch: bool,
    ) -> None:
        super().__init__()
        self.input_paths = input_paths
        self.output_dir = output_dir
        self.options = options
        self.is_batch = is_batch
        self.is_cancelled = False
        self.is_killed = False
        # Will be set to the actual project dir created by pipeline so cleanup knows what to remove
        self._created_project_dir: Optional[Path] = None

    def run(self) -> None:
        if not _BACKEND_AVAILABLE:
            self.finished_error.emit("Backend không khả dụng (Pass-1 shell).")
            self.finished_signal.emit(False, "Backend không khả dụng (Pass-1 shell).")
            return

        def _cb(msg: str) -> None:
            if self.is_cancelled:
                raise PipelineCancelledError("Cancelled")
            self.status_received.emit(msg)
            self.log_signal.emit(msg)

            # ── Phân bổ tiến độ thông minh theo keyword ──────────────────
            # Whisper (bóc băng):  0% → 50%
            # Dịch AI (song song): 50% → 95%
            # Xuất file:           95% → 100%
            ml = msg.lower()
            _kw_progress = [
                # Giai đoạn chuẩn bị & validate
                ("validating", 3),  ("project dir", 5),
                # Giai đoạn merge / pre-process
                ("merg", 10),       ("cộng hưởng", 12),
                # Giai đoạn làm sạch giọng, normalize
                ("clean", 18),      ("denois", 18),
                ("level", 26),      ("cân bằng", 26),   ("normaliz", 26),
                # Cắt khoảng lặng
                ("silence", 34),    ("khoảng lặng", 34),
                # Bóc băng Whisper (0→50%)
                ("speech-to-text", 42), ("transcrib", 42), ("whisper", 42),
                ("phụ đề", 48),     ("subtitles", 48),
                # Dịch AI (50→95%)
                ("dịch thuật", 60), ("translat", 60),
                ("đoạn 1", 62),     ("đoạn 2", 66),    ("đoạn 3", 70),
                ("đoạn 4", 74),     ("đoạn 5", 78),
                ("chunk", 72),
                # Xuất file (95→100%)
                ("metadata", 92),   ("ghi file", 95),
                ("completed", 100), ("thành công", 100), ("hoàn thành", 100),
            ]
            for kw, pct in _kw_progress:
                if kw in ml:
                    self.progress_signal.emit(pct, msg)
                    break

            # Track the project dir as soon as pipeline creates it
            if "Creating project directories" in msg:
                try:
                    import re
                    m = re.search(r"under (.+?)\.\.\.", msg)
                    if m:
                        self._created_project_dir = Path(m.group(1).strip())
                except Exception:
                    pass

        def _project_dir_cb(p: Path) -> None:
            self._created_project_dir = p

        def _progress_cb(pct: int, msg: str) -> None:
            if self.is_cancelled:
                raise PipelineCancelledError("cancelled")
            self.progress_signal.emit(pct, msg)

        try:
            if self.is_batch:
                results = run_batch_pipeline(
                    self.input_paths, self.output_dir, self.options,
                    status_callback=_cb,
                    cancel_check=lambda: self.is_cancelled,
                    project_dir_callback=_project_dir_cb,
                    progress_callback=_progress_cb,
                )
                self.progress_signal.emit(100, "Hoàn thành!")
                self.finished_signal.emit(True, "Tiến trình xử lý hoàn tất thành công!")
                self.finished_success.emit(results)
            else:
                result = run_audio_pipeline(
                    self.input_paths, self.output_dir, self.options,
                    status_callback=_cb,
                    cancel_check=lambda: self.is_cancelled,
                    project_dir_callback=_project_dir_cb,
                    progress_callback=_progress_cb,
                )
                self.progress_signal.emit(100, "Hoàn thành!")
                self.finished_signal.emit(True, "Tiến trình xử lý hoàn tất thành công!")
                self.finished_success.emit(result)
        except PipelineCancelledError:
            self._cleanup_partial_output()
            self.finished_error.emit("cancelled")
            self.finished_signal.emit(False, "Đã hủy tiến trình.")
        except Exception as exc:
            # Bắt trường hợp Whisper raise TranscriptionError("cancelled")
            # hoặc bất kỳ exception nào chứa từ khóa cancel trong msg
            msg = str(exc).lower()
            if self.is_cancelled or "cancelled" in msg:
                self._cleanup_partial_output()
                self.finished_error.emit("cancelled")
                self.finished_signal.emit(False, "Đã hủy tiến trình.")
            else:
                self.finished_error.emit(str(exc))
                self.finished_signal.emit(False, str(exc))

    def _cleanup_partial_output(self) -> None:
        """Delete the partially-created project directory on cancellation with retry logic."""
        target = self._created_project_dir
        if target is None:
            # Fallback: try to find most recent subdir in output_dir
            try:
                subdirs = sorted(
                    self.output_dir.iterdir(),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True
                )
                for d in subdirs:
                    if d.is_dir() and d.name.startswith(self.options.project_name):
                        target = d
                        break
            except Exception:
                return

        if target and target.exists() and target.is_dir():
            import time
            import shutil
            for attempt in range(3):
                try:
                    shutil.rmtree(target)
                    self.cleanup_done.emit(str(target))
                    break
                except Exception:
                    time.sleep(0.5)

    def cancel(self) -> None:
        """
        Request cancellation:
        1. Set the flag so _cb raises PipelineCancelledError at next checkpoint.
        2. Kill all active FFmpeg subprocesses IMMEDIATELY — do not wait for
           the current subprocess.Popen.communicate() to finish on its own.
        """
        self.is_cancelled = True
        self.is_killed = True
        kill_active_ffmpeg_processes()


# ─────────────────────────────────────────────────────────────────────────────
# Translation Worker (Tính năng #5)
# ─────────────────────────────────────────────────────────────────────────────

class TranslationWorker(QThread):
    """
    Worker thread riêng cho tác vụ dịch phụ đề (Tính năng #5).

    Tách khỏi PipelineWorker để:
    - Không block UI sau khi pipeline hoàn thành
    - Có thể hủy độc lập với pipeline
    - Bắt lỗi quota và phát signal đặc biệt để hiển thị popup

    Signals:
        status_received(str):  Thông báo tiến trình từng bước
        finished_success(str): Đường dẫn file SRT đã dịch (hoặc danh sách join)
        finished_error(str):   Thông báo lỗi chung
        quota_exceeded(str):   Hết quota API — UI cần hiển thị popup và dừng
    """

    status_received  = Signal(str)
    finished_success = Signal(str)   # path(s) của SRT đã dịch, phân cách bởi \n
    finished_error   = Signal(str)
    quota_exceeded   = Signal(str)   # Custom signal — hiển thị popup quota

    def __init__(
        self,
        srt_paths: List[Path],
        engine: str,
        target_lang: str,
        api_key: str,
    ) -> None:
        super().__init__()
        self.srt_paths   = srt_paths
        self.engine      = engine
        self.target_lang = target_lang
        self.api_key     = api_key
        self.is_cancelled = False
        self.is_killed = False

    def run(self) -> None:
        if not _TRANSLATION_AVAILABLE:
            self.finished_error.emit(
                "Translation backend không khả dụng. "
                "Kiểm tra cài đặt core/translator.py."
            )
            return

        translated_paths: List[str] = []

        for srt_path in self.srt_paths:
            if self.is_cancelled or self.is_killed:
                self.finished_error.emit("Người dùng đã hủy tiến trình dịch thuật.")
                return

            try:
                from core.translator import is_already_translated_srt
                if is_already_translated_srt(srt_path):
                    self.status_received.emit(f"[DỊCH THUẬT] ⚠️ Bỏ qua tệp đã dịch thuật: {srt_path.name}")
                    continue

                out_path = translate_srt_file(
                    srt_path=srt_path,
                    engine=self.engine,
                    target_lang=self.target_lang,
                    api_key=self.api_key,
                    status_callback=self.status_received.emit,
                    cancel_check=lambda: self.is_cancelled or self.is_killed,
                )
                translated_paths.append(str(out_path))

            except TranslationQuotaError as e:
                # Lỗi đặc biệt: hết quota → phát signal riêng để UI xử lý
                self.quota_exceeded.emit(str(e))
                return
            except TranslationError as e:
                if self.is_cancelled or self.is_killed or "hủy" in str(e).lower():
                    self.finished_error.emit("cancelled")
                    return
                self.finished_error.emit(str(e))
                return
            except Exception as e:
                self.finished_error.emit(f"Lỗi không xác định: {e}")
                return

        if translated_paths:
            self.finished_success.emit("\n".join(translated_paths))
        else:
            self.finished_error.emit("Không có file SRT nào được dịch.")

    def cancel(self) -> None:
        """Yêu cầu dừng luồng dịch thuật."""
        self.is_cancelled = True
        self.is_killed = True


# ─────────────────────────────────────────────────────────────────────────────
# Main Window
# ─────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):
    """
    Audio Factory – Main Window (Pass 1 Shell).

    Layout macro:
    ┌──────────────────────────────────────────────────────────┐
    │  HEADER (app title + logo placeholder)                   │
    ├───────────────────────────────┬──────────────────────────┤
    │  Row 1-L: 1. Cấu hình đầu vào│  Row 1-R: 2. Đầu ra     │
    ├───────────────────────────────┴──────────────────────────┤
    │  Row 2: 3. Tiến trình xử lý (5 feature cards)           │
    ├──────────────────────────────────────────────────────────┤
    │  Row 3: 4. Cấu hình phụ đề (collapsed by default)       │
    ├───────────────────────────────┬──────────────────────────┤
    │  Bottom-L: Nhật ký xử lý     │  Bottom-R: Tiến trình    │
    ├──────────────────────────────┴───────────────────────────┤
    │  FOOTER                                                  │
    └──────────────────────────────────────────────────────────┘
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Audio Factory")
        logo_path = Path(__file__).parent.parent / "assets" / "logo.png"
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))
        self.resize(1140, 840)
        self.setMinimumSize(960, 720)
        self.center_on_cursor_screen()

        # Runtime state
        self.worker: Optional[PipelineWorker] = None
        self.translation_worker: Optional[TranslationWorker] = None  # Tính năng #5
        self.last_output_dir: Optional[str] = None
        self.input_paths_list: List[Path] = []
        self.duration_cache: Dict[str, float] = {}

        # UI state variables
        self.output_dir: str = ""
        self.project_name: str = "audio_project"
        self.output_format: str = "wav"

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick_elapsed)
        self.elapsed_seconds: int = 0

        self._setup_ui()
        self.apply_branded_titlebar()
        self.setStyleSheet(APP_STYLESHEET)

        # Tính năng #5: Load config sau khi UI đã dựng xong
        self._load_translation_config()

    def center_on_cursor_screen(self) -> None:
        """Dùng QCursor và QApplication.screenAt(QCursor.pos()) để căn giữa cửa sổ ứng dụng ở màn hình chứa con trỏ chuột khi khởi động."""
        try:
            screen = QApplication.screenAt(QCursor.pos())
            if screen:
                screen_geometry = screen.availableGeometry()
                frame_geometry = self.frameGeometry()
                frame_geometry.moveCenter(screen_geometry.center())
                self.move(frame_geometry.topLeft())
        except Exception:
            pass


    # =========================================================================
    # UI Construction
    # =========================================================================

    def _setup_ui(self) -> None:
        """Build the full shell layout."""

        # Root scroll area
        self.main_scroll_area = SmoothScrollArea()
        self.main_scroll_area.setWidgetResizable(True)
        self.main_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.main_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setCentralWidget(self.main_scroll_area)

        container = QWidget()
        self.main_scroll_area.setWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(9)

        # ── Header ────────────────────────────────────────────────────────
        root.addWidget(self._build_header())

        # ── Row 1: Input (55%) + Output (45%) ─────────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(9)

        self.panel_input = SectionPanel(
            "Đầu Vào",
        )
        self._build_input_section()
        row1.addWidget(self.panel_input, 55)

        self.panel_output = SectionPanel("Đầu Ra")
        self._build_output_section()
        row1.addWidget(self.panel_output, 45)

        root.addLayout(row1)

        # ── Row 2: Processing cards ───────────────────────────────────────
        self.panel_processing = SectionPanel("Cấu Hình Xử Lý")
        self._build_processing_section()
        root.addWidget(self.panel_processing)

        # ── Row 3: Subtitle config ────────────────────────────────────────
        self._build_subtitle_section()
        root.addWidget(self.panel_subtitles)

        # ── Bottom row: Log (60%) + Progress (40%) ────────────────────────
        row_bottom = QHBoxLayout()
        row_bottom.setSpacing(9)

        self.panel_log = self._build_log_section()
        row_bottom.addWidget(self.panel_log, 60)

        self.panel_progress = self._build_progress_section()
        row_bottom.addWidget(self.panel_progress, 40)

        root.addLayout(row_bottom)

        # ── Footer ────────────────────────────────────────────────────────
        self.lbl_footer = QLabel("Powered by FFmpeg + Whisper Local + Lực Nguyễn")
        self.lbl_footer.setAlignment(Qt.AlignCenter)
        self.lbl_footer.setObjectName("FooterLabel")
        root.addWidget(self.lbl_footer)

        # Fix transparent override issue: restrict background transparency to the content widget specifically
        for panel in [
            self.panel_input, self.panel_output, self.panel_processing,
            self.panel_subtitles, self.panel_log, self.panel_progress
        ]:
            panel.content_widget.setObjectName("SectionContentWidget")
            panel.content_widget.setStyleSheet(
                "QWidget#SectionContentWidget { background: transparent; border: none; }"
            )

        # ── Legacy aliases (backward-compat with tests) ───────────────────
        self.chk_merge  = self.card_merge.switch
        self.chk_voice  = self.card_voice.switch
        self.chk_volume = self.card_volume.switch
        self.chk_silence = self.card_silence.switch
        self.chk_sub    = self.switch_auto_sub
        self.sub_section    = self
        self.content_panel  = self.sub_content_panel

        # Aliases for the dropdowns (to support conceptual naming in instructions)
        self.combo_source_lang = self.combo_lang
        self.combo_whisper_model = self.combo_model
        self.combo_asr_speed = self.combo_speed
        self.combo_batch_size = self.combo_batch
        self.combo_aspect_ratio = self.combo_format
        self.combo_max_lines = self.combo_lines
        self.combo_target_lang = self.combo_translate_lang
        self.combo_translation_model = self.combo_translate_engine
        self.lbl_api_hint = self.lbl_gemini_hint

        # Connect state synchronization signals
        self.txt_output.textChanged.connect(self._on_output_dir_changed)
        self.txt_project_name.textChanged.connect(self._on_project_name_changed)
        self.combo_out_format.currentIndexChanged.connect(self._on_format_changed)

        # Initialize state values from widgets
        self.output_dir = self.txt_output.text()
        self.project_name = self.txt_project_name.text()
        self.output_format = self.combo_out_format.currentData() or "wav"

        # Check for updates automatically in the background
        # main.py performs the single update check after license verification.

    # =========================================================================
    # Header
    # =========================================================================

    def _build_header(self) -> QWidget:
        """App title bar with logo icon on the left — synced with Video Cutter."""
        header = QWidget()
        header.setObjectName("HeaderPanel")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(10)

        # Logo placeholder
        self.logo_label = QLabel()
        self.logo_label.setFixedSize(32, 32)
        self.logo_label.setAlignment(Qt.AlignCenter)
        logo_path = Path(__file__).parent.parent / "assets" / "logo.png"
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path)).scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.logo_label.setPixmap(pixmap)
        else:
            self.logo_label.setText("🎵")
            self.logo_label.setStyleSheet("""
                QLabel {
                    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                        stop:0 #2563eb, stop:1 #7c3aed);
                    border-radius: 8px;
                    font-size: 16px;
                    border: none;
                }
            """)
        layout.addWidget(self.logo_label)

        title_block = QWidget()
        title_vbox = QVBoxLayout(title_block)
        title_vbox.setContentsMargins(0, 0, 0, 0)
        title_vbox.setSpacing(2)

        self.title_label = QLabel("AUDIO FACTORY")
        self.title_label.setObjectName("HeaderTitle")
        title_vbox.addWidget(self.title_label)

        self.subtitle_label = QLabel()
        self.subtitle_label.setObjectName("HeaderSubtitle")
        title_vbox.addWidget(self.subtitle_label)

        self.header_divider = QFrame()
        self.header_divider.setObjectName("HeaderDivider")
        self.header_divider.setFixedHeight(2)
        title_vbox.addWidget(self.header_divider)

        layout.addWidget(title_block)
        layout.addStretch()

        # Ô chọn ngôn ngữ giao diện (UI Language Selector)
        self.combo_ui_lang = NoScrollComboBox()
        self.combo_ui_lang.setObjectName("HeaderLangMenu")
        self.combo_ui_lang.addItem("Tiếng Việt", "vi")
        self.combo_ui_lang.addItem("English", "en")
        self.combo_ui_lang.setFixedWidth(110)
        layout.addWidget(self.combo_ui_lang)

        # Nút chuyển đổi giao diện Sáng/Tối
        self.theme_button = QPushButton()
        self.theme_button.setObjectName("ThemeToggleButton")
        self.theme_button.setFixedSize(36, 26)
        self.theme_button.setIconSize(QSize(18, 18))
        self.theme_button.setCursor(Qt.PointingHandCursor)
        self.theme_button.setText("") # Đảm bảo xóa text
        
        self._icon_sun = QIcon(str(Path(__file__).parent.parent / "assets" / "sun.svg"))
        self._icon_moon = QIcon(str(Path(__file__).parent.parent / "assets" / "moon.svg"))
        
        self.theme_is_dark = False
        self.theme_button.setIcon(self._icon_sun)
        self.theme_button.setToolTip("Chuyển sang giao diện tối")
        self.theme_button.clicked.connect(self.toggle_theme)
        
        layout.addWidget(self.theme_button)

        return header

    # =========================================================================
    # Section 1 – Input
    # =========================================================================

    def _build_input_section(self) -> None:
        # ── Action button row ─────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(6)

        self.btn_add_files = QPushButton("＋  Thêm tệp")
        self.btn_add_files.setObjectName("btn_add")
        self.btn_add_files.setCursor(Qt.PointingHandCursor)
        self.btn_add_files.setMinimumHeight(34)
        self.btn_add_files.clicked.connect(self.browse_inputs)

        self.btn_remove_selected = QPushButton("🗑  Xóa tất cả")
        self.btn_remove_selected.setObjectName("btn_remove")
        self.btn_remove_selected.setCursor(Qt.PointingHandCursor)
        self.btn_remove_selected.setMinimumHeight(34)
        self.btn_remove_selected.clicked.connect(self.clear_all_inputs)

        self.btn_move_up = QPushButton("↑  Lên")
        self.btn_move_up.setObjectName("btn_neutral")
        self.btn_move_up.setCursor(Qt.PointingHandCursor)
        self.btn_move_up.setMinimumHeight(34)
        self.btn_move_up.clicked.connect(self.move_up)

        self.btn_move_down = QPushButton("↓  Xuống")
        self.btn_move_down.setObjectName("btn_neutral")
        self.btn_move_down.setCursor(Qt.PointingHandCursor)
        self.btn_move_down.setMinimumHeight(34)
        self.btn_move_down.clicked.connect(self.move_down)

        btn_row.addWidget(self.btn_add_files)
        btn_row.addWidget(self.btn_remove_selected)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_move_up)
        btn_row.addWidget(self.btn_move_down)
        self.panel_input.content_layout.addLayout(btn_row)

        # ── File table inside drop zone ───────────────────────────────────
        self.drop_zone = DropZoneFrame()
        dz_layout = QVBoxLayout(self.drop_zone)
        dz_layout.setContentsMargins(0, 0, 0, 0)
        dz_layout.setSpacing(0)

        self.table = DragDropTable()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["STT", "Tên tệp", "Thời lượng", "Kích thước", "✕"])
        self.table.setColumnWidth(0, 52)
        self.table.setColumnWidth(2, 96)
        self.table.setColumnWidth(3, 104)
        self.table.setColumnWidth(4, 45)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(36)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setMinimumHeight(185)
        # The file list is mouse-driven.  Keep row selection, but do not draw
        # a focused-cell frame around the file name after a click.
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.order_changed.connect(self._handle_row_move)
        # Bắt drop từ bên trong bảng (viewport) — bổ sung cho drop_zone bên ngoài
        self.table.files_dropped.connect(self.add_files_from_paths)

        dz_layout.addWidget(self.table)
        # Cài DropZoneFrame làm event filter trên viewport bảng:
        # drag events trên MỌI pixel trong lòng bảng đều kích hoạt highlight viền nét đứt
        self.drop_zone.install_on_viewport(self.table)
        self.drop_zone.files_dropped.connect(self.add_files_from_paths)
        self.panel_input.content_layout.addWidget(self.drop_zone)

        # ── Summary chips ─────────────────────────────────────────────────
        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(0, 4, 0, 0)
        summary_row.setSpacing(8)

        self.lbl_sum_count    = QLabel("📁  Tổng số: 0 tệp")
        self.lbl_sum_duration = QLabel("⏱  Tổng thời lượng: 00:00:00")
        self.lbl_sum_size     = QLabel("💾  Tổng kích thước: 0 B")

        for chip in [self.lbl_sum_count, self.lbl_sum_duration, self.lbl_sum_size]:
            chip.setObjectName("SummaryChip")
            summary_row.addWidget(chip)
        summary_row.addStretch()

        self.panel_input.content_layout.addLayout(summary_row)

        # Legacy hidden label
        self.lbl_summary = QLabel()
        self.lbl_summary.setVisible(False)
        self.panel_input.content_layout.addWidget(self.lbl_summary)

    # =========================================================================
    # Section 2 – Output
    # =========================================================================

    def _build_output_section(self) -> None:
        LABEL_W = 120  # chiều rộng cố định cho 3 label lề trái → căn thẳng đứng

        v = QVBoxLayout()
        v.setContentsMargins(0, 8, 0, 8)
        v.setSpacing(12)

        # ── Hàng 1: Thư mục đầu ra ───────────────────────────────────────
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(8)
        row1.setAlignment(Qt.AlignVCenter)

        self.lbl_out_dir = QLabel("Thư mục đầu ra:")
        self.lbl_out_dir.setObjectName("FieldLabel")
        self.lbl_out_dir.setFixedWidth(LABEL_W)
        self.lbl_out_dir.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        row1.addWidget(self.lbl_out_dir)

        self.txt_output = QLineEdit()
        self.txt_output.setObjectName("InputField")
        self.txt_output.setPlaceholderText("Chọn thư mục lưu kết quả...")
        self.txt_output.setFixedHeight(32)
        row1.addWidget(self.txt_output, 1)

        self.btn_browse_output = QPushButton("📁  Chọn thư mục")
        self.btn_browse_output.setObjectName("btn_browse")
        self.btn_browse_output.setCursor(Qt.PointingHandCursor)
        self.btn_browse_output.setFixedHeight(32)
        self.btn_browse_output.clicked.connect(self.browse_output)
        row1.addWidget(self.btn_browse_output)

        v.addLayout(row1)

        # ── Hàng 2: Tên dự án ────────────────────────────────────────────
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(8)
        row2.setAlignment(Qt.AlignVCenter)

        self.lbl_project_name = QLabel("Tên dự án:")
        self.lbl_project_name.setObjectName("FieldLabel")
        self.lbl_project_name.setFixedWidth(LABEL_W)
        self.lbl_project_name.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        row2.addWidget(self.lbl_project_name)

        self.txt_project_name = QLineEdit()
        self.txt_project_name.setObjectName("InputField")
        self.txt_project_name.setText("audio_project")
        self.txt_project_name.setFixedHeight(32)
        row2.addWidget(self.txt_project_name, 1)

        v.addLayout(row2)

        # ── Hàng 3: Định dạng xuất ───────────────────────────────────────
        row3 = QHBoxLayout()
        row3.setContentsMargins(0, 0, 0, 0)
        row3.setSpacing(8)
        row3.setAlignment(Qt.AlignVCenter)

        self.lbl_output_format = QLabel("Định dạng xuất:")
        self.lbl_output_format.setObjectName("FieldLabel")
        self.lbl_output_format.setFixedWidth(LABEL_W)
        self.lbl_output_format.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        row3.addWidget(self.lbl_output_format)

        self.combo_out_format = NoScrollComboBox()
        self.combo_out_format.setObjectName("OutputFormatCombo")
        # NOTE: setMaxVisibleItems(5) ensures dropdown stays compact
        self.combo_out_format.setMaxVisibleItems(5)
        self.combo_out_format.addItem(".wav (WAV - Không nén)", "wav")
        self.combo_out_format.addItem(".mp3 (MP3 - Nén phổ biến)", "mp3")
        self.combo_out_format.addItem(".m4a (M4A - AAC)", "m4a")
        self.combo_out_format.addItem(".flac (FLAC - Không nén)", "flac")
        self.combo_out_format.addItem(".ogg (OGG - Vorbis)", "ogg")
        self.combo_out_format.view().setItemDelegate(
            ComboBoxCheckmarkDelegate(self.combo_out_format)
        )
        self.combo_out_format.setFixedHeight(32)
        row3.addWidget(self.combo_out_format, 1)

        v.addLayout(row3)
        v.addStretch()
        self.panel_output.content_layout.addLayout(v)



    # =========================================================================
    # Section 3 – Processing cards
    # =========================================================================

    def _build_processing_section(self) -> None:
        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(8)

        self.card_merge = FeatureCard(
            "Merge",
            "🔊", "#7c3aed",
        )
        self.card_voice = VoiceCleanerCard(
            "Denoise",
            "🎙", "#ea580c",
        )
        self.card_volume = FeatureCard(
            "Normalize",
            "📶", "#2563eb",
        )
        self.card_silence = FeatureCard(
            "Cut Silence",
            "✂", "#d97706",
        )

        for card in [
            self.card_merge, self.card_voice,
            self.card_volume, self.card_silence,
        ]:
            card.setFixedHeight(52)
            cards_row.addWidget(card, 1)  # stretch 1 đồng đều → 4 phần bằng nhau

        # KHÔNG addStretch ở cuối — để 4 card chiếm trọn chiều ngang

        self.panel_processing.content_layout.addLayout(cards_row)

        # Default switch states
        self.card_merge.switch.setChecked(False)
        self.card_voice.switch.setChecked(False)
        self.card_volume.switch.setChecked(True)
        self.card_volume.setToolTip(
            "Bật để làm đều vùng giọng nói. Tắt để giữ nguyên âm lượng gốc; "
            "bảo vệ chống vỡ tiếng vẫn luôn chạy khi xuất."
        )
        self.card_silence.switch.setChecked(True)

    # =========================================================================
    # Section 4 – Subtitle config
    # =========================================================================

    def _build_subtitle_section(self) -> None:
        # ── Right-side header: label + Switch (animated, đồng bộ với Section 3) ──
        sub_header = QWidget()
        sub_header.setStyleSheet("background: transparent; border: none;")
        sub_header_layout = QHBoxLayout(sub_header)
        sub_header_layout.setContentsMargins(0, 0, 0, 0)
        sub_header_layout.setSpacing(8)

        self.lbl_auto_sub = QLabel("Tạo phụ đề tự động")
        self.lbl_auto_sub.setObjectName("SubtitleToggleLabel")
        sub_header_layout.addWidget(self.lbl_auto_sub)

        # QCheckBox#ToggleSwitch – ĐÚNG class như Merge/Denoise/Normalize/CutSilence ở Section 3
        self.switch_auto_sub = QCheckBox()
        self.switch_auto_sub.setObjectName("ToggleSwitch")
        self.switch_auto_sub.setCursor(Qt.PointingHandCursor)
        sub_header_layout.addWidget(self.switch_auto_sub)

        self.panel_subtitles = SectionPanel(
            "Cấu Hình Phụ Đề",
            right_header_widget=sub_header,
        )

        # Placeholder đã được xóa bỏ: khi OFF, content_layout trống → panel
        # thu lại chỉ còn thanh tiêu đề; layout bên dưới tự động đẩy lên khít.

        # ── Expanded content panel (hiện khi bật) ─────────────────────────
        self.sub_content_panel = QFrame()
        self.sub_content_panel.setObjectName("SubContentPanel")
        outer_v = QVBoxLayout(self.sub_content_panel)
        outer_v.setContentsMargins(0, 0, 0, 0)
        outer_v.setSpacing(0)

        # ── subtitle_settings_card: QFrame card chứa 6 ô cấu hình phụ đề ──────
        # CSS màu nền được định nghĩa trong theme.py (QFrame#subtitle_settings_card)
        self.subtitle_settings_card = QFrame()
        self.subtitle_settings_card.setObjectName("subtitle_settings_card")
        self.subtitle_settings_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        grid_sub = QGridLayout(self.subtitle_settings_card)
        grid_sub.setContentsMargins(16, 14, 16, 14)
        grid_sub.setHorizontalSpacing(16)
        grid_sub.setVerticalSpacing(12)
        # 3 cột stretch đều nhau → 6 ComboBox giãn đều tăm tắp 100% chiều ngang
        grid_sub.setColumnStretch(0, 1)
        grid_sub.setColumnStretch(1, 1)
        grid_sub.setColumnStretch(2, 1)

        # ComboBox – không setFixedWidth → tự do co giãn theo cột
        self.combo_lang = NoScrollComboBox()
        self.combo_lang.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_lang.addItems([
            "Tự động nhận diện",
            "Tiếng Việt",
            "Tiếng Anh (English)",
            "Tiếng Trung (中文)",
            "Tiếng Nhật (日本語)",
            "Tiếng Hàn (한국어)",
            "Tiếng Nga (Русский)",
            "Tiếng Pháp (Français)",
            "Tiếng Tây Ban Nha",
        ])

        self.combo_model = NoScrollComboBox()
        self.combo_model.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_model.addItems([
            "large-v3-turbo (Nhanh x8, chính xác tốt - Khuyên dùng)",
            "large-v3 (Chính xác tối đa - Yêu cầu cấu hình mạnh)",
            "medium (Tốc độ nhanh, nhẹ máy - Độ chính xác khá)",
        ])
        self.combo_model.setCurrentIndex(0)  # Mặc định: large-v3-turbo

        self.combo_speed = NoScrollComboBox()
        self.combo_speed.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_speed.addItems([
            "1.0x (Tốc độ gốc - Mặc định)",
            "0.9x (Giọng nói nhanh - Tăng chính xác)",
            "0.8x (Giọng nói cực nhanh / Tin tức / Rap)",
        ])
        self.combo_speed.setCurrentIndex(0)  # Mặc định: 1.0x (Tốc độ gốc)

        self.combo_batch = NoScrollComboBox()
        self.combo_batch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_batch.addItems([
            "1 (Tuần tự - Ít VRAM nhất, chậm nhất)",
            "2 (Song song nhẹ)",
            "4 (Song song vừa)",
            "8 (Song song nhanh - Khuyên dùng)",
            "16 (Song song tối đa - Cần nhiều VRAM)",
            "32 (Cực nhanh - Yêu cầu GPU khủng)",
        ])
        self.combo_batch.setCurrentIndex(3)  # Mặc định: 8 (Song song nhanh - Khuyên dùng)

        self.combo_format = NoScrollComboBox()
        self.combo_format.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_format.addItems([
            "16:9 (Video Ngang)",
            "9:16 (Video Dọc)",
            "1:1 (Video Vuông)",
        ])
        self.combo_format.setCurrentIndex(0)  # Mặc định: 16:9 (Video Ngang)

        self.combo_lines = NoScrollComboBox()
        self.combo_lines.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_lines.addItems([
            "1 dòng (Gọn – 1 hàng chữ mỗi đoạn)",
            "2 dòng (2 hàng chữ mỗi đoạn)",
        ])
        self.combo_lines.setCurrentIndex(0)  # Mặc định: 1 dòng (shorts/tiktok)

        self.w_lang = create_labeled_combo("Ngôn ngữ",             self.combo_lang)
        self.w_model = create_labeled_combo("Mô hình Whisper",       self.combo_model)
        self.w_speed = create_labeled_combo("Tốc độ ASR",            self.combo_speed)
        self.w_batch = create_labeled_combo("Kích thước lô (Batch)", self.combo_batch)
        self.w_format = create_labeled_combo("Khung hình video",       self.combo_format)
        self.w_lines = create_labeled_combo("Số dòng tối đa",        self.combo_lines)

        grid_sub.addWidget(self.w_lang,   0, 0)
        grid_sub.addWidget(self.w_model,  0, 1)
        grid_sub.addWidget(self.w_speed,  0, 2)
        grid_sub.addWidget(self.w_batch,  1, 0)
        grid_sub.addWidget(self.w_format, 1, 1)
        grid_sub.addWidget(self.w_lines,  1, 2)

        outer_v.addWidget(self.subtitle_settings_card)

        # ── Spacer giữa 2 card ─────────────────────────────────────────────
        outer_v.addSpacing(8)

        # ── Translation Settings Card (Tính năng #5) ───────────────────────
        self.translation_settings_card = QFrame()
        self.translation_settings_card.setObjectName("translation_settings_card")
        self.translation_settings_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.translation_settings_card.setMinimumHeight(150)

        self.trans_v = QVBoxLayout(self.translation_settings_card)
        self.trans_v.setContentsMargins(16, 14, 16, 22)   # top: 14px, bottom: 22px
        self.trans_v.setSpacing(12)                       # khoảng cách header → detail panel

        # ── Header row: Toggle + Label ─────────────────────────────────────
        # Căn giữa trục dọc tuyệt đối cho toàn bộ hàng tiêu đề
        trans_header = QHBoxLayout()
        trans_header.setContentsMargins(0, 0, 0, 0)
        trans_header.setSpacing(10)
        trans_header.setAlignment(Qt.AlignVCenter)  # căn giữa dọc toàn hàng

        self.lbl_trans_toggle = QLabel("Dịch Phụ Đề")
        self.lbl_trans_toggle.setObjectName("TranslationToggleLabel")
        self.lbl_trans_toggle.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)  # căn giữa dọc tường minh
        trans_header.addWidget(self.lbl_trans_toggle, 0, Qt.AlignVCenter)
        trans_header.addStretch()

        self.switch_translate = QCheckBox()
        self.switch_translate.setObjectName("ToggleSwitch")
        self.switch_translate.setCursor(Qt.PointingHandCursor)
        self.switch_translate.setChecked(False)
        trans_header.addWidget(self.switch_translate, 0, Qt.AlignVCenter)  # căn giữa dọc

        self.trans_v.addLayout(trans_header)

        # ── Detail panel: chỉ hiện khi toggle ON ──────────────────────────
        self.translation_detail_panel = QFrame()
        self.translation_detail_panel.setObjectName("TranslationDetailPanel")

        # QGridLayout 2×3: căn chỉnh cột pixel-perfect
        #   Cột 0 (trái):  Ngôn ngữ đích (hàng 0) │ combo lang (hàng 1) │ Hint (hàng 2)
        #   Cột 1 (phải):  Động cơ dịch (hàng 0)  │ combo engine (hàng 1) │ API key (hàng 2)
        detail_grid = QGridLayout(self.translation_detail_panel)
        detail_grid.setContentsMargins(0, 4, 0, 18)  # top 4px, bottom 18px
        detail_grid.setHorizontalSpacing(12)
        detail_grid.setVerticalSpacing(12)
        detail_grid.setColumnStretch(0, 1)
        detail_grid.setColumnStretch(1, 1)

        _COMBO_H = 32  # chiều cao chuẩn đồng bộ ComboBox ↔ QLineEdit

        # ══ Hàng 0: Labels tiêu đề ══
        self.lbl_trans_lang = QLabel("Ngôn ngữ đích")
        self.lbl_trans_lang.setObjectName("TranslationFieldLabel")
        detail_grid.addWidget(self.lbl_trans_lang, 0, 0)

        self.lbl_trans_engine = QLabel("Model dịch")
        self.lbl_trans_engine.setObjectName("TranslationFieldLabel")
        detail_grid.addWidget(self.lbl_trans_engine, 0, 1)

        # ══ Hàng 1: ComboBox Ngôn ngữ đích ══
        self.combo_translate_lang = NoScrollComboBox()
        self.combo_translate_lang.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_translate_lang.setFixedHeight(_COMBO_H)
        for lang_label in TRANSLATION_TARGET_LANGUAGES:
            self.combo_translate_lang.addItem(lang_label, TRANSLATION_TARGET_LANGUAGES[lang_label])
        detail_grid.addWidget(self.combo_translate_lang, 1, 0)

        # ══ Hàng 1: ComboBox Động cơ dịch (chỉ Gemini + Google) ══
        self.combo_translate_engine = NoScrollComboBox()
        self.combo_translation_model = self.combo_translate_engine
        self.combo_translation_model.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.combo_translation_model.setFixedHeight(_COMBO_H)
        for engine_label in TRANSLATION_ENGINES:
            self.combo_translation_model.addItem(engine_label, TRANSLATION_ENGINES[engine_label])
        # Mặc định: Google Bypass (engine miễn phí, không cần key)
        google_idx = list(TRANSLATION_ENGINES.keys()).index("Google Bypass (Online Free)") \
            if "Google Bypass (Online Free)" in TRANSLATION_ENGINES else 0
        self.combo_translation_model.setCurrentIndex(google_idx)
        detail_grid.addWidget(self.combo_translation_model, 1, 1)

        # ══ Hàng 2, Cột 0: Layout chứa [Hint Label bên trái] + [API Key: Label bên phải] ══
        col0_widget = QWidget()
        col0_widget.setObjectName("TransCol0Widget")
        col0_widget.setStyleSheet("QWidget#TransCol0Widget { background: transparent; border: none; }")
        col0_layout = QHBoxLayout(col0_widget)
        col0_layout.setContentsMargins(0, 0, 0, 0)
        col0_layout.setSpacing(8)

        # Khung chứa các câu Hướng dẫn / Thông báo bên trái
        hints_container = QWidget()
        hints_container.setStyleSheet("background: transparent; border: none;")
        hints_v = QVBoxLayout(hints_container)
        hints_v.setContentsMargins(0, 0, 0, 0)
        hints_v.setSpacing(0)

        # 1. Gemini Hint Link
        self.lbl_gemini_hint = QLabel(
            'Gemini API lấy tại '
            '<a href="https://aistudio.google.com/apikey" style="color: #2563eb; text-decoration: underline;">'
            'Lấy Key tại đây</a>.'
        )
        self.lbl_gemini_hint.setObjectName("TranslationStatusLabel")
        self.lbl_gemini_hint.setOpenExternalLinks(True)
        self.lbl_gemini_hint.setTextFormat(Qt.RichText)
        self.lbl_gemini_hint.setVisible(False)
        hints_v.addWidget(self.lbl_gemini_hint)

        # 2. DeepSeek Hint Link
        self.lbl_deepseek_hint = QLabel(
            'DeepSeek API lấy tại '
            '<a href="https://platform.deepseek.com/api_keys" style="color: #2563eb; text-decoration: underline;">'
            'Lấy Key tại đây</a>.'
        )
        self.lbl_deepseek_hint.setObjectName("TranslationStatusLabel")
        self.lbl_deepseek_hint.setOpenExternalLinks(True)
        self.lbl_deepseek_hint.setTextFormat(Qt.RichText)
        self.lbl_deepseek_hint.setVisible(False)
        hints_v.addWidget(self.lbl_deepseek_hint)

        # 3. Google Free Message
        self.lbl_google_msg = QLabel("✅ Dịch miễn phí qua Google — Không cần API Key")
        self.lbl_google_msg.setObjectName("TranslationStatusLabel")
        self.lbl_google_msg.setVisible(True)
        hints_v.addWidget(self.lbl_google_msg)

        col0_layout.addWidget(hints_container, 1, Qt.AlignLeft | Qt.AlignVCenter)

        # Label "API Key:" đặt sát bên phải của Cột 0 (ngay lề trái ô nhập Key)
        self.lbl_api_key_title = QLabel("API Key:")
        self.lbl_api_key_title.setStyleSheet("font-weight: 600; font-size: 13px; background: transparent; border: none;")
        self.lbl_api_key_title.setVisible(False)
        col0_layout.addWidget(self.lbl_api_key_title, 0, Qt.AlignRight | Qt.AlignVCenter)

        # Button Kiểm tra Key (đặt sát bên phải Cột 0 bên cạnh label API Key:)
        self.btn_check_keys = QPushButton("🔍  Kiểm tra")
        self.btn_check_keys.setObjectName("btn_check_keys")
        self.btn_check_keys.setCursor(Qt.PointingHandCursor)
        self.btn_check_keys.setFixedHeight(26)
        self.btn_check_keys.setStyleSheet("""
            QPushButton#btn_check_keys {
                font-size: 11px;
                padding: 2px 8px;
                font-weight: 600;
                background-color: #2563eb;
                color: #ffffff;
                border: none;
                border-radius: 4px;
            }
            QPushButton#btn_check_keys:hover {
                background-color: #3b82f6;
            }
            QPushButton#btn_check_keys:disabled {
                background-color: #64748b;
                color: #94a3b8;
            }
        """)
        self.btn_check_keys.setVisible(False)
        self.btn_check_keys.clicked.connect(self._on_check_keys_clicked)
        col0_layout.addWidget(self.btn_check_keys, 0, Qt.AlignRight | Qt.AlignVCenter)

        detail_grid.addWidget(col0_widget, 2, 0)

        # ══ Hàng 2, Cột 1: Ô nhập Key (100% Width = ngang với Model dịch) ══
        self.gemini_key_input = QPlainTextEdit()
        self.gemini_key_input.setObjectName("gemini_key_input")
        self.gemini_key_input.setPlaceholderText("Dán danh sách Gemini API Key (mỗi key 1 dòng)...")
        self.gemini_key_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.gemini_key_input.setFixedHeight(32)
        self.gemini_key_input.setVisible(False)
        detail_grid.addWidget(self.gemini_key_input, 2, 1, Qt.AlignVCenter)

        self.deepseek_key_input = QPlainTextEdit()
        self.deepseek_key_input.setObjectName("deepseek_key_input")
        self.deepseek_key_input.setPlaceholderText("Nhập 1 API key DeepSeek")
        self.deepseek_key_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.deepseek_key_input.setFixedHeight(32)
        self.deepseek_key_input.setVisible(False)
        detail_grid.addWidget(self.deepseek_key_input, 2, 1, Qt.AlignVCenter)

        self.trans_v.addWidget(self.translation_detail_panel)
        outer_v.addWidget(self.translation_settings_card)

        # Kết nối signals cho translation card
        self.switch_translate.toggled.connect(self._on_translate_toggle)
        self.combo_translate_engine.currentIndexChanged.connect(self._on_engine_changed)
        self.gemini_key_input.textChanged.connect(self._save_gemini_key)
        self.deepseek_key_input.textChanged.connect(self._save_deepseek_key)

        # Init trạng thái mặc định
        self._on_translate_toggle(False)
        self._on_engine_changed(self.combo_translate_engine.currentIndex())

        self.panel_subtitles.content_layout.addWidget(self.sub_content_panel)

        # Kết nối toggle – trạng thái mặc định: OFF (thu gọn)
        self.switch_auto_sub.toggled.connect(self.handle_sub_toggle)
        self.handle_sub_toggle(False)


    # =========================================================================
    # Log Section
    # =========================================================================

    def _build_log_section(self) -> SectionPanel:
        log_header = QWidget()
        log_header_layout = QHBoxLayout(log_header)
        log_header_layout.setContentsMargins(0, 0, 0, 0)
        log_header_layout.setSpacing(6)

        self.btn_export_log = QPushButton("💾  Xuất log")
        self.btn_export_log.setObjectName("btn_export_log")
        self.btn_export_log.setCursor(Qt.PointingHandCursor)
        self.btn_export_log.clicked.connect(self.export_log_to_file)

        self.btn_clear_log = QPushButton("🗑  Xóa log")
        self.btn_clear_log.setObjectName("btn_clear_log")
        self.btn_clear_log.setCursor(Qt.PointingHandCursor)
        self.btn_clear_log.clicked.connect(self.clear_logs)

        log_header_layout.addWidget(self.btn_export_log)
        log_header_layout.addWidget(self.btn_clear_log)

        panel = SectionPanel(
            "⚙  Nhật ký xử lý",
            right_header_widget=log_header,
        )

        self.txt_logs = QTextEdit()
        self.txt_logs.setObjectName("LogConsole")
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setMinimumHeight(190)
        panel.content_layout.addWidget(self.txt_logs)

        return panel

    # =========================================================================
    # Progress Section
    # =========================================================================

    def _build_progress_section(self) -> SectionPanel:
        panel = SectionPanel("Tiến trình")

        v = QVBoxLayout()
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(18)
        self.progress_bar.setFormat("%p%")
        v.addWidget(self.progress_bar)

        # Status row
        status_row = QHBoxLayout()
        self.lbl_status_title = QLabel("Trạng thái:")
        self.lbl_status_title.setObjectName("ProgressLabel")
        status_row.addWidget(self.lbl_status_title)
        self.lbl_status = QLabel("Sẵn sàng")
        self.lbl_status.setObjectName("ProgressValue")
        self.current_status_key = "status_ready"
        status_row.addWidget(self.lbl_status)
        status_row.addStretch()
        v.addLayout(status_row)

        # Elapsed time row
        elapsed_row = QHBoxLayout()
        self.lbl_elapsed_title = QLabel("Thời gian xử lý:")
        self.lbl_elapsed_title.setObjectName("ProgressLabel")
        elapsed_row.addWidget(self.lbl_elapsed_title)
        self.lbl_elapsed = QLabel("00:00:00")
        self.lbl_elapsed.setObjectName("ProgressValueGreen")
        elapsed_row.addWidget(self.lbl_elapsed)
        elapsed_row.addStretch()
        v.addLayout(elapsed_row)

        v.addStretch()

        # Action buttons — solid blocks filling full panel width
        self.btn_start = QPushButton("▶  Bắt đầu xử lý")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self.start_processing)
        self.btn_start.setMinimumHeight(48)
        self.btn_start.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_start.setStyleSheet("""
            QPushButton#btn_start {
                background-color: #2da44e;
                color: white;
                border-radius: 6px;
                padding: 10px;
                font-weight: bold;
                border: none;
            }
            QPushButton#btn_start:hover {
                background-color: #34c05a;
            }
            QPushButton#btn_start:pressed {
                background-color: #1e7e34;
            }
            QPushButton#btn_start:disabled {
                background-color: #0d2e18;
                color: #2d6b42;
            }
        """)
        v.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("■  Hủy bỏ")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_processing)
        self.btn_cancel.setMinimumHeight(48)
        self.btn_cancel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.btn_cancel.setStyleSheet("""
            QPushButton#btn_cancel {
                background-color: #cf222e;
                color: white;
                border-radius: 6px;
                padding: 10px;
                font-weight: bold;
                border: none;
            }
            QPushButton#btn_cancel:hover {
                background-color: #e0333e;
            }
            QPushButton#btn_cancel:pressed {
                background-color: #8e1820;
            }
            QPushButton#btn_cancel:disabled {
                background-color: #2a0e10;
                color: #5e2428;
            }
        """)
        v.addWidget(self.btn_cancel)

        self.btn_open_folder = QPushButton("📁  Mở thư mục kết quả")
        self.btn_open_folder.setObjectName("btn_open_folder")
        self.btn_open_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.clicked.connect(self.open_output_folder)
        self.btn_open_folder.setMinimumHeight(38)
        self.btn_open_folder.setStyleSheet("""
            QPushButton#btn_open_folder {
                background-color: #12202f;
                color: #7a94b4;
                border: 1px solid #253d5c;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 600;
            }
            QPushButton#btn_open_folder:hover {
                background-color: #1c2f45;
                color: #e2eaf5;
                border-color: #3a5a80;
            }
            QPushButton#btn_open_folder:disabled {
                color: #2a3f55;
                border-color: #182030;
                background-color: transparent;
            }
        """)
        v.addWidget(self.btn_open_folder)

        panel.content_layout.addLayout(v)
        return panel

    # =========================================================================
    # File table helpers
    # =========================================================================

    def _get_cached_duration(self, path: Path) -> Optional[float]:
        key = str(path)
        if key in self.duration_cache:
            return self.duration_cache[key]
        try:
            dur = get_duration_seconds(path)
            if dur is not None:
                self.duration_cache[key] = dur
            return dur
        except Exception:
            return None

    def update_file_table(self) -> None:
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.input_paths_list))

        total_dur = 0.0
        total_sz = 0
        dur_ok = True

        for idx, path in enumerate(self.input_paths_list):
            # Col 0 – serial number
            stt = QTableWidgetItem(str(idx + 1))
            stt.setTextAlignment(Qt.AlignCenter)
            stt.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(idx, 0, stt)

            # Col 1 – file name
            name_item = QTableWidgetItem(f"🎵  {path.name}")
            name_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            name_item.setData(Qt.UserRole, str(path))
            self.table.setItem(idx, 1, name_item)

            # Col 2 – duration
            dur = self._get_cached_duration(path)
            if dur is not None:
                total_dur += dur
                dur_str = _format_duration(dur)
            else:
                dur_str = "--:--:--"
                dur_ok = False
            dur_item = QTableWidgetItem(dur_str)
            dur_item.setTextAlignment(Qt.AlignCenter)
            dur_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(idx, 2, dur_item)

            # Col 3 – file size
            try:
                sz = path.stat().st_size
                total_sz += sz
                sz_str = _format_size(sz)
            except Exception:
                sz_str = "N/A"
            sz_item = QTableWidgetItem(sz_str)
            sz_item.setTextAlignment(Qt.AlignCenter)
            sz_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(idx, 3, sz_item)

            # Col 4 – delete button
            btn_del = QPushButton()
            btn_del.setObjectName("delete_row_btn")
            btn_del.setText("X")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setFixedSize(24, 24)
            btn_del.setStyleSheet("""
                QPushButton#delete_row_btn, QPushButton#btn_delete_row {
                    background-color: #d32f2f;
                    color: #ffffff;
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                    font-weight: bold;
                    padding: 0px;
                    margin: 0px;
                }
                QPushButton#delete_row_btn:hover, QPushButton#btn_delete_row:hover {
                    background-color: #b71c1c;
                    border: none;
                    color: #ffffff;
                }
                QPushButton#delete_row_btn:pressed, QPushButton#btn_delete_row:pressed {
                    background-color: #c62828;
                    border: none;
                }
            """)
            btn_del.clicked.connect(lambda _=False, r=idx: self._remove_file_at(r))
            
            # Center the button in the cell using a container widget and clean margins/spacing
            cell_container = QWidget()
            cell_layout = QHBoxLayout(cell_container)
            cell_layout.addWidget(btn_del)
            cell_layout.setAlignment(Qt.AlignCenter)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(0)
            self.table.setCellWidget(idx, 4, cell_container)

        self.table.blockSignals(False)

        dur_summary = _format_duration(total_dur) if dur_ok else "N/A"
        lang = "vi"
        if hasattr(self, "combo_ui_lang"):
            lang = self.combo_ui_lang.currentData() or "vi"
        tr = get_translation(lang)

        self.lbl_sum_count.setText(tr["lbl_sum_count"].format(count=len(self.input_paths_list)))
        self.lbl_sum_duration.setText(tr["lbl_sum_duration"].format(duration=dur_summary))
        self.lbl_sum_size.setText(tr["lbl_sum_size"].format(size=_format_size(total_sz)))
        self.lbl_summary.setText(
            f"{tr['lbl_sum_count'].format(count=len(self.input_paths_list))} | "
            f"{tr['lbl_sum_duration'].format(duration=dur_summary)} | "
            f"{tr['lbl_sum_size'].format(size=_format_size(total_sz))}"
        )

    def _remove_file_at(self, index: int) -> None:
        if 0 <= index < len(self.input_paths_list):
            self.input_paths_list.pop(index)
            self.update_file_table()

    # =========================================================================
    # Slots
    # =========================================================================

    @Slot(int, int)
    def _handle_row_move(self, from_row: int, to_row: int) -> None:
        n = len(self.input_paths_list)
        if 0 <= from_row < n and 0 <= to_row < n:
            item = self.input_paths_list.pop(from_row)
            self.input_paths_list.insert(to_row, item)
            self.update_file_table()
            self.table.selectRow(to_row)

    @Slot()
    def remove_selected(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.input_paths_list):
            self.input_paths_list.pop(row)
            self.update_file_table()

    @Slot()
    def clear_all_inputs(self) -> None:
        self.input_paths_list.clear()
        self.update_file_table()

    @Slot()
    def move_up(self) -> None:
        row = self.table.currentRow()
        if row > 0:
            lst = self.input_paths_list
            lst[row], lst[row - 1] = lst[row - 1], lst[row]
            self.update_file_table()
            self.table.selectRow(row - 1)

    @Slot()
    def move_down(self) -> None:
        row = self.table.currentRow()
        lst = self.input_paths_list
        if 0 <= row < len(lst) - 1:
            lst[row], lst[row + 1] = lst[row + 1], lst[row]
            self.update_file_table()
            self.table.selectRow(row + 1)

    @Slot()
    def browse_inputs(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn tập tin âm thanh hoặc video",
            "",
            "Audio/Video Files (*.wav *.mp3 *.m4a *.flac *.ogg *.mp4 *.mkv *.avi *.mov)"
            ";;All Files (*)",
        )
        if files:
            added = sum(
                1 for f in files
                if (p := Path(f)) not in self.input_paths_list
                and not self.input_paths_list.append(p)  # type: ignore[func-returns-value]
            )
            if added:
                self.update_file_table()
                if self.txt_project_name.text() in ("", "audio_project") and self.input_paths_list:
                    self.txt_project_name.setText(
                        self.input_paths_list[0].stem.replace(" ", "_")
                    )

    @Slot(list)
    def add_files_from_paths(self, paths: List[Path]) -> None:
        added = sum(
            1 for p in paths
            if p not in self.input_paths_list
            and not self.input_paths_list.append(p)  # type: ignore[func-returns-value]
        )
        if added:
            self.update_file_table()
            if self.txt_project_name.text() in ("", "audio_project") and self.input_paths_list:
                self.txt_project_name.setText(
                    self.input_paths_list[0].stem.replace(" ", "_")
                )

    @Slot()
    def browse_output(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu kết quả")
        if d:
            self.txt_output.setText(d)

    @Slot(str)
    def _on_output_dir_changed(self, text: str) -> None:
        self.output_dir = text

    @Slot(str)
    def _on_project_name_changed(self, text: str) -> None:
        self.project_name = text

    @Slot(int)
    def _on_format_changed(self, index: int) -> None:
        self.output_format = self.combo_out_format.itemData(index) or "wav"

    @Slot()
    def clear_logs(self) -> None:
        self.txt_logs.clear()

    @Slot()
    def export_log_to_file(self) -> None:
        """Xuất toàn bộ nội dung nhật ký xử lý ra tệp văn bản (.txt)."""
        from datetime import datetime
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"

        default_filename = f"Log_AudioFactory_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        dialog_title = "Xuất nhật ký xử lý" if lang == "vi" else "Export Process Log"
        filter_str = "Text Files (*.txt);;All Files (*)"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            dialog_title,
            default_filename,
            filter_str
        )

        if not file_path:
            return

        try:
            log_content = self.txt_logs.toPlainText()
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(log_content)

            success_title = "Thành công" if lang == "vi" else "Success"
            success_msg = f"Đã xuất nhật ký xử lý thành công ra tệp:\n{file_path}" if lang == "vi" else f"Successfully exported log to file:\n{file_path}"
            QMessageBox.information(self, success_title, success_msg)
        except Exception as e:
            err_title = "Lỗi xuất file" if lang == "vi" else "Export Error"
            err_msg = f"Không thể lưu tệp nhật ký:\n{e}" if lang == "vi" else f"Failed to save log file:\n{e}"
            QMessageBox.critical(self, err_title, err_msg)

    @Slot()
    def _tick_elapsed(self) -> None:
        self.elapsed_seconds += 1
        self.lbl_elapsed.setText(_format_duration(self.elapsed_seconds))

    @Slot(bool)
    def handle_sub_toggle(self, checked: bool) -> None:
        """Ẩn/hiện card cài đặt phụ đề theo trạng thái nút gạt.

        - OFF (False): sub_content_panel ẩn → Phần 4 chỉ còn thanh tiêu đề.
          Ép panel thu gọn bằng setFixedHeight để không còn khoảng trống thừa.
        - ON  (True) : sub_content_panel hiện → card 6 ComboBox xổ xuống.
          Giải phóng giới hạn chiều cao để Qt tự tính toán kích thước tự nhiên.
        """
        self.sub_content_panel.setVisible(checked)
        if checked:
            # ON: giải phóng giới hạn → Qt tính chiều cao tự nhiên
            self.panel_subtitles.setMinimumHeight(0)
            self.panel_subtitles.setMaximumHeight(16_777_215)  # QWIDGETSIZE_MAX
        else:
            # OFF: xả chiều cao tối thiểu, ép về chiều cao header panel
            self.panel_subtitles.setMinimumHeight(0)
            # Dùng sizeHint để ép về thanh header
            QTimer.singleShot(0, lambda: (
                self.panel_subtitles.setFixedHeight(
                    self.panel_subtitles.sizeHint().height()
                ) if not self.switch_auto_sub.isChecked() else None
            ))
        # Ép scroll area tính lại diện tích ngay lập tức
        if hasattr(self, "main_scroll_area"):
            w = self.main_scroll_area.widget()
            if w is not None:
                w.adjustSize()

    # ── Processing stubs (full logic in Pass 2+) ──────────────────────────

    def get_pipeline_options(self) -> PipelineOptions:
        options = PipelineOptions()
        options.merge_first                = self.card_merge.switch.isChecked()
        options.enable_voice_cleanup       = self.card_voice.switch.isChecked()
        options.clean_preset               = "auto"
        options.strict_subtitle_validation = load_config().get("strict_subtitle_validation", False)
        options.enable_volume_leveling     = self.card_volume.switch.isChecked()
        options.enable_silence_shortening  = self.card_silence.switch.isChecked()
        options.silence_preset              = "auto"
        # Hidden delivery safeguard remains active, while this visible switch
        # controls whether voice-only loudness leveling is applied.
        options.enable_social_optimize     = True
        options.social_platform             = "social_safe"
        options.output_format = self.output_format
        options.enable_transcription  = self.switch_auto_sub.isChecked()
        options.enable_subtitle_export = self.switch_auto_sub.isChecked()
        if options.enable_transcription:
            # ── LANGUAGE: ánh xạ label UI → mã ISO 639-1 mà Whisper nhận ──────
            lang_data = self.combo_lang.currentData()
            if lang_data is not None:
                options.language = lang_data if lang_data != "auto" else None
            else:
                _MISSING = object()
                _lang_raw = LANGUAGE_MAP.get(self.combo_lang.currentText(), _MISSING)
                if _lang_raw is _MISSING:
                    # English display labels mapping fallback
                    english_map = {
                        "Auto Detect": None,
                        "Vietnamese": "vi",
                        "English": "en",
                        "Chinese (中文)": "zh",
                        "Japanese (日本語)": "ja",
                        "Korean (한국어)": "ko",
                        "Russian (Русский)": "ru",
                        "French (Français)": "fr",
                        "Spanish": "es"
                    }
                    options.language = english_map.get(self.combo_lang.currentText(), None)
                else:
                    options.language = _lang_raw

            # ── MODEL: cắt phần chú thích trước khi truyền vào faster-whisper ──
            options.whisper_model         = self.combo_model.currentText().split(" ")[0]

            # ── TỐC ĐỘ ASR: cắt đuôi "x (...)" → lấy số thực sạch truyền vào atempo ——
            options.asr_audio_speed       = float(self.combo_speed.currentText().split("x")[0])
            options.batch_size            = int(self.combo_batch.currentText().split(" ")[0])

            # ── KHUNG HÌNH: ánh xạ label tỷ lệ → từ khóa backend ───────────────
            fmt_data = self.combo_format.currentData()
            if fmt_data:
                options.target_video_format = fmt_data
            else:
                _fmt_map = {
                    "16:9 (Video Ngang)": "16:9",
                    "9:16 (Video Dọc)":   "9:16",
                    "1:1 (Video Vuông)":  "1:1",
                    "16:9 (Horizontal Video)": "16:9",
                    "9:16 (Vertical Video)":   "9:16",
                    "1:1 (Square Video)":      "1:1",
                }
                options.target_video_format = _fmt_map.get(
                    self.combo_format.currentText(), "16:9"
                )
            
            # Resolve backward aliases
            _aliases = {
                "horizontal": "16:9",
                "vertical": "9:16",
                "square": "1:1"
            }
            if options.target_video_format in _aliases:
                options.target_video_format = _aliases[options.target_video_format]
            # ── SỐ DÒNG: cắt phần chú thích, lấy số người dùng ──────────────────────
            options.subtitle_lines        = int(self.combo_lines.currentText().split()[0])
        
        # ── TRANSLATION OPTIONS ────────────────────────────────────────────────
        options.enable_translation = self.switch_translate.isChecked() and self.switch_auto_sub.isChecked()
        options.translation_engine = self.combo_translate_engine.currentData() or "google"
        # Pass the stable ISO language code, never the translated display label.
        # The old path used currentText(), so switching the UI to English turned
        # "Vietnamese (vi)" into the invalid target code "vietnamese".
        options.translation_target_lang = self.combo_translate_lang.currentData() or "vi"
        if options.translation_engine.startswith("gemini"):
            options.translation_api_key = self.gemini_key_input.toPlainText().strip()
        elif options.translation_engine.startswith("deepseek"):
            options.translation_api_key = self.deepseek_key_input.toPlainText().strip()
        else:
            options.translation_api_key = ""

        options.project_name = self.project_name.strip()
        return options

    @Slot()
    def start_processing(self) -> None:
        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"
        tr = get_translation(lang)

        if not self.input_paths_list:
            err_title = "Lỗi cấu hình" if lang == "vi" else "Configuration Error"
            err_msg = "Danh sách tệp tin đầu vào trống. Vui lòng bấm 'Thêm tệp'." if lang == "vi" else "Input file list is empty. Please click 'Add Files'."
            QMessageBox.critical(self, err_title, err_msg)
            return
        out_str = self.output_dir.strip()
        if not out_str:
            err_title = "Lỗi cấu hình" if lang == "vi" else "Configuration Error"
            err_msg = "Chưa chọn thư mục đầu ra. Vui lòng bấm 'Chọn thư mục'." if lang == "vi" else "Output directory not selected. Please click 'Browse'."
            QMessageBox.critical(self, err_title, err_msg)
            return
        if not self.project_name.strip():
            err_title = "Lỗi cấu hình" if lang == "vi" else "Configuration Error"
            err_msg = "Tên dự án không được để trống." if lang == "vi" else "Project name cannot be empty."
            QMessageBox.critical(self, err_title, err_msg)
            return

        if not _BACKEND_AVAILABLE:
            info_title = "Pass 1 Shell"
            info_msg = "Backend chưa khả dụng trong Pass 1.<br>Giao diện hoạt động bình thường." if lang == "vi" else "Backend not available in Pass 1.<br>GUI is functional."
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.NoIcon)
            msg_box.setWindowTitle(info_title)
            msg_box.setTextFormat(Qt.RichText)
            msg_box.setText(info_msg)
            msg_box.exec()
            return

        out_dir = Path(out_str)
        options = self.get_pipeline_options()
        self.txt_logs.clear()

        # ── PHÂN LOẠI LUỒNG: AUDIOPILINE VS STANDALONE SRT TRANSLATION ──────────
        srt_inputs = [f for f in self.input_paths_list if f.suffix.lower() == ".srt"]
        media_inputs = [f for f in self.input_paths_list if f.suffix.lower() != ".srt"]

        # CASE 1: Standalone SRT Translation Mode (Chỉ chọn tệp .srt đầu vào)
        if not media_inputs and srt_inputs:
            if not self.switch_translate.isChecked():
                err_title = "Lỗi dịch thuật" if lang == "vi" else "Translation Error"
                err_msg = "Bạn đã chọn tệp SRT nhưng chưa bật công tắc 'Dịch Phụ Đề'." if lang == "vi" else "You selected SRT files but haven't enabled 'Translate Subtitles'."
                QMessageBox.warning(self, err_title, err_msg)
                return

            from core.translator import is_already_translated_srt
            valid_srt_files = [f for f in srt_inputs if not is_already_translated_srt(f)]

            if not valid_srt_files:
                err_title = "Cảnh báo tệp SRT" if lang == "vi" else "SRT Warning"
                err_msg = "Tất cả các tệp SRT đầu vào đều là tệp đã dịch (*_vi.srt). Vui lòng chọn tệp SRT gốc." if lang == "vi" else "All selected SRT files are already translated (*_vi.srt). Please select original SRT files."
                QMessageBox.warning(self, err_title, err_msg)
                return

            engine_key = options.translation_engine
            target_lang = options.translation_target_lang
            api_key = options.translation_api_key

            self.txt_logs.append("Khởi động tiến trình dịch thuật SRT độc lập..." if lang == "vi" else "Starting standalone SRT translation process...")
            self.txt_logs.append(
                f"[DỊCH THUẬT] Bắt đầu dịch {len(valid_srt_files)} file SRT "
                f"bằng {self.combo_translate_engine.currentText()}..."
            )
            self._set_processing_state(True)
            self.progress_bar.setValue(0)
            self.elapsed_seconds = 0
            self.lbl_elapsed.setText("00:00:00")
            self.timer.start(1000)
            self.lbl_status.setText(tr.get("status_translating", "Đang dịch phụ đề..."))
            self.current_status_key = "status_translating"

            self.translation_worker = TranslationWorker(
                srt_paths=valid_srt_files,
                engine=engine_key,
                target_lang=target_lang,
                api_key=api_key,
            )
            self.translation_worker.status_received.connect(self._on_translation_status)
            self.translation_worker.finished_success.connect(self._on_translation_success)
            self.translation_worker.finished_error.connect(self._on_translation_error)
            self.translation_worker.quota_exceeded.connect(self._on_translation_quota_exceeded)
            self.translation_worker.start()
            return

        # CASE 2: Audio/Video Processing Pipeline Mode
        self.txt_logs.append("Khởi động tiến trình xử lý..." if lang == "vi" else "Starting audio processing pipeline...")
        self._set_processing_state(True)
        self.progress_bar.setValue(0)
        self.elapsed_seconds = 0
        self.lbl_elapsed.setText("00:00:00")
        self.timer.start(1000)

        is_batch = (not options.merge_first) and len(self.input_paths_list) > 1
        self.worker = PipelineWorker(self.input_paths_list, out_dir, options, is_batch)
        self.worker.status_received.connect(self._on_worker_status)
        self.worker.finished_success.connect(self._on_worker_success)
        self.worker.finished_error.connect(self._on_worker_error)
        # ── Kết nối progress_signal & log_signal (Spec Phần 5) ──────────
        self.worker.progress_signal.connect(self._on_worker_progress)
        self.worker.log_signal.connect(self._on_worker_log)
        self.worker.start()

    def _set_processing_state(self, processing: bool) -> None:
        self.btn_start.setEnabled(not processing)
        # Đổi text nút bắt đầu khi đang xử lý
        if processing:
            self.btn_start.setText("⏳  Đang xử lý...")
        else:
            self.btn_start.setText("▶  Bắt đầu xử lý")
        self.btn_cancel.setEnabled(processing)
        self.btn_open_folder.setEnabled(False)
        
        # Danh sách các widget cần lock/unlock khi bấm bắt đầu xử lý
        for w in [
            self.btn_add_files, self.btn_remove_selected,
            self.btn_move_up, self.btn_move_down, self.table,
            self.txt_output, self.btn_browse_output,
            self.txt_project_name, self.combo_out_format,
            self.card_merge.switch, self.card_voice.switch,
            self.card_volume.switch, self.card_silence.switch,
            self.switch_auto_sub, self.combo_lang, self.combo_model,
            self.combo_speed, self.combo_batch, self.combo_format,
            self.combo_lines,
            # Lock/unlock translation widgets (Sửa lỗi api_key_widget)
            self.switch_translate, self.combo_translate_lang,
            self.combo_translate_engine, self.gemini_key_input,
            self.deepseek_key_input, self.btn_check_keys,
        ]:
            if hasattr(self, w) if isinstance(w, str) else True:
                w.setEnabled(not processing)

        # Cập nhật hiển thị ô key theo engine khi kết thúc xử lý
        if not processing:
            self._on_engine_changed(self.combo_translate_engine.currentIndex())

    @Slot(int, str)
    def _on_worker_progress(self, percent: int, status_text: str) -> None:
        """Nhận progress_signal(int, str) từ PipelineWorker — cập nhật bar + label."""
        self.progress_bar.setValue(percent)
        # Cắt ngắn text dài để label không bị vỡ layout
        short = status_text[:72] + "..." if len(status_text) > 72 else status_text
        self.lbl_status.setText(short)

    @Slot(str)
    def _on_worker_log(self, msg: str) -> None:
        """Nhận log_signal(str) từ PipelineWorker — append vào ô Nhật ký."""
        # Tránh duplicate: _on_worker_status cũng append, nên _on_worker_log
        # chỉ dùng cho các message không qua status_received.
        pass  # Hiện tại status_received đã xử lý log → không append thêm lần nữa

    @Slot(str)
    def _on_worker_status(self, msg: str) -> None:
        self.txt_logs.append(f"[TIẾN TRÌNH] {msg}")
        self.txt_logs.verticalScrollBar().setValue(
            self.txt_logs.verticalScrollBar().maximum()
        )
        # Cập nhật status label ngắn gọn
        short = msg[:72] + "..." if len(msg) > 72 else msg
        self.lbl_status.setText(short)

    @Slot(object)
    def _on_worker_success(self, result: object) -> None:
        self._set_processing_state(False)
        self.timer.stop()
        self.progress_bar.setValue(100)
        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"
        tr = get_translation(lang)
        self.lbl_status.setText(tr["status_done"])
        self.current_status_key = "status_done"
        self.txt_logs.append("\n[THÀNH CÔNG] Tiến trình hoàn thành xuất sắc!" if lang == "vi" else "\n[SUCCESS] Pipeline completed successfully!")
        if isinstance(result, list):
            if result:
                self.last_output_dir = result[0].output_dir
        else:
            self.last_output_dir = result.output_dir
        if self.last_output_dir:
            self.btn_open_folder.setEnabled(True)

        # Vì PipelineWorker đã tự động dịch thuật đồng bộ bên trong pipeline khi switch_translate=True,
        # nên khi Pipeline hoàn thành, KHÔNG gọi thêm TranslationWorker để tránh dịch đè / dịch chồng dịch (_vi_vi.srt).
        try:
            import winsound
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass
        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"
        title = "Thành công" if lang == "vi" else "Success"
        msg = "Tiến trình xử lý hoàn tất thành công!" if lang == "vi" else "Processing pipeline completed successfully!"
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.NoIcon)
        msg_box.setWindowTitle(title)
        msg_box.setText(msg)
        msg_box.exec()

    @Slot(str)
    def _on_worker_error(self, err_msg: str) -> None:
        self.timer.stop()
        if "cancelled" in err_msg.lower() or any(w in err_msg.lower() for w in ["dừng", "hủy"]):
            # Worker đã thoát sau cancel — _on_cancel_complete() sẽ được gọi
            # qua worker.finished signal ngay sau đây → KHÔNG reset UI ở đây
            # để tránh double-call _set_processing_state(False).
            pass
        else:
            self._set_processing_state(False)
            try:
                import winsound
                winsound.PlaySound("SystemHand", winsound.SND_ALIAS | winsound.SND_ASYNC)
            except Exception:
                pass
            lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"
            tr = get_translation(lang)
            self.lbl_status.setText(tr["status_error"])
            self.current_status_key = "status_error"
            self.txt_logs.append(f"\n[LỖI] Xảy ra sự cố: {err_msg}" if lang == "vi" else f"\n[ERROR] An issue occurred: {err_msg}")
            err_title = "Lỗi" if lang == "vi" else "Error"
            err_body = f"Xử lý thất bại:\n{err_msg}" if lang == "vi" else f"Processing failed:\n{err_msg}"
            QMessageBox.critical(self, err_title, err_body)

    @Slot()
    def cancel_processing(self) -> None:
        """Kill-switch: terminate FFmpeg instantly, request Worker to stop, reset UI.

        Cơ chế non-blocking:
        - worker.cancel() set cờ + kill FFmpeg subprocess ngay lập tức.
        - worker.finished signal kết nối đến _on_cancel_complete().
        - Signal được emit từ worker thread khi run() kết thúc → main thread
          nhận qua Qt event loop → GUI KHÔNG BAO GIờ bị block.
        - Tuyệt đối KHÔNG gọi worker.wait() từ main thread (gây deadlock).
        """
        # Hủy Translation Worker nếu đang dịch (tính năng #5)
        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"
        tr = get_translation(lang)

        if self.translation_worker and self.translation_worker.isRunning():
            self.translation_worker.cancel()
            self.txt_logs.append(
                '<span style="color:#FF4444; font-weight:bold;">[HỆ THỐNG] '
                'Đang dừng tiến trình dịch thuật...</span>'
                if lang == "vi" else
                '<span style="color:#FF4444; font-weight:bold;">[SYSTEM] '
                'Stopping translation process...</span>'
            )
            self._set_processing_state(False)
            self.lbl_status.setText(tr["status_cancelled"])
            self.current_status_key = "status_cancelled"
            self.btn_cancel.setEnabled(False)
            return
        if self.worker and self.worker.isRunning():
            # 1. Log đỏ ngay lập tức (không đợi Worker thoát)
            self.txt_logs.append(
                '<span style="color:#FF4444; font-weight:bold;">[HỆ THỐNG] '
                'Tiến trình đã bị hủy bởi người dùng. '
                'Đang dọn dẹp file tạm...</span>'
                if lang == "vi" else
                '<span style="color:#FF4444; font-weight:bold;">[SYSTEM] '
                'Process cancelled by user. '
                'Cleaning up temporary files...</span>'
            )
            self.txt_logs.verticalScrollBar().setValue(
                self.txt_logs.verticalScrollBar().maximum()
            )
            # 2. Reset progress + label ngay lập tức
            self.lbl_status.setText(tr["status_cancelling"])
            self.current_status_key = "status_cancelling"
            self.progress_bar.setValue(0)
            self.timer.stop()
            # 3. Disable nút hủy — tránh bấm đúp
            self.btn_cancel.setEnabled(False)
            # 4. Kết nối finished signal TRƯỚC khi gọi cancel()
            #    để không bỏ lỡ signal nếu worker thoát rất nhanh
            try:
                self.worker.finished.connect(
                    self._on_cancel_complete,
                    Qt.SingleShotConnection,  # Tự động ngắt kết nối sau 1 lần
                )
            except Exception:
                # Qt < 6.0 không có SingleShotConnection → fallback
                self.worker.finished.connect(self._on_cancel_complete)
            # 5. Gọi cancel() — set cờ + kill FFmpeg ngay lập tức
            #    Worker sẽ thoát, emit finished → _on_cancel_complete() được gọi
            self.worker.cancel()

    def _on_cancel_complete(self) -> None:
        """Called via worker.finished signal after cancel. Non-blocking, safe to call from
        main thread. Resets UI fully and disconnects signal to avoid duplicate calls."""
        # Disconnect phòng ngừa khi dùng Qt không có SingleShotConnection
        if self.worker is not None:
            try:
                self.worker.finished.disconnect(self._on_cancel_complete)
            except Exception:
                pass  # Đã bị disconnect hoặc không tồn tại → bỏ qua
        self._set_processing_state(False)
        
        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"
        tr = get_translation(lang)

        self.lbl_status.setText(f"{tr['status_cancelled']} {tr['status_ready']}")
        self.current_status_key = "status_cancelled_ready"
        self.progress_bar.setValue(0)
        self.txt_logs.append(
            '<span style="color:#FF4444; font-weight:bold;">[HỆ THỐNG] '
            'Tiến trình đã bị hủy bởi người dùng. '
            'Đã dọn dẹp file tạm.</span>'
            if lang == "vi" else
            '<span style="color:#FF4444; font-weight:bold;">[SYSTEM] '
            'Process cancelled by user. '
            'Temporary files cleaned.</span>'
        )
        self.txt_logs.verticalScrollBar().setValue(
            self.txt_logs.verticalScrollBar().maximum()
        )

    # =========================================================================
    # Tính năng #5: Translation Slots
    # =========================================================================

    @Slot(bool)
    def _on_translate_toggle(self, checked: bool) -> None:
        """Ẩn/hiện detail panel dịch thuật, điều khiển chiều cao card động."""
        self.translation_detail_panel.setVisible(checked)
        save_config({"translation_enabled": checked})

        if checked:
            self.translation_settings_card.setMinimumHeight(180)
            self.translation_settings_card.setMaximumHeight(16_777_215)
            self.trans_v.setContentsMargins(16, 12, 16, 16)

            # ✅ Khóa chiều cao 32px đồng bộ hoàn hảo với ô Model dịch
            self.gemini_key_input.setFixedHeight(32)
            self.deepseek_key_input.setFixedHeight(32)
            self.combo_translate_engine.setFixedHeight(32)
            self.combo_translate_lang.setFixedHeight(32)
        else:
            self.trans_v.setContentsMargins(16, 6, 16, 6)
            self.translation_settings_card.setMinimumHeight(0)
            self.translation_settings_card.setFixedHeight(54)

        if hasattr(self, "main_scroll_area"):
            w = self.main_scroll_area.widget()
            if w is not None:
                w.adjustSize()

    @Slot(int)
    def _on_engine_changed(self, index: int) -> None:
        engine_key = self.combo_translate_engine.itemData(index) or "google"
        save_config({"last_selected_engine": self.combo_translate_engine.currentText()})

        if engine_key.startswith("gemini"):
            self.lbl_api_key_title.setVisible(True)
            self.btn_check_keys.setVisible(True)
            self.lbl_gemini_hint.setVisible(True)
            self.lbl_deepseek_hint.setVisible(False)
            self.lbl_google_msg.setVisible(False)
            self.gemini_key_input.setVisible(True)
            self.deepseek_key_input.setVisible(False)
        elif engine_key.startswith("deepseek"):
            self.lbl_api_key_title.setVisible(True)
            self.btn_check_keys.setVisible(True)
            self.lbl_gemini_hint.setVisible(False)
            self.lbl_deepseek_hint.setVisible(True)
            self.lbl_google_msg.setVisible(False)
            self.gemini_key_input.setVisible(False)
            self.deepseek_key_input.setVisible(True)
        else:  # google
            self.lbl_api_key_title.setVisible(False)
            self.btn_check_keys.setVisible(False)
            self.lbl_gemini_hint.setVisible(False)
            self.lbl_deepseek_hint.setVisible(False)
            self.lbl_google_msg.setVisible(True)
            self.gemini_key_input.setVisible(False)
            self.deepseek_key_input.setVisible(False)

    @Slot()
    def _save_gemini_key(self) -> None:
        """Auto-save Gemini key vào config.json khi người dùng nhập/sửa."""
        key = self.gemini_key_input.toPlainText().strip()
        save_config({"gemini_api_key": key})

    @Slot()
    def _save_deepseek_key(self) -> None:
        """Auto-save DeepSeek key vào config.json khi người dùng nhập/sửa."""
        key = self.deepseek_key_input.toPlainText().strip()
        save_config({"deepseek_api_key": key})

    @Slot()
    def _on_check_keys_clicked(self) -> None:
        """Xử lý sự kiện bấm nút Kiểm tra API Key."""
        idx = self.combo_translate_engine.currentIndex()
        engine_key = self.combo_translate_engine.itemData(idx) or "google"
        
        if engine_key.startswith("gemini"):
            raw_keys = self.gemini_key_input.toPlainText().strip()
            engine_name = "Gemini"
        elif engine_key.startswith("deepseek"):
            raw_keys = self.deepseek_key_input.toPlainText().strip()
            engine_name = "DeepSeek"
        else:
            return

        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"

        if not raw_keys:
            msg = "⚠️ Chưa nhập API Key để kiểm tra." if lang == "vi" else "⚠️ No API Key entered to check."
            self.lbl_status.setText(msg)
            self.txt_logs.append(f'<span style="color:#FFB347; font-weight:bold;">[KIỂM TRA KEY] {msg}</span>')
            return

        self.btn_check_keys.setEnabled(False)
        self.btn_check_keys.setText("⏳ Đang kiểm tra..." if lang == "vi" else "⏳ Checking...")
        self.txt_logs.append(
            f'<span style="color:#4a9eff; font-weight:bold;">'
            f'[KIỂM TRA KEY] ⏳ Đang kiểm tra danh sách API Key {engine_name}...</span>'
        )

        self._key_val_worker = KeyValidationWorker(raw_keys, engine_key)
        self._key_val_worker.finished_signal.connect(self._on_key_validation_finished)
        self._key_val_worker.start()

    @Slot(dict)
    def _on_key_validation_finished(self, result: dict) -> None:
        """Nhận kết quả kiểm tra API Key từ KeyValidationWorker."""
        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"
        btn_text = "🔍  Kiểm tra" if lang == "vi" else "🔍  Check"
        self.btn_check_keys.setText(btn_text)
        self.btn_check_keys.setEnabled(True)

        valid = result.get("valid", 0)
        total = result.get("total", 0)
        details = result.get("details", [])

        idx = self.combo_translate_engine.currentIndex()
        engine_key = self.combo_translate_engine.itemData(idx) or "google"
        engine_name = "Gemini" if engine_key.startswith("gemini") else "DeepSeek"

        for line in details:
            if "✅" in line:
                color = "#10d98c"
            elif "⚠️" in line:
                color = "#FFB347"
            else:
                color = "#FF6B6B"
            self.txt_logs.append(f'<span style="color:{color}; font-weight: 500;">  • {line}</span>')

        self.txt_logs.verticalScrollBar().setValue(
            self.txt_logs.verticalScrollBar().maximum()
        )

        status_msg = (
            f"✅ {valid}/{total} Key {engine_name} hoạt động tốt."
            if lang == "vi" else
            f"✅ {valid}/{total} {engine_name} API Keys working."
        )
        self.lbl_status.setText(status_msg)
        self.txt_logs.append(
            f'<span style="color:#10d98c; font-weight:bold;">'
            f'[KIỂM TRA KEY] {status_msg}</span>\n'
        )

    def _load_translation_config(self) -> None:
        """
        Nạp cài đặt dịch thuật và ngôn ngữ giao diện từ config.json vào UI khi khởi động app.
        Gọi sau _setup_ui() để tất cả widget đã tồn tại.
        """
        try:
            cfg = load_config()

            # Restore UI language
            ui_lang = cfg.get("language", "vi")
            if ui_lang == "en":
                self.combo_ui_lang.setCurrentIndex(1)
            else:
                self.combo_ui_lang.setCurrentIndex(0)
            
            # Kích hoạt dịch giao diện động ngay từ đầu
            self.retranslate_ui(ui_lang)

            # Restore Theme (Mặc định Light Mode)
            saved_theme = cfg.get("theme", "light")
            if saved_theme == "dark":
                self.theme_is_dark = False  # Set False để hàm toggle lật ngược lại thành True
                self.toggle_theme()
            else:
                self.theme_is_dark = True   # Set True để hàm toggle lật ngược lại thành False
                self.toggle_theme()

            # Kết nối sự kiện thay đổi ngôn ngữ sau khi đã nạp xong (để tránh kích hoạt sớm)
            self.combo_ui_lang.currentIndexChanged.connect(self._on_ui_lang_changed)

            # Restore Gemini API key
            gemini_key = cfg.get("gemini_api_key", "")
            if gemini_key:
                self.gemini_key_input.setPlainText(gemini_key)

            # Restore DeepSeek API key
            deepseek_key = cfg.get("deepseek_api_key", "")
            if deepseek_key:
                self.deepseek_key_input.setPlainText(deepseek_key)

            # Restore engine selection
            last_engine = cfg.get("last_selected_engine", "")
            if last_engine:
                idx = self.combo_translate_engine.findText(last_engine)
                if idx < 0:
                    idx = self.combo_translate_engine.findData(last_engine)
                if idx >= 0:
                    self.combo_translate_engine.setCurrentIndex(idx)

            # Restore target language
            last_lang = cfg.get("last_target_lang", "")
            if last_lang:
                idx = self.combo_translate_lang.findData(last_lang)
                if idx < 0:
                    idx = self.combo_translate_lang.findText(last_lang)
                if idx < 0:
                    # Fallback mapping from old Vietnamese display text to code
                    fallback_map = {
                        "Tiếng Việt (vi)": "vi",
                        "Tiếng Anh (en)": "en",
                        "Tiếng Trung giản thể (zh)": "zh",
                        "Tiếng Nhật (ja)": "ja",
                        "Tiếng Hàn (ko)": "ko",
                        "Tiếng Tây Ban Nha (es)": "es",
                        "Tiếng Pháp (fr)": "fr",
                        "Tiếng Nga (ru)": "ru",
                    }
                    if last_lang in fallback_map:
                        idx = self.combo_translate_lang.findData(fallback_map[last_lang])
                if idx >= 0:
                    self.combo_translate_lang.setCurrentIndex(idx)

            # Restore translation toggle
            trans_enabled = cfg.get("translation_enabled", False)
            if trans_enabled:
                self.switch_translate.setChecked(True)

            # Cập nhật UX state theo engine đã restore
            self._on_engine_changed(self.combo_translate_engine.currentIndex())

            # Kết nối auto-save ngôn ngữ đích (chỉ connect 1 lần sau khi load xong)
            self.combo_translate_lang.currentIndexChanged.connect(
                lambda _: self._save_target_lang()
            )

        except Exception as e:
            import traceback
            print(f"Error in _load_translation_config: {e}")
            traceback.print_exc()

    # Kết nối target lang để auto-save
    def _save_target_lang(self) -> None:
        """Auto-save ngôn ngữ đích khi thay đổi."""
        val = self.combo_translate_lang.currentData()
        if val:
            save_config({"last_target_lang": val})

    def _on_ui_lang_changed(self) -> None:
        """Xử lý khi người dùng thay đổi ngôn ngữ giao diện."""
        lang = self.combo_ui_lang.currentData()
        if lang:
            save_config({"language": lang})
            self.retranslate_ui(lang)

    def apply_branded_titlebar(self) -> None:
        """Đổi màu thanh tiêu đề Windows sang cam nhạt #FFD5A1 (brand color)."""
        if platform.system() != "Windows":
            return
        try:
            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi
            dark_mode = ctypes.c_int(0)
            dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode))
            caption_color = ctypes.c_int(0x00A1D5FF)
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(caption_color), ctypes.sizeof(caption_color))
            text_color = ctypes.c_int(0x00202020)
            dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(text_color), ctypes.sizeof(text_color))
        except Exception:
            pass

    @Slot()
    def toggle_theme(self) -> None:
        """Đảo ngược trạng thái Sáng/Tối, lưu config và áp dụng QSS mới."""
        self.theme_is_dark = not self.theme_is_dark

        # Lưu vào config.json
        save_config({"theme": "dark" if self.theme_is_dark else "light"})

        # Re-build Stylesheet
        from ui.theme import build_stylesheet
        new_qss = build_stylesheet("dark" if self.theme_is_dark else "light")
        self.setStyleSheet(new_qss)

        # Đổi Icon
        lang = self.combo_ui_lang.currentData() or "vi"
        if self.theme_is_dark:
            self.theme_button.setIcon(self._icon_moon)
            self.theme_button.setToolTip("Chuyển sang giao diện sáng" if lang == "vi" else "Switch to light mode")
        else:
            self.theme_button.setIcon(self._icon_sun)
            self.theme_button.setToolTip("Chuyển sang giao diện tối" if lang == "vi" else "Switch to dark mode")

        # Xóa các style inline (nếu có) do Qt tự sinh ra để QSS Global tiếp quản 100%
        for panel in [
            self.panel_input, self.panel_output, self.panel_processing,
            self.panel_subtitles, self.panel_log, self.panel_progress
        ]:
            if hasattr(panel, "content_widget"):
                panel.content_widget.setStyleSheet(
                    "QWidget#SectionContentWidget { background: transparent; border: none; }"
                )

    def check_update_at_startup(self) -> None:
        """Kiểm tra cập nhật phiên bản mới ngầm khi khởi động ứng dụng."""
        try:
            from core.updater import run_update_check
            if getattr(sys, "frozen", False) and run_update_check(self):
                QApplication.quit()
        except Exception as e:
            print(f"[UPDATER] Không thể khởi tạo checker: {e}")

    def _on_update_available(self, info: dict) -> None:
        """Xử lý khi có phiên bản mới từ Supabase — KHÓA CỨNG BẮT BUỘC CẬP NHẬT 100%."""
        latest = info.get("latest_version")
        url = info.get("download_url")
        changelog = info.get("changelog", "")
        update_type = info.get("update_type", "full")
        
        # Lấy ngôn ngữ giao diện đang dùng
        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"
        
        if lang == "vi":
            title = "🚨 BẮT BUỘC CẬP NHẬT PHIÊN BẢN MỚI"
            msg = f"Đã có phiên bản mới bắt buộc: <b>v{latest}</b> (Phiên bản hiện tại: v{self.current_version_str()})<br><br>" \
                  f"<b>Nội dung nâng cấp:</b><br>{changelog.replace('\n', '<br>')}<br><br>" \
                  f"Ứng dụng yêu cầu cập nhật lên phiên bản mới nhất để tiếp tục sử dụng."
            btn_yes = "Cập nhật ngay"
            btn_no = "Thoát ứng dụng"
        else:
            title = "🚨 MANDATORY UPDATE REQUIRED"
            msg = f"A mandatory new version is required: <b>v{latest}</b> (Current version: v{self.current_version_str()})<br><br>" \
                  f"<b>Changelog:</b><br>{changelog.replace('\n', '<br>')}<br><br>" \
                  f"You must update to the latest version to continue using the application."
            btn_yes = "Update Now"
            btn_no = "Exit Application"
            
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(msg)
        box.setTextFormat(Qt.RichText)
        box.setIcon(QMessageBox.Warning)
        yes_btn = box.addButton(btn_yes, QMessageBox.AcceptRole)
        no_btn = box.addButton(btn_no, QMessageBox.RejectRole)
        
        box.exec()
        
        if box.clickedButton() == yes_btn:
            self._start_download_update(url, latest, update_type)
        else:
            # Chọn "Thoát ứng dụng" hoặc đóng dialog -> Ép tắt ứng dụng ngay lập tức
            sys.exit(0)

    def current_version_str(self) -> str:
        """Trả về phiên bản hiện tại từ core.updater."""
        try:
            from version import APP_VERSION
            return APP_VERSION
        except Exception:
            return ""

    def _start_download_update(self, url: str, latest: str, update_type: str = "full") -> None:
        """Tải xuống tệp cài đặt cập nhật và hiển thị tiến trình dialog (Khóa cứng tải xuống)."""
        import os
        from PySide6.QtWidgets import QProgressDialog
        from core.updater import DownloadWorker
        
        # Đường dẫn tệp cài đặt tải về thư mục tạm
        temp_dir = os.environ.get("TEMP", os.environ.get("TMP", ""))
        if not temp_dir:
            temp_dir = os.path.expanduser("~")
            
        if update_type == "patch":
            dest_filename = f"Audio_Factory_Patch_{latest}.zip"
        else:
            dest_filename = f"Audio_Factory_Setup_{latest}.exe"
            
        dest_path = os.path.join(temp_dir, dest_filename)
        
        # Bản dịch
        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"
        if lang == "vi":
            dl_title = "Tải xuống bản cập nhật"
            dl_label = f"Đang tải {dest_filename}..."
            btn_cancel = "Hủy & Thoát"
        else:
            dl_title = "Downloading Update"
            dl_label = f"Downloading {dest_filename}..."
            btn_cancel = "Cancel & Exit"
            
        progress_dialog = QProgressDialog(dl_label, btn_cancel, 0, 100, self)
        progress_dialog.setWindowTitle(dl_title)
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.setValue(0)
        progress_dialog.setStyleSheet("""
            QProgressDialog {
                background-color: #f8f9fa;
            }
            QLabel {
                color: #333333;
                font-size: 13px;
                font-weight: bold;
            }
            QProgressBar {
                border: 1px solid #dcdcdc;
                border-radius: 6px;
                text-align: center;
                color: #333333;
                font-weight: bold;
                background-color: #ffffff;
            }
            QProgressBar::chunk {
                background-color: #10b981;
                border-radius: 5px;
            }
            QPushButton {
                background-color: #e0e0e0;
                color: #424242;
                border: 1px solid #bdbdbd;
                border-radius: 6px;
                padding: 6px 15px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #d5d5d5;
            }
        """)
        
        # Khởi tạo Worker tải ngầm
        self._download_worker = DownloadWorker(url, dest_path)
        
        def on_progress(downloaded: int, total: int):
            if total > 0:
                pct = int((downloaded / total) * 100)
                progress_dialog.setValue(pct)
                if lang == "vi":
                    progress_dialog.setLabelText(f"Đang tải: {pct}% ({downloaded // 1024 // 1024}MB / {total // 1024 // 1024}MB)")
                else:
                    progress_dialog.setLabelText(f"Downloading: {pct}% ({downloaded // 1024 // 1024}MB / {total // 1024 // 1024}MB)")
            else:
                progress_dialog.setValue(0)
                if lang == "vi":
                    progress_dialog.setLabelText(f"Đang tải: {downloaded // 1024 // 1024}MB")
                else:
                    progress_dialog.setLabelText(f"Downloading: {downloaded // 1024 // 1024}MB")
                    
        def on_finished(file_path: str):
            progress_dialog.close()
            try:
                if update_type == "patch":
                    import zipfile
                    import shutil
                    import subprocess
                    
                    extract_dir = os.path.join(temp_dir, f"Audio_Factory_Patch_{latest}")
                    if os.path.exists(extract_dir):
                        shutil.rmtree(extract_dir, ignore_errors=True)
                    os.makedirs(extract_dir, exist_ok=True)
                    
                    with zipfile.ZipFile(file_path, 'r') as zip_ref:
                        zip_ref.extractall(extract_dir)
                        
                    exe_files = [f for f in os.listdir(extract_dir) if f.lower().endswith(".exe")]
                    if not exe_files:
                        raise Exception("Không tìm thấy tệp Audio Factory.exe trong file patch!")
                        
                    patch_exe_name = exe_files[0]
                    temp_exe_path = os.path.join(extract_dir, patch_exe_name)
                    
                    # Xác định vị trí chạy hiện tại của app
                    current_exe_path = os.path.abspath(sys.executable)
                    current_exe_dir = os.path.dirname(current_exe_path)
                    current_exe_name = os.path.basename(current_exe_path)
                    
                    target_exe_path = current_exe_path
                    target_exe_name = current_exe_name
                    if current_exe_name.lower() in ["python.exe", "pythonw.exe"]:
                        target_exe_name = "Audio Factory.exe"
                        target_exe_path = os.path.join(current_exe_dir, target_exe_name)
                        
                    bat_path = os.path.join(temp_dir, "patch_worker.bat")
                    bat_content = f"""@echo off
setlocal enabledelayedexpansion

:: Chờ tiến trình cũ tắt hẳn
:loop
tasklist /fi "imagename eq {target_exe_name}" | find /i "{target_exe_name}" > nul
if !errorlevel! equ 0 (
    timeout /t 1 /nobreak > nul
    goto loop
)

:: Thực hiện sao chép đè
copy /y "{temp_exe_path}" "{target_exe_path}"

:: Khởi động lại tool
start "" "{target_exe_path}"

:: Tự xóa chính mình
del "%~f0"
"""
                    with open(bat_path, "w", encoding="ansi") as bat_f:
                        bat_f.write(bat_content)
                        
                    subprocess.Popen([bat_path], creationflags=subprocess.CREATE_NO_WINDOW)
                    QApplication.quit()
                else:
                    from core.updater import launch_silent_installer
                    launch_silent_installer(file_path, latest)
            except Exception as e:
                if lang == "vi":
                    QMessageBox.critical(self, "Lỗi", f"Không thể kích hoạt bản cập nhật: {e}")
                else:
                    QMessageBox.critical(self, "Error", f"Failed to activate update: {e}")
                sys.exit(0)
                
        def on_error(err_msg: str):
            progress_dialog.close()
            if lang == "vi":
                QMessageBox.critical(self, "Lỗi tải xuống", f"Không thể tải bản cập nhật:\n{err_msg}\nỨng dụng sẽ tắt ngay lập tức.")
            else:
                QMessageBox.critical(self, "Download Error", f"Failed to download update:\n{err_msg}\nApplication will exit.")
            sys.exit(0)
                
        # Hủy tải hoặc đóng dialog -> TẮT APP NGAY LẬP TỨC!
        def on_cancel():
            if hasattr(self, "_download_worker"):
                self._download_worker.cancel()
            sys.exit(0)

        progress_dialog.canceled.connect(on_cancel)
        
        # Kết nối tín hiệu worker
        self._download_worker.progress.connect(on_progress)
        self._download_worker.finished.connect(on_finished)
        self._download_worker.error.connect(on_error)
        
        self._download_worker.start()

    def _retranslate_combo(self, combo, items_list: List[tuple[str, str]]):
        """Retranslate QComboBox items while preserving current index/selection."""
        current_idx = combo.currentIndex()
        combo.blockSignals(True)
        combo.clear()
        for label, val in items_list:
            combo.addItem(label, val)
        if current_idx >= 0 and current_idx < combo.count():
            combo.setCurrentIndex(current_idx)
        else:
            combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def retranslate_ui(self, lang: str) -> None:
        """Cập nhật các chuỗi văn bản giao diện động theo ngôn ngữ được chọn."""
        try:
            tr = get_translation(lang)
            if not tr:
                from core.localization import TRANSLATIONS
                tr = TRANSLATIONS.get(lang, TRANSLATIONS.get("vi", {}))

            def get_txt(key: str, default_val: str = "") -> str:
                return tr.get(key, default_val)

            # 1. Tiêu đề Window
            self.setWindowTitle(get_txt("window_title", "Audio Factory"))

            # 2. Tiêu đề Header & Footer
            if hasattr(self, "title_label") and self.title_label is not None:
                self.title_label.setText("AUDIO FACTORY")
            if hasattr(self, "subtitle_label") and self.subtitle_label is not None:
                self.subtitle_label.setText(get_txt("header_subtitle"))
            if hasattr(self, "lbl_footer") and self.lbl_footer is not None:
                self.lbl_footer.setText(get_txt("footer"))

            # 3. Các Section Panel
            if hasattr(self, "panel_input") and self.panel_input is not None:
                self.panel_input.lbl_title.setText(get_txt("panel_input"))
            if hasattr(self, "panel_output") and self.panel_output is not None:
                self.panel_output.lbl_title.setText(get_txt("panel_output"))
            if hasattr(self, "panel_processing") and self.panel_processing is not None:
                self.panel_processing.lbl_title.setText(get_txt("panel_processing"))
            if hasattr(self, "panel_subtitles") and self.panel_subtitles is not None:
                self.panel_subtitles.lbl_title.setText(get_txt("panel_subtitles"))
            if hasattr(self, "panel_log") and self.panel_log is not None:
                self.panel_log.lbl_title.setText("⚙  " + get_txt("panel_log"))
            if hasattr(self, "panel_progress") and self.panel_progress is not None:
                self.panel_progress.lbl_title.setText(get_txt("panel_progress"))

            # 4. Các nút cấu hình đầu vào
            if hasattr(self, "btn_add_files") and self.btn_add_files is not None:
                self.btn_add_files.setText(get_txt("btn_add_files"))
            if hasattr(self, "btn_remove_selected") and self.btn_remove_selected is not None:
                self.btn_remove_selected.setText(get_txt("btn_remove_selected"))
            if hasattr(self, "btn_move_up") and self.btn_move_up is not None:
                self.btn_move_up.setText(get_txt("btn_move_up"))
            if hasattr(self, "btn_move_down") and self.btn_move_down is not None:
                self.btn_move_down.setText(get_txt("btn_move_down"))

            # 5. Các nhãn cấu hình đầu ra
            if hasattr(self, "lbl_out_dir") and self.lbl_out_dir is not None:
                self.lbl_out_dir.setText(get_txt("lbl_out_dir"))
            if hasattr(self, "txt_output") and self.txt_output is not None:
                self.txt_output.setPlaceholderText(get_txt("placeholder_out_dir"))
            if hasattr(self, "btn_browse_output") and self.btn_browse_output is not None:
                self.btn_browse_output.setText(get_txt("btn_browse_output"))
            if hasattr(self, "lbl_project_name") and self.lbl_project_name is not None:
                self.lbl_project_name.setText(get_txt("lbl_project_name"))
            if hasattr(self, "lbl_output_format") and self.lbl_output_format is not None:
                self.lbl_output_format.setText(get_txt("lbl_output_format"))

            # 6. Các Feature Cards
            if hasattr(self, "card_merge") and self.card_merge is not None:
                self.card_merge.lbl_title.setText(get_txt("card_merge"))
            if hasattr(self, "card_voice") and self.card_voice is not None:
                self.card_voice.lbl_title.setText(get_txt("card_voice"))
            if hasattr(self, "card_volume") and self.card_volume is not None:
                self.card_volume.lbl_title.setText(get_txt("card_volume"))
            if hasattr(self, "card_silence") and self.card_silence is not None:
                self.card_silence.lbl_title.setText(get_txt("card_silence"))
            if hasattr(self, "card_split") and self.card_split is not None:
                self.card_split.lbl_title.setText(get_txt("card_split"))

            # Retranslate Combobox items
            if hasattr(self, "combo_lang") and self.combo_lang is not None:
                self._retranslate_combo(self.combo_lang, [
                    (get_txt("combo_lang_auto", "Tự động nhận diện"), "auto"),
                    (get_txt("combo_lang_vi", "Tiếng Việt"), "vi"),
                    (get_txt("combo_lang_en", "Tiếng Anh (English)"), "en"),
                    (get_txt("combo_lang_zh", "Tiếng Trung (中文)"), "zh"),
                    (get_txt("combo_lang_ja", "Tiếng Nhật (日本語)"), "ja"),
                    (get_txt("combo_lang_ko", "Tiếng Hàn (한국어)"), "ko"),
                    (get_txt("combo_lang_ru", "Tiếng Nga (Русский)"), "ru"),
                    (get_txt("combo_lang_fr", "Tiếng Pháp (Français)"), "fr"),
                    (get_txt("combo_lang_es", "Tiếng Tây Ban Nha"), "es")
                ])

            if hasattr(self, "combo_model") and self.combo_model is not None:
                self._retranslate_combo(self.combo_model, [
                    (get_txt("combo_model_turbo", "large-v3-turbo (Nhanh x8, chính xác tốt - Khuyên dùng)"), "turbo"),
                    (get_txt("combo_model_large", "large-v3 (Chính xác tối đa - Yêu cầu cấu hình mạnh)"), "large"),
                    (get_txt("combo_model_medium", "medium (Tốc độ nhanh, nhẹ máy - Độ chính xác khá)"), "medium")
                ])

            if hasattr(self, "combo_speed") and self.combo_speed is not None:
                self._retranslate_combo(self.combo_speed, [
                    (get_txt("combo_speed_10x", "1.0x (Tốc độ gốc - Mặc định)"), "1.0"),
                    (get_txt("combo_speed_09x", "0.9x (Giọng nói nhanh - Tăng chính xác)"), "0.9"),
                    (get_txt("combo_speed_08x", "0.8x (Giọng nói cực nhanh / Tin tức / Rap)"), "0.8")
                ])

            if hasattr(self, "combo_batch") and self.combo_batch is not None:
                self._retranslate_combo(self.combo_batch, [
                    (get_txt("combo_batch_1", "1 (Tuần tự - Ít VRAM nhất, chậm nhất)"), "1"),
                    (get_txt("combo_batch_2", "2 (Song song nhẹ)"), "2"),
                    (get_txt("combo_batch_4", "4 (Song song vừa)"), "4"),
                    (get_txt("combo_batch_8", "8 (Song song nhanh - Khuyên dùng)"), "8"),
                    (get_txt("combo_batch_16", "16 (Song song tối đa - Cần nhiều VRAM)"), "16"),
                    (get_txt("combo_batch_32", "32 (Cực nhanh - Yêu cầu GPU khủng)"), "32")
                ])

            if hasattr(self, "combo_format") and self.combo_format is not None:
                self._retranslate_combo(self.combo_format, [
                    (get_txt("combo_format_169", "16:9 (Video Ngang)"), "16:9"),
                    (get_txt("combo_format_916", "9:16 (Video Dọc)"), "9:16"),
                    (get_txt("combo_format_11", "1:1 (Video Vuông)"), "1:1")
                ])

            if hasattr(self, "combo_lines") and self.combo_lines is not None:
                self._retranslate_combo(self.combo_lines, [
                    (get_txt("combo_lines_1", "1 dòng (Gọn – 1 hàng chữ mỗi đoạn)"), "1"),
                    (get_txt("combo_lines_2", "2 dòng (2 hàng chữ mỗi đoạn)"), "2")
                ])

            if hasattr(self, "combo_translate_lang") and self.combo_translate_lang is not None:
                self._retranslate_combo(self.combo_translate_lang, [
                    (get_txt("combo_target_vi", "Tiếng Việt (vi)"), "vi"),
                    (get_txt("combo_target_en", "Tiếng Anh (en)"), "en"),
                    (get_txt("combo_target_zh", "Tiếng Trung giản thể (zh)"), "zh"),
                    (get_txt("combo_target_ja", "Tiếng Nhật (ja)"), "ja"),
                    (get_txt("combo_target_ko", "Tiếng Hàn (ko)"), "ko"),
                    (get_txt("combo_target_es", "Tiếng Tây Ban Nha (es)"), "es"),
                    (get_txt("combo_target_fr", "Tiếng Pháp (fr)"), "fr"),
                    (get_txt("combo_target_ru", "Tiếng Nga (ru)"), "ru")
                ])

            if hasattr(self, "combo_translate_engine") and self.combo_translate_engine is not None:
                self._retranslate_combo(self.combo_translate_engine, [
                    (get_txt("engine_google", "Google Bypass (Miễn phí)"), "google"),
                    (get_txt("engine_gemini", "Gemini Flash (Tự động xoay Key & Model)"), "gemini"),
                    (get_txt("engine_deepseek", "DeepSeek V4 Pro"), "deepseek"),
                ])

            # Localization for API key hints and placeholders
            if lang == "vi":
                gemini_hint = 'Gemini API lấy tại <a href="https://aistudio.google.com/apikey" style="color: #2563eb; text-decoration: underline;">Lấy Key tại đây</a>.'
                deepseek_hint = 'DeepSeek API lấy tại <a href="https://platform.deepseek.com/api_keys" style="color: #2563eb; text-decoration: underline;">Lấy Key tại đây</a>.'
                gemini_ph = "Dán danh sách Gemini API Key (mỗi key 1 dòng)..."
                deepseek_ph = "Nhập 1 API key DeepSeek"
            else:
                gemini_hint = 'Get Gemini API Key <a href="https://aistudio.google.com/apikey" style="color: #2563eb; text-decoration: underline;">here</a>.'
                deepseek_hint = 'Get DeepSeek API Key <a href="https://platform.deepseek.com/api_keys" style="color: #2563eb; text-decoration: underline;">here</a>.'
                gemini_ph = "Paste Gemini API Keys (one key per line)..."
                deepseek_ph = "Enter 1 DeepSeek API key"

            if hasattr(self, "lbl_gemini_hint") and self.lbl_gemini_hint is not None:
                self.lbl_gemini_hint.setText(gemini_hint)
            if hasattr(self, "lbl_deepseek_hint") and self.lbl_deepseek_hint is not None:
                self.lbl_deepseek_hint.setText(deepseek_hint)
            if hasattr(self, "gemini_key_input") and self.gemini_key_input is not None:
                self.gemini_key_input.setPlaceholderText(gemini_ph)
            if hasattr(self, "deepseek_key_input") and self.deepseek_key_input is not None:
                self.deepseek_key_input.setPlaceholderText(deepseek_ph)

            if hasattr(self, "btn_check_keys") and self.btn_check_keys is not None:
                self.btn_check_keys.setText("🔍  Kiểm tra" if lang == "vi" else "🔍  Check")

            # Container labels
            def set_combo_label(container, text):
                if hasattr(self, container) and getattr(self, container) is not None:
                    lbl = getattr(self, container).findChild(QLabel, "FieldLabel")
                    if lbl is not None:
                        lbl.setText(text)

            set_combo_label("w_lang", get_txt("lbl_lang"))
            set_combo_label("w_model", get_txt("lbl_model"))
            set_combo_label("w_speed", get_txt("lbl_speed"))
            set_combo_label("w_batch", get_txt("lbl_batch"))
            set_combo_label("w_format", get_txt("lbl_format"))
            set_combo_label("w_lines", get_txt("lbl_lines"))

            # Update Google message
            if hasattr(self, "lbl_google_msg") and self.lbl_google_msg is not None:
                self.lbl_google_msg.setText(get_txt("lbl_google_msg"))

            # 8. Nhật ký và Tiến trình
            if hasattr(self, "btn_clear_log") and self.btn_clear_log is not None:
                self.btn_clear_log.setText(get_txt("btn_clear_log"))
            if hasattr(self, "btn_export_log") and self.btn_export_log is not None:
                self.btn_export_log.setText(get_txt("btn_export_log"))
            if hasattr(self, "lbl_status_title") and self.lbl_status_title is not None:
                self.lbl_status_title.setText(get_txt("lbl_status_title"))
            if hasattr(self, "lbl_elapsed_title") and self.lbl_elapsed_title is not None:
                self.lbl_elapsed_title.setText(get_txt("lbl_elapsed_title"))
            if hasattr(self, "btn_open_folder") and self.btn_open_folder is not None:
                self.btn_open_folder.setText(get_txt("btn_open_folder"))

            # Translate buttons
            if hasattr(self, "btn_start") and self.btn_start is not None:
                if self.worker is not None and self.worker.isRunning():
                    self.btn_start.setText(get_txt("btn_start_processing"))
                else:
                    self.btn_start.setText(get_txt("btn_start"))
            if hasattr(self, "btn_cancel") and self.btn_cancel is not None:
                self.btn_cancel.setText(get_txt("btn_cancel"))

            # Translate status label if we have a key
            if hasattr(self, "lbl_status") and self.lbl_status is not None:
                if hasattr(self, "current_status_key") and self.current_status_key:
                    status_text = get_txt(self.current_status_key, None)
                    if status_text:
                        self.lbl_status.setText(status_text)
                    elif self.current_status_key == "status_cancelled_ready":
                        self.lbl_status.setText(f"{get_txt('status_cancelled')} {get_txt('status_ready')}")

            # Cập nhật lại header của bảng
            if hasattr(self, "table") and self.table is not None:
                self.table.setHorizontalHeaderLabels([
                    get_txt("table_header_stt"),
                    get_txt("table_header_name"),
                    get_txt("table_header_duration"),
                    get_txt("table_header_size"),
                    get_txt("table_header_action")
                ])
            
            # Cập nhật thông số bảng file
            self.update_file_table()
        except Exception as e:
            import traceback
            print(f"Error in retranslate_ui: {e}")
            traceback.print_exc()

    @Slot(str)
    def _on_translation_status(self, msg: str) -> None:
        """Nhận thông báo tiến trình từ TranslationWorker."""
        self.txt_logs.append(f"  {msg}")
        self.txt_logs.verticalScrollBar().setValue(
            self.txt_logs.verticalScrollBar().maximum()
        )
        self.lbl_status.setText(msg[:60] + "..." if len(msg) > 60 else msg)

    @Slot(str)
    def _on_translation_success(self, paths_str: str) -> None:
        """Dịch hoàn thành — hiện popup thành công và cập nhật UI."""
        self.btn_cancel.setEnabled(False)
        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"
        tr = get_translation(lang)
        self.lbl_status.setText(tr.get("status_translation_done", "Dịch phụ đề hoàn thành!"))
        self.current_status_key = "status_translation_done"

        paths = [p for p in paths_str.split("\n") if p.strip()]
        file_list = "\n".join(f"  • {Path(p).name}" for p in paths)
        self.txt_logs.append(
            f'\n<span style="color:#10d98c; font-weight:bold;">'
            f'[DỊCH THUẬT] ✅ Hoàn thành! Đã tạo {len(paths)} file phụ đề dịch:</span>\n'
            f'{file_list}'
        )
        self.txt_logs.verticalScrollBar().setValue(
            self.txt_logs.verticalScrollBar().maximum()
        )
        try:
            import winsound
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass
        title = "Dịch phụ đề thành công" if lang == "vi" else "Translation Success"
        body = (
            f"Đã dịch xong {len(paths)} file phụ đề!<br><br>{file_list.replace('\n', '<br>')}<br><br>"
            f"File được lưu cùng thư mục với file SRT gốc."
        ) if lang == "vi" else (
            f"Translated {len(paths)} subtitle files successfully!<br><br>{file_list.replace('\n', '<br>')}<br><br>"
            f"Files are saved in the same directory as the source SRT files."
        )
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.NoIcon)
        msg_box.setWindowTitle(title)
        msg_box.setTextFormat(Qt.RichText)
        msg_box.setText(body)
        msg_box.exec()

    @Slot(str)
    def _on_translation_error(self, err_msg: str) -> None:
        """Xử lý lỗi từ TranslationWorker."""
        self.btn_cancel.setEnabled(False)
        self._set_processing_state(False)
        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"
        tr = get_translation(lang)
        if "cancelled" in err_msg.lower() or "hủy" in err_msg.lower():
            self.lbl_status.setText(tr.get("status_translation_cancelled", "Đã hủy dịch thuật."))
            self.current_status_key = "status_translation_cancelled"
            self._cleanup_project_dir_on_translation_cancel()
            return
        self.lbl_status.setText(tr.get("status_translation_error", "Dịch phụ đề gặp lỗi."))
        self.current_status_key = "status_translation_error"
        self.txt_logs.append(
            f'\n<span style="color:#FF6B6B;">[DỊCH THUẬT] ❌ Lỗi: {err_msg}</span>'
        )
        self.txt_logs.verticalScrollBar().setValue(
            self.txt_logs.verticalScrollBar().maximum()
        )
        try:
            import winsound
            winsound.PlaySound("SystemHand", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass
        QMessageBox.critical(
            self, "Lỗi dịch thuật",
            f"Dịch phụ đề thất bại:\n{err_msg}"
        )

    def _cleanup_project_dir_on_translation_cancel(self) -> None:
        """Dọn dẹp thư mục dự án dở dang khi hủy dịch thuật."""
        if self.last_output_dir:
            target = Path(self.last_output_dir)
            if target.exists() and target.is_dir():
                import time
                import shutil
                for attempt in range(3):
                    try:
                        shutil.rmtree(target)
                        self.txt_logs.append(
                            '<span style="color:#FF4444; font-weight:bold;">[HỆ THỐNG] '
                            'Đã dọn dẹp sạch thư mục dự án dở dang.</span>'
                        )
                        self.txt_logs.verticalScrollBar().setValue(
                            self.txt_logs.verticalScrollBar().maximum()
                        )
                        break
                    except Exception:
                        time.sleep(0.5)

    @Slot(str)
    def _on_translation_quota_exceeded(self, err_msg: str) -> None:
        """
        Xử lý khi API hết quota/tiền — hiện popup riêng, dừng an toàn.
        Signal đặc biệt từ TranslationWorker để UX phân biệt với lỗi kỹ thuật.
        """
        self.btn_cancel.setEnabled(False)
        lang = self.combo_ui_lang.currentData() if hasattr(self, "combo_ui_lang") else "vi"
        tr = get_translation(lang)
        self.lbl_status.setText(tr.get("status_quota_exceeded", "API đạt giới hạn quota."))
        self.current_status_key = "status_quota_exceeded"
        self.txt_logs.append(
            f'\n<span style="color:#FFB347; font-weight:bold;">'
            f'[DỊCH THUẬT] ⚠️  Hết Quota API: {err_msg}</span>'
        )
        self.txt_logs.verticalScrollBar().setValue(
            self.txt_logs.verticalScrollBar().maximum()
        )
        try:
            import winsound
            winsound.PlaySound("SystemHand", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass
        QMessageBox.warning(
            self,
            "⚠️  Hết hạn mức API",
            f"API đã đạt giới hạn quota hoặc số dư không đủ.\n\n"
            f"Chi tiết: {err_msg}\n\n"
            f"Gợi ý:\n"
            f"• Chuyển sang 'Google Bypass' để dịch miễn phí\n"
            f"• Hoặc nạp thêm credit vào tài khoản API\n"
            f"• Hoặc thử lại sau khi quota được reset"
        )


    @Slot()
    def open_output_folder(self) -> None:
        target = self.last_output_dir or self.txt_output.text().strip()
        if target and os.path.exists(target):
            try:
                if sys.platform == "win32":
                    os.startfile(target)
                elif sys.platform == "darwin":
                    subprocess.run(["open", target])
                else:
                    subprocess.run(["xdg-open", target])
            except Exception as exc:
                QMessageBox.warning(self, "Cảnh báo", f"Không thể mở thư mục: {exc}")
        else:
            QMessageBox.warning(self, "Cảnh báo", "Thư mục không tồn tại hoặc chưa được chọn.")

    def closeEvent(self, event) -> None:  # type: ignore[override]
        _any_running = (
            (self.worker and self.worker.isRunning())
            or (self.translation_worker and self.translation_worker.isRunning())
        )
        if _any_running:
            reply = QMessageBox.question(
                self, "Xác nhận thoát",
                "Tiến trình đang chạy. Bạn có chắc chắn muốn hủy và thoát ứng dụng?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply == QMessageBox.Yes:
                if self.translation_worker and self.translation_worker.isRunning():
                    self.translation_worker.cancel()
                    self.translation_worker.wait()
                if self.worker and self.worker.isRunning():
                    self.worker.cancel()
                    self.worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if not hasattr(self, "_screen_connected"):
            self._screen_connected = False
        if not self._screen_connected:
            handle = self.windowHandle()
            if handle:
                handle.screenChanged.connect(self.handle_screen_changed)
                self._screen_connected = True
                # Call once to scale for the launch monitor
                self.handle_screen_changed(handle.screen())

    def handle_screen_changed(self, new_screen) -> None:
        if not new_screen:
            return
            
        screen_geom = new_screen.availableGeometry()
        screen_w = screen_geom.width()
        screen_h = screen_geom.height()
        
        # Khóa tuyệt đối cuộn ngang, kích hoạt cuộn dọc tự động
        self.main_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.main_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        
        # Đặt mốc Minimum linh hoạt để người dùng tự do kéo giãn sau đó
        self.setMinimumSize(int(screen_w * 0.50), 550)
        
        # Chỉ resize khi kích thước hiện tại vượt quá màn hình mới
        curr_width = self.width()
        curr_height = self.height()
        target_width = curr_width
        target_height = curr_height
        resized = False
        
        if curr_width > screen_w:
            target_width = int(screen_w * 0.95)
            resized = True
        if curr_height > screen_h:
            target_height = int(screen_h * 0.95)
            resized = True
            
        if resized:
            self.resize(target_width, target_height)
            
        self.updateGeometry()

    # ── Legacy aliases kept for backward-compat ───────────────────────────

    def apply_styles(self) -> None:
        """Legacy alias – styles are applied in __init__ via APP_STYLESHEET."""
        self.setStyleSheet(APP_STYLESHEET)

    def setup_ui(self) -> None:
        """Legacy alias – called by __init__ via _setup_ui()."""
        pass  # already built in __init__

    def handle_row_move(self, from_row: int, to_row: int) -> None:
        """Legacy alias for tests."""
        self._handle_row_move(from_row, to_row)

    def get_cached_duration(self, path: Path) -> Optional[float]:
        """Legacy alias for tests."""
        return self._get_cached_duration(path)

    def handle_worker_status(self, msg: str) -> None:
        self._on_worker_status(msg)

    def handle_worker_success(self, result: object) -> None:
        self._on_worker_success(result)

    def handle_worker_error(self, err_msg: str) -> None:
        self._on_worker_error(err_msg)

    def set_ui_processing_state(self, processing: bool) -> None:
        self._set_processing_state(processing)

    def update_elapsed_time(self) -> None:
        self._tick_elapsed()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

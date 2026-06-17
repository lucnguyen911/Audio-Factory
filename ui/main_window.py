import os
import sys
import subprocess
import datetime
import re
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable

from PySide6.QtCore import (
    Qt, QThread, Signal, Slot, QSize, QPropertyAnimation,
    QEasingCurve, Property, QPoint, QTimer
)
from PySide6.QtGui import QPainter, QColor, QFont, QFontDatabase
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
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
)

from core.pipeline import (
    run_audio_pipeline,
    run_batch_pipeline,
    PipelineOptions,
    PipelineResult,
    PipelineError
)
from core.importer import get_duration_seconds, MediaImportError


# ──────────────────────────────────────────────────────────────────────────────
# Worker Thread
# ──────────────────────────────────────────────────────────────────────────────

class PipelineCancelledError(Exception):
    """Exception raised when pipeline execution is cancelled by the user."""
    pass


class PipelineWorker(QThread):
    status_received = Signal(str)
    finished_success = Signal(object)
    finished_error = Signal(str)

    def __init__(
        self,
        input_paths: List[Path],
        output_dir: Path,
        options: PipelineOptions,
        is_batch: bool
    ):
        super().__init__()
        self.input_paths = input_paths
        self.output_dir = output_dir
        self.options = options
        self.is_batch = is_batch
        self.is_cancelled = False

    def run(self):
        def worker_status_callback(msg: str):
            if self.is_cancelled:
                raise PipelineCancelledError("Cancelled by user")
            self.status_received.emit(msg)

        try:
            if self.is_batch:
                results = run_batch_pipeline(
                    self.input_paths,
                    self.output_dir,
                    self.options,
                    status_callback=worker_status_callback
                )
                self.finished_success.emit(results)
            else:
                result = run_audio_pipeline(
                    self.input_paths,
                    self.output_dir,
                    self.options,
                    status_callback=worker_status_callback
                )
                self.finished_success.emit(result)
        except PipelineCancelledError:
            self.finished_error.emit("Processing was cancelled by the user.")
        except Exception as e:
            self.finished_error.emit(str(e))

    def cancel(self):
        self.is_cancelled = True


# ──────────────────────────────────────────────────────────────────────────────
# Custom Widgets
# ──────────────────────────────────────────────────────────────────────────────

class Switch(QAbstractButton):
    """Animated sliding toggle switch matching the mockup."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._margin = 3
        self._thumb_position = float(self._margin)
        self._animation = QPropertyAnimation(self, b"thumb_position", self)
        self._animation.setDuration(130)
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)

    @Property(float)
    def thumb_position(self):
        return self._thumb_position

    @thumb_position.setter
    def thumb_position(self, pos):
        self._thumb_position = pos
        self.update()

    def sizeHint(self):
        return QSize(44, 22)

    def nextCheckState(self):
        self.setChecked(not self.isChecked())

    def checkStateSet(self):
        w = self.width() if self.width() > 0 else 44
        h = self.height() if self.height() > 0 else 22
        end_value = w - h + self._margin if self.isChecked() else float(self._margin)
        self._animation.stop()
        self._animation.setEndValue(end_value)
        self._animation.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        h = self.height()
        self._thumb_position = w - h + self._margin if self.isChecked() else float(self._margin)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Track colour
        if not self.isEnabled():
            bg_color = QColor("#1e293b")
        elif self.isChecked():
            bg_color = QColor("#10b981")
        else:
            bg_color = QColor("#334155")

        painter.setBrush(bg_color)
        painter.setPen(Qt.NoPen)

        rect = self.rect()
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        # Thumb
        thumb_color = QColor("#ffffff") if self.isEnabled() else QColor("#64748b")
        painter.setBrush(thumb_color)
        h = rect.height() - 2 * self._margin
        painter.drawEllipse(
            QPoint(int(self._thumb_position + h / 2), int(self._margin + h / 2)),
            int(h / 2),
            int(h / 2)
        )


class DragDropTable(QTableWidget):
    order_changed = Signal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragDropOverwriteMode(False)

    def dragEnterEvent(self, event):
        if event.source() == self:
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.source() == self:
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):
        if event.source() == self:
            from_row = self.currentRow()
            to_row = self.rowAt(event.position().toPoint().y())
            if to_row == -1:
                to_row = self.rowCount() - 1
            if from_row != to_row and from_row != -1 and to_row != -1:
                self.order_changed.emit(from_row, to_row)
                event.accept()
            else:
                event.ignore()
        else:
            super().dropEvent(event)


class IconBadge(QLabel):
    def __init__(self, char: str, bg_color: str, parent=None):
        super().__init__(char, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(36, 36)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: #ffffff;
                font-size: 16px;
                border-radius: 18px;
                border: none;
            }}
        """)


class FeatureCard(QFrame):
    """Horizontal card: [icon] [title+desc]  [switch]"""

    def __init__(self, title: str, desc: str, icon_char: str, icon_bg: str, parent=None):
        super().__init__(parent)
        self.setObjectName("FeatureCard")
        self.setMinimumWidth(160)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self.badge = IconBadge(icon_char, icon_bg)
        layout.addWidget(self.badge, 0, Qt.AlignVCenter)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        text_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("CardTitle")
        text_layout.addWidget(self.lbl_title)

        self.lbl_desc = QLabel(desc)
        self.lbl_desc.setObjectName("CardDesc")
        self.lbl_desc.setWordWrap(True)
        text_layout.addWidget(self.lbl_desc)

        layout.addLayout(text_layout, 1)

        self.switch = Switch()
        layout.addWidget(self.switch, 0, Qt.AlignVCenter)


class SocialOptimizeCard(QFrame):
    """Horizontal card with optional dropdown shown when switch is ON."""

    def __init__(self, title: str, desc: str, icon_char: str, icon_bg: str, parent=None):
        super().__init__(parent)
        self.setObjectName("FeatureCard")
        self.setMinimumWidth(160)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)

        # Top row
        top_widget = QWidget()
        top_widget.setStyleSheet("background: transparent; border: none;")
        top_layout = QHBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)

        self.badge = IconBadge(icon_char, icon_bg)
        top_layout.addWidget(self.badge, 0, Qt.AlignVCenter)

        text_layout = QVBoxLayout()
        text_layout.setSpacing(3)
        text_layout.setContentsMargins(0, 0, 0, 0)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("CardTitle")
        text_layout.addWidget(self.lbl_title)

        self.lbl_desc = QLabel(desc)
        self.lbl_desc.setObjectName("CardDesc")
        self.lbl_desc.setWordWrap(True)
        text_layout.addWidget(self.lbl_desc)

        top_layout.addLayout(text_layout, 1)

        self.switch = Switch()
        top_layout.addWidget(self.switch, 0, Qt.AlignVCenter)

        main_layout.addWidget(top_widget)

        # Platform dropdown (hidden when OFF)
        self.dropdown_widget = QWidget()
        self.dropdown_widget.setStyleSheet("background: transparent; border: none;")
        dropdown_layout = QHBoxLayout(self.dropdown_widget)
        dropdown_layout.setContentsMargins(46, 0, 0, 0)
        dropdown_layout.setSpacing(8)

        lbl_platform = QLabel("Nền tảng:")
        lbl_platform.setObjectName("CardSubLabel")
        dropdown_layout.addWidget(lbl_platform)

        self.combo_platform = QComboBox()
        self.combo_platform.addItems([
            "Tổng quát / An toàn",
            "YouTube / Facebook / X",
            "TikTok / Instagram Reels",
            "Podcast / Voice Clean"
        ])
        self.combo_platform.setObjectName("SmallCombo")
        dropdown_layout.addWidget(self.combo_platform, 1)

        main_layout.addWidget(self.dropdown_widget)

        self.switch.toggled.connect(self._handle_switch)
        self._handle_switch(self.switch.isChecked())

    def _handle_switch(self, checked: bool):
        self.dropdown_widget.setVisible(checked)


class SectionPanel(QFrame):
    """Rounded panel with a header row (title + optional right widget) and content area."""

    def __init__(
        self,
        title_text: str,
        subtitle_text: str = "",
        right_header_widget: QWidget = None,
        parent=None
    ):
        super().__init__(parent)
        self.setObjectName("SectionPanel")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 14, 16, 14)
        self.main_layout.setSpacing(10)

        # Header
        header_widget = QWidget()
        header_widget.setStyleSheet("background: transparent; border: none;")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(8)

        title_block = QWidget()
        title_block.setStyleSheet("background: transparent; border: none;")
        title_block_layout = QVBoxLayout(title_block)
        title_block_layout.setContentsMargins(0, 0, 0, 0)
        title_block_layout.setSpacing(2)

        self.lbl_title = QLabel(title_text)
        self.lbl_title.setObjectName("SectionTitle")
        title_block_layout.addWidget(self.lbl_title)

        if subtitle_text:
            self.lbl_subtitle = QLabel(subtitle_text)
            self.lbl_subtitle.setObjectName("SectionSubtitle")
            self.lbl_subtitle.setWordWrap(True)
            title_block_layout.addWidget(self.lbl_subtitle)

        header_layout.addWidget(title_block)
        header_layout.addStretch()

        if right_header_widget:
            header_layout.addWidget(right_header_widget, 0, Qt.AlignVCenter)

        self.main_layout.addWidget(header_widget)

        # Content area
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent; border: none;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)

        self.main_layout.addWidget(self.content_widget)


# ──────────────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────────────

def create_labeled_combo(label_text: str, combo_box: QComboBox) -> QWidget:
    w = QWidget()
    w.setStyleSheet("background: transparent; border: none;")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lbl = QLabel(label_text)
    lbl.setObjectName("FieldLabel")
    lay.addWidget(lbl)
    lay.addWidget(combo_box)
    return w


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
    elif size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.2f} KB"
    else:
        return f"{size_bytes} B"


def format_duration(seconds: float) -> str:
    if seconds < 0:
        return "00:00"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    if h > 0:
        return f"{h:d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


FORMAT_MAP = {
    ".wav (WAV - Không nén)": "wav",
    ".mp3 (MP3 - Nén phổ biến)": "mp3",
    ".m4a (M4A - AAC)": "m4a",
    ".flac (FLAC - Không nén)": "flac",
    ".ogg (OGG - Vorbis)": "ogg"
}

PLATFORM_MAP = {
    "Tổng quát / An toàn": "general",
    "YouTube / Facebook / X": "youtube_facebook_x",
    "TikTok / Instagram Reels": "tiktok_instagram",
    "Podcast / Voice Clean": "podcast_voice"
}

LANGUAGE_MAP = {
    "Tự động nhận diện": None,
    "Tiếng Trung (中文)": "zh",
    "Tiếng Anh (English)": "en",
    "Tiếng Việt": "vi",
    "Tiếng Nhật (日本語)": "ja",
    "Tiếng Hàn (한국어)": "ko",
    "Tiếng Nga (Русский)": "ru",
    "Tiếng Pháp (Français)": "fr",
    "Tiếng Tây Ban Nha": "es"
}


# ──────────────────────────────────────────────────────────────────────────────
# Main Window
# ──────────────────────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Audio Factory By Lực Nguyễn")
        self.resize(1100, 820)
        self.setMinimumSize(900, 680)

        self.worker: Optional[PipelineWorker] = None
        self.last_output_dir: Optional[str] = None
        self.input_paths_list: List[Path] = []
        self.duration_cache: Dict[str, float] = {}

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_elapsed_time)
        self.elapsed_seconds = 0

        self.setup_ui()
        self.apply_styles()

    # ──────────────────────────────────────────────────────────────────────────
    # UI Construction
    # ──────────────────────────────────────────────────────────────────────────

    def setup_ui(self):
        # Root scroll area so the window never clips content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setCentralWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        root = QVBoxLayout(container)
        root.setContentsMargins(14, 14, 14, 10)
        root.setSpacing(10)

        # ── Row 1: Input (left) + Output (right) ──────────────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        # Section 1 – Input
        self.panel_input = SectionPanel(
            "1. Cấu hình đầu vào  (Sắp xếp thứ tự các tệp)",
            "Kéo thả để sắp xếp thứ tự. Khi bật Gộp âm thanh, các tệp sẽ được gộp theo thứ tự từ trên xuống dưới."
        )
        self._build_input_section()
        row1.addWidget(self.panel_input, 6)

        # Section 2 – Output
        self.panel_output = SectionPanel("2. Cấu hình đầu ra")
        self._build_output_section()
        row1.addWidget(self.panel_output, 4)

        root.addLayout(row1)

        # ── Section 3: Processing cards ───────────────────────────────────
        self.panel_processing = SectionPanel("3. Tiến trình xử lý")
        self._build_processing_section()
        root.addWidget(self.panel_processing)

        # ── Section 4: Subtitle config ────────────────────────────────────
        self._build_subtitle_section()
        root.addWidget(self.panel_subtitles)

        # ── Row 2: Log (left) + Progress (right) ─────────────────────────
        row2 = QHBoxLayout()
        row2.setSpacing(10)

        self.panel_log = self._build_log_section()
        row2.addWidget(self.panel_log, 6)

        self.panel_progress = self._build_progress_section()
        row2.addWidget(self.panel_progress, 4)

        root.addLayout(row2)

        # ── Footer ────────────────────────────────────────────────────────
        footer = QLabel("Powered by FFmpeg + Whisper Local + Lực Nguyễn")
        footer.setAlignment(Qt.AlignCenter)
        footer.setObjectName("FooterLabel")
        root.addWidget(footer)

        # ── Backward-compat aliases (required by tests) ───────────────────
        self.chk_merge = self.card_merge.switch
        self.chk_voice = self.card_voice.switch
        self.chk_volume = self.card_volume.switch
        self.chk_silence = self.card_silence.switch
        self.chk_social = self.card_social.switch
        self.chk_sub = self.switch_auto_sub

        self.sub_section = self
        self.content_panel = self.sub_content_panel

    # ── Section builders ──────────────────────────────────────────────────

    def _build_input_section(self):
        # File list action buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(8)

        self.btn_add_files = QPushButton("＋  Thêm tệp")
        self.btn_add_files.setObjectName("btn_add")
        self.btn_add_files.setCursor(Qt.PointingHandCursor)
        self.btn_add_files.clicked.connect(self.browse_inputs)

        self.btn_remove_selected = QPushButton("🗑  Xóa đã chọn")
        self.btn_remove_selected.setObjectName("btn_remove")
        self.btn_remove_selected.setCursor(Qt.PointingHandCursor)
        self.btn_remove_selected.clicked.connect(self.remove_selected)

        self.btn_move_up = QPushButton("↑  Lên")
        self.btn_move_up.setObjectName("btn_neutral")
        self.btn_move_up.setCursor(Qt.PointingHandCursor)
        self.btn_move_up.clicked.connect(self.move_up)

        self.btn_move_down = QPushButton("↓  Xuống")
        self.btn_move_down.setObjectName("btn_neutral")
        self.btn_move_down.setCursor(Qt.PointingHandCursor)
        self.btn_move_down.clicked.connect(self.move_down)

        btn_row.addWidget(self.btn_add_files)
        btn_row.addWidget(self.btn_remove_selected)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_move_up)
        btn_row.addWidget(self.btn_move_down)

        self.panel_input.content_layout.addLayout(btn_row)

        # File table
        self.table = DragDropTable()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["#", "Tên tệp", "Thời lượng", "Kích thước", "✕"])
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(2, 90)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 40)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Interactive)
        self.table.setMinimumHeight(180)
        self.table.order_changed.connect(self.handle_row_move)
        self.panel_input.content_layout.addWidget(self.table)

        # Summary chips
        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(0, 2, 0, 0)
        summary_row.setSpacing(10)

        self.lbl_sum_count = QLabel("📁  Tổng số: 0 tệp")
        self.lbl_sum_duration = QLabel("⏱  Tổng thời lượng: 00:00")
        self.lbl_sum_size = QLabel("💾  Tổng kích thước: 0 B")

        for lbl in [self.lbl_sum_count, self.lbl_sum_duration, self.lbl_sum_size]:
            lbl.setObjectName("SummaryChip")
            summary_row.addWidget(lbl)
        summary_row.addStretch()

        self.panel_input.content_layout.addLayout(summary_row)

        # Hidden compat label
        self.lbl_summary = QLabel()
        self.lbl_summary.setVisible(False)
        self.panel_input.content_layout.addWidget(self.lbl_summary)

    def _build_output_section(self):
        grid = QGridLayout()
        grid.setSpacing(8)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(1, 1)

        lbl_out = QLabel("Thư mục đầu ra:")
        lbl_out.setObjectName("FieldLabel")
        grid.addWidget(lbl_out, 0, 0)

        self.txt_output = QLineEdit()
        self.txt_output.setPlaceholderText("Chọn thư mục lưu kết quả...")
        grid.addWidget(self.txt_output, 0, 1)

        self.btn_browse_output = QPushButton("📁  Chọn thư mục")
        self.btn_browse_output.setObjectName("btn_neutral")
        self.btn_browse_output.setCursor(Qt.PointingHandCursor)
        self.btn_browse_output.clicked.connect(self.browse_output)
        grid.addWidget(self.btn_browse_output, 0, 2)

        lbl_proj = QLabel("Tên dự án:")
        lbl_proj.setObjectName("FieldLabel")
        grid.addWidget(lbl_proj, 1, 0)

        self.txt_project_name = QLineEdit()
        self.txt_project_name.setText("audio_project")
        grid.addWidget(self.txt_project_name, 1, 1, 1, 2)

        lbl_proj_hint = QLabel("Tên dự án sẽ được dùng để tạo thư mục kết quả.")
        lbl_proj_hint.setObjectName("HintLabel")
        grid.addWidget(lbl_proj_hint, 2, 1, 1, 2)

        lbl_fmt = QLabel("Định dạng xuất:")
        lbl_fmt.setObjectName("FieldLabel")
        grid.addWidget(lbl_fmt, 3, 0)

        self.combo_out_format = QComboBox()
        self.combo_out_format.addItems([
            ".wav (WAV - Không nén)",
            ".mp3 (MP3 - Nén phổ biến)",
            ".m4a (M4A - AAC)",
            ".flac (FLAC - Không nén)",
            ".ogg (OGG - Vorbis)"
        ])
        grid.addWidget(self.combo_out_format, 3, 1, 1, 2)

        self.panel_output.content_layout.addLayout(grid)
        self.panel_output.content_layout.addStretch()

    def _build_processing_section(self):
        cards_row = QHBoxLayout()
        cards_row.setContentsMargins(0, 0, 0, 0)
        cards_row.setSpacing(8)

        self.card_merge = FeatureCard(
            "Gộp âm thanh",
            "Nối các tệp theo thứ tự đã sắp xếp",
            "🔊", "#7c3aed"
        )
        self.card_voice = FeatureCard(
            "Làm sạch giọng nói",
            "Loại bỏ tạp âm, tiếng ồn nền",
            "🎙", "#ea580c"
        )
        self.card_volume = FeatureCard(
            "Cân bằng âm lượng",
            "Chuẩn hóa và cân bằng âm lượng",
            "📶", "#2563eb"
        )
        self.card_silence = FeatureCard(
            "Rút ngắn khoảng lặng",
            "Loại bỏ khoảng lặng dư thừa",
            "✂", "#d97706"
        )
        self.card_social = SocialOptimizeCard(
            "Tối ưu mạng xã hội",
            "Tối ưu âm lượng",
            "📣", "#dc2626"
        )

        for card in [self.card_merge, self.card_voice, self.card_volume,
                     self.card_silence, self.card_social]:
            cards_row.addWidget(card, 1)

        self.panel_processing.content_layout.addLayout(cards_row)

        # Default states
        self.card_merge.switch.setChecked(False)
        self.card_voice.switch.setChecked(False)
        self.card_volume.switch.setChecked(True)
        self.card_silence.switch.setChecked(True)
        self.card_social.switch.setChecked(True)

    def _build_subtitle_section(self):
        # Header: subtitle switch on the right
        sub_header = QWidget()
        sub_header.setStyleSheet("background: transparent; border: none;")
        sub_header_layout = QHBoxLayout(sub_header)
        sub_header_layout.setContentsMargins(0, 0, 0, 0)
        sub_header_layout.setSpacing(8)

        lbl_sub_switch = QLabel("Tạo phụ đề tự động")
        lbl_sub_switch.setObjectName("SubtitleToggleLabel")
        sub_header_layout.addWidget(lbl_sub_switch)

        self.switch_auto_sub = Switch()
        sub_header_layout.addWidget(self.switch_auto_sub)

        self.panel_subtitles = SectionPanel(
            "4. Cấu hình phụ đề",
            right_header_widget=sub_header
        )

        # Content panel (hidden when subtitle OFF)
        self.sub_content_panel = QFrame()
        self.sub_content_panel.setObjectName("SubContentPanel")

        grid_sub = QGridLayout(self.sub_content_panel)
        grid_sub.setContentsMargins(14, 14, 14, 14)
        grid_sub.setSpacing(12)
        grid_sub.setColumnStretch(0, 1)
        grid_sub.setColumnStretch(1, 1)
        grid_sub.setColumnStretch(2, 1)

        self.combo_lang = QComboBox()
        self.combo_lang.addItems([
            "Tự động nhận diện",
            "Tiếng Trung (中文)",
            "Tiếng Anh (English)",
            "Tiếng Việt",
            "Tiếng Nhật (日本語)",
            "Tiếng Hàn (한국어)",
            "Tiếng Nga (Русский)",
            "Tiếng Pháp (Français)",
            "Tiếng Tây Ban Nha"
        ])

        self.combo_model = QComboBox()
        self.combo_model.addItems(["large-v3-turbo", "large-v3", "medium", "small", "base", "tiny"])

        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["1.0", "0.9", "0.8", "0.7"])

        self.combo_batch = QComboBox()
        self.combo_batch.addItems(["1", "4", "8", "16", "24"])
        self.combo_batch.setCurrentText("8")

        self.combo_format = QComboBox()
        self.combo_format.addItems(["horizontal", "vertical"])

        self.combo_lines = QComboBox()
        self.combo_lines.addItems(["1", "2", "3"])

        grid_sub.addWidget(create_labeled_combo("Ngôn ngữ", self.combo_lang), 0, 0)
        grid_sub.addWidget(create_labeled_combo("Mô hình Whisper", self.combo_model), 0, 1)
        grid_sub.addWidget(create_labeled_combo("Tốc độ ASR", self.combo_speed), 0, 2)
        grid_sub.addWidget(create_labeled_combo("Kích thước lô (Batch)", self.combo_batch), 1, 0)
        grid_sub.addWidget(create_labeled_combo("Khung hình video", self.combo_format), 1, 1)
        grid_sub.addWidget(create_labeled_combo("Số dòng tối đa", self.combo_lines), 1, 2)

        self.panel_subtitles.content_layout.addWidget(self.sub_content_panel)

        self.switch_auto_sub.toggled.connect(self.handle_sub_toggle)
        self.handle_sub_toggle(self.switch_auto_sub.isChecked())

    def _build_log_section(self) -> SectionPanel:
        self.btn_clear_log = QPushButton("🗑  Xóa log")
        self.btn_clear_log.setObjectName("btn_clear_log")
        self.btn_clear_log.setCursor(Qt.PointingHandCursor)
        self.btn_clear_log.clicked.connect(self.clear_logs)

        panel = SectionPanel("⚙  Nhật ký xử lý", right_header_widget=self.btn_clear_log)

        self.txt_logs = QTextEdit()
        self.txt_logs.setObjectName("LogConsole")
        self.txt_logs.setReadOnly(True)
        self.txt_logs.setMinimumHeight(180)
        panel.content_layout.addWidget(self.txt_logs)

        return panel

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
        v.addWidget(self.progress_bar)

        # Status + elapsed
        status_row = QHBoxLayout()

        self.lbl_status_label = QLabel("Trạng thái:")
        self.lbl_status_label.setObjectName("ProgressLabel")
        status_row.addWidget(self.lbl_status_label)

        self.lbl_status = QLabel("Sẵn sàng")
        self.lbl_status.setObjectName("ProgressValue")
        status_row.addWidget(self.lbl_status)
        status_row.addStretch()
        v.addLayout(status_row)

        elapsed_row = QHBoxLayout()
        lbl_elapsed_label = QLabel("Thời gian xử lý:")
        lbl_elapsed_label.setObjectName("ProgressLabel")
        elapsed_row.addWidget(lbl_elapsed_label)

        self.lbl_elapsed = QLabel("00:00")
        self.lbl_elapsed.setObjectName("ProgressValueGreen")
        elapsed_row.addWidget(self.lbl_elapsed)
        elapsed_row.addStretch()
        v.addLayout(elapsed_row)

        v.addStretch()

        # Action buttons
        self.btn_start = QPushButton("▶  Bắt đầu xử lý")
        self.btn_start.setObjectName("btn_start")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self.start_processing)
        self.btn_start.setMinimumHeight(44)
        v.addWidget(self.btn_start)

        self.btn_cancel = QPushButton("■  Hủy bỏ")
        self.btn_cancel.setObjectName("btn_cancel")
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.clicked.connect(self.cancel_processing)
        self.btn_cancel.setMinimumHeight(44)
        v.addWidget(self.btn_cancel)

        self.btn_open_folder = QPushButton("📁  Mở thư mục kết quả")
        self.btn_open_folder.setObjectName("btn_open_folder")
        self.btn_open_folder.setCursor(Qt.PointingHandCursor)
        self.btn_open_folder.setEnabled(False)
        self.btn_open_folder.clicked.connect(self.open_output_folder)
        self.btn_open_folder.setMinimumHeight(38)
        v.addWidget(self.btn_open_folder)

        panel.content_layout.addLayout(v)
        return panel

    # ──────────────────────────────────────────────────────────────────────────
    # Stylesheet
    # ──────────────────────────────────────────────────────────────────────────

    def apply_styles(self):
        self.setStyleSheet("""
/* ─── Base ────────────────────────────────────────────── */
QMainWindow, QScrollArea > QWidget > QWidget {
    background-color: #020617;
}
QScrollArea {
    background-color: #020617;
    border: none;
}
QWidget {
    color: #f1f5f9;
    font-family: 'Segoe UI', 'Roboto', sans-serif;
    font-size: 13px;
}

/* ─── Section panels ──────────────────────────────────── */
QFrame#SectionPanel {
    background-color: #0b1425;
    border: 1px solid #1e293b;
    border-radius: 10px;
}

/* ─── Feature cards ───────────────────────────────────── */
QFrame#FeatureCard {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
}
QFrame#FeatureCard:hover {
    border-color: #3b82f6;
}

/* ─── Subtitle content frame ──────────────────────────── */
QFrame#SubContentPanel {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
}

/* ─── Section titles ──────────────────────────────────── */
QLabel#SectionTitle {
    font-weight: 700;
    font-size: 14px;
    color: #3b82f6;
    background: transparent;
    border: none;
}
QLabel#SectionSubtitle {
    color: #64748b;
    font-size: 11px;
    background: transparent;
    border: none;
}

/* ─── Card typography ─────────────────────────────────── */
QLabel#CardTitle {
    font-weight: 700;
    font-size: 13px;
    color: #f1f5f9;
    background: transparent;
    border: none;
}
QLabel#CardDesc {
    color: #94a3b8;
    font-size: 11px;
    background: transparent;
    border: none;
}
QLabel#CardSubLabel {
    color: #94a3b8;
    font-size: 11px;
    background: transparent;
    border: none;
    font-weight: 600;
}

/* ─── Field labels ────────────────────────────────────── */
QLabel#FieldLabel {
    color: #94a3b8;
    font-size: 11px;
    font-weight: 600;
    background: transparent;
    border: none;
}
QLabel#HintLabel {
    color: #475569;
    font-size: 11px;
    background: transparent;
    border: none;
}
QLabel#SubtitleToggleLabel {
    font-size: 13px;
    font-weight: 600;
    color: #f1f5f9;
    background: transparent;
    border: none;
}

/* ─── Progress labels ─────────────────────────────────── */
QLabel#ProgressLabel {
    color: #64748b;
    font-size: 12px;
    background: transparent;
    border: none;
}
QLabel#ProgressValue {
    color: #f1f5f9;
    font-size: 12px;
    font-weight: 600;
    background: transparent;
    border: none;
}
QLabel#ProgressValueGreen {
    color: #10b981;
    font-size: 12px;
    font-weight: 700;
    background: transparent;
    border: none;
}

/* ─── Footer ──────────────────────────────────────────── */
QLabel#FooterLabel {
    color: #334155;
    font-size: 10px;
    background: transparent;
    border: none;
    padding-top: 6px;
}

/* ─── Summary chips ───────────────────────────────────── */
QLabel#SummaryChip {
    background-color: #1e293b;
    color: #94a3b8;
    padding: 5px 12px;
    border-radius: 6px;
    font-size: 11px;
    font-weight: 600;
    border: none;
}

/* ─── Inputs ──────────────────────────────────────────── */
QLineEdit, QComboBox {
    background-color: #1e293b;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 10px;
    color: #f1f5f9;
    min-height: 22px;
}
QLineEdit:focus, QComboBox:focus {
    border-color: #3b82f6;
}
QComboBox::drop-down {
    border: none;
    width: 22px;
    subcontrol-origin: padding;
    subcontrol-position: center right;
}
QComboBox QAbstractItemView {
    background-color: #1e293b;
    border: 1px solid #334155;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    color: #f1f5f9;
    outline: none;
}
QComboBox#SmallCombo {
    font-size: 11px;
    min-width: 140px;
}

/* ─── Buttons ─────────────────────────────────────────── */
QPushButton {
    background-color: #1e293b;
    color: #f1f5f9;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
    font-size: 13px;
}
QPushButton:hover { background-color: #334155; }
QPushButton:pressed { background-color: #0f172a; }
QPushButton:disabled {
    background-color: #0f172a;
    border-color: #1e293b;
    color: #475569;
}

QPushButton#btn_add {
    background-color: #2563eb;
    color: #ffffff;
    border: none;
}
QPushButton#btn_add:hover { background-color: #3b82f6; }
QPushButton#btn_add:pressed { background-color: #1d4ed8; }

QPushButton#btn_remove {
    background-color: #dc2626;
    color: #ffffff;
    border: none;
}
QPushButton#btn_remove:hover { background-color: #ef4444; }
QPushButton#btn_remove:pressed { background-color: #b91c1c; }

QPushButton#btn_start {
    background-color: #059669;
    color: #ffffff;
    border: none;
    font-size: 14px;
    font-weight: 700;
    border-radius: 8px;
}
QPushButton#btn_start:hover { background-color: #10b981; }
QPushButton#btn_start:pressed { background-color: #047857; }

QPushButton#btn_cancel {
    background-color: #dc2626;
    color: #ffffff;
    border: none;
    font-size: 14px;
    font-weight: 700;
    border-radius: 8px;
}
QPushButton#btn_cancel:hover { background-color: #ef4444; }
QPushButton#btn_cancel:pressed { background-color: #b91c1c; }

QPushButton#btn_open_folder {
    background-color: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
    font-size: 12px;
    border-radius: 6px;
}
QPushButton#btn_open_folder:hover { background-color: #334155; color: #f1f5f9; }
QPushButton#btn_open_folder:disabled { color: #334155; border-color: #1e293b; }

QPushButton#btn_neutral {
    background-color: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
    font-size: 12px;
}
QPushButton#btn_neutral:hover { background-color: #334155; color: #f1f5f9; }

QPushButton#btn_clear_log {
    background-color: #1e293b;
    color: #94a3b8;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 500;
}
QPushButton#btn_clear_log:hover { background-color: #334155; color: #f1f5f9; }

/* ─── Table ───────────────────────────────────────────── */
QTableWidget {
    background-color: #020617;
    border: 1px solid #1e293b;
    border-radius: 8px;
    gridline-color: #0f172a;
    color: #f1f5f9;
    selection-background-color: #1e293b;
}
QHeaderView::section {
    background-color: #0f172a;
    color: #64748b;
    padding: 7px;
    border: none;
    border-bottom: 1px solid #1e293b;
    font-weight: 700;
    font-size: 12px;
}
QTableWidget::item {
    padding: 6px;
    border-bottom: 1px solid #0d1829;
}
QTableWidget::item:selected {
    background-color: #1e293b;
    color: #ffffff;
}

/* ─── Progress bar ────────────────────────────────────── */
QProgressBar {
    border: 1px solid #1e293b;
    border-radius: 5px;
    text-align: center;
    background-color: #0f172a;
    color: #ffffff;
    font-weight: 700;
    font-size: 11px;
}
QProgressBar::chunk {
    background-color: #10b981;
    border-radius: 4px;
}

/* ─── Log console ─────────────────────────────────────── */
QTextEdit#LogConsole {
    background-color: #020617;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 10px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 12px;
    color: #34d399;
}

/* ─── Scrollbars ──────────────────────────────────────── */
QScrollBar:vertical {
    border: none;
    background: #020617;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #1e293b;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #334155; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

QScrollBar:horizontal {
    border: none;
    background: #020617;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #1e293b;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover { background: #334155; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
""")

    # ──────────────────────────────────────────────────────────────────────────
    # Slots & Actions
    # ──────────────────────────────────────────────────────────────────────────

    def get_cached_duration(self, path: Path) -> Optional[float]:
        path_str = str(path)
        if path_str in self.duration_cache:
            return self.duration_cache[path_str]
        try:
            dur = get_duration_seconds(path)
            self.duration_cache[path_str] = dur
            return dur
        except Exception:
            return None

    def update_file_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.input_paths_list))

        total_duration = 0.0
        total_size = 0
        duration_available = True

        for idx, path in enumerate(self.input_paths_list):
            stt_item = QTableWidgetItem(f"⋮⋮  {idx + 1}")
            stt_item.setTextAlignment(Qt.AlignCenter)
            stt_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(idx, 0, stt_item)

            name_item = QTableWidgetItem(f"🎵  {path.name}")
            name_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled | Qt.ItemIsDragEnabled)
            name_item.setData(Qt.UserRole, str(path))
            self.table.setItem(idx, 1, name_item)

            dur = self.get_cached_duration(path)
            if dur is not None:
                total_duration += dur
                dur_str = format_duration(dur)
            else:
                dur_str = "--:--"
                duration_available = False
            dur_item = QTableWidgetItem(dur_str)
            dur_item.setTextAlignment(Qt.AlignCenter)
            dur_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(idx, 2, dur_item)

            try:
                sz = path.stat().st_size
                total_size += sz
                sz_str = format_size(sz)
            except Exception:
                sz_str = "N/A"
            sz_item = QTableWidgetItem(sz_str)
            sz_item.setTextAlignment(Qt.AlignCenter)
            sz_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.table.setItem(idx, 3, sz_item)

            btn_del = QPushButton("✕")
            btn_del.setObjectName("btn_delete_row")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setStyleSheet("""
                QPushButton#btn_delete_row {
                    background-color: transparent;
                    color: #475569;
                    border: none;
                    font-size: 14px;
                    font-weight: bold;
                    min-width: 24px;
                    max-width: 24px;
                    min-height: 24px;
                    max-height: 24px;
                }
                QPushButton#btn_delete_row:hover {
                    color: #ef4444;
                    background-color: rgba(239,68,68,0.12);
                    border-radius: 12px;
                }
            """)
            btn_del.clicked.connect(lambda checked=False, r=idx: self.remove_file_at(r))
            self.table.setCellWidget(idx, 4, btn_del)

        self.table.blockSignals(False)

        self.lbl_sum_count.setText(f"📁  Tổng số: {len(self.input_paths_list)} tệp")
        dur_summary = format_duration(total_duration) if duration_available else "N/A"
        self.lbl_sum_duration.setText(f"⏱  Tổng thời lượng: {dur_summary}")
        size_summary = format_size(total_size)
        self.lbl_sum_size.setText(f"💾  Tổng kích thước: {size_summary}")

        self.lbl_summary.setText(
            f"Tổng số file: {len(self.input_paths_list)} | "
            f"Tổng thời lượng: {dur_summary} | "
            f"Tổng kích thước: {size_summary}"
        )

    def remove_file_at(self, index: int):
        if 0 <= index < len(self.input_paths_list):
            self.input_paths_list.pop(index)
            self.update_file_table()

    @Slot()
    def remove_selected(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.input_paths_list):
            self.input_paths_list.pop(row)
            self.update_file_table()

    @Slot(int, int)
    def handle_row_move(self, from_row: int, to_row: int):
        if (0 <= from_row < len(self.input_paths_list)
                and 0 <= to_row < len(self.input_paths_list)):
            item = self.input_paths_list.pop(from_row)
            self.input_paths_list.insert(to_row, item)
            self.update_file_table()
            self.table.selectRow(to_row)

    @Slot()
    def move_up(self):
        row = self.table.currentRow()
        if row > 0:
            self.input_paths_list[row], self.input_paths_list[row - 1] = (
                self.input_paths_list[row - 1], self.input_paths_list[row]
            )
            self.update_file_table()
            self.table.selectRow(row - 1)

    @Slot()
    def move_down(self):
        row = self.table.currentRow()
        if 0 <= row < len(self.input_paths_list) - 1:
            self.input_paths_list[row], self.input_paths_list[row + 1] = (
                self.input_paths_list[row + 1], self.input_paths_list[row]
            )
            self.update_file_table()
            self.table.selectRow(row + 1)

    @Slot()
    def browse_inputs(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Chọn tập tin âm thanh hoặc video",
            "",
            "Audio/Video Files (*.wav *.mp3 *.m4a *.flac *.ogg *.mp4 *.mkv *.avi *.mov);;All Files (*)"
        )
        if files:
            added = 0
            for f in files:
                p = Path(f)
                if p not in self.input_paths_list:
                    self.input_paths_list.append(p)
                    added += 1
            if added > 0:
                self.update_file_table()
                if (self.txt_project_name.text() in ["", "audio_project"]
                        and self.input_paths_list):
                    self.txt_project_name.setText(
                        self.input_paths_list[0].stem.replace(" ", "_")
                    )

    @Slot()
    def browse_output(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu kết quả")
        if dir_path:
            self.txt_output.setText(dir_path)

    @Slot()
    def clear_logs(self):
        self.txt_logs.clear()

    @Slot()
    def update_elapsed_time(self):
        self.elapsed_seconds += 1
        h = self.elapsed_seconds // 3600
        m = (self.elapsed_seconds % 3600) // 60
        s = self.elapsed_seconds % 60
        if h > 0:
            self.lbl_elapsed.setText(f"{h:02d}:{m:02d}:{s:02d}")
        else:
            self.lbl_elapsed.setText(f"{m:02d}:{s:02d}")

    @Slot(bool)
    def handle_sub_toggle(self, checked: bool):
        self.sub_content_panel.setVisible(checked)

    def get_pipeline_options(self) -> PipelineOptions:
        options = PipelineOptions()
        options.merge_first = self.card_merge.switch.isChecked()
        options.enable_voice_cleanup = self.card_voice.switch.isChecked()
        options.enable_volume_leveling = self.card_volume.switch.isChecked()
        options.enable_silence_shortening = self.card_silence.switch.isChecked()
        options.enable_social_optimize = self.card_social.switch.isChecked()

        display_platform = self.card_social.combo_platform.currentText()
        options.social_platform = PLATFORM_MAP.get(display_platform, "general")

        display_format = self.combo_out_format.currentText()
        options.output_format = FORMAT_MAP.get(display_format, "wav")

        options.enable_transcription = self.switch_auto_sub.isChecked()
        options.enable_subtitle_export = self.switch_auto_sub.isChecked()

        if options.enable_transcription:
            display_lang = self.combo_lang.currentText()
            options.language = LANGUAGE_MAP.get(display_lang, None)
            options.whisper_model = self.combo_model.currentText()
            options.asr_audio_speed = float(self.combo_speed.currentText())
            options.batch_size = int(self.combo_batch.currentText())
            options.target_video_format = self.combo_format.currentText()
            options.subtitle_lines = int(self.combo_lines.currentText())

        options.project_name = self.txt_project_name.text().strip()
        return options

    @Slot()
    def start_processing(self):
        if not self.input_paths_list:
            QMessageBox.critical(
                self, "Lỗi cấu hình",
                "Danh sách tệp tin đầu vào trống. Vui lòng bấm 'Thêm tệp'."
            )
            return

        out_dir_str = self.txt_output.text().strip()
        if not out_dir_str:
            QMessageBox.critical(
                self, "Lỗi cấu hình",
                "Chưa chọn thư mục đầu ra. Vui lòng bấm 'Chọn thư mục'."
            )
            return

        proj_name = self.txt_project_name.text().strip()
        if not proj_name:
            QMessageBox.critical(self, "Lỗi cấu hình", "Tên dự án không được để trống.")
            return

        out_dir = Path(out_dir_str)
        options = self.get_pipeline_options()

        self.txt_logs.clear()
        self.txt_logs.append("Khởi động tiến trình xử lý...")
        self.txt_logs.append(f"Tập tin: {len(self.input_paths_list)} tệp.")
        self.txt_logs.append(f"Thư mục lưu: {out_dir.as_posix()}")

        self.set_ui_processing_state(True)
        self.progress_bar.setValue(0)

        self.elapsed_seconds = 0
        self.lbl_elapsed.setText("00:00")
        self.timer.start(1000)

        is_batch_run = (not options.merge_first) and len(self.input_paths_list) > 1

        self.worker = PipelineWorker(self.input_paths_list, out_dir, options, is_batch_run)
        self.worker.status_received.connect(self.handle_worker_status)
        self.worker.finished_success.connect(self.handle_worker_success)
        self.worker.finished_error.connect(self.handle_worker_error)
        self.worker.start()

    def set_ui_processing_state(self, processing: bool):
        self.btn_start.setEnabled(not processing)
        self.btn_cancel.setEnabled(processing)
        self.btn_open_folder.setEnabled(False)

        self.btn_add_files.setEnabled(not processing)
        self.btn_remove_selected.setEnabled(not processing)
        self.btn_move_up.setEnabled(not processing)
        self.btn_move_down.setEnabled(not processing)
        self.table.setEnabled(not processing)

        self.txt_output.setEnabled(not processing)
        self.btn_browse_output.setEnabled(not processing)
        self.txt_project_name.setEnabled(not processing)
        self.combo_out_format.setEnabled(not processing)

        self.card_merge.switch.setEnabled(not processing)
        self.card_voice.switch.setEnabled(not processing)
        self.card_volume.switch.setEnabled(not processing)
        self.card_silence.switch.setEnabled(not processing)
        self.card_social.switch.setEnabled(not processing)
        self.card_social.combo_platform.setEnabled(not processing)

        self.switch_auto_sub.setEnabled(not processing)
        self.combo_lang.setEnabled(not processing)
        self.combo_model.setEnabled(not processing)
        self.combo_speed.setEnabled(not processing)
        self.combo_batch.setEnabled(not processing)
        self.combo_format.setEnabled(not processing)
        self.combo_lines.setEnabled(not processing)

    @Slot(str)
    def handle_worker_status(self, msg: str):
        self.txt_logs.append(f"[TIẾN TRÌNH] {msg}")
        scrollbar = self.txt_logs.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.lbl_status.setText(msg)

        msg_lower = msg.lower()
        if "validating" in msg_lower:
            self.progress_bar.setValue(5)
        elif "merg" in msg_lower:
            self.progress_bar.setValue(15)
        elif "clean" in msg_lower:
            self.progress_bar.setValue(30)
        elif "level" in msg_lower or "cân bằng" in msg_lower:
            self.progress_bar.setValue(50)
        elif "silence" in msg_lower or "khoảng lặng" in msg_lower:
            self.progress_bar.setValue(70)
        elif "social" in msg_lower or "tối ưu" in msg_lower:
            self.progress_bar.setValue(80)
        elif "transcrib" in msg_lower or "speech-to-text" in msg_lower:
            self.progress_bar.setValue(85)
        elif "subtitles" in msg_lower or "phụ đề" in msg_lower:
            self.progress_bar.setValue(90)
        elif "metadata" in msg_lower:
            self.progress_bar.setValue(95)
        elif "completed" in msg_lower or "thành công" in msg_lower:
            self.progress_bar.setValue(100)

    @Slot(object)
    def handle_worker_success(self, result):
        self.set_ui_processing_state(False)
        self.timer.stop()
        self.progress_bar.setValue(100)
        self.lbl_status.setText("Hoàn thành!")
        self.txt_logs.append("\n[THÀNH CÔNG] Tiến trình hoàn thành xuất sắc!")

        if isinstance(result, list):
            if result:
                self.last_output_dir = result[0].output_dir
        else:
            self.last_output_dir = result.output_dir

        if self.last_output_dir:
            self.btn_open_folder.setEnabled(True)

        QMessageBox.information(self, "Thành công", "Tiến trình xử lý hoàn tất thành công!")

    @Slot(str)
    def handle_worker_error(self, err_msg: str):
        self.set_ui_processing_state(False)
        self.timer.stop()
        self.progress_bar.setValue(0)

        if any(w in err_msg.lower() for w in ["cancelled", "dừng", "hủy"]):
            self.lbl_status.setText("Đã dừng tiến trình.")
            self.txt_logs.append("\n[ĐÃ HỦY] Tiến trình đã được dừng.")
            QMessageBox.information(self, "Đã hủy", "Đã dừng tiến trình xử lý.")
        else:
            self.lbl_status.setText("Gặp lỗi trong quá trình xử lý.")
            self.txt_logs.append(f"\n[LỖI] Xảy ra sự cố: {err_msg}")
            QMessageBox.critical(self, "Lỗi", f"Xử lý thất bại:\n{err_msg}")

    @Slot()
    def cancel_processing(self):
        if self.worker and self.worker.isRunning():
            self.txt_logs.append("\n[HỦY BỎ] Đang yêu cầu hủy...")
            self.worker.cancel()
            self.btn_cancel.setEnabled(False)

    @Slot()
    def open_output_folder(self):
        target_dir = self.last_output_dir
        if not target_dir or not os.path.exists(target_dir):
            target_dir = self.txt_output.text().strip()

        if target_dir and os.path.exists(target_dir):
            try:
                if sys.platform == "win32":
                    os.startfile(target_dir)
                elif sys.platform == "darwin":
                    subprocess.run(["open", target_dir])
                else:
                    subprocess.run(["xdg-open", target_dir])
            except Exception as e:
                QMessageBox.warning(self, "Cảnh báo", f"Không thể mở thư mục: {e}")
        else:
            QMessageBox.warning(self, "Cảnh báo", "Thư mục không tồn tại hoặc chưa được chọn.")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "Xác nhận thoát",
                "Tiến trình đang chạy. Bạn có chắc chắn muốn hủy và thoát ứng dụng?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.worker.cancel()
                self.worker.wait()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

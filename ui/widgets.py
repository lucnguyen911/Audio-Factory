"""
ui/widgets.py
──────────────────────────────────────────────────────────────────────────────
Reusable custom widgets cho Audio Factory.
Pass 1 – Foundation Shell.

Các widget ở đây là pure-UI, không kết nối backend.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import (
    Qt, QSize, QPoint, QRect, QPropertyAnimation, QEasingCurve, Property,
    Signal, QModelIndex, QEvent,
)
from PySide6.QtGui import QPainter, QColor, QFont, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTableWidget,
    QVBoxLayout,
    QWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
)

from ui.theme import ACCENT_SWITCH


# ─────────────────────────────────────────────────────────────────────────────
# Switch (toggle)
# ─────────────────────────────────────────────────────────────────────────────

class Switch(QAbstractButton):
    """Animated sliding toggle switch matching the mockup design."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._margin: int = 3
        self._thumb_position: float = float(self._margin)
        self._animation = QPropertyAnimation(self, b"thumb_position", self)
        self._animation.setDuration(220)
        self._animation.setEasingCurve(QEasingCurve.InOutQuad)

    # ── Qt property (animatable) ──────────────────────────────────────────

    @Property(float)
    def thumb_position(self) -> float:
        return self._thumb_position

    @thumb_position.setter
    def thumb_position(self, pos: float) -> None:
        self._thumb_position = pos
        self.update()

    # ── Size ─────────────────────────────────────────────────────────────

    def sizeHint(self) -> QSize:
        return QSize(44, 22)

    # ── State changes ─────────────────────────────────────────────────────

    def nextCheckState(self) -> None:
        self.setChecked(not self.isChecked())

    def checkStateSet(self) -> None:
        w = self.width() if self.width() > 0 else 44
        h = self.height() if self.height() > 0 else 22
        end_val = float(w - h + self._margin) if self.isChecked() else float(self._margin)
        self._animation.stop()
        # setStartValue rõ ràng → animation luôn bắt đầu từ vị trí hiện tại
        self._animation.setStartValue(self._thumb_position)
        self._animation.setEndValue(end_val)
        self._animation.start()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        # Chỉ snap position khi animation đã DỪNG — tránh override thumb đang chạy
        from PySide6.QtCore import QAbstractAnimation
        if self._animation.state() != QAbstractAnimation.State.Running:
            w, h = self.width(), self.height()
            self._thumb_position = float(w - h + self._margin) if self.isChecked() else float(self._margin)
        self.update()

    # ── Painting ──────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:  # type: ignore[override]
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if not self.isEnabled():
            bg = QColor("#1e293b")
        elif self.isChecked():
            bg = QColor(ACCENT_SWITCH)
        else:
            bg = QColor("#2a3e55")

        painter.setBrush(bg)
        painter.setPen(Qt.NoPen)

        rect = self.rect()
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)

        # Thumb
        thumb_color = QColor("#ffffff") if self.isEnabled() else QColor("#4a6070")
        painter.setBrush(thumb_color)
        h = rect.height() - 2 * self._margin
        painter.drawEllipse(
            QPoint(int(self._thumb_position + h / 2), int(self._margin + h / 2)),
            int(h / 2),
            int(h / 2),
        )


# ─────────────────────────────────────────────────────────────────────────────
# IconBadge – coloured square-rounded icon block
# ─────────────────────────────────────────────────────────────────────────────

class IconBadge(QLabel):
    """Square-rounded icon block used inside FeatureCard."""

    def __init__(self, char: str, bg_color: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(char, parent)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(38, 38)
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: #ffffff;
                font-size: 17px;
                border-radius: 9px;
                border: none;
            }}
        """)


# ─────────────────────────────────────────────────────────────────────────────
# FeatureCard – single-row horizontal card
# ─────────────────────────────────────────────────────────────────────────────

class FeatureCard(QFrame):
    """Single-row card: [icon] [title] [stretch] [toggle]."""

    def __init__(
        self,
        title: str,
        icon_char: str,
        icon_bg: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("FeatureCard")
        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)   # 38px badge + 7+7 = 52px → khớp setFixedHeight(52)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignVCenter)

        self.badge = IconBadge(icon_char, icon_bg)
        layout.addWidget(self.badge, 0, Qt.AlignVCenter)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("CardTitle")
        self.lbl_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.lbl_title, 0, Qt.AlignVCenter)

        layout.addStretch(1)  # đẩy toggle sang phải

        self.switch = QCheckBox()
        self.switch.setObjectName("ToggleSwitch")
        self.switch.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.switch, 0, Qt.AlignVCenter)


# ─────────────────────────────────────────────────────────────────────────────
# SocialOptimizeCard – card with platform dropdown
# ─────────────────────────────────────────────────────────────────────────────

class SocialOptimizeCard(QFrame):
    """Single-row card with inline platform combo: [Icon][Title][stretch][lbl·combo][Toggle]."""

    def __init__(
        self,
        title: str,
        icon_char: str,
        icon_bg: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("FeatureCard")
        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)  # Fixed: không phình dọc

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignVCenter)

        # [Icon]
        self.badge = IconBadge(icon_char, icon_bg)
        layout.addWidget(self.badge, 0, Qt.AlignVCenter)

        # [Title]
        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("CardTitle")
        self.lbl_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.lbl_title, 0, Qt.AlignVCenter)

        # [stretch] — đẩy platform section + toggle về phải
        layout.addStretch(1)

        # [Platform label] (inline, ẩn khi OFF)
        self.lbl_platform = QLabel("·")
        self.lbl_platform.setObjectName("CardSubLabel")
        self.lbl_platform.setVisible(False)
        layout.addWidget(self.lbl_platform, 0, Qt.AlignVCenter)

        # [SmallCombo] (inline, ẩn khi OFF)
        self.combo_platform = QComboBox()
        self.combo_platform.setObjectName("SmallCombo")
        self.combo_platform.setFixedHeight(24)
        self.combo_platform.setVisible(False)
        self.combo_platform.addItem("YouTube / Facebook / X", "youtube_facebook_x")
        self.combo_platform.addItem("TikTok / Instagram Reels", "tiktok_instagram")
        self.combo_platform.addItem("Podcast / Voice Clean", "podcast_voice")
        layout.addWidget(self.combo_platform, 0, Qt.AlignVCenter)

        # [Toggle]
        self.switch = QCheckBox()
        self.switch.setObjectName("ToggleSwitch")
        self.switch.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.switch, 0, Qt.AlignVCenter)

        self.switch.toggled.connect(self._on_switch)
        self._on_switch(self.switch.isChecked())

    def _on_switch(self, checked: bool) -> None:
        self.lbl_platform.setVisible(checked)
        self.combo_platform.setVisible(checked)


class VoiceCleanerCard(QFrame):
    """Single-row card with inline voice cleaner preset combo: [Icon][Title][stretch][lbl·combo][Toggle]."""

    def __init__(
        self,
        title: str,
        icon_char: str,
        icon_bg: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("FeatureCard")
        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignVCenter)

        # [Icon]
        self.badge = IconBadge(icon_char, icon_bg)
        layout.addWidget(self.badge, 0, Qt.AlignVCenter)

        # [Title]
        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("CardTitle")
        self.lbl_title.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.lbl_title, 0, Qt.AlignVCenter)

        # [stretch]
        layout.addStretch(1)

        # [Toggle]
        self.switch = QCheckBox()
        self.switch.setObjectName("ToggleSwitch")
        self.switch.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.switch, 0, Qt.AlignVCenter)


# ─────────────────────────────────────────────────────────────────────────────
# SectionPanel – rounded panel with header + content area
# ─────────────────────────────────────────────────────────────────────────────

class SectionPanel(QFrame):
    """
    Rounded dark panel with an optional right-side widget in the header.

    Usage::

        panel = SectionPanel("1. Cấu hình đầu vào", "Subtitle text")
        panel.content_layout.addWidget(some_widget)
    """

    def __init__(
        self,
        title_text: str,
        subtitle_text: str = "",
        right_header_widget: Optional[QWidget] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("SectionPanel")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(16, 14, 16, 14)
        self.main_layout.setSpacing(10)

        # ── Header row ────────────────────────────────────────────────────
        header = QWidget()
        header.setStyleSheet("background: transparent; border: none;")
        header_layout = QHBoxLayout(header)
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

        if right_header_widget is not None:
            header_layout.addWidget(right_header_widget, 0, Qt.AlignVCenter)

        self.main_layout.addWidget(header)

        # ── Content area ──────────────────────────────────────────────────
        self.content_widget = QWidget()
        self.content_widget.setStyleSheet("background: transparent; border: none;")
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(8)

        self.main_layout.addWidget(self.content_widget)


# ─────────────────────────────────────────────────────────────────────────────
# DragDropTable
# ─────────────────────────────────────────────────────────────────────────────

class DragDropTable(QTableWidget):
    """QTableWidget with internal row-drag and external URL-drop support.

    Hai loại sự kiện khác nhau:
    - order_changed  : kéo hàng nội bộ (reorder)
    - files_dropped  : thả file từ OS vào bất kỳ điểm nào trong bảng

    Lý do cần files_dropped riêng: khi dragEnterEvent đã gọi
    acceptProposedAction(), Qt coi widget này là drop target dứt điểm.
    event.ignore() trong dropEvent sẽ không bubble lên DropZoneFrame cha
    — file bị nuốt im lặng. Signal này giải quyết triệt để.
    """

    order_changed: Signal = Signal(int, int)
    files_dropped: Signal = Signal(list)   # List[Path] – trục tiếp từ bảng

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        # The file list is display-only.  Selecting a row must not open Qt's
        # inline editor around the file name.
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setDragDropOverwriteMode(False)
        # Viewport phải nhận drops độc lập – mới bắt được thả vào vùng trống giữa bảng
        self.viewport().setAcceptDrops(True)

    def dragEnterEvent(self, event):  # type: ignore[override]
        if event.source() is self or event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):  # type: ignore[override]
        if event.source() is self or event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)

    def dropEvent(self, event):  # type: ignore[override]
        if event.source() is self:
            # Kéo hàng nội bộ (reorder)
            from_row = self.currentRow()
            to_row = self.rowAt(event.position().toPoint().y())
            if to_row == -1:
                to_row = self.rowCount() - 1
            if from_row != to_row and from_row != -1 and to_row != -1:
                self.order_changed.emit(from_row, to_row)
                event.accept()
            else:
                event.ignore()
        elif event.mimeData().hasUrls():
            # Thả file từ OS vào bảng: trích xuất path và emit signal
            # (KHÔNG dùng event.ignore() vì Qt không bubble sau acceptProposedAction)
            paths = [
                Path(url.toLocalFile())
                for url in event.mimeData().urls()
                if url.isLocalFile()
                and Path(url.toLocalFile()).suffix.lower() in _SUPPORTED_EXTS
            ]
            if paths:
                self.files_dropped.emit(paths)
                event.accept()
            else:
                event.ignore()
        else:
            super().dropEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# DropZoneFrame – OS-level file drag-and-drop wrapper
# ─────────────────────────────────────────────────────────────────────────────

_SUPPORTED_EXTS = {
    ".wav", ".mp3", ".m4a", ".flac", ".ogg",
    ".mp4", ".mkv", ".avi", ".mov",
}


class DropZoneFrame(QFrame):
    """Wraps the file table; emits *files_dropped(list[Path])* on OS file drop.

    Ngoài việc xử lý drop trực tiếp trên chính mình, DropZoneFrame còn
    cài eventFilter lên viewport() của bảng con (được đăng ký qua
    install_on_viewport) — đảm bảo viền nét đứt hiện ở MỌI pixel trong lòng
    bảng, không chỉ vùng header của DropZoneFrame nữm ngoài bảng.
    """

    files_dropped: Signal = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZoneFrame")
        self.setAcceptDrops(True)
        self._highlighting = False

    # ── Cài event filter lên viewport của bảng con ──────────────────────

    def install_on_viewport(self, table: QWidget) -> None:
        """Cài eventFilter lên viewport() của DragDropTable.

        Gọi sau khi table đã được tạo và add vào layout.
        Kết quả: mọi drag event trên viewport đều đi qua eventFilter
        của DropZoneFrame trước — cho phép điều khiển highlight.
        """
        table.viewport().installEventFilter(self)

    def eventFilter(self, source: QWidget, event: QEvent) -> bool:  # type: ignore[override]
        """Bắt drag events từ viewport của bảng con để quản lý highlight."""
        etype = event.type()
        if etype == QEvent.Type.DragEnter:
            if event.mimeData().hasUrls() and self._media_paths(event.mimeData().urls()):
                self._set_highlight(True)
        elif etype == QEvent.Type.DragLeave:
            self._set_highlight(False)
        elif etype in (QEvent.Type.Drop, ):
            self._set_highlight(False)
        # Trả False — không nuốt event, để DragDropTable tiếp tục xử lý bình thường
        return False

    # ── Drag events trực tiếp trên DropZoneFrame (vùng ngoài bảng) ────

    def dragEnterEvent(self, event):  # type: ignore[override]
        if event.mimeData().hasUrls():
            if self._media_paths(event.mimeData().urls()):
                self._set_highlight(True)
                event.acceptProposedAction()
                return
        super().dragEnterEvent(event)

    def dragLeaveEvent(self, event):  # type: ignore[override]
        self._set_highlight(False)
        super().dragLeaveEvent(event)

    def dragMoveEvent(self, event):  # type: ignore[override]
        if event.mimeData().hasUrls():
            if self._media_paths(event.mimeData().urls()):
                event.acceptProposedAction()
                return
        super().dragMoveEvent(event)

    def dropEvent(self, event):  # type: ignore[override]
        self._set_highlight(False)
        if event.mimeData().hasUrls():
            paths = self._media_paths(event.mimeData().urls())
            if paths:
                self.files_dropped.emit(paths)
                event.acceptProposedAction()
                return
        super().dropEvent(event)

    # ── helpers ──────────────────────────────────────────────────────────

    def _media_paths(self, urls: list) -> List[Path]:
        result = []
        for url in urls:
            if url.isLocalFile():
                p = Path(url.toLocalFile())
                if p.suffix.lower() in _SUPPORTED_EXTS:
                    result.append(p)
        return result

    def _set_highlight(self, active: bool) -> None:
        if active == self._highlighting:
            return
        self._highlighting = active
        if active:
            self.setStyleSheet(
                "QFrame#DropZoneFrame { border: 2px dashed #3b82f6;"
                " border-radius: 10px; background-color: rgba(59,130,246,0.06); }"
            )
        else:
            self.setStyleSheet("")


# ─────────────────────────────────────────────────────────────────────────────
# Helper: labeled combo widget
# ─────────────────────────────────────────────────────────────────────────────

def create_labeled_combo(label_text: str, combo_box: QComboBox) -> QWidget:
    """Return a QWidget containing a FieldLabel above the given QComboBox.

    QUAN TRỌNG: Không dùng setStyleSheet() trực tiếp trên widget container,
    vì Qt sẽ tạo style context mới – điều này cắt đứt QSS descendant chain
    từ QFrame#subtitle_settings_card xuống QComboBox bên trong.
    Thay vào đó dùng objectName để CSS scope không bị gián đoạn.
    """
    w = QWidget()
    w.setObjectName("LabeledComboContainer")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(4)
    lbl = QLabel(label_text)
    lbl.setObjectName("FieldLabel")
    lay.addWidget(lbl)
    lay.addWidget(combo_box)
    return w


# ─────────────────────────────────────────────────────────────────────────────
# ComboBoxCheckmarkDelegate
# ─────────────────────────────────────────────────────────────────────────────

class ComboBoxCheckmarkDelegate(QStyledItemDelegate):
    """
    Hiển thị dấu tick (✓) bên phải của item đang được chọn trong dropdown menu.
    Theo đặc tả Bước 2: dùng drawText để vẽ ký tự ✓ màu xanh tại lề phải
    sau khi paint standard item.
    """

    def __init__(self, combo: QComboBox, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.combo = combo

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex) -> None:
        # Bước 1: Vẽ nền/chữ chuẩn (bảo toàn hover/selection của QSS)
        super().paint(painter, option, index)

        # Bước 2: Nếu đây là item đang được chọn trong combo box
        if index.row() == self.combo.currentIndex():
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)

            # Màu xanh accent #3b82f6 cho dấu tick
            pen = QPen(QColor("#3b82f6"))
            pen.setWidthF(1.5)
            painter.setPen(pen)

            tick_font = painter.font()
            tick_font.setBold(True)
            # KHÔNG thay đổi point size / pixel size để tránh lỗi 'QFont::setPointSize: Point size <= 0'
            # khi QSS đặt font bằng pixel size, pointSize() = -1 → bất kỳ phép tính nào cũng lỗi.
            painter.setFont(tick_font)

            # Vẽ ký tự ✓ sát lề phải (trong vùng padding 30px đã đặt trong QSS)
            rect = option.rect
            tick_rect = QRect(rect.right() - 28, rect.top(), 22, rect.height())
            painter.drawText(tick_rect, Qt.AlignVCenter | Qt.AlignHCenter, "✓")

            painter.restore()

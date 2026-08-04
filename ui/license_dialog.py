"""
ui/license_dialog.py
──────────────────────────────────────────────────────────────────────────────
Giao diện Dialog kích hoạt bản quyền — Premium Dark Theme.
Tác giả: Nguyễn Văn Lực (AUDIO FACTORY PREMIUM SUITE)
"""

import sys
from pathlib import Path
from PySide6.QtCore import Qt, QSize, QThread, QTimer, Signal
from PySide6.QtGui import QIcon, QPixmap, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QWidget, QApplication
)

from ui.theme import (
    BG_APP, BG_PANEL, BG_FIELD, BORDER_PANEL, BORDER_FIELD,
    BORDER_FOCUS, TEXT_PRIMARY, TEXT_MUTED, TEXT_DIM,
    ACCENT_SWITCH, ACCENT_RED
)
from core.security import verify_license_online, save_local_license, get_hwid

class LicenseVerifyWorker(QThread):
    finished = Signal(bool, str)

    def __init__(self, key: str, hwid: str) -> None:
        super().__init__()
        self.key = key
        self.hwid = hwid

    def run(self) -> None:
        try:
            is_valid, msg = verify_license_online(self.key, self.hwid)
            self.finished.emit(is_valid, msg)
        except Exception as e:
            self.finished.emit(False, str(e))

class LicenseDialog(QDialog):
    """
    Cửa sổ Dialog yêu cầu nhập và xác thực License Key bản quyền qua Supabase.
    """
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Kích hoạt Bản quyền - Audio Factory")
        self.resize(480, 280)
        self.setMinimumSize(480, 280)
        self.setMaximumSize(480, 280)
        
        # Thiết lập các Window Flags (Modal, không có nút phóng to/thu nhỏ)
        self.setWindowFlags(Qt.Dialog | Qt.CustomizeWindowHint | Qt.WindowTitleHint | Qt.WindowCloseButtonHint)
        self.setModal(True)
        
        # Nạp logo cho cửa sổ
        logo_path = Path(__file__).parent.parent / "assets" / "logo.png"
        if logo_path.exists():
            self.setWindowIcon(QIcon(str(logo_path)))
            
        self.hwid = get_hwid()
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(f"QDialog {{ background-color: {BG_APP}; }}")
        # Layout tổng thể của Dialog
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Panel chứa thông tin
        container = QFrame()
        container.setObjectName("LicenseContainer")
        container.setStyleSheet(f"""
            QFrame#LicenseContainer {{
                background-color: {BG_PANEL};
                border: 1px solid {BORDER_PANEL};
                border-radius: 12px;
            }}
        """)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(15, 15, 15, 15)
        container_layout.setSpacing(12)
        
        # Tiêu đề Header thương hiệu Nguyễn Văn Lực
        header_layout = QHBoxLayout()
        header_layout.setSpacing(10)
        
        self.logo_label = QLabel()
        self.logo_label.setFixedSize(36, 36)
        logo_path = Path(__file__).parent.parent / "assets" / "logo.png"
        if logo_path.exists():
            self.logo_label.setPixmap(QPixmap(str(logo_path)).scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.logo_label.setText("🎵")
            self.logo_label.setStyleSheet("font-size: 24px;")
        header_layout.addWidget(self.logo_label)
        
        title_info_layout = QVBoxLayout()
        title_info_layout.setSpacing(2)
        
        app_title = QLabel("AUDIO FACTORY PREMIUM")
        app_title.setStyleSheet(f"""
            font-size: 14px;
            font-weight: 800;
            color: {TEXT_PRIMARY};
            font-family: 'Segoe UI', sans-serif;
            letter-spacing: 1px;
        """)
        
        author_title = QLabel("Hệ thống bảo mật bản quyền • Lực Nguyễn")
        author_title.setStyleSheet(f"font-size: 10px; color: {TEXT_DIM};")
        
        title_info_layout.addWidget(app_title)
        title_info_layout.addWidget(author_title)
        header_layout.addLayout(title_info_layout)
        header_layout.addStretch()
        container_layout.addLayout(header_layout)
        
        # Dòng hướng dẫn nhập Key
        instruction = QLabel("Vui lòng nhập License Key kích hoạt phần mềm:")
        instruction.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; font-weight: 500;")
        container_layout.addWidget(instruction)
        
        # Ô nhập Key (LineEdit)
        self.key_input = QLineEdit()
        self.key_input.setPlaceholderText("AF-XXXX-XXXX-XXXX-XXXX")
        self.key_input.setStyleSheet(f"""
            QLineEdit {{
                background-color: {BG_FIELD};
                border: 1px solid {BORDER_FIELD};
                border-radius: 6px;
                padding: 8px 10px;
                color: {TEXT_PRIMARY};
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {BORDER_FOCUS};
            }}
        """)
        container_layout.addWidget(self.key_input)
        
        # Nhãn hiển thị trạng thái (Lỗi hiển thị màu đỏ, thành công hiển thị màu xanh)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet("font-size: 11px; font-weight: 500;")
        container_layout.addWidget(self.status_label)
        
        # Khung chứa nút kích hoạt & nút thoát
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        self.btn_exit = QPushButton("Thoát")
        self.btn_exit.setCursor(Qt.PointingHandCursor)
        self.btn_exit.setStyleSheet(f"""
            QPushButton {{
                background-color: #e2e8f0;
                color: #1e293b;
                border: 1px solid #cbd5e1;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: #cbd5e1;
                color: #0f172a;
            }}
        """)
        self.btn_exit.clicked.connect(self.reject)
        
        self.btn_activate = QPushButton("Kích hoạt ngay")
        self.btn_activate.setCursor(Qt.PointingHandCursor)
        self.btn_activate.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {ACCENT_SWITCH}, stop:1 #059669);
                color: #ffffff;
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #059669, stop:1 #047857);
            }}
            QPushButton:disabled {{
                background: #e2e8f0;
                color: #94a3b8;
            }}
        """)
        self.btn_activate.clicked.connect(self.on_activate_clicked)
        
        button_layout.addWidget(self.btn_exit)
        button_layout.addStretch()
        button_layout.addWidget(self.btn_activate)
        container_layout.addLayout(button_layout)
        
        layout.addWidget(container)

    def on_activate_clicked(self) -> None:
        """
        Xử lý sự kiện bấm nút Kích hoạt.
        """
        key = self.key_input.text().strip()
        if not key:
            self.status_label.setText("Vui lòng nhập License Key.")
            self.status_label.setStyleSheet(f"color: {ACCENT_RED};")
            return
            
        # Cập nhật trạng thái chờ xử lý trên giao diện
        self.btn_activate.setEnabled(False)
        self.btn_exit.setEnabled(False)
        self.status_label.setText("Đang kiểm tra kết nối và bản quyền...")
        self.status_label.setStyleSheet(f"color: {TEXT_DIM};")
        
        # Khởi chạy Worker thread
        self.worker = LicenseVerifyWorker(key, self.hwid)
        self.worker.finished.connect(lambda is_valid, msg: self.on_verification_finished(key, is_valid, msg))
        self.worker.start()

    def on_verification_finished(self, key: str, is_valid: bool, msg: str) -> None:
        if is_valid:
            # Lưu License cục bộ nếu thành công (truyền trạng thái thành công)
            save_local_license(key, server_status="ACTIVATED")
            self.status_label.setText("Kích hoạt bản quyền thành công!")
            self.status_label.setStyleSheet(f"color: {ACCENT_SWITCH};")
            
            # Đợi 1 giây để người dùng đọc thông tin thành công trước khi đóng
            QTimer.singleShot(1000, self.accept)
        else:
            self.status_label.setText(msg)
            self.status_label.setStyleSheet(f"color: {ACCENT_RED};")
            self.btn_activate.setEnabled(True)
            self.btn_exit.setEnabled(True)

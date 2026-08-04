import os
import subprocess
import sys

try:
    import asyncio
    import asyncio.base_events
except ImportError:
    pass

if sys.platform.startswith("win"):
    _original_popen = subprocess.Popen

    def _hidden_popen(*args, **kwargs):
        kwargs["creationflags"] = (
            kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        )
        return _original_popen(*args, **kwargs)

    subprocess.Popen = _hidden_popen

if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception as exc:
        print(f"Warning: DPI setup failed: {type(exc).__name__}", file=sys.stderr)

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from core.security import check_license_on_startup
from core.updater import check_and_clear_pending_update
from ui.license_dialog import LicenseDialog
from ui.main_window import MainWindow
from ui.theme import APP_STYLESHEET


def main() -> None:
    # Pending verification is local and must run before the startup flow.
    pending = check_and_clear_pending_update()
    if pending is not None:
        state = "success" if pending["success"] else "failed"
        print(
            f"[UPDATER] Previous update {state}: "
            f"{pending['from_version']} -> {pending['to_version']}",
            file=sys.stderr,
        )

    QApplication.setAttribute(Qt.AA_ShareOpenGLContexts, True)
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)

    # License verification precedes update checking.
    valid, _ = check_license_on_startup()
    if not valid:
        dialog = LicenseDialog()
        if dialog.exec() != LicenseDialog.Accepted:
            sys.exit(0)

    # Never self-update a source/dev run.
    if getattr(sys, "frozen", False):
        from core.updater import run_update_check

        if run_update_check():
            sys.exit(0)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

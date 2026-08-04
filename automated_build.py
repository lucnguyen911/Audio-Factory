"""Fail-closed commercial build: PyArmor -> PyInstaller onedir -> Inno Setup."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from version import APP_NAME, APP_VERSION

ROOT = Path(__file__).resolve().parent
DIST_DIR = ROOT / "dist"
OBF_DIR = ROOT / "obfuscated_dist"
SENSITIVE_OUTPUTS = (
    "core/security.py",
    "core/license_client.py",
    "core/device_identity.py",
    "core/dpapi_storage.py",
    "core/updater.py",
    "ui/license_dialog.py",
    "version.py",
)


def _run(command: list[str]) -> bool:
    print(" ".join(command))
    return subprocess.run(command, cwd=ROOT).returncode == 0


def clean() -> None:
    for name in ("build", "dist", "obfuscated_dist"):
        path = (ROOT / name).resolve()
        if path.parent != ROOT:
            raise RuntimeError(f"Unsafe build path: {path}")
        if path.exists():
            shutil.rmtree(path)


def obfuscate() -> bool:
    """No plaintext fallback is allowed for protected modules."""
    cmd = ["pyarmor", "gen", "-O", str(OBF_DIR)]
    cmd.extend(SENSITIVE_OUTPUTS)
    if not _run(cmd):
        return False
    
    # Restore directory structure
    for name in SENSITIVE_OUTPUTS:
        src = OBF_DIR / Path(name).name
        dst = OBF_DIR / name
        if src.is_file() and src != dst:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(src, dst)
    missing = [name for name in SENSITIVE_OUTPUTS if not (OBF_DIR / name).is_file()]
    if missing:
        print("Protected output missing:", ", ".join(missing))
        return False
    return True


def build_onedir() -> bool:
    if not _run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "Audio Factory.spec",
        ]
    ):
        return False
    return (DIST_DIR / APP_NAME / f"{APP_NAME}.exe").is_file()


def _find_iscc() -> str | None:
    candidates = (
        shutil.which("iscc"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        os.path.expanduser(r"~\AppData\Local\Programs\Inno Setup 6\ISCC.exe"),
    )
    return next((str(item) for item in candidates if item and Path(item).is_file()), None)


def sign_if_configured(path: Path) -> bool:
    """Use a certificate-store thumbprint; private keys never enter source."""
    thumbprint = os.environ.get("AUDIO_FACTORY_SIGN_CERT_SHA1", "").replace(" ", "")
    if not thumbprint:
        print(f"Authenticode not configured; leaving unsigned: {path.name}")
        return True
    signtool = shutil.which("signtool")
    if not signtool:
        print("AUDIO_FACTORY_SIGN_CERT_SHA1 is set but signtool was not found.")
        return False
    timestamp_url = os.environ.get(
        "AUDIO_FACTORY_TIMESTAMP_URL", "http://timestamp.digicert.com"
    )
    return _run(
        [
            signtool,
            "sign",
            "/sha1",
            thumbprint,
            "/fd",
            "SHA256",
            "/tr",
            timestamp_url,
            "/td",
            "SHA256",
            str(path),
        ]
    )


def build_installer() -> bool:
    iscc = _find_iscc()
    if not iscc:
        print("Inno Setup 6 was not found. Build stopped; no ZIP/patch fallback.")
        return False
    if not _run(
        [iscc, f"/DMyAppVersion={APP_VERSION}", "installer_config.iss"]
    ):
        return False
    installer = DIST_DIR / f"Audio_Factory_Premium_Setup_v{APP_VERSION}.exe"
    if not installer.is_file():
        print(f"Expected installer was not created: {installer}")
        return False
    if not sign_if_configured(installer):
        return False
    digest = __import__("hashlib").sha256()
    with open(installer, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    print(f"Installer: {installer}")
    print(f"file_size={installer.stat().st_size}")
    print(f"sha256={digest.hexdigest()}")
    return True


def main() -> int:
    clean()
    if not obfuscate():
        print("Build stopped: PyArmor protection failed.")
        return 1
    if not build_onedir():
        print("Build stopped: PyInstaller onedir failed.")
        return 1
    if not sign_if_configured(DIST_DIR / APP_NAME / f"{APP_NAME}.exe"):
        print("Build stopped: application signing failed.")
        return 1
    if not build_installer():
        print("Build stopped: full installer failed.")
        return 1
    print(f"Audio Factory {APP_VERSION} build completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

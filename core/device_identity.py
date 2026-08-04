"""Stable, privacy-preserving Windows device identity (HWID v3)."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from version import APP_DATA_DIRNAME, APP_ID

logger = logging.getLogger(__name__)

HWID_VERSION = 3
HWID_NAMESPACE = APP_ID
_LEGACY_V2_NAMESPACE = "audio-factory|hwid-v2"
_PROFILE_FILE = (
    Path(os.environ.get("APPDATA", os.path.expanduser("~")))
    / APP_DATA_DIRNAME
    / "device_profile.dat"
)

_INVALID_ANCHORS = frozenset(
    {
        "",
        "0",
        "none",
        "unknown",
        "default string",
        "not specified",
        "to be filled by o.e.m.",
        "to be filled by o.e.m",
        "00000000-0000-0000-0000-000000000000",
        "ffffffff-ffff-ffff-ffff-ffffffffffff",
    }
)


class DeviceIdentityError(Exception):
    """Raised when neither supported Windows anchor can be read."""


@dataclass(frozen=True)
class DeviceIdentity:
    hwid: str
    version: int
    source: str


def _normalise_anchor(raw: str, label: str) -> str:
    value = re.sub(r"\s+", "", str(raw).strip().lower().strip("{}"))
    if (
        len(value) < 8
        or value in _INVALID_ANCHORS
        or len(set(value.replace("-", ""))) <= 1
    ):
        raise DeviceIdentityError(f"{label} is empty or a known placeholder.")
    return value


def read_smbios_uuid() -> str:
    """Read Win32_ComputerSystemProduct.UUID without using deprecated WMIC."""
    if os.name != "nt":
        raise DeviceIdentityError("SMBIOS UUID is only available on Windows.")
    command = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "(Get-CimInstance -ClassName Win32_ComputerSystemProduct "
        "-ErrorAction Stop).UUID",
    ]
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return _normalise_anchor(result.stdout.splitlines()[0], "SMBIOS UUID")
    except (OSError, subprocess.SubprocessError, IndexError) as exc:
        raise DeviceIdentityError("Cannot read SMBIOS UUID.") from exc


def read_windows_machine_guid() -> str:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
        return str(value)
    except (ImportError, OSError) as exc:
        raise DeviceIdentityError("Cannot read Windows MachineGuid.") from exc


def normalize_machine_guid(raw: str) -> str:
    return _normalise_anchor(raw, "MachineGuid")


def build_hwid(source: str, anchor: str) -> str:
    payload = f"{HWID_NAMESPACE}|{source}|{anchor.lower()}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_hwid_v2(machine_guid: str) -> str:
    """Compatibility hash for migrating already activated v2 licenses."""
    payload = f"{_LEGACY_V2_NAMESPACE}|{normalize_machine_guid(machine_guid)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _build_fallback_proof(machine_guid: str) -> str:
    value = normalize_machine_guid(machine_guid)
    return hashlib.sha256(
        f"{HWID_NAMESPACE}|fallback-proof|{value}".encode("utf-8")
    ).hexdigest()


def _load_profile_data() -> Optional[dict]:
    from core.dpapi_storage import load_protected_json

    data = load_protected_json(_PROFILE_FILE)
    return data if isinstance(data, dict) else None


def _load_device_profile() -> Optional[DeviceIdentity]:
    data = _load_profile_data()
    if not isinstance(data, dict) or data.get("schema_version") != 3:
        return None
    if data.get("hwid_version") != HWID_VERSION:
        return None
    hwid, source = str(data.get("hwid", "")), str(data.get("source", ""))
    if not re.fullmatch(r"[0-9a-f]{64}", hwid) or source not in {
        "smbios_uuid",
        "machine_guid",
    }:
        return None
    return DeviceIdentity(hwid, HWID_VERSION, source)


def _save_device_profile(
    identity: DeviceIdentity, fallback_proof: str = ""
) -> None:
    from core.dpapi_storage import save_protected_json

    save_protected_json(
        _PROFILE_FILE,
        {
            "schema_version": 3,
            "hwid_version": identity.version,
            "hwid": identity.hwid,
            "source": identity.source,
            "fallback_proof": fallback_proof,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def _read_current_anchor() -> tuple[str, str]:
    try:
        return "smbios_uuid", read_smbios_uuid()
    except DeviceIdentityError:
        try:
            return "machine_guid", normalize_machine_guid(read_windows_machine_guid())
        except DeviceIdentityError as exc:
            raise DeviceIdentityError(
                "Không thể xác định mã thiết bị ổn định từ SMBIOS UUID hoặc MachineGuid."
            ) from exc


def get_device_identity() -> DeviceIdentity:
    """Recompute from hardware every run; the cache never overrides an anchor."""
    cached = _load_device_profile()
    profile = _load_profile_data() or {}
    machine_guid: Optional[str] = None
    try:
        machine_guid = normalize_machine_guid(read_windows_machine_guid())
    except DeviceIdentityError:
        pass

    try:
        source, anchor = "smbios_uuid", read_smbios_uuid()
    except DeviceIdentityError:
        if (
            cached
            and cached.source == "smbios_uuid"
            and machine_guid
            and profile.get("fallback_proof") == _build_fallback_proof(machine_guid)
        ):
            logger.warning(
                "[SECURITY] SMBIOS temporarily unavailable; using cache tied "
                "to the current MachineGuid."
            )
            return cached
        if not machine_guid:
            raise DeviceIdentityError(
                "Không thể xác định mã thiết bị ổn định từ SMBIOS UUID hoặc MachineGuid."
            )
        source, anchor = "machine_guid", machine_guid

    fresh = DeviceIdentity(build_hwid(source, anchor), HWID_VERSION, source)
    if cached and cached != fresh:
        logger.warning(
            "[SECURITY] Device anchor changed (cached source=%s, current source=%s).",
            cached.source,
            fresh.source,
        )
    try:
        proof = _build_fallback_proof(machine_guid) if machine_guid else ""
        _save_device_profile(fresh, proof)
    except OSError:
        logger.warning("[SECURITY] Could not persist device profile.")
    return fresh


def get_hwid() -> str:
    return get_device_identity().hwid


def get_legacy_hwid_candidates() -> List[str]:
    """Return hashes only; raw hardware values never leave this process."""
    candidates: List[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        if digest not in seen:
            seen.add(digest)
            candidates.append(digest)

    cached = _load_device_profile()
    if cached:
        candidates.append(cached.hwid)
        seen.add(cached.hwid)

    try:
        machine_guid = read_windows_machine_guid()
        candidates.append(build_hwid_v2(machine_guid))
    except DeviceIdentityError:
        pass

    # Pre-v2 migration only. These values never become the active v3 anchor
    # and only their hashes are sent to the migration RPC.
    motherboard: Optional[str] = None
    disks: List[str] = []
    try:
        motherboard = read_smbios_uuid()
    except DeviceIdentityError:
        pass
    if os.name == "nt":
        try:
            output = subprocess.run(
                [
                    "powershell.exe",
                    "-NoLogo",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "Get-CimInstance Win32_DiskDrive | "
                    "ForEach-Object {$_.SerialNumber}",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            ).stdout
            disks = [
                line.strip()
                for line in output.splitlines()
                if line.strip() and line.strip().lower() not in _INVALID_ANCHORS
            ]
        except (OSError, subprocess.SubprocessError):
            pass
    if motherboard:
        for board_variant in {motherboard, motherboard.upper()}:
            add(board_variant)
            for disk in disks:
                add(f"{board_variant}|{disk}")
    for disk in disks:
        add(disk)
    try:
        add(str(uuid.getnode()))
    except Exception:
        pass
    return candidates

"""
core/dpapi_storage.py
──────────────────────────────────────────────────────────────────────────────
Windows DPAPI (Data Protection API) wrapper for encrypting/decrypting
sensitive data at rest.

Uses ctypes to call CryptProtectData / CryptUnprotectData directly,
avoiding any heavy third-party dependency.  All data is protected with
a fixed application-specific entropy string and the CRYPTPROTECT_LOCAL_MACHINE
flag so that any Windows user on the same physical machine can decrypt it
(appropriate for a per-machine license model).

No sensitive data is ever logged.
"""

import ctypes
import ctypes.wintypes
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ── Windows constants ────────────────────────────────────────────────────────
CRYPTPROTECT_LOCAL_MACHINE = 0x04

# Fixed entropy so that only this application can decrypt the data,
# even if another app on the same machine uses DPAPI with LOCAL_MACHINE.
DPAPI_ENTROPY = b"AudioFactory-License-v2"


# ── DPAPI DATA_BLOB structure ────────────────────────────────────────────────
class _DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", ctypes.wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _bytes_to_blob(data: bytes) -> _DATA_BLOB:
    """Create a DATA_BLOB from a Python bytes object."""
    blob = _DATA_BLOB()
    blob.cbData = len(data)
    blob.pbData = ctypes.cast(
        ctypes.create_string_buffer(data, len(data)),
        ctypes.POINTER(ctypes.c_byte),
    )
    return blob


def _blob_to_bytes(blob: _DATA_BLOB) -> bytes:
    """Extract a Python bytes object from a DATA_BLOB and free the memory."""
    if blob.cbData == 0 or not blob.pbData:
        return b""
    result = ctypes.string_at(blob.pbData, blob.cbData)
    # Free the memory allocated by CryptProtectData / CryptUnprotectData
    ctypes.windll.kernel32.LocalFree(blob.pbData)
    return result


# ── Core DPAPI functions ─────────────────────────────────────────────────────

def dpapi_encrypt(
    data: bytes,
    machine_scope: bool = True,
    entropy: bytes = DPAPI_ENTROPY,
) -> bytes:
    """
    Encrypt *data* using Windows DPAPI.

    Args:
        data:          Plaintext bytes to protect.
        machine_scope: If True, use CRYPTPROTECT_LOCAL_MACHINE so any user
                       on this machine can decrypt.
        entropy:       Optional entropy bytes for additional isolation.

    Returns:
        Encrypted blob bytes.

    Raises:
        OSError: If CryptProtectData fails.
    """
    plaintext_blob = _bytes_to_blob(data)
    entropy_blob = _bytes_to_blob(entropy)
    encrypted_blob = _DATA_BLOB()

    flags = CRYPTPROTECT_LOCAL_MACHINE if machine_scope else 0

    success = ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(plaintext_blob),   # pDataIn
        None,                           # szDataDescr (optional)
        ctypes.byref(entropy_blob),     # pOptionalEntropy
        None,                           # pvReserved
        None,                           # pPromptStruct
        ctypes.wintypes.DWORD(flags),   # dwFlags
        ctypes.byref(encrypted_blob),   # pDataOut
    )

    if not success:
        error_code = ctypes.get_last_error() or ctypes.GetLastError()
        raise OSError(
            f"CryptProtectData failed (error code {error_code}). "
            f"Ensure the process has sufficient privileges."
        )

    return _blob_to_bytes(encrypted_blob)


def dpapi_decrypt(
    blob: bytes,
    machine_scope: bool = True,
    entropy: bytes = DPAPI_ENTROPY,
) -> bytes:
    """
    Decrypt a DPAPI-encrypted blob.

    Args:
        blob:          Encrypted bytes (output of dpapi_encrypt).
        machine_scope: Must match the flag used during encryption.
        entropy:       Must match the entropy used during encryption.

    Returns:
        Original plaintext bytes.

    Raises:
        OSError: If CryptUnprotectData fails (wrong machine, tampered data, etc.)
    """
    encrypted_blob = _bytes_to_blob(blob)
    entropy_blob = _bytes_to_blob(entropy)
    decrypted_blob = _DATA_BLOB()

    flags = CRYPTPROTECT_LOCAL_MACHINE if machine_scope else 0

    success = ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(encrypted_blob),   # pDataIn
        None,                           # ppszDataDescr
        ctypes.byref(entropy_blob),     # pOptionalEntropy
        None,                           # pvReserved
        None,                           # pPromptStruct
        ctypes.wintypes.DWORD(flags),   # dwFlags
        ctypes.byref(decrypted_blob),   # pDataOut
    )

    if not success:
        error_code = ctypes.get_last_error() or ctypes.GetLastError()
        raise OSError(
            f"CryptUnprotectData failed (error code {error_code}). "
            f"Data may be from a different machine or corrupted."
        )

    return _blob_to_bytes(decrypted_blob)


# ── High-level JSON helpers ──────────────────────────────────────────────────

def save_protected_json(path: Path, data: Dict[str, Any]) -> None:
    """
    Serialise *data* to JSON, encrypt with DPAPI, and write atomically.

    Atomic write sequence:
      1. Write to a temporary file in the same directory.
      2. Flush + fsync.
      3. os.replace() to atomically swap with the target.

    This prevents half-written files on crash or power loss.
    """
    path_obj = Path(path)
    path_obj.parent.mkdir(parents=True, exist_ok=True)

    plaintext = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

    try:
        encrypted = dpapi_encrypt(plaintext)
    except OSError as exc:
        logger.error("[SECURITY] DPAPI encryption failed: %s", type(exc).__name__)
        raise

    # Atomic write: temp → flush → fsync → replace
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path_obj.parent),
        prefix=f".{path_obj.stem}_",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(encrypted)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(path_obj))
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_protected_json(path: Path) -> Optional[Dict[str, Any]]:
    """
    Read a DPAPI-encrypted file and return the parsed JSON dict.

    Returns None (without crashing) if:
      - File does not exist.
      - File is corrupted or tampered.
      - DPAPI decryption fails (wrong machine, etc.).
      - JSON parsing fails.
    """
    path_obj = Path(path)
    if not path_obj.exists():
        return None

    try:
        encrypted = path_obj.read_bytes()
        if not encrypted:
            return None

        plaintext = dpapi_decrypt(encrypted)
        return json.loads(plaintext.decode("utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        logger.warning(
            "[SECURITY] Failed to load protected file '%s': %s",
            path_obj.name,
            type(exc).__name__,
        )
        return None

"""Windows NVIDIA DLL bootstrap shared by GUI and command-line entry points."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List


_DLL_HANDLES: List[object] = []
_BOOTSTRAPPED = False


def bootstrap_nvidia_dlls() -> List[str]:
    """Register NVIDIA wheel DLL folders and return the paths that were found.

    ``os.add_dll_directory`` handles must stay alive for as long as native CUDA
    libraries can be loaded, so they are retained at module scope.
    """
    global _BOOTSTRAPPED
    if _BOOTSTRAPPED or sys.platform != "win32":
        return []

    roots = [Path(sys.prefix) / "Lib" / "site-packages"]
    executable_venv = Path(sys.executable).resolve().parent.parent / "Lib" / "site-packages"
    if executable_venv not in roots:
        roots.append(executable_venv)
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        roots.append(Path(frozen_root))

    relative_paths = (
        Path("nvidia/cublas/bin"),
        Path("nvidia/cudnn/bin"),
        Path("nvidia/cuda_runtime/bin"),
        Path("nvidia/cuda_nvrtc/bin"),
    )
    found: List[str] = []
    current_path = os.environ.get("PATH", "").split(os.pathsep)
    for root in roots:
        for relative in relative_paths:
            candidate = (root / relative).resolve()
            candidate_str = str(candidate)
            if not candidate.is_dir() or candidate_str in found:
                continue
            found.append(candidate_str)
            try:
                _DLL_HANDLES.append(os.add_dll_directory(candidate_str))
            except (AttributeError, FileNotFoundError, OSError):
                pass
            if candidate_str not in current_path:
                current_path.insert(0, candidate_str)

    os.environ["PATH"] = os.pathsep.join(current_path)
    _BOOTSTRAPPED = True
    return found


__all__ = ["bootstrap_nvidia_dlls"]

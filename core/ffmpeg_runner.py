import os
import subprocess
import shutil
import threading
from pathlib import Path
from typing import List, Optional


class FFmpegError(Exception):
    """Exception raised when an FFmpeg or FFprobe command fails."""
    def __init__(self, cmd: List[str], returncode: int, stdout: Optional[str], stderr: Optional[str], message: str = ""):
        self.cmd = cmd
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

        # Build clear error message
        cmd_str = " ".join(cmd)
        msg = f"FFmpeg/FFprobe command failed with exit code {returncode}.\nCommand: {cmd_str}"
        if message:
            msg += f"\nDetails: {message}"
        if stderr:
            msg += f"\nStderr:\n{stderr.strip()}"
        super().__init__(msg)


# ─────────────────────────────────────────────────────────────────────────────
# Process Registry — thread-safe kill switch for active FFmpeg subprocesses
# ─────────────────────────────────────────────────────────────────────────────

class _ProcessRegistry:
    """
    Thread-safe registry that tracks all active Popen instances.
    Allows any thread to call kill_all() to forcibly terminate every
    running FFmpeg subprocess — used when the user clicks 'Cancel'.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._procs: List[subprocess.Popen] = []

    def register(self, proc: subprocess.Popen) -> None:
        with self._lock:
            self._procs.append(proc)

    def unregister(self, proc: subprocess.Popen) -> None:
        with self._lock:
            try:
                self._procs.remove(proc)
            except ValueError:
                pass

    def kill_all(self) -> None:
        """Terminate every registered process immediately."""
        with self._lock:
            procs = list(self._procs)   # snapshot under lock
        for proc in procs:
            try:
                proc.terminate()        # SIGTERM — graceful first
            except Exception:
                pass
            try:
                proc.kill()             # SIGKILL — force if still alive
            except Exception:
                pass


_REGISTRY = _ProcessRegistry()


def kill_active_ffmpeg_processes() -> None:
    """
    Public API: terminate all FFmpeg/FFprobe subprocesses currently running.

    Call this from the cancellation code path (PipelineWorker.cancel())
    to guarantee that a blocking FFmpeg call does not keep the worker
    thread alive after the user has requested cancellation.
    """
    _REGISTRY.kill_all()


# ─────────────────────────────────────────────────────────────────────────────
# Executable discovery
# ─────────────────────────────────────────────────────────────────────────────

def find_executable(name: str) -> Optional[Path]:
    """
    Find the executable by name.
    Checks:
    1. The project's 'bin' directory.
    2. The system PATH.
    """
    # Check local bin/ folder relative to project root
    project_root = Path(__file__).parent.parent.resolve()
    local_bin = project_root / "bin"

    # On Windows, check for .exe extensions
    names_to_try = [name]
    if os.name == "nt" and not name.lower().endswith(".exe"):
        names_to_try.append(f"{name}.exe")

    for try_name in names_to_try:
        local_path = local_bin / try_name
        if local_path.is_file():
            return local_path

    # Check system PATH
    for try_name in names_to_try:
        sys_path = shutil.which(try_name)
        if sys_path:
            return Path(sys_path).resolve()

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Core runner — uses Popen so processes can be killed mid-run
# ─────────────────────────────────────────────────────────────────────────────

def run_command(args: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """
    Execute a system command via Popen (registered for kill-switch support).

    Uses Popen instead of subprocess.run so that kill_active_ffmpeg_processes()
    can terminate any in-flight FFmpeg call the moment the user clicks Cancel,
    without waiting for it to finish on its own.

    Returns a CompletedProcess-compatible object identical to the old API.
    """
    proc: Optional[subprocess.Popen] = None
    try:
        proc = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        _REGISTRY.register(proc)
        try:
            stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            stdout_bytes, stderr_bytes = proc.communicate()
            stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else None
            stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else None
            raise FFmpegError(
                cmd=args,
                returncode=-1,
                stdout=stdout,
                stderr=stderr,
                message=f"Command execution timed out after {timeout} seconds.",
            )
        finally:
            _REGISTRY.unregister(proc)

        stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
        stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""

        return subprocess.CompletedProcess(
            args=args,
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
        )

    except FFmpegError:
        raise
    except FileNotFoundError as e:
        raise FFmpegError(
            cmd=args,
            returncode=-1,
            stdout=None,
            stderr=None,
            message=f"Executable file not found: {e}",
        ) from e
    except Exception as e:
        raise FFmpegError(
            cmd=args,
            returncode=-1,
            stdout=None,
            stderr=None,
            message=f"Error executing command: {str(e)}",
        ) from e
    finally:
        # Safety: always unregister even on unexpected exceptions
        if proc is not None:
            _REGISTRY.unregister(proc)


# ─────────────────────────────────────────────────────────────────────────────
# FFmpeg / FFprobe wrappers
# ─────────────────────────────────────────────────────────────────────────────

def check_ffmpeg_available() -> bool:
    """
    Check if both ffmpeg and ffprobe are available and functional.
    """
    ffmpeg_path = find_executable("ffmpeg")
    ffprobe_path = find_executable("ffprobe")

    if not ffmpeg_path or not ffprobe_path:
        return False

    try:
        ffmpeg_res = run_command([str(ffmpeg_path), "-version"])
        if ffmpeg_res.returncode != 0:
            return False

        ffprobe_res = run_command([str(ffprobe_path), "-version"])
        if ffprobe_res.returncode != 0:
            return False

        return True
    except Exception:
        return False


def run_ffmpeg(args: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """
    Run the local ffmpeg executable with the given arguments.
    Raises FFmpegError on failure or if ffmpeg is missing.

    The underlying Popen handle is registered in _REGISTRY so that
    kill_active_ffmpeg_processes() can terminate it immediately on cancel.
    """
    ffmpeg_path = find_executable("ffmpeg")
    if not ffmpeg_path:
        raise FFmpegError(
            cmd=["ffmpeg"] + args,
            returncode=-1,
            stdout=None,
            stderr=None,
            message="ffmpeg executable not found in bin/ or in system PATH. Please ensure FFmpeg is installed.",
        )

    cmd = [str(ffmpeg_path)] + args
    result = run_command(cmd, timeout=timeout)
    if result.returncode != 0:
        # returncode=-1 means process was killed (cancelled) — propagate cleanly
        if result.returncode == -1 or result.returncode == 1 and not result.stderr.strip():
            raise FFmpegError(
                cmd=cmd,
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        raise FFmpegError(
            cmd=cmd,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    return result


def run_ffprobe(args: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """
    Run the local ffprobe executable with the given arguments.
    Raises FFmpegError on failure or if ffprobe is missing.
    """
    ffprobe_path = find_executable("ffprobe")
    if not ffprobe_path:
        raise FFmpegError(
            cmd=["ffprobe"] + args,
            returncode=-1,
            stdout=None,
            stderr=None,
            message="ffprobe executable not found in bin/ or in system PATH. Please ensure FFmpeg is installed.",
        )

    cmd = [str(ffprobe_path)] + args
    result = run_command(cmd, timeout=timeout)
    if result.returncode != 0:
        raise FFmpegError(
            cmd=cmd,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    return result

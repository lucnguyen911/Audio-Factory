import os
import subprocess
import shutil
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


def run_command(args: List[str], timeout: Optional[int] = None) -> subprocess.CompletedProcess:
    """
    Safely execute a system command and capture stdout/stderr.
    """
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace"
        )
        return result
    except subprocess.TimeoutExpired as e:
        stdout = e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else e.stdout
        stderr = e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else e.stderr
        raise FFmpegError(
            cmd=args,
            returncode=-1,
            stdout=stdout,
            stderr=stderr,
            message=f"Command execution timed out after {timeout} seconds."
        ) from e
    except FileNotFoundError as e:
        raise FFmpegError(
            cmd=args,
            returncode=-1,
            stdout=None,
            stderr=None,
            message=f"Executable file not found: {e}"
        ) from e
    except Exception as e:
        raise FFmpegError(
            cmd=args,
            returncode=-1,
            stdout=None,
            stderr=None,
            message=f"Error executing command: {str(e)}"
        ) from e


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
    """
    ffmpeg_path = find_executable("ffmpeg")
    if not ffmpeg_path:
        raise FFmpegError(
            cmd=["ffmpeg"] + args,
            returncode=-1,
            stdout=None,
            stderr=None,
            message="ffmpeg executable not found in bin/ or in system PATH. Please ensure FFmpeg is installed."
        )
        
    cmd = [str(ffmpeg_path)] + args
    result = run_command(cmd, timeout=timeout)
    if result.returncode != 0:
        raise FFmpegError(
            cmd=cmd,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr
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
            message="ffprobe executable not found in bin/ or in system PATH. Please ensure FFmpeg is installed."
        )
        
    cmd = [str(ffprobe_path)] + args
    result = run_command(cmd, timeout=timeout)
    if result.returncode != 0:
        raise FFmpegError(
            cmd=cmd,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr
        )
    return result

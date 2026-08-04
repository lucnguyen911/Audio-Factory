import json
from pathlib import Path
from typing import Dict, Any, List

from core.ffmpeg_runner import run_ffmpeg, run_ffprobe, FFmpegError

SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".wma",
    ".mp4", ".mov", ".mkv", ".avi"
}

class MediaImportError(Exception):
    """Exception raised for errors during media importing or validation."""
    pass


def is_supported_media(path: Path) -> bool:
    """
    Check if the path has a supported media file extension.
    """
    return Path(path).suffix.lower() in SUPPORTED_EXTENSIONS


def validate_input_file(path: Path) -> Path:
    """
    Validate the input file path.
    Converts path to Path object, checks existence, checks it is a file, and supports extensions.
    Raises MediaImportError on validation failure.
    """
    path_obj = Path(path)
    
    if not path_obj.exists():
        raise MediaImportError(f"Input path does not exist: {path_obj}")
        
    if not path_obj.is_file():
        raise MediaImportError(f"Input path is not a file (it might be a directory): {path_obj}")
        
    if not is_supported_media(path_obj):
        raise MediaImportError(
            f"Unsupported file format '{path_obj.suffix}'. "
            f"Supported extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
        
    return path_obj


def probe_media(path: Path) -> Dict[str, Any]:
    """
    Use ffprobe to retrieve metadata from the given media file.
    Returns the parsed JSON metadata as a dictionary.
    """
    path_obj = validate_input_file(path)
    
    # ffprobe command arguments
    # -show_format: show container information
    # -show_streams: show audio/video stream details
    # -print_format json: print output as JSON
    args = [
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        str(path_obj)
    ]
    
    try:
        result = run_ffprobe(args)
        return json.loads(result.stdout)
    except FFmpegError as e:
        raise MediaImportError(f"Failed to probe media file '{path_obj}': {e}") from e
    except json.JSONDecodeError as e:
        raise MediaImportError(f"Failed to parse ffprobe output for '{path_obj}': {e}") from e


def get_duration_seconds(path: Path) -> float:
    """
    Retrieve the duration of the media file in seconds.
    Raises MediaImportError if duration cannot be determined.
    """
    metadata = probe_media(path)
    
    # Try format duration first
    duration_str = metadata.get("format", {}).get("duration")
    if duration_str is not None:
        try:
            return float(duration_str)
        except ValueError:
            pass
            
    # Try streams duration if format duration is missing
    for stream in metadata.get("streams", []):
        duration_str = stream.get("duration")
        if duration_str is not None:
            try:
                return float(duration_str)
            except ValueError:
                pass
                
    raise MediaImportError(f"Could not determine duration for media file: {path}")


def convert_to_work_wav(
    input_path: Path,
    output_path: Path,
    sample_rate: int = 16000,
    channels: int = 1,
    overwrite: bool = True
) -> Path:
    """
    Convert the input media file to a standardized WAV format (PCM 16-bit)
    with specified sample rate and channel count.
    
    Returns the resolved output Path.
    """
    input_path_obj = validate_input_file(input_path)
    output_path_obj = Path(output_path)
    
    # Create parent output directory if it doesn't exist
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    # Check overwrite condition
    if output_path_obj.exists() and not overwrite:
        raise MediaImportError(f"Output file already exists and overwrite is set to False: {output_path_obj}")
        
    # ffmpeg args:
    # -y (overwrite) or -n (do not overwrite)
    # -i input
    # -ar sample_rate
    # -ac channels
    # -acodec pcm_s16le (standard 16-bit PCM WAV)
    overwrite_flag = "-y" if overwrite else "-n"
    args = [
        overwrite_flag,
        "-i", str(input_path_obj),
        "-ar", str(sample_rate),
        "-ac", str(channels),
        "-acodec", "pcm_s16le",
        str(output_path_obj)
    ]
    
    try:
        run_ffmpeg(args)
        return output_path_obj
    except FFmpegError as e:
        raise MediaImportError(f"Failed to convert media file to WAV: {e}") from e


def normalize_to_pcm(
    input_path: Path,
    output_path: Path,
    sample_rate: int = 48000,
    channels: int = 2,
    overwrite: bool = True,
) -> Path:
    """
    Normalize input media to WAV PCM format (default f32le, 48kHz, stereo) for internal DSP processing.
    """
    input_path_obj = validate_input_file(input_path)
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    overwrite_flag = "-y" if overwrite else "-n"
    args = [
        overwrite_flag,
        "-i", str(input_path_obj),
        "-ar", str(sample_rate),
        "-ac", str(channels),
        "-c:a", "pcm_f32le",
        str(output_path_obj)
    ]

    try:
        run_ffmpeg(args)
        return output_path_obj
    except Exception as e:
        raise MediaImportError(f"Failed to normalize media file to PCM: {e}") from e


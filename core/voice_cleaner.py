import os
from pathlib import Path
from core.ffmpeg_runner import run_ffmpeg, FFmpegError

class VoiceCleanerError(Exception):
    """Exception raised for errors during voice cleanup."""
    pass


def clean_voice(input_path: Path, output_path: Path, overwrite: bool = True) -> Path:
    """
    Apply a safe FFmpeg audio filter chain for voice cleanup:
    - highpass=f=80: cut low frequency rumble
    - lowpass=f=12000: cut high frequency hiss
    - afftdn=nf=-35: light noise reduction
    - agate=threshold=-40dB:range=12dB: noise gate to reduce breath/silence noise
    """
    input_path_obj = Path(input_path)
    output_path_obj = Path(output_path)
    
    if not input_path_obj.exists():
        raise VoiceCleanerError(f"Input path does not exist: {input_path_obj}")
        
    if output_path_obj.exists() and not overwrite:
        raise VoiceCleanerError(f"Output file already exists and overwrite is False: {output_path_obj}")
        
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    filter_chain = "highpass=f=80,lowpass=f=12000,afftdn=nf=-35,agate=threshold=-40dB:range=0.25"
    overwrite_flag = "-y" if overwrite else "-n"
    
    args = [
        overwrite_flag,
        "-i", str(input_path_obj),
        "-af", filter_chain
    ]
    
    ext = output_path_obj.suffix.lower().lstrip(".")
    if ext == "wav":
        args += ["-c:a", "pcm_s16le"]
    elif ext == "mp3":
        args += ["-c:a", "libmp3lame"]
    elif ext == "m4a":
        args += ["-c:a", "aac"]
        
    args.append(str(output_path_obj))
    
    try:
        run_ffmpeg(args)
        return output_path_obj
    except FFmpegError as e:
        raise VoiceCleanerError(f"Failed to clean voice of '{input_path_obj}': {e}") from e

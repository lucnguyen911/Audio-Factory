import os
from pathlib import Path
from core.ffmpeg_runner import run_ffmpeg, FFmpegError

class SocialOptimizerError(Exception):
    """Exception raised for errors during social media optimization."""
    pass


def optimize_social_audio(input_path: Path, output_path: Path, overwrite: bool = True) -> Path:
    """
    Apply FFmpeg audio filters to optimize audio loudness for social platforms:
    - loudnorm=i=-14:tp=-1.0:lra=7: target YouTube/TikTok standard of -14 LUFS, -1.0 True Peak
    - alimiter=limit=0.89: limit peaks to prevent clipping
    """
    input_path_obj = Path(input_path)
    output_path_obj = Path(output_path)
    
    if not input_path_obj.exists():
        raise SocialOptimizerError(f"Input path does not exist: {input_path_obj}")
        
    if output_path_obj.exists() and not overwrite:
        raise SocialOptimizerError(f"Output file already exists and overwrite is False: {output_path_obj}")
        
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    filter_chain = "loudnorm=i=-14:tp=-1.0:lra=7,alimiter=limit=0.89"
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
        raise SocialOptimizerError(f"Failed to optimize social audio of '{input_path_obj}': {e}") from e

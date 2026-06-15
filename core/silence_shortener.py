import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from core.ffmpeg_runner import run_ffmpeg, FFmpegError
from core.importer import validate_input_file, MediaImportError

class SilenceShortenerError(Exception):
    """Exception raised for errors during silence shortening."""
    pass


@dataclass
class SilenceShortenerOptions:
    preset: str = "natural"
    silence_threshold_db: float = -35.0
    min_silence_duration: float = 0.35
    keep_silence_duration: float = 0.18
    trim_start: bool = True
    trim_end: bool = True
    process_middle: bool = True
    overwrite: bool = True


VALID_PRESETS = {"natural", "fast", "hard"}


def validate_preset(preset: str) -> str:
    """
    Check if the preset is valid.
    Raises SilenceShortenerError if the preset is not supported.
    """
    preset_lower = preset.lower()
    if preset_lower not in VALID_PRESETS:
        raise SilenceShortenerError(
            f"Invalid preset '{preset}'. Valid options are: {', '.join(sorted(VALID_PRESETS))}"
        )
    return preset_lower


def options_from_preset(preset: str) -> SilenceShortenerOptions:
    """
    Return predefined SilenceShortenerOptions for the given preset.
    """
    preset_lower = validate_preset(preset)
    if preset_lower == "natural":
        return SilenceShortenerOptions(
            preset="natural",
            silence_threshold_db=-35.0,
            min_silence_duration=0.5,
            keep_silence_duration=0.3
        )
    elif preset_lower == "fast":
        return SilenceShortenerOptions(
            preset="fast",
            silence_threshold_db=-35.0,
            min_silence_duration=0.35,
            keep_silence_duration=0.18
        )
    else:  # hard
        return SilenceShortenerOptions(
            preset="hard",
            silence_threshold_db=-30.0,
            min_silence_duration=0.25,
            keep_silence_duration=0.1
        )


def build_silenceremove_filter(options: SilenceShortenerOptions) -> str:
    """
    Build the FFmpeg silenceremove audio filter chain.
    """
    parts = []
    
    # 1. Trim start silence
    if options.trim_start:
        parts.append(
            f"start_periods=1"
            f":start_duration=0.1"
            f":start_threshold={options.silence_threshold_db}dB"
        )
    else:
        parts.append("start_periods=0")
        
    # 2. Process middle and end silence
    if options.process_middle or options.trim_end:
        periods = -1 if options.process_middle else 1
        parts.append(
            f"stop_periods={periods}"
            f":stop_duration={options.min_silence_duration}"
            f":stop_threshold={options.silence_threshold_db}dB"
            f":stop_silence={options.keep_silence_duration}"
        )
        
    return f"silenceremove={':'.join(parts)}"


def shorten_silence(
    input_path: Path,
    output_path: Path,
    options: Optional[SilenceShortenerOptions] = None
) -> Path:
    """
    Shorten silence pauses in a single audio file.
    Raises SilenceShortenerError on failure.
    """
    if options is None:
        options = options_from_preset("natural")
        
    try:
        input_path_obj = validate_input_file(input_path)
    except MediaImportError as e:
        raise SilenceShortenerError(f"Invalid input file: {e}") from e
        
    output_path_obj = Path(output_path)
    
    if output_path_obj.exists() and not options.overwrite:
        raise SilenceShortenerError(f"Output file already exists and overwrite is False: {output_path_obj}")
        
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    filter_chain = build_silenceremove_filter(options)
    
    overwrite_flag = "-y" if options.overwrite else "-n"
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
        raise SilenceShortenerError(f"Failed to shorten silence in '{input_path_obj}': {e}") from e


def shorten_silence_batch(
    input_paths: List[Path],
    output_dir: Path,
    options: Optional[SilenceShortenerOptions] = None
) -> List[Path]:
    """
    Apply silence shortening on a list of audio files, saving them to output_dir
    with suffix '_shortened'.
    """
    if options is None:
        options = options_from_preset("natural")
        
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)
    
    shortened_paths = []
    for path in input_paths:
        input_path_obj = Path(path)
        output_file = output_dir_obj / f"{input_path_obj.stem}_shortened{input_path_obj.suffix}"
        
        try:
            shortened = shorten_silence(input_path_obj, output_file, options)
            shortened_paths.append(shortened)
        except Exception as e:
            raise SilenceShortenerError(f"Batch execution failed on file '{input_path_obj}': {e}") from e
            
    return shortened_paths

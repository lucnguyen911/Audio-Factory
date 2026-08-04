import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from core.ffmpeg_runner import run_ffmpeg, FFmpegError
from core.importer import get_duration_seconds, validate_input_file, MediaImportError

class SilenceShortenerError(Exception):
    """Exception raised for errors during silence shortening."""
    pass


@dataclass
class SilenceShortenerOptions:
    preset: str = "auto"
    silence_threshold_db: float = -45.0
    min_silence_duration: float = 0.8
    keep_silence_duration: float = 0.4
    # TTS often starts with a soft breath or consonant.  Never trim the start
    # automatically; only the caller can opt into that destructive behaviour.
    trim_start: bool = False
    trim_end: bool = True
    process_middle: bool = True
    overwrite: bool = True


# "auto" is the only policy exposed by the product UI.  The legacy names are
# retained for API compatibility with older CLI/config callers.
VALID_PRESETS = {"auto", "natural", "fast", "hard"}


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
    if preset_lower == "auto":
        # Conservative TTS policy: protect soft starts and normal sentence
        # pauses, then shorten only clear dead air.  -45 dB is deliberately
        # below the old -35 dB threshold so quiet breaths/consonants are not
        # mistaken for silence.
        return SilenceShortenerOptions(
            preset="auto",
            silence_threshold_db=-45.0,
            min_silence_duration=0.8,
            keep_silence_duration=0.4,
            trim_start=False,
        )
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


_SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")


def _detect_auto_silences(input_path: Path, options: SilenceShortenerOptions) -> List[tuple[float, float]]:
    """Return silence intervals long enough for the Auto policy to consider."""
    result = run_ffmpeg([
        "-hide_banner", "-i", str(input_path),
        "-af", f"silencedetect=n={options.silence_threshold_db}dB:d={options.min_silence_duration}",
        "-f", "null", "-",
    ])
    intervals: List[tuple[float, float]] = []
    start: Optional[float] = None
    for line in result.stderr.splitlines():
        start_match = _SILENCE_START_RE.search(line)
        if start_match:
            start = float(start_match.group(1))
            continue
        end_match = _SILENCE_END_RE.search(line)
        if end_match and start is not None:
            end = float(end_match.group(1))
            if end > start:
                intervals.append((start, end))
            start = None
    return intervals


def _build_auto_removal_ranges(
    intervals: List[tuple[float, float]],
    duration: float,
    keep_silence: float,
) -> List[tuple[float, float]]:
    """Keep padding on both sides of a middle pause and protect file start."""
    ranges: List[tuple[float, float]] = []
    half_keep = keep_silence / 2.0
    for start, end in intervals:
        # Never infer that the first quiet samples are disposable: AI TTS often
        # begins with a low-level breath or consonant.
        if start <= 0.02:
            continue
        if end >= duration - 0.02:
            remove_start, remove_end = start, end - keep_silence
        else:
            remove_start, remove_end = start + half_keep, end - half_keep
        if remove_end - remove_start >= 0.01:
            ranges.append((remove_start, remove_end))
    return ranges


def _shorten_silence_auto(
    input_path: Path,
    output_path: Path,
    options: SilenceShortenerOptions,
) -> Path:
    """Safely shorten detected dead air without ever trimming a quiet start."""
    duration = get_duration_seconds(input_path)
    intervals = _detect_auto_silences(input_path, options)
    removal_ranges = _build_auto_removal_ranges(
        intervals, duration, options.keep_silence_duration,
    )
    if not removal_ranges:
        shutil.copy2(input_path, output_path)
        return output_path

    # Drop only the middle of eligible silence intervals.  The retained padding
    # means the new joins happen in quiet audio, avoiding speech clipping.
    selected = "+".join(
        f"between(t\\,{start:.6f}\\,{end:.6f})"
        for start, end in removal_ranges
    )
    filter_chain = f"aselect=not({selected}),asetpts=N/SR/TB"
    args = ["-y", "-i", str(input_path), "-af", filter_chain]
    ext = output_path.suffix.lower().lstrip(".")
    if ext == "wav":
        args += ["-c:a", "pcm_s16le"]
    elif ext == "mp3":
        args += ["-c:a", "libmp3lame"]
    elif ext == "m4a":
        args += ["-c:a", "aac"]
    args.append(str(output_path))
    run_ffmpeg(args)
    return output_path


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
        options = options_from_preset("auto")
        
    try:
        input_path_obj = validate_input_file(input_path)
    except MediaImportError as e:
        raise SilenceShortenerError(f"Invalid input file: {e}") from e
        
    output_path_obj = Path(output_path)
    
    if output_path_obj.exists() and not options.overwrite:
        raise SilenceShortenerError(f"Output file already exists and overwrite is False: {output_path_obj}")
        
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    if options.preset.lower() == "auto":
        try:
            return _shorten_silence_auto(input_path_obj, output_path_obj, options)
        except (FFmpegError, MediaImportError) as e:
            raise SilenceShortenerError(
                f"Failed to automatically shorten silence in '{input_path_obj}': {e}"
            ) from e

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
        options = options_from_preset("auto")
        
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

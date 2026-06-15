import os
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from core.ffmpeg_runner import run_ffmpeg, FFmpegError
from core.importer import validate_input_file, MediaImportError

class VolumeLevelingError(Exception):
    """Exception raised for errors during volume leveling."""
    pass


@dataclass
class VolumeLevelingOptions:
    preset: str = "natural"
    target_lufs: float = -16.0
    true_peak: float = -1.5
    loudness_range: float = 11.0
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    overwrite: bool = True


VALID_PRESETS = {"natural", "strong", "aggressive"}


def validate_preset(preset: str) -> str:
    """
    Check if the preset is valid.
    Raises VolumeLevelingError if the preset is not supported.
    """
    preset_lower = preset.lower()
    if preset_lower not in VALID_PRESETS:
        raise VolumeLevelingError(
            f"Invalid preset '{preset}'. Valid options are: {', '.join(sorted(VALID_PRESETS))}"
        )
    return preset_lower


def build_volume_filter_chain(options: VolumeLevelingOptions) -> str:
    """
    Build the FFmpeg audio filter chain based on preset and leveling settings.
    Combines compand (compressor), loudnorm (loudness normalization), and alimiter.
    """
    preset = validate_preset(options.preset)
    
    # 1. Setup dynamic range compression (compand) per preset
    if preset == "natural":
        # Gentle dynamic leveling keeping original characteristics
        compand_filter = "compand=attacks=0.3|0.3:decays=0.8|0.8:points=-70|-60|-25|-20|0|-5:soft-knee=2.0:gain=-2"
    elif preset == "strong":
        # Moderate leveling suitable for regular content podcasts
        compand_filter = "compand=attacks=0.2|0.2:decays=0.6|0.6:points=-70|-50|-20|-12|0|-2:soft-knee=2.0:gain=-1"
    else:  # aggressive
        # Fast compression suited for short form / MMO content
        compand_filter = "compand=attacks=0.1|0.1:decays=0.4|0.4:points=-70|-40|-20|-8|0|0:soft-knee=2.0:gain=0"

    # 2. Loudness normalization (loudnorm)
    loudnorm_filter = f"loudnorm=i={options.target_lufs}:tp={options.true_peak}:lra={options.loudness_range}"

    # 3. Limiter to guarantee zero digital clipping (limiter set at -1.0dB amplitude (~0.89))
    limiter_filter = "alimiter=limit=0.89"

    return f"{compand_filter},{loudnorm_filter},{limiter_filter}"


def level_volume(
    input_path: Path,
    output_path: Path,
    options: Optional[VolumeLevelingOptions] = None
) -> Path:
    """
    Apply volume leveling on a single audio file.
    Raises VolumeLevelingError on failure.
    """
    if options is None:
        options = VolumeLevelingOptions()

    try:
        input_path_obj = validate_input_file(input_path)
    except MediaImportError as e:
        raise VolumeLevelingError(f"Invalid input file: {e}") from e
        
    output_path_obj = Path(output_path)
    
    if output_path_obj.exists() and not options.overwrite:
        raise VolumeLevelingError(f"Output file already exists and overwrite is False: {output_path_obj}")

    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    filter_chain = build_volume_filter_chain(options)
    
    overwrite_flag = "-y" if options.overwrite else "-n"
    args = [
        overwrite_flag,
        "-i", str(input_path_obj),
        "-af", filter_chain
    ]
    
    if options.sample_rate is not None:
        args += ["-ar", str(options.sample_rate)]
    if options.channels is not None:
        args += ["-ac", str(options.channels)]
        
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
        raise VolumeLevelingError(f"Failed to level volume of '{input_path_obj}': {e}") from e


def level_volume_batch(
    input_paths: List[Path],
    output_dir: Path,
    options: Optional[VolumeLevelingOptions] = None
) -> List[Path]:
    """
    Apply volume leveling on a list of audio files, saving them to output_dir
    with suffix '_leveled'.
    """
    if options is None:
        options = VolumeLevelingOptions()
        
    output_dir_obj = Path(output_dir)
    output_dir_obj.parent.mkdir(parents=True, exist_ok=True)
    
    leveled_paths = []
    for path in input_paths:
        input_path_obj = Path(path)
        output_file = output_dir_obj / f"{input_path_obj.stem}_leveled{input_path_obj.suffix}"
        
        try:
            leveled = level_volume(input_path_obj, output_file, options)
            leveled_paths.append(leveled)
        except Exception as e:
            raise VolumeLevelingError(f"Batch execution failed on file '{input_path_obj}': {e}") from e
            
    return leveled_paths

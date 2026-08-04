import os
import re
import shutil
from pathlib import Path
from core.ffmpeg_runner import run_ffmpeg, FFmpegError

from dataclasses import dataclass
from typing import Optional

class VoiceCleanerError(Exception):
    """Exception raised for errors during voice cleanup."""
    pass


@dataclass
class VoiceCleanerOptions:
    # Auto is the only policy exposed by the UI.  Legacy names remain valid
    # for callers that explicitly request the old fixed chain.
    preset: str = "auto"
    overwrite: bool = True


@dataclass(frozen=True)
class _NoiseProfile:
    ambient_db: float
    highpass_hz: int
    noise_reduction_db: float


_SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")
_MEAN_VOLUME_RE = re.compile(r"mean_volume:\s*(-?[0-9.]+)\s*dB")


def _find_quiet_region(input_path: Path) -> Optional[tuple[float, float]]:
    """Find a stable quiet region without assuming the beginning is noise."""
    result = run_ffmpeg([
        "-hide_banner", "-i", str(input_path),
        "-af", "silencedetect=n=-30dB:d=0.4", "-f", "null", "-",
    ])
    start: Optional[float] = None
    for line in result.stderr.splitlines():
        match = _SILENCE_START_RE.search(line)
        if match:
            start = float(match.group(1))
            continue
        match = _SILENCE_END_RE.search(line)
        if match and start is not None:
            end = float(match.group(1))
            if end - start >= 0.4:
                return start, end
            start = None
    return None


def _measure_ambient_db(input_path: Path, start: float, end: float) -> Optional[float]:
    sample_duration = min(0.75, end - start)
    if sample_duration < 0.2:
        return None
    result = run_ffmpeg([
        "-hide_banner", "-ss", f"{start:.3f}", "-t", f"{sample_duration:.3f}",
        "-i", str(input_path), "-af", "volumedetect", "-f", "null", "-",
    ])
    match = _MEAN_VOLUME_RE.search(result.stderr)
    return float(match.group(1)) if match else None


def _build_auto_profile(input_path: Path) -> Optional[_NoiseProfile]:
    """Return a conservative profile, or None when the source appears clean."""
    quiet_region = _find_quiet_region(input_path)
    if quiet_region is None:
        return None
    ambient_db = _measure_ambient_db(input_path, *quiet_region)
    if ambient_db is None or ambient_db <= -60.0:
        return None
    if ambient_db <= -50.0:
        return _NoiseProfile(ambient_db, highpass_hz=70, noise_reduction_db=4)
    if ambient_db <= -42.0:
        return _NoiseProfile(ambient_db, highpass_hz=80, noise_reduction_db=6)
    return _NoiseProfile(ambient_db, highpass_hz=100, noise_reduction_db=8)


def _clean_voice_auto(input_path: Path, output_path: Path, overwrite: bool) -> Path:
    profile = _build_auto_profile(input_path)
    if profile is None:
        # A clean source (or one without a trustworthy noise-only sample) is
        # safer unchanged than damaged by speculative denoise/gating.
        shutil.copy2(input_path, output_path)
        return output_path

    noise_floor = max(-70.0, min(-30.0, profile.ambient_db))
    filter_chain = (
        f"highpass=f={profile.highpass_hz},"
        f"afftdn=nr={profile.noise_reduction_db}:nf={noise_floor:.1f}:tn=1:gs=8"
    )
    args = ["-y" if overwrite else "-n", "-i", str(input_path), "-af", filter_chain]
    ext = output_path.suffix.lower().lstrip(".")
    if ext == "wav":
        args += ["-c:a", "pcm_f32le"]
    elif ext == "mp3":
        args += ["-c:a", "libmp3lame"]
    elif ext == "m4a":
        args += ["-c:a", "aac"]
    args.append(str(output_path))
    run_ffmpeg(args)
    return output_path


def clean_voice(
    input_path: Path,
    output_path: Path,
    overwrite: bool = True,
    options: Optional[VoiceCleanerOptions] = None,
) -> Path:
    """
    Apply Auto Denoise when selected.  It uses a quiet sample to choose a
    light cleanup profile per file, and leaves ambiguous/clean sources intact.
    """
    input_path_obj = Path(input_path)
    output_path_obj = Path(output_path)
    if options is not None:
        overwrite = options.overwrite
    
    if not input_path_obj.exists():
        raise VoiceCleanerError(f"Input path does not exist: {input_path_obj}")
        
    if output_path_obj.exists() and not overwrite:
        raise VoiceCleanerError(f"Output file already exists and overwrite is False: {output_path_obj}")
        
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    if options is None or options.preset.lower() == "auto":
        try:
            return _clean_voice_auto(input_path_obj, output_path_obj, overwrite)
        except FFmpegError as e:
            raise VoiceCleanerError(
                f"Failed to automatically clean voice in '{input_path_obj}': {e}"
            ) from e
    
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

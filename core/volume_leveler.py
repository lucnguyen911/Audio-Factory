"""
Volume Leveler — DSP-correct loudness normalisation.

Design principles:
  1. NO upward compression — never boost breath, room tone or residual noise.
  2. Downward-only compression controls loud peaks gently.
  3. Two-pass loudnorm when possible (measure → render with linear mode).
  4. Always force -ar 48000 to prevent FFmpeg loudnorm 192 kHz bug.
  5. Limiter calibrated to actual true-peak target (0.84 ≈ -1.5 dBFS).
  6. No duplicate highpass (voice_cleaner already does 80 Hz).
  7. No de-esser by default (treble boost is now ≤ +1 dB in cleaner).
  8. Social platform presets integrated — single normalisation pass.
"""

import json
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import soundfile as sf

from core.ffmpeg_runner import run_ffmpeg, FFmpegError
from core.importer import validate_input_file, MediaImportError


class VolumeLevelingError(Exception):
    """Exception raised for errors during volume leveling."""
    pass


# ---------------------------------------------------------------------------
# Volume Leveling Options
# ---------------------------------------------------------------------------

@dataclass
class VolumeLevelingOptions:
    preset: str = "natural"
    target_lufs: float = -16.0
    true_peak: float = -1.5
    loudness_range: float = 9.0
    social_platform: str = "general"
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    overwrite: bool = True
    # Voice-only mode keeps breaths and room tone at their original gain.
    # It is the default for the application's speech-first workflow.
    voice_only: bool = True


VALID_PRESETS = {"natural", "strong", "aggressive"}

_VOICE_FRAME_SECONDS = 0.020
_VOICE_ANALYSIS_BLOCK_FRAMES = 500
_VOICE_MIN_DB = -42.0
_VOICE_MAX_GAIN_DB = 10.0


@dataclass(frozen=True)
class _VoiceActivity:
    sample_rate: int
    frame_samples: int
    speech_mask: np.ndarray


# ---------------------------------------------------------------------------
# Social / Platform presets
# ---------------------------------------------------------------------------
# Each preset adjusts the loudnorm target values.  The pipeline calls
# volume leveling exactly ONCE — these presets replace the old separate
# SocialOptimizer step.
# ---------------------------------------------------------------------------

PLATFORM_PRESETS: Dict[str, Dict[str, float]] = {
    # One conservative target that travels safely across the major social-video
    # platforms.  It is the hidden default used by the pipeline.
    "social_safe":        {"lufs": -14.0, "tp": -1.0, "lra": 8.0,  "limiter": 0.89},
    "general":            {"lufs": -16.0, "tp": -1.5, "lra": 9.0,  "limiter": 0.84},
    "youtube_facebook_x": {"lufs": -14.0, "tp": -1.5, "lra": 10.0, "limiter": 0.84},
    "tiktok_instagram":   {"lufs": -14.0, "tp": -1.0, "lra": 8.0,  "limiter": 0.89},
    "podcast_voice":      {"lufs": -16.0, "tp": -1.5, "lra": 8.0,  "limiter": 0.84},
}


# ---------------------------------------------------------------------------
# Preset Descriptions
# ---------------------------------------------------------------------------
# natural   – Gentle downward-only compression + two-pass loudnorm.
#             Target: I=-16 LUFS / TP=-1.5 dBFS / LRA=9
#             No highpass (voice_cleaner already handles 80 Hz).
#             No de-esser (treble boost is now ≤ +1 dB).
#             compand points: no boost below -30 dBFS.
#
# strong    – dynaudnorm moderate leveling; good for podcasts / clean-room.
#
# aggressive – dynaudnorm fast leveling; for short-form / MMO game content.
# ---------------------------------------------------------------------------


def validate_preset(preset: str) -> str:
    """
    Validate and normalise the preset name.

    Raises:
        VolumeLevelingError: If the preset is not supported.
    """
    preset_lower = preset.lower()
    if preset_lower not in VALID_PRESETS:
        raise VolumeLevelingError(
            f"Invalid preset '{preset}'. Valid options are: {', '.join(sorted(VALID_PRESETS))}"
        )
    return preset_lower


def _resolve_loudness_targets(options: VolumeLevelingOptions) -> Dict[str, float]:
    """
    Resolve the final loudness targets by merging the volume preset with
    the social platform preset.

    Priority: social platform overrides the base preset defaults when the
    user has explicitly chosen a platform other than "general".
    """
    platform = options.social_platform
    if platform and platform in PLATFORM_PRESETS:
        p = PLATFORM_PRESETS[platform]
        return {
            "lufs": p["lufs"],
            "tp": p["tp"],
            "lra": p["lra"],
            "limiter": p["limiter"],
        }
    # Fallback: use options fields directly
    return {
        "lufs": options.target_lufs,
        "tp": options.true_peak,
        "lra": options.loudness_range,
        "limiter": 0.84,
    }


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Pre-filter helper and Two-pass loudnorm measurement
# ---------------------------------------------------------------------------

def get_pre_filter(preset: str) -> Optional[str]:
    """
    Return the pre-filter/compressor chain for the selected volume preset.
    Only Strong/Aggressive presets apply dynamic dynamic range control.
    """
    preset_lower = validate_preset(preset)
    if preset_lower == "natural":
        return None
    elif preset_lower == "strong":
        # Monotonic downward-only compand: preserves noise/breath floor below -30 dBFS
        return (
            "compand="
            "attacks=0.02:decays=0.25:"
            "points=-80/-80|-30/-30|-20/-20|-10/-16|0/-12:"
            "soft-knee=6"
        )
    elif preset_lower == "aggressive":
        # Fast dynaudnorm for MMO / short-form content
        return "dynaudnorm=f=150:g=15:p=0.95:m=10"
    return None


def _measure_loudness(
    input_path: Path,
    targets: Dict[str, float],
    pre_filter: Optional[str] = None,
) -> Optional[Dict[str, float]]:
    """
    Run loudnorm in measurement-only mode (first pass), applying the pre-filter
    before measurement to ensure identical signal conditions between pass 1 and pass 2.

    Returns measured values or None if measurement fails.
    """
    lufs = targets["lufs"]
    tp = targets["tp"]
    lra = targets["lra"]

    loudnorm_af = f"loudnorm=I={lufs}:TP={tp}:LRA={lra}:print_format=json"
    filter_chain = f"{pre_filter},{loudnorm_af}" if pre_filter else loudnorm_af

    args = [
        "-y",
        "-i", str(input_path),
        "-af", filter_chain,
        "-f", "null",
        "-",
    ]

    try:
        result = run_ffmpeg(args)
    except FFmpegError:
        return None

    stderr = result.stderr or ""

    # Find the JSON block in stderr
    json_match = re.search(r"\{[^}]*\"input_i\"[^}]*\}", stderr, re.DOTALL)
    if not json_match:
        return None

    try:
        data = json.loads(json_match.group())
        measured = {
            "measured_I": float(data.get("input_i", lufs)),
            "measured_TP": float(data.get("input_tp", tp)),
            "measured_LRA": float(data.get("input_lra", lra)),
            "measured_thresh": float(data.get("input_thresh", -70.0)),
            "offset": float(data.get("target_offset", 0.0)),
        }
        # Validate: FFmpeg loudnorm rejects -inf / inf / NaN values.
        # This happens when input is silent or near-silent.
        import math
        for key, val in measured.items():
            if math.isinf(val) or math.isnan(val):
                return None  # fall back to one-pass
        # FFmpeg loudnorm measured_I valid range is [-99, 0]
        if measured["measured_I"] < -99.0 or measured["measured_I"] > 0.0:
            return None
        return measured
    except (ValueError, KeyError, json.JSONDecodeError):
        return None


def build_volume_filter_chain(
    options: VolumeLevelingOptions,
    measured: Optional[Dict[str, float]] = None,
) -> str:
    """
    Build the FFmpeg ``-af`` filter chain string for the requested preset.

    If ``measured`` is provided (from two-pass loudnorm), the loudnorm
    filter uses linear mode with measured values for transparent processing.
    """
    preset = validate_preset(options.preset)
    targets = _resolve_loudness_targets(options)

    lufs = targets["lufs"]
    tp = targets["tp"]
    lra = targets["lra"]
    lim = targets["limiter"]

    pre_filter = get_pre_filter(preset)

    # ── Loudnorm ────────────────────────────────────────────────────
    if measured:
        loudnorm = (
            f"loudnorm=I={lufs}:TP={tp}:LRA={lra}"
            f":measured_I={measured['measured_I']}"
            f":measured_TP={measured['measured_TP']}"
            f":measured_LRA={measured['measured_LRA']}"
            f":measured_thresh={measured['measured_thresh']}"
            f":offset={measured['offset']}"
            f":linear=true"
        )
    else:
        loudnorm = f"loudnorm=I={lufs}:TP={tp}:LRA={lra}"

    # ── Limiter safety ──────────────────────────────────────────────
    # limit calibrated to actual true-peak target.
    # level=false prevents auto-level makeup gain which would clip.
    limiter = f"alimiter=limit={lim}:attack=5:release=50:level=false"

    filters = []
    if pre_filter:
        filters.append(pre_filter)
    filters.append(loudnorm)
    filters.append(limiter)

    return ",".join(filters)


def _analyse_voice_activity(input_path: Path) -> _VoiceActivity:
    """Build a lightweight voice mask without transcription or a model download.

    The detector works on 20 ms frames.  Speech normally has lower zero-crossing
    activity than an inhale/hiss; a short temporal support test prevents one
    noisy frame from being treated as speech.  It is deliberately conservative:
    missing a little voice is preferable to amplifying a breath or room tone.
    """
    try:
        with sf.SoundFile(str(input_path), "r") as source:
            sample_rate = int(source.samplerate)
            frame_samples = max(1, round(sample_rate * _VOICE_FRAME_SECONDS))
            block_samples = frame_samples * _VOICE_ANALYSIS_BLOCK_FRAMES
            rms_parts: List[np.ndarray] = []
            zcr_parts: List[np.ndarray] = []

            while True:
                block = source.read(block_samples, dtype="float32", always_2d=True)
                if block.size == 0:
                    break

                # The block size is an exact multiple of a frame.  Only the
                # final partial frame needs zero-padding.
                remainder = block.shape[0] % frame_samples
                if remainder:
                    block = np.pad(block, ((0, frame_samples - remainder), (0, 0)))

                mono_frames = block.mean(axis=1, dtype=np.float32).reshape(-1, frame_samples)
                rms = np.sqrt(np.mean(np.square(mono_frames), axis=1) + 1e-12)
                rms_parts.append(20.0 * np.log10(rms))
                crossings = np.count_nonzero(
                    np.diff(np.signbit(mono_frames), axis=1), axis=1
                )
                zcr_parts.append(crossings / max(1, frame_samples - 1))
    except Exception as exc:
        raise VolumeLevelingError(f"Could not analyse voice activity in '{input_path}': {exc}") from exc

    if not rms_parts:
        return _VoiceActivity(48000, 960, np.zeros(0, dtype=bool))

    rms_db = np.concatenate(rms_parts)
    zcr = np.concatenate(zcr_parts)
    # Use the quieter fifth of the material to set an adaptive energy gate,
    # but never raise it above -32 dB.  Soft speech remains eligible while a
    # very quiet room does not turn every tiny fluctuation into "voice".
    noise_floor = float(np.percentile(rms_db, 20))
    energy_gate = min(-32.0, max(_VOICE_MIN_DB, noise_floor + 10.0))
    candidate = (rms_db >= energy_gate) & (zcr <= 0.18)

    # A syllable normally produces several nearby voiced frames.  Requiring
    # two hits inside 100 ms rejects isolated breath/noise frames.  Then keep
    # a short *tail only* for unvoiced consonants; no pre-roll means an inhale
    # immediately before speech remains at its original gain.
    support = np.convolve(candidate.astype(np.int8), np.ones(5, dtype=np.int8), mode="same") >= 2
    speech_mask = support.copy()
    for shift in range(1, 5):
        speech_mask[shift:] |= support[:-shift]

    return _VoiceActivity(
        sample_rate=sample_rate,
        frame_samples=max(1, round(sample_rate * _VOICE_FRAME_SECONDS)),
        speech_mask=speech_mask,
    )


def _write_speech_reference(input_path: Path, output_path: Path, activity: _VoiceActivity) -> int:
    """Write only speech-marked frames for fast speech-loudness measurement."""
    written_samples = 0
    with sf.SoundFile(str(input_path), "r") as source, sf.SoundFile(
        str(output_path), "w", samplerate=source.samplerate,
        channels=source.channels, subtype="FLOAT",
    ) as destination:
        position = 0
        while True:
            block = source.read(65536, dtype="float32", always_2d=True)
            if block.size == 0:
                break
            frame_indexes = (np.arange(block.shape[0]) + position) // activity.frame_samples
            frame_indexes = np.minimum(frame_indexes, activity.speech_mask.size - 1)
            keep = activity.speech_mask[frame_indexes] if activity.speech_mask.size else np.zeros(block.shape[0], dtype=bool)
            if np.any(keep):
                selected = block[keep]
                destination.write(selected)
                written_samples += selected.shape[0]
            position += block.shape[0]
    return written_samples


def _apply_voice_gain(
    input_path: Path,
    output_path: Path,
    activity: _VoiceActivity,
    gain_db: float,
) -> None:
    """Apply a smooth gain envelope to speech only; leave all other samples raw."""
    gain_linear = float(10.0 ** (gain_db / 20.0))
    frame_gain = np.where(activity.speech_mask, gain_linear, 1.0).astype(np.float32)
    # Nodes are placed at frame ends, making the gain fade in after a speech
    # frame starts instead of boosting the breath just before it.
    node_positions = np.arange(frame_gain.size, dtype=np.float64) + 1.0

    with sf.SoundFile(str(input_path), "r") as source, sf.SoundFile(
        str(output_path), "w", samplerate=source.samplerate,
        channels=source.channels, subtype="FLOAT",
    ) as destination:
        position = 0
        while True:
            block = source.read(65536, dtype="float32", always_2d=True)
            if block.size == 0:
                break
            if frame_gain.size:
                frame_positions = (np.arange(block.shape[0], dtype=np.float64) + position) / activity.frame_samples
                envelope = np.interp(frame_positions, node_positions, frame_gain, left=1.0, right=float(frame_gain[-1]))
                block *= envelope.astype(np.float32)[:, None]
            destination.write(block)
            position += block.shape[0]


def _render_limiter(input_path: Path, output_path: Path, overwrite: bool, limit: float) -> Path:
    """Apply the single final peak safeguard without any makeup gain."""
    run_ffmpeg([
        "-y" if overwrite else "-n", "-i", str(input_path),
        "-af", f"alimiter=limit={limit}:attack=5:release=50:level=false",
        "-ar", "48000", "-c:a", "pcm_f32le", str(output_path),
    ])
    return output_path


def apply_delivery_limiter(
    input_path: Path,
    output_path: Path,
    options: Optional[VolumeLevelingOptions] = None,
) -> Path:
    """Keep the non-optional delivery peak safeguard without changing loudness."""
    if options is None:
        options = VolumeLevelingOptions()
    try:
        input_path_obj = validate_input_file(input_path)
    except MediaImportError as e:
        raise VolumeLevelingError(f"Invalid input file: {e}") from e

    output_path_obj = Path(output_path)
    if output_path_obj.exists() and not options.overwrite:
        raise VolumeLevelingError(
            f"Output file already exists and overwrite is False: {output_path_obj}"
        )
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    targets = _resolve_loudness_targets(options)
    try:
        return _render_limiter(input_path_obj, output_path_obj, options.overwrite, targets["limiter"])
    except FFmpegError as e:
        raise VolumeLevelingError(
            f"Failed to apply delivery peak protection to '{input_path_obj}': {e}"
        ) from e


def _level_voice_only(input_path: Path, output_path: Path, options: VolumeLevelingOptions) -> Path:
    """Normalise speech loudness while leaving breaths/background untouched."""
    activity = _analyse_voice_activity(input_path)
    targets = _resolve_loudness_targets(options)

    with tempfile.TemporaryDirectory(prefix="audio_factory_voice_level_") as temp_dir:
        temp_root = Path(temp_dir)
        speech_reference = temp_root / "speech_reference.wav"
        speech_samples = _write_speech_reference(input_path, speech_reference, activity)

        if speech_samples:
            measured = _measure_loudness(speech_reference, targets)
            # ``target_offset`` is not reliable for short, low-LRA material
            # (for example a single steady TTS phrase).  Speech-only leveling
            # needs the direct integrated-loudness difference instead.
            gain_db = (targets["lufs"] - float(measured["measured_I"])) if measured else 0.0
            gain_db = max(-_VOICE_MAX_GAIN_DB, min(_VOICE_MAX_GAIN_DB, gain_db))
        else:
            gain_db = 0.0

        gain_applied = temp_root / "voice_gain_applied.wav"
        _apply_voice_gain(input_path, gain_applied, activity, gain_db)
        return _render_limiter(gain_applied, output_path, options.overwrite, targets["limiter"])


def level_volume(
    input_path: Path,
    output_path: Path,
    options: Optional[VolumeLevelingOptions] = None,
) -> Path:
    """
    Apply volume leveling to a single audio file.

    For the default ``natural`` preset, performs Voice-only leveling: speech
    receives the calculated gain while breaths and room tone keep their source
    gain. Other legacy presets retain the original two-pass loudnorm path.
    Output always includes ``-ar 48000`` to prevent FFmpeg's loudnorm
    from silently upsampling to 192 kHz.

    Output uses WAV PCM float32 (pipeline internal format).

    Args:
        input_path:  Path to the source audio file.
        output_path: Destination path for the leveled audio file.
        options:     Leveling options; defaults to VolumeLevelingOptions().

    Returns:
        The resolved output Path on success.

    Raises:
        VolumeLevelingError: On invalid input or FFmpeg processing failure.
    """
    if options is None:
        options = VolumeLevelingOptions()

    try:
        input_path_obj = validate_input_file(input_path)
    except MediaImportError as e:
        raise VolumeLevelingError(f"Invalid input file: {e}") from e

    output_path_obj = Path(output_path)

    if output_path_obj.exists() and not options.overwrite:
        raise VolumeLevelingError(
            f"Output file already exists and overwrite is False: {output_path_obj}"
        )

    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    preset = validate_preset(options.preset)
    if options.voice_only and preset == "natural":
        try:
            return _level_voice_only(input_path_obj, output_path_obj, options)
        except (FFmpegError, OSError, RuntimeError) as e:
            raise VolumeLevelingError(
                f"Failed to apply voice-only volume leveling to '{input_path_obj}': {e}"
            ) from e

    # ── Two-pass loudnorm measurement ─────────────────────────────
    pre_filter = get_pre_filter(preset)
    targets = _resolve_loudness_targets(options)

    measured = _measure_loudness(input_path_obj, targets, pre_filter=pre_filter)
    # If measurement fails, falls back to one-pass (measured = None)

    filter_chain = build_volume_filter_chain(options, measured)
    overwrite_flag = "-y" if options.overwrite else "-n"

    args = [
        overwrite_flag,
        "-i", str(input_path_obj),
        "-af", filter_chain,
        "-ar", "48000",          # ← force 48 kHz, prevent 192 kHz bug
        "-c:a", "pcm_f32le",    # ← lossless intermediate
        str(output_path_obj),
    ]

    try:
        run_ffmpeg(args)
        return output_path_obj
    except FFmpegError as e:
        raise VolumeLevelingError(
            f"Failed to level volume of '{input_path_obj}': {e}"
        ) from e


def level_volume_batch(
    input_paths: List[Path],
    output_dir: Path,
    options: Optional[VolumeLevelingOptions] = None,
) -> List[Path]:
    """
    Apply volume leveling to a list of audio files.

    Each output file is saved to ``output_dir`` with a ``_leveled`` suffix
    appended to the original stem.

    Returns:
        List of resolved output Paths.

    Raises:
        VolumeLevelingError: If any file in the batch fails.
    """
    if options is None:
        options = VolumeLevelingOptions()

    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    leveled_paths: List[Path] = []
    for path in input_paths:
        input_path_obj = Path(path)
        output_file = output_dir_obj / f"{input_path_obj.stem}_leveled{input_path_obj.suffix}"

        try:
            leveled = level_volume(input_path_obj, output_file, options)
            leveled_paths.append(leveled)
        except Exception as e:
            raise VolumeLevelingError(
                f"Batch execution failed on file '{input_path_obj}': {e}"
            ) from e

    return leveled_paths

"""
Audio Factory Pipeline — DSP-optimised architecture.

Processing order (correct for audio quality):
  1. Normalise each input to internal PCM (WAV f32le 48 kHz stereo)
  2. Clean/Denoise per-file (if enabled)
  3. Silence Shortening per-file (if enabled)
  4. Merge processed files + insert gaps (if enabled)
  5. Volume/Loudness normalisation once (if enabled) — with social preset
  6. Final encode to output format (lossy encode happens exactly once)

Key invariants:
  - Clean runs before Silence
  - Silence runs before Volume
  - Silence runs before Merge (per-file)
  - Merge gaps are inserted AFTER silence shortening (never shortened)
  - Volume normalisation runs AFTER merge (once, not per-file)
  - Social Optimizer presets are folded into Volume — no second loudnorm
  - All intermediate files are WAV PCM f32le 48 kHz
  - Lossy encoding (MP3/AAC/OGG) happens exactly once at final export
"""

import os
import re
import datetime
import shutil
import json
import logging
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Callable, List, Dict, Any, Optional

from core.ffmpeg_runner import run_ffmpeg, FFmpegError
from core.importer import validate_input_file, normalize_to_pcm, adjust_audio_speed, get_duration_seconds, MediaImportError
from core.merger import merge_audio_files, MergeOptions, AudioMergeError
from core.volume_leveler import level_volume, apply_delivery_limiter, VolumeLevelingOptions, VolumeLevelingError
from core.silence_shortener import shorten_silence, SilenceShortenerOptions, options_from_preset, SilenceShortenerError
from core.transcriber import transcribe_media, TranscriptionOptions, model_size_from_preset, TranscriptionError, SubtitleCoverageError, detect_speech_regions
from core.subtitle_exporter import export_all_subtitles, export_srt
from core.sentence_splitter import split_segments_by_sentence, SentenceSplitOptions, SentenceSplitError
from core.audio_cutter import cut_audio_by_sentences, AudioCutOptions, AudioCutError
from core.metadata_exporter import build_project_metadata, export_project_json
from core.voice_cleaner import clean_voice, VoiceCleanerError, VoiceCleanerOptions
from core.social_optimizer import optimize_social_audio, SocialOptimizerError
from core.subtitle_optimizer import optimize_subtitles, SubtitleOptimizerError

logger = logging.getLogger(__name__)

class PipelineError(Exception):
    """Exception raised for errors during pipeline processing."""
    pass


@dataclass
class PipelineOptions:
    merge_first: bool = False
    enable_voice_cleanup: bool = False
    enable_volume_leveling: bool = True
    enable_silence_shortening: bool = True
    # Peak protection is always applied at delivery.  Voice-only loudness
    # leveling remains controlled by the visible volume switch.
    enable_social_optimize: bool = True
    social_platform: str = "social_safe"
    enable_transcription: bool = False
    enable_subtitle_export: bool = False
    output_format: str = "wav"
    audio_speed: float = 1.0
    project_name: str = "audio_project"
    overwrite: bool = True
    merge_gap_seconds: float = 0.0
    volume_preset: str = "natural"
    # The UI exposes one switch only; Auto is the internal TTS-safe policy.
    silence_preset: str = "auto"
    clean_preset: str = "auto"
    transcription_preset: str = "balanced"
    subtitle_base_name: str = "subtitles"
    language: Optional[str] = None
    whisper_model: str = "large-v3-turbo"
    asr_audio_speed: float = 1.0
    batch_size: int = 8
    target_video_format: str = "horizontal"
    # Film/streaming subtitles may use a second line to preserve natural
    # sentence breaks instead of forcing a rapid run of one-line cues.
    subtitle_lines: int = 2
    # Tính năng #5: Dịch phụ đề đa ngôn ngữ
    enable_translation: bool = False
    translation_engine: str = "google"
    translation_target_lang: str = "vi"
    translation_api_key: str = ""
    # Keep deprecated options for compatibility
    enable_sentence_split: bool = False
    enable_audio_cutting: bool = False
    strict_coverage: bool = False
    debug_mode: bool = False
    subtitle_sync_offset_ms: float = 0.0
    recovery_pass_enabled: bool = True
    strict_subtitle_validation: bool = False


@dataclass
class PipelineResult:
    project_name: str
    output_dir: str
    input_files: List[str]
    working_audio: Optional[str] = None
    merged_file: Optional[str] = None
    leveled_file: Optional[str] = None
    shortened_file: Optional[str] = None
    subtitle_files: Optional[Dict[str, str]] = None
    chunks: Optional[List[Dict[str, Any]]] = None
    metadata_file: Optional[str] = None
    # Tính năng #5: Danh sách đường dẫn file SRT gốc để TranslationWorker feed vào
    srt_paths: Optional[List[str]] = None


def validate_pipeline_inputs(input_paths: List[Path]) -> List[Path]:
    """
    Validate all input paths for the pipeline.
    """
    if not input_paths:
        raise PipelineError("Input path list is empty.")
        
    validated = []
    for path in input_paths:
        try:
            val = validate_input_file(path)
            validated.append(val)
        except MediaImportError as e:
            raise PipelineError(f"Invalid input file '{path}': {e}") from e
            
    return validated


def _object_value(obj: Any, key: str, default: Any = None) -> Any:
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def _offset_transcript_segments(
    segments: List[Any],
    offset_seconds: float,
    source_file_index: int,
    starting_index: int = 1,
) -> List[Dict[str, Any]]:
    """Copy ASR segments onto a merged timeline without losing file identity."""
    shifted: List[Dict[str, Any]] = []
    offset = max(0.0, float(offset_seconds))
    boundary_pending = source_file_index > 0

    for segment in segments:
        words_payload = []
        for raw_word in (_object_value(segment, "words", None) or []):
            if isinstance(raw_word, dict):
                word = dict(raw_word)
            else:
                word = {
                    "word": _object_value(raw_word, "word", _object_value(raw_word, "text", "")),
                    "start": _object_value(raw_word, "start", 0.0),
                    "end": _object_value(raw_word, "end", 0.0),
                    "probability": _object_value(raw_word, "probability", None),
                }
            if word.get("start") is not None:
                word["start"] = float(word["start"]) + offset
            if word.get("end") is not None:
                word["end"] = float(word["end"]) + offset
            words_payload.append(word)

        text = str(_object_value(segment, "text", "") or "").strip()
        if not text and not words_payload:
            continue
        shifted.append({
            "index": starting_index + len(shifted),
            "start": float(_object_value(segment, "start", 0.0) or 0.0) + offset,
            "end": float(_object_value(segment, "end", 0.0) or 0.0) + offset,
            "text": text,
            "words": words_payload or None,
            "source_file_index": source_file_index,
            "source_boundary_before": boundary_pending,
        })
        boundary_pending = False

    return shifted


def _offset_time_regions(
    regions: List[Any],
    offset_seconds: float,
    source_file_index: int,
) -> List[Dict[str, Any]]:
    """Shift optional ASR recovery diagnostics onto a merged timeline."""
    shifted: List[Dict[str, Any]] = []
    offset = max(0.0, float(offset_seconds))
    for region in regions or []:
        payload = dict(region) if isinstance(region, dict) else {
            "start": _object_value(region, "start", 0.0),
            "end": _object_value(region, "end", 0.0),
        }
        if payload.get("start") is not None:
            payload["start"] = float(payload["start"]) + offset
        if payload.get("end") is not None:
            payload["end"] = float(payload["end"]) + offset
        payload["source_file_index"] = source_file_index
        shifted.append(payload)
    return shifted


def prepare_output_dirs(output_dir: Path) -> Dict[str, Path]:
    """
    Return temporary working subdirectories (work, metadata).
    These are cleaned up after successful pipeline completion.
    The final audio and subtitle files are written directly to output_dir.
    """
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)

    dirs = {
        "work":     output_dir_obj / "work",
        "metadata": output_dir_obj / "metadata",
        # kept for legacy compatibility in case any caller still references these keys
        "subtitles": output_dir_obj / "subtitles",
        "final":     output_dir_obj / "final",
    }

    # Only create the two dirs actually needed during processing
    for key in ("work", "metadata"):
        dirs[key].mkdir(parents=True, exist_ok=True)

    return dirs


def _cleanup_temp_dirs(project_dir: Path, dirs: Dict[str, Path]) -> None:
    """
    Remove all temporary subdirectories that were created during pipeline processing.
    Only deletes directories that are confirmed children of project_dir.
    Never touches files located directly inside project_dir (the final outputs).
    """
    for key in ("work", "metadata", "subtitles", "final"):
        candidate = dirs.get(key)
        if candidate is None:
            continue
        try:
            # Safety: confirm the dir is inside the project directory
            candidate.resolve().relative_to(project_dir.resolve())
        except ValueError:
            continue  # Not a child of project_dir — never delete
        if candidate.exists() and candidate.is_dir():
            try:
                shutil.rmtree(candidate)
            except Exception:
                pass  # Best-effort: log failure silently, don't abort success path


# ---------------------------------------------------------------------------
# Final Export — single lossy encode
# ---------------------------------------------------------------------------

_CODEC_MAP = {
    "wav":  ["-c:a", "pcm_s16le"],
    "mp3":  ["-c:a", "libmp3lame", "-q:a", "2"],
    "m4a":  ["-c:a", "aac", "-b:a", "192k"],
    "flac": ["-c:a", "flac"],
    "ogg":  ["-c:a", "libvorbis", "-q:a", "5"],
}


def _export_audio(
    source: Path,
    dest: Path,
    output_format: str,
    project_dir: Path,
) -> None:
    """
    Write *source* audio to *dest* in the requested format.

    This is the ONLY place where lossy encoding happens.
    Source is always internal PCM f32le; dest gets the final codec.

    For WAV output: convert from f32le to s16le (with dithering via SoX).
    For FLAC: lossless compression from f32le.
    For MP3/AAC/OGG: single lossy encode.

    Always forces -ar 48000 on output.
    """
    ext = output_format.lower()
    codec_args = _CODEC_MAP.get(ext, [])

    same_format = source.suffix.lower() == f".{ext}"
    in_project = (source.parent.resolve() == project_dir.resolve())

    if same_format and in_project and ext == "wav":
        # Source is already WAV at the correct location — just copy.
        # Note: it may be f32le; if user expects s16le we should convert.
        # For safety, always convert to final format.
        pass  # fall through to FFmpeg conversion

    # Encode/remux via FFmpeg into the flat destination.
    args = [
        "-y",
        "-i", str(source),
    ] + codec_args + [
        "-ar", "48000",
        str(dest),
    ]

    try:
        run_ffmpeg(args)
    except Exception as exc:
        raise PipelineError(f"Failed to export final audio to '{dest}': {exc}") from exc


# ---------------------------------------------------------------------------
# Core pipeline
# ---------------------------------------------------------------------------

class MonotonicProgressTracker:
    def __init__(self, total_ops: int, progress_cb: Optional[Callable[[int, str], None]] = None):
        self.total_ops = total_ops
        self.completed_ops = 0
        self.last_progress = 0
        self.progress_cb = progress_cb

    def update_op_complete(self, status_msg: str):
        self.completed_ops += 1
        pct = int(100 * self.completed_ops / self.total_ops)
        if pct > self.last_progress:
            self.last_progress = min(pct, 99) # Keep 100 for final success
        if self.progress_cb:
            self.progress_cb(self.last_progress, status_msg)


def run_audio_pipeline(
    input_paths: List[Path],
    output_dir: Path,
    options: Optional[PipelineOptions] = None,
    status_callback: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    project_dir_callback: Optional[Callable[[Path], None]] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> PipelineResult:
    """
    Run the end-to-end audio processing pipeline on input files.
    """
    if options is None:
        options = PipelineOptions()
        
    def update_status(msg: str):
        if status_callback:
            status_callback(msg)

    # Log Audio DSP and Whisper backends at start
    update_status("Audio DSP backend: CPU / FFmpeg audio filters")
    from core.transcriber import detect_best_backend
    backend = detect_best_backend()
    update_status(f"Whisper backend selected: {backend.device.upper()} / {backend.compute_type}")

    update_status("Validating input paths...")
    validated_inputs = validate_pipeline_inputs(input_paths)
    
    # Early language validation
    from core.language_options import resolve_language_code
    try:
        options.language = resolve_language_code(options.language)
    except ValueError as e:
        raise PipelineError(str(e)) from e

    # Validate output format
    valid_formats = {"wav", "mp3", "m4a", "flac", "ogg"}
    fmt = options.output_format.lower().lstrip(".")
    if fmt not in valid_formats:
        raise PipelineError(f"Unsupported output format: '{options.output_format}'. Valid options: {', '.join(sorted(valid_formats))}")
    options.output_format = fmt

    # The final delivery pass is intentionally always on.  Keeping the option
    # for backward-compatible callers must not let a UI or legacy config skip
    # loudness/peak protection.
    options.enable_social_optimize = True

    # Validate social platform
    valid_platforms = {"social_safe", "general", "youtube_facebook_x", "tiktok_instagram", "podcast_voice"}
    if options.social_platform not in valid_platforms:
        raise PipelineError(f"Unsupported social platform preset: '{options.social_platform}'. Valid options: {', '.join(sorted(valid_platforms))}")
        
    output_dir_obj = Path(output_dir)
    
    # 1. Resolve a new project directory with safety suffix increments.
    # A run must never reuse an existing project folder: the UI deletes the
    # resolved folder on cancellation, so reusing an older folder could delete
    # a previous completed project.
    def sanitize_folder_name(name: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

    if not options.project_name or options.project_name.strip() == "":
        first_stem = validated_inputs[0].stem
        sanitized_stem = sanitize_folder_name(first_stem)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        proj_folder_name = f"{sanitized_stem}_{timestamp}"
    else:
        proj_folder_name = sanitize_folder_name(options.project_name)

    final_project_dir = Path(output_dir) / proj_folder_name
    if final_project_dir.exists():
        suffix = 1
        while True:
            candidate = Path(output_dir) / f"{proj_folder_name}_{suffix:02d}"
            if not candidate.exists():
                final_project_dir = candidate
                break
            suffix += 1

    # Update options.project_name to match resolved folder name
    options.project_name = final_project_dir.name

    # Notify caller about resolved project directory path
    if project_dir_callback:
        project_dir_callback(final_project_dir)

    # Initialize Monotonic Progress Tracker
    N = len(validated_inputs)
    total_ops = N # Normalize is always done per-file
    if options.enable_voice_cleanup:
        total_ops += N
    if options.enable_silence_shortening:
        total_ops += N
        
    if options.merge_first and N > 1:
        total_ops += 1 # Merge step
        if options.enable_volume_leveling or options.enable_social_optimize:
            total_ops += 1
        total_ops += 1 # Export
        if options.enable_transcription:
            total_ops += N
    else:
        if options.enable_volume_leveling or options.enable_social_optimize:
            total_ops += N
        total_ops += N # Export
        if options.enable_transcription:
            total_ops += N

    tracker = MonotonicProgressTracker(total_ops, progress_callback)

    update_status(f"Creating project directories under {final_project_dir}...")
    dirs = prepare_output_dirs(final_project_dir)
    
    merged_file_path = None
    final_audio_paths = []
    subtitle_files_dict = {}
    srt_paths_list: List[Path] = []

    coordinator = None
    coordinator_thread = None
    if options.enable_transcription and options.enable_translation and options.translation_engine != "google" and options.translation_api_key.strip():
        try:
            import threading
            from core.translator import TranslationCoordinator, TranslationConfig, PRIMARY_MODEL_A, PRIMARY_MODEL_B
            api_keys = [k.strip() for k in options.translation_api_key.replace(",", "\n").split("\n") if k.strip()]
            config = TranslationConfig(max_workers=options.batch_size)
            coordinator = TranslationCoordinator(
                api_keys=api_keys,
                primary_model_a=PRIMARY_MODEL_A,
                primary_model_b=PRIMARY_MODEL_B,
                config=config,
                status_callback=update_status,
                cancel_check=cancel_check,
            )
            coordinator_thread = threading.Thread(target=coordinator.process_all_jobs, daemon=True)
            coordinator_thread.start()
        except Exception as exc:
            pass

    try:
        if options.merge_first:
            # ══════════════════════════════════════════════════════════════
            # MERGE MODE: Process each file individually, then merge
            # ══════════════════════════════════════════════════════════════
            if len(validated_inputs) > 1:
                processed_files: List[Path] = []

                for idx, input_path in enumerate(validated_inputs, 1):
                    update_status(f"Normalizing input {idx}/{len(validated_inputs)}: {input_path.name}...")
                    pcm_file = dirs["work"] / f"{idx:03d}_{input_path.stem}.wav"
                    try:
                        current_audio = normalize_to_pcm(input_path, pcm_file)
                        tracker.update_op_complete(f"[{input_path.name}] Normalized")
                    except MediaImportError as e:
                        raise PipelineError(f"Failed to normalize '{input_path}': {e}") from e

                    # A.0 Audio Speed Adjustment (if speed != 1.0)
                    if abs(options.audio_speed - 1.0) > 0.001:
                        update_status(f"[{input_path.name}] Adjusting audio speed to {options.audio_speed:.2f}x...")
                        speed_file = dirs["work"] / f"{idx:03d}_{input_path.stem}_speed.wav"
                        try:
                            current_audio = adjust_audio_speed(current_audio, speed_file, options.audio_speed)
                            tracker.update_op_complete(f"[{input_path.name}] Speed adjusted ({options.audio_speed:.2f}x)")
                        except MediaImportError as e:
                            raise PipelineError(f"Failed in audio speed adjustment on '{input_path}': {e}") from e

                    # A. Voice Cleanup (per-file)
                    if options.enable_voice_cleanup:
                        update_status(f"[{input_path.name}] Applying voice cleanup...")
                        cleaned_file = dirs["work"] / f"{idx:03d}_{input_path.stem}_cleaned.wav"
                        try:
                            clean_opts = VoiceCleanerOptions(
                                preset=options.clean_preset,
                                overwrite=options.overwrite,
                            )
                            current_audio = clean_voice(current_audio, cleaned_file, options=clean_opts)
                            tracker.update_op_complete(f"[{input_path.name}] Voice cleaned")
                        except VoiceCleanerError as e:
                            raise PipelineError(f"Failed in voice cleaner step on '{input_path}': {e}") from e

                    # B. Silence Shortening (per-file, BEFORE merge)
                    if options.enable_silence_shortening:
                        update_status(f"[{input_path.name}] Shortening silence...")
                        shortened_file = dirs["work"] / f"{idx:03d}_{input_path.stem}_shortened.wav"
                        try:
                            sil_opts = options_from_preset(options.silence_preset)
                            sil_opts.overwrite = options.overwrite
                            current_audio = shorten_silence(current_audio, shortened_file, sil_opts)
                            tracker.update_op_complete(f"[{input_path.name}] Silence shortened")
                        except SilenceShortenerError as e:
                            raise PipelineError(f"Failed in silence shortening on '{input_path}': {e}") from e

                    processed_files.append(current_audio)

                # ── Merge processed files ────────────────────────────────
                update_status("Merging processed audio files...")
                merged_file = dirs["work"] / "merged.wav"
                merge_opts = MergeOptions(
                    gap_seconds=options.merge_gap_seconds,
                    output_format="wav",
                    sample_rate=48000,
                    channels=2,
                    overwrite=options.overwrite,
                )
                try:
                    current_audio = merge_audio_files(processed_files, merged_file, merge_opts)
                    merged_file_path = current_audio
                    tracker.update_op_complete("Merged audio files")
                except AudioMergeError as e:
                    raise PipelineError(f"Failed in merger step: {e}") from e

            else:
                # Single file with merge_first=True — skip merge
                update_status("Merge requested but only one input file provided. Skipping merge step safely.")
                input_path = validated_inputs[0]

                pcm_file = dirs["work"] / f"001_{input_path.stem}.wav"
                try:
                    current_audio = normalize_to_pcm(input_path, pcm_file)
                    tracker.update_op_complete(f"[{input_path.name}] Normalized")
                except MediaImportError as e:
                    raise PipelineError(f"Failed to normalize '{input_path}': {e}") from e

                # Audio Speed Adjustment (if speed != 1.0)
                if abs(options.audio_speed - 1.0) > 0.001:
                    update_status(f"Adjusting audio speed to {options.audio_speed:.2f}x...")
                    speed_file = dirs["work"] / f"001_{input_path.stem}_speed.wav"
                    try:
                        current_audio = adjust_audio_speed(current_audio, speed_file, options.audio_speed)
                        tracker.update_op_complete(f"[{input_path.name}] Speed adjusted ({options.audio_speed:.2f}x)")
                    except MediaImportError as e:
                        raise PipelineError(f"Failed in audio speed adjustment: {e}") from e

                # A. Voice Cleanup
                if options.enable_voice_cleanup:
                    update_status("Applying voice cleanup...")
                    cleaned_file = dirs["work"] / f"001_{input_path.stem}_cleaned.wav"
                    try:
                        clean_opts = VoiceCleanerOptions(
                            preset=options.clean_preset,
                            overwrite=options.overwrite,
                        )
                        current_audio = clean_voice(current_audio, cleaned_file, options=clean_opts)
                        tracker.update_op_complete(f"[{input_path.name}] Voice cleaned")
                    except VoiceCleanerError as e:
                        raise PipelineError(f"Failed in voice cleaner step: {e}") from e

                # B. Silence Shortening
                if options.enable_silence_shortening:
                    update_status("Shortening silence...")
                    shortened_file = dirs["work"] / f"001_{input_path.stem}_shortened.wav"
                    try:
                        sil_opts = options_from_preset(options.silence_preset)
                        sil_opts.overwrite = options.overwrite
                        current_audio = shorten_silence(current_audio, shortened_file, sil_opts)
                        tracker.update_op_complete(f"[{input_path.name}] Silence shortened")
                    except SilenceShortenerError as e:
                        raise PipelineError(f"Failed in silence shortening: {e}") from e

                merged_file_path = None

            # ── Post-merge: Voice level or delivery peak protection ─────
            if options.enable_volume_leveling or options.enable_social_optimize:
                leveled_file = dirs["work"] / "leveled.wav"
                vol_opts = VolumeLevelingOptions(
                    preset=options.volume_preset,
                    social_platform=options.social_platform if options.enable_social_optimize else "general",
                    overwrite=options.overwrite,
                )
                try:
                    if options.enable_volume_leveling:
                        update_status("Applying voice-only volume leveling (social-safe)...")
                        current_audio = level_volume(current_audio, leveled_file, vol_opts)
                        tracker.update_op_complete("Leveled voice volume")
                    else:
                        update_status("Applying delivery peak protection...")
                        current_audio = apply_delivery_limiter(current_audio, leveled_file, vol_opts)
                        tracker.update_op_complete("Protected delivery peak")
                except VolumeLevelingError as e:
                    raise PipelineError(f"Failed in volume leveling step: {e}") from e

            # ── Final export (single lossy encode) ───────────────────────
            update_status("Exporting final audio...")
            _merge_stem = validated_inputs[0].stem
            final_audio_path = final_project_dir / f"{_merge_stem}_processed.{options.output_format}"
            _export_audio(current_audio, final_audio_path, options.output_format, final_project_dir)
            final_audio_paths = [final_audio_path]
            tracker.update_op_complete("Exported final audio")

            # ── Auto Sub ─────────────────────────────────────────────────
            if options.enable_transcription:
                update_status("Running speech-to-text transcription...")
                try:
                    model_size = options.whisper_model if options.whisper_model else model_size_from_preset(options.transcription_preset)
                    trans_opts = TranscriptionOptions(
                        model_size=model_size,
                        language=options.language,
                        device=backend.device,
                        compute_type=backend.compute_type,
                        asr_audio_speed=options.asr_audio_speed,
                        batch_size=options.batch_size,
                        word_timestamps=options.enable_subtitle_export,
                        strict_coverage=options.strict_coverage,
                        subtitle_sync_offset_ms=options.subtitle_sync_offset_ms,
                        recovery_pass_enabled=options.recovery_pass_enabled,
                    )
                    # For a real multi-file merge, transcribe each processed
                    # source independently.  This prevents Whisper from joining
                    # the end of one file to the beginning of the next.  The
                    # timestamps are then shifted onto the exact merged timeline.
                    if options.merge_first and len(validated_inputs) > 1:
                        segments = []
                        source_offset = 0.0
                        trans_result = None
                        recovered_regions = []
                        unresolved_regions = []
                        for source_index, source_audio in enumerate(processed_files):
                            update_status(
                                f"Transcribing merged source {source_index + 1}/{len(processed_files)}: "
                                f"{validated_inputs[source_index].name}..."
                            )
                            source_result = transcribe_media(source_audio, trans_opts, cancel_check=cancel_check)
                            source_segments = (
                                source_result.segments if hasattr(source_result, "segments") else source_result
                            )
                            shifted = _offset_transcript_segments(
                                list(source_segments),
                                source_offset,
                                source_index,
                                starting_index=len(segments) + 1,
                            )
                            segments.extend(shifted)
                            trans_result = source_result
                            recovered_regions.extend(_offset_time_regions(
                                getattr(source_result, "recovered_regions", []) or [],
                                source_offset,
                                source_index,
                            ))
                            unresolved_regions.extend(_offset_time_regions(
                                getattr(source_result, "unresolved_regions", []) or [],
                                source_offset,
                                source_index,
                            ))
                            tracker.update_op_complete(
                                f"[{validated_inputs[source_index].name}] Speech transcribed"
                            )

                            if source_index < len(processed_files) - 1:
                                source_duration = get_duration_seconds(source_audio)
                                source_offset += source_duration + max(0.0, options.merge_gap_seconds)
                    else:
                        # Single input: transcribe the final lossless WAV.
                        trans_result = transcribe_media(current_audio, trans_opts, cancel_check=cancel_check)
                        if hasattr(trans_result, "segments"):
                            segments = trans_result.segments
                        else:
                            segments = trans_result
                        recovered_regions = getattr(trans_result, "recovered_regions", [])
                        unresolved_regions = getattr(trans_result, "unresolved_regions", [])
                        tracker.update_op_complete("Speech transcribed")

                    # Handle fallback properties for mock/legacy list results
                    backend_used = getattr(trans_result, "backend_used", "CPU")
                    batch_size_used = getattr(trans_result, "batch_size_used", options.batch_size)
                    vad_used = getattr(trans_result, "vad_used", True)
                    vad_parameters = getattr(trans_result, "vad_parameters", {})
                    model_used = getattr(trans_result, "model_used", model_size)
                    language_used = getattr(trans_result, "language", options.language or "auto")
                    recovered_regions = recovered_regions or []
                    unresolved_regions = unresolved_regions or []

                    if options.debug_mode:
                        update_status("Saving transcription diagnostics...")
                        raw_data = {
                            "segments": [
                                {
                                    "index": _object_value(seg, "index"),
                                    "start": _object_value(seg, "start"),
                                    "end": _object_value(seg, "end"),
                                    "text": _object_value(seg, "text", ""),
                                    "words": _object_value(seg, "words", None),
                                    "source_file_index": _object_value(seg, "source_file_index", None),
                                    "source_boundary_before": _object_value(seg, "source_boundary_before", False),
                                }
                                for seg in segments
                            ],
                            "metadata": {
                                "backend_used": backend_used,
                                "batch_size_used": batch_size_used,
                                "vad_filter": vad_used,
                                "vad_parameters": vad_parameters,
                                "model": model_used,
                                "language": language_used,
                                "asr_audio_speed": options.asr_audio_speed
                            }
                        }
                        # Disabled raw whisper debug JSON output
                        # with open(final_project_dir / "raw_whisper_segments.json", "w", encoding="utf-8") as df:
                        #     json.dump(raw_data, df, indent=2, ensure_ascii=False)

                    if options.enable_subtitle_export and segments:
                        update_status("Optimizing and exporting subtitles...")
                        debug_boundary_candidates = [] if options.debug_mode else None
                        debug_dp_report = {} if options.debug_mode else None
                        debug_validation_report = {}

                        try:
                            optimized_segments = optimize_subtitles(
                                segments,
                                video_format=options.target_video_format,
                                max_lines=options.subtitle_lines,
                                wav_path=current_audio,
                                debug_boundary_candidates=debug_boundary_candidates,
                                debug_dp_report=debug_dp_report,
                                debug_validation_report=debug_validation_report,
                                subtitle_sync_offset_ms=options.subtitle_sync_offset_ms,
                                strict_subtitle_validation=options.strict_subtitle_validation,
                            )
                            qa_warnings = debug_validation_report.get("quality_warnings", [])
                            qa_gate = debug_validation_report.get("release_gate", {})
                            if qa_gate.get("status") == "review":
                                update_status(
                                    f"Subtitle QA: accepted with {len(qa_warnings)} unavoidable fast cue(s) "
                                    f"(max {qa_gate.get('max_observed_cps', 0):.1f} CPS)."
                                )
                            
                            # Disabled debug JSON report outputs
                            # if options.debug_mode:
                            #     with open(final_project_dir / "optimized_segments.json", "w", encoding="utf-8") as df:
                            #         json.dump(optimized_segments, df, indent=2, ensure_ascii=False)
                            #     with open(final_project_dir / "boundary_candidates.json", "w", encoding="utf-8") as df:
                            #         json.dump(debug_boundary_candidates, df, indent=2, ensure_ascii=False)
                            #     with open(final_project_dir / "dp_segmentation_report.json", "w", encoding="utf-8") as df:
                            #         json.dump(debug_dp_report, df, indent=2, ensure_ascii=False)
                                    
                            srt_path = final_project_dir / f"{_merge_stem}.srt"
                            export_srt(optimized_segments, srt_path, strict=False)
                            subtitle_files_dict = {"srt": srt_path.as_posix()}
                            srt_paths_list.append(srt_path)

                            if options.enable_translation:
                                update_status(f"Translating subtitles to {options.translation_target_lang}...")
                                try:
                                    file_id = _merge_stem
                                    trans_srt_path = srt_path.with_name(f"{file_id}_{options.translation_target_lang}.srt")
                                    if coordinator:
                                        coordinator.register_file_job(file_id, srt_path, trans_srt_path, target_lang=options.translation_target_lang)
                                        coordinator.enqueue_file_for_translation(file_id)
                                    else:
                                        from core.translator import translate_srt_file
                                        translate_srt_file(
                                            srt_path=srt_path,
                                            engine=options.translation_engine,
                                            target_lang=options.translation_target_lang,
                                            api_key=options.translation_api_key,
                                            status_callback=update_status,
                                            cancel_check=cancel_check,
                                            output_path=trans_srt_path,
                                        )
                                    subtitle_files_dict["srt_translated"] = trans_srt_path.as_posix()
                                    srt_paths_list.append(trans_srt_path)
                                except Exception as e:
                                    raise PipelineError(f"Failed in subtitle translation step: {e}") from e
                        except Exception as e:
                            raise PipelineError(f"Failed in transcription/subtitle step: {e}") from e
                        finally:
                            # Disabled writing subtitle_validation_report.json
                            pass

                        # Disabled writing subtitle_coverage_report.json
                        # if options.debug_mode and segments:
                        #     cov_report = {
                        #         "speech_regions": detect_speech_regions(current_audio),
                        #         "recovered_regions": recovered_regions,
                        #         "unresolved_regions": unresolved_regions,
                        #         "strict_coverage": options.strict_coverage
                        #     }
                        #     with open(final_project_dir / "subtitle_coverage_report.json", "w", encoding="utf-8") as df:
                        #         json.dump(cov_report, df, indent=2, ensure_ascii=False)
                    else:
                        subtitle_files_dict = None
                except Exception as e:
                    raise PipelineError(f"Failed in transcription/subtitle step: {e}") from e
            else:
                subtitle_files_dict = None

        else:
            # ══════════════════════════════════════════════════════════════
            # NON-MERGE MODE: Process each input independently
            # ══════════════════════════════════════════════════════════════
            for idx, input_path in enumerate(validated_inputs, 1):
                update_status(f"Processing input file {idx}/{len(validated_inputs)}: {input_path.name}...")

                # ── Step 1: Normalise to internal PCM ────────────────────
                update_status(f"[{input_path.name}] Normalizing to internal format...")
                pcm_file = dirs["work"] / f"{idx:03d}_{input_path.stem}.wav"
                try:
                    current_audio = normalize_to_pcm(input_path, pcm_file)
                    tracker.update_op_complete(f"[{input_path.name}] Normalized")
                except MediaImportError as e:
                    raise PipelineError(f"Failed to normalize '{input_path}': {e}") from e

                # ── Step 1.5: Audio Speed Adjustment (if speed != 1.0) ───
                if abs(options.audio_speed - 1.0) > 0.001:
                    update_status(f"[{input_path.name}] Adjusting audio speed to {options.audio_speed:.2f}x...")
                    speed_file = dirs["work"] / f"{idx:03d}_{input_path.stem}_speed.wav"
                    try:
                        current_audio = adjust_audio_speed(current_audio, speed_file, options.audio_speed)
                        tracker.update_op_complete(f"[{input_path.name}] Speed adjusted ({options.audio_speed:.2f}x)")
                    except MediaImportError as e:
                        raise PipelineError(f"Failed in audio speed adjustment on '{input_path}': {e}") from e

                # ── Step 2: Voice Cleanup ────────────────────────────────
                if options.enable_voice_cleanup:
                    update_status(f"[{input_path.name}] Applying voice cleanup...")
                    cleaned_file = dirs["work"] / f"{idx:03d}_{input_path.stem}_cleaned.wav"
                    try:
                        clean_opts = VoiceCleanerOptions(
                            preset=options.clean_preset,
                            overwrite=options.overwrite,
                        )
                        current_audio = clean_voice(current_audio, cleaned_file, options=clean_opts)
                        tracker.update_op_complete(f"[{input_path.name}] Voice cleaned")
                    except VoiceCleanerError as e:
                        raise PipelineError(f"Failed in voice cleaner step on '{input_path}': {e}") from e

                # ── Step 3: Silence Shortening ───────────────────────────
                if options.enable_silence_shortening:
                    update_status(f"[{input_path.name}] Shortening silence...")
                    shortened_file = dirs["work"] / f"{idx:03d}_{input_path.stem}_shortened.wav"
                    try:
                        sil_opts = options_from_preset(options.silence_preset)
                        sil_opts.overwrite = options.overwrite
                        current_audio = shorten_silence(current_audio, shortened_file, sil_opts)
                        tracker.update_op_complete(f"[{input_path.name}] Silence shortened")
                    except SilenceShortenerError as e:
                        raise PipelineError(f"Failed in silence shortening on '{input_path}': {e}") from e

                # ── Step 4: Voice level or delivery peak protection ─────
                if options.enable_volume_leveling or options.enable_social_optimize:
                    leveled_file = dirs["work"] / f"{idx:03d}_{input_path.stem}_leveled.wav"
                    vol_opts = VolumeLevelingOptions(
                        preset=options.volume_preset,
                        social_platform=options.social_platform if options.enable_social_optimize else "general",
                        overwrite=options.overwrite,
                    )
                    try:
                        if options.enable_volume_leveling:
                            update_status(f"[{input_path.name}] Applying voice-only volume leveling...")
                            current_audio = level_volume(current_audio, leveled_file, vol_opts)
                            tracker.update_op_complete(f"[{input_path.name}] Leveled voice volume")
                        else:
                            update_status(f"[{input_path.name}] Applying delivery peak protection...")
                            current_audio = apply_delivery_limiter(current_audio, leveled_file, vol_opts)
                            tracker.update_op_complete(f"[{input_path.name}] Protected delivery peak")
                    except VolumeLevelingError as e:
                        raise PipelineError(f"Failed in volume leveling on '{input_path}': {e}") from e

                # ── Step 5: Final export ─────────────────────────────────
                update_status(f"[{input_path.name}] Exporting final audio...")
                final_audio_path = final_project_dir / f"{idx:03d}_{input_path.stem}_processed.{options.output_format}"
                _export_audio(current_audio, final_audio_path, options.output_format, final_project_dir)
                final_audio_paths.append(final_audio_path)
                tracker.update_op_complete(f"[{input_path.name}] Exported final audio")

                # ── Step 6: Auto Sub ─────────────────────────────────────
                if options.enable_transcription:
                    update_status(f"[{input_path.name}] Running speech-to-text transcription...")
                    try:
                        model_size = options.whisper_model if options.whisper_model else model_size_from_preset(options.transcription_preset)
                        trans_opts = TranscriptionOptions(
                            model_size=model_size,
                            language=options.language,
                            device=backend.device,
                            compute_type=backend.compute_type,
                            asr_audio_speed=options.asr_audio_speed,
                            batch_size=options.batch_size,
                            word_timestamps=options.enable_subtitle_export,
                            strict_coverage=options.strict_coverage,
                            subtitle_sync_offset_ms=options.subtitle_sync_offset_ms,
                            recovery_pass_enabled=options.recovery_pass_enabled,
                        )
                        # Transcribe lossless WAV PCM instead of lossy export
                        trans_result = transcribe_media(current_audio, trans_opts, cancel_check=cancel_check)
                        if hasattr(trans_result, "segments"):
                            segments = trans_result.segments
                        else:
                            segments = trans_result
                        tracker.update_op_complete(f"[{input_path.name}] Speech transcribed")

                        # Handle fallback properties for mock/legacy list results
                        backend_used = getattr(trans_result, "backend_used", "CPU")
                        batch_size_used = getattr(trans_result, "batch_size_used", options.batch_size)
                        vad_used = getattr(trans_result, "vad_used", True)
                        vad_parameters = getattr(trans_result, "vad_parameters", {})
                        model_used = getattr(trans_result, "model_used", model_size)
                        language_used = getattr(trans_result, "language", options.language or "auto")
                        recovered_regions = getattr(trans_result, "recovered_regions", [])
                        unresolved_regions = getattr(trans_result, "unresolved_regions", [])

                        if options.debug_mode:
                            update_status(f"[{input_path.name}] Saving transcription diagnostics...")
                            raw_data = {
                                "segments": [
                                    {
                                        "index": seg.index,
                                        "start": seg.start,
                                        "end": seg.end,
                                        "text": seg.text,
                                        "words": seg.words
                                    }
                                    for seg in segments
                                ],
                                "metadata": {
                                    "backend_used": backend_used,
                                    "batch_size_used": batch_size_used,
                                    "vad_filter": vad_used,
                                    "vad_parameters": vad_parameters,
                                    "model": model_used,
                                    "language": language_used,
                                    "asr_audio_speed": options.asr_audio_speed
                                }
                            }
                            # Disabled raw whisper debug JSON output
                            # with open(final_project_dir / f"raw_whisper_segments_{idx:03d}_{input_path.stem}.json", "w", encoding="utf-8") as df:
                            #     json.dump(raw_data, df, indent=2, ensure_ascii=False)

                        if options.enable_subtitle_export and segments:
                            update_status(f"[{input_path.name}] Optimizing and exporting subtitles...")
                            debug_boundary_candidates = [] if options.debug_mode else None
                            debug_dp_report = {} if options.debug_mode else None
                            debug_validation_report = {}

                            try:
                                optimized_segments = optimize_subtitles(
                                    segments,
                                    video_format=options.target_video_format,
                                    max_lines=options.subtitle_lines,
                                    wav_path=current_audio,
                                    debug_boundary_candidates=debug_boundary_candidates,
                                    debug_dp_report=debug_dp_report,
                                    debug_validation_report=debug_validation_report,
                                    subtitle_sync_offset_ms=options.subtitle_sync_offset_ms,
                                    strict_subtitle_validation=options.strict_subtitle_validation,
                                )
                                qa_warnings = debug_validation_report.get("quality_warnings", [])
                                qa_gate = debug_validation_report.get("release_gate", {})
                                if qa_gate.get("status") == "review":
                                    update_status(
                                        f"[{input_path.name}] Subtitle QA: accepted with {len(qa_warnings)} unavoidable fast cue(s) "
                                        f"(max {qa_gate.get('max_observed_cps', 0):.1f} CPS)."
                                    )
                                
                                # Disabled debug JSON report outputs
                                # if options.debug_mode:
                                #     with open(final_project_dir / f"optimized_segments_{idx:03d}_{input_path.stem}.json", "w", encoding="utf-8") as df:
                                #         json.dump(optimized_segments, df, indent=2, ensure_ascii=False)
                                #     with open(final_project_dir / f"boundary_candidates_{idx:03d}_{input_path.stem}.json", "w", encoding="utf-8") as df:
                                #         json.dump(debug_boundary_candidates, df, indent=2, ensure_ascii=False)
                                #     with open(final_project_dir / f"dp_segmentation_report_{idx:03d}_{input_path.stem}.json", "w", encoding="utf-8") as df:
                                #         json.dump(debug_dp_report, df, indent=2, ensure_ascii=False)
                                        
                                srt_path = final_project_dir / f"{idx:03d}_{input_path.stem}.srt"
                                export_srt(optimized_segments, srt_path, strict=False)
                                sub_entry = {"srt": srt_path.as_posix()}
                                srt_paths_list.append(srt_path)

                                if options.enable_translation:
                                    file_id = f"{idx:03d}_{input_path.stem}"
                                    trans_srt_path = srt_path.with_name(f"{file_id}_{options.translation_target_lang}.srt")
                                    sub_entry["srt_translated"] = trans_srt_path.as_posix()
                                    srt_paths_list.append(trans_srt_path)
                                    if coordinator:
                                        update_status(f"[{input_path.name}] Enqueuing subtitle translation to {options.translation_target_lang}...")
                                        coordinator.register_file_job(file_id, srt_path, trans_srt_path, target_lang=options.translation_target_lang)
                                        coordinator.enqueue_file_for_translation(file_id)
                                    else:
                                        update_status(f"[{input_path.name}] Translating subtitles to {options.translation_target_lang}...")
                                        try:
                                            from core.translator import translate_srt_file
                                            translate_srt_file(
                                                srt_path=srt_path,
                                                engine=options.translation_engine,
                                                target_lang=options.translation_target_lang,
                                                api_key=options.translation_api_key,
                                                status_callback=update_status,
                                                cancel_check=cancel_check,
                                                output_path=trans_srt_path,
                                            )
                                        except Exception as e:
                                            raise PipelineError(f"Failed in subtitle translation step on '{input_path}': {e}") from e

                                subtitle_files_dict[f"{idx:03d}_{input_path.stem}"] = sub_entry
                            except Exception as e:
                                raise PipelineError(f"Failed in transcription/subtitle step on '{input_path}': {e}") from e
                            finally:
                                # Disabled writing subtitle_validation_report.json
                                pass

                            # Disabled writing subtitle_coverage_report.json
                            # if options.debug_mode and segments:
                            #     cov_report = {
                            #         "speech_regions": detect_speech_regions(current_audio),
                            #         "recovered_regions": recovered_regions,
                            #         "unresolved_regions": unresolved_regions,
                            #         "strict_coverage": options.strict_coverage
                            #     }
                            #     with open(final_project_dir / f"subtitle_coverage_report_{idx:03d}_{input_path.stem}.json", "w", encoding="utf-8") as df:
                            #         json.dump(cov_report, df, indent=2, ensure_ascii=False)
                        else:
                            subtitle_files_dict = None
                    except Exception as e:
                        raise PipelineError(f"Failed in transcription/subtitle step on '{input_path}': {e}") from e

        if coordinator:
            update_status("Signaling TranslationCoordinator that ASR producer has finished...")
            coordinator.mark_producer_finished()
            update_status("Waiting for TranslationCoordinator to finalize all background translation jobs...")
            if coordinator_thread and coordinator_thread.is_alive():
                coordinator_thread.join()
            # Disabled exporting API key usage report file to keep output directory clean
            # try:
            #     report_file = final_project_dir / "api_key_usage_report.txt"
            #     coordinator.export_key_usage_report(report_file)
            # except Exception as r_err:
            #     logger.warning("Failed to export API key usage report: %s", r_err)
            coordinator.shutdown()

    finally:
        # Cleanup: always remove temp dirs even on failure
        if dirs:
            update_status("Cleaning up temporary files...")
            try:
                _cleanup_temp_dirs(final_project_dir, dirs)
            except Exception as e:
                logger.warning("Failed to clean up temp directories: %s", e)
        
        # Clear Whisper model cache to release system/GPU memory
        try:
            from core.transcriber import clear_whisper_model_cache
            clear_whisper_model_cache()
        except Exception as e:
            logger.warning("Failed to clear Whisper model cache: %s", e)

        # Cleanup any leftover report files from output directory (only keep audio & srt/vtt)
        try:
            for json_pattern in ["*_report*.json", "*_segments*.json", "*_candidates*.json", "*_trace*.json", "merge_dedup_report.json", "*report*.txt", "api_key_usage_report.txt"]:
                for json_file in final_project_dir.glob(json_pattern):
                    if json_file.exists():
                        json_file.unlink()
        except Exception as exc:
            logger.debug("Minor warning during JSON report cleanup: %s", exc)

    update_status("Pipeline completed successfully!")
    return PipelineResult(
        project_name=options.project_name,
        output_dir=final_project_dir.as_posix(),
        input_files=[p.as_posix() for p in validated_inputs],
        working_audio=final_audio_paths[0].as_posix() if len(final_audio_paths) == 1 else [p.as_posix() for p in final_audio_paths],
        merged_file=merged_file_path.as_posix() if merged_file_path else None,
        leveled_file=None,
        shortened_file=None,
        subtitle_files=subtitle_files_dict if subtitle_files_dict else None,
        chunks=None,
        metadata_file=None,
        srt_paths=[p.as_posix() for p in srt_paths_list] if srt_paths_list else None,
    )


def run_batch_pipeline(
    input_paths: List[Path],
    output_dir: Path,
    options: Optional[PipelineOptions] = None,
    status_callback: Optional[Callable[[str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    project_dir_callback: Optional[Callable[[Path], None]] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> List[PipelineResult]:
    """
    Run batch pipelines sequentially, isolating each file into its own stem subdirectory
    inside a unified parent batch folder.
    """
    if options is None:
        options = PipelineOptions()
        
    batch_options = PipelineOptions(
        merge_first=False,
        enable_voice_cleanup=options.enable_voice_cleanup,
        enable_volume_leveling=options.enable_volume_leveling,
        enable_silence_shortening=options.enable_silence_shortening,
        enable_social_optimize=options.enable_social_optimize,
        enable_transcription=options.enable_transcription,
        enable_subtitle_export=options.enable_subtitle_export,
        enable_translation=options.enable_translation,
        translation_engine=options.translation_engine,
        translation_target_lang=options.translation_target_lang,
        translation_api_key=options.translation_api_key,
        output_format=options.output_format,
        project_name=options.project_name,
        overwrite=options.overwrite,
        merge_gap_seconds=options.merge_gap_seconds,
        volume_preset=options.volume_preset,
        silence_preset=options.silence_preset,
        clean_preset=options.clean_preset,
        transcription_preset=options.transcription_preset,
        subtitle_base_name=options.subtitle_base_name,
        language=options.language,
        whisper_model=options.whisper_model,
        asr_audio_speed=options.asr_audio_speed,
        batch_size=options.batch_size,
        target_video_format=options.target_video_format,
        subtitle_lines=options.subtitle_lines,
        social_platform=options.social_platform,
        strict_coverage=options.strict_coverage,
        debug_mode=options.debug_mode,
        subtitle_sync_offset_ms=options.subtitle_sync_offset_ms,
        recovery_pass_enabled=options.recovery_pass_enabled,
        strict_subtitle_validation=options.strict_subtitle_validation,
    )
    
    full_result = run_audio_pipeline(
        input_paths, output_dir, batch_options, status_callback,
        cancel_check=cancel_check, project_dir_callback=project_dir_callback,
        progress_callback=progress_callback
    )
    
    results = []
    validated_inputs = validate_pipeline_inputs(input_paths)
    for idx, path in enumerate(validated_inputs, 1):
        # Flat structure: audio files are now at [output_dir]/[idx:03d]_[stem]_processed.[ext]
        final_audio = Path(full_result.output_dir) / f"{idx:03d}_{path.stem}_processed.{batch_options.output_format}"

        individual_subs = None
        sub_key = f"{idx:03d}_{path.stem}"
        if full_result.subtitle_files and sub_key in full_result.subtitle_files:
            individual_subs = full_result.subtitle_files[sub_key]

        results.append(
            PipelineResult(
                project_name=path.stem,
                output_dir=full_result.output_dir,
                input_files=[path.as_posix()],
                working_audio=final_audio.as_posix() if final_audio.exists() else None,
                merged_file=None,
                leveled_file=None,
                shortened_file=None,
                subtitle_files=individual_subs,
                chunks=None,
                metadata_file=None,
            )
        )
        
    return results


def pipeline_result_to_dict(result: PipelineResult) -> Dict[str, Any]:
    """
    Convert PipelineResult object to JSON-safe dictionary.
    """
    try:
        return asdict(result)
    except Exception as e:
        raise PipelineError(f"Failed to serialize PipelineResult: {e}") from e

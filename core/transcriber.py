"""
core/transcriber.py
──────────────────────────────────────────────────────────────────────────────
Faster Whisper ASR module with CTranslate2 CUDA hardware auto-detection,
thread-safe model caching, automatic CUDA -> CPU fallback, and cancellation.
"""

import os
import gc
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable, Tuple

from core.importer import validate_input_file, MediaImportError
from core.subtitle_exporter import TranscriptSegment
from core.cuda_runtime import bootstrap_nvidia_dlls

# Must run before importing ctranslate2/faster-whisper.  Keeping this bootstrap
# in the ASR module makes GUI, CLI and tests use the same GPU path.
bootstrap_nvidia_dlls()

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Exception raised for errors during media transcription."""
    pass


class SubtitleCoverageError(TranscriptionError):
    """Exception raised for insufficient subtitle speech coverage."""
    pass


def _raise_if_cancelled(cancel_check: Optional[Callable[[], bool]]) -> None:
    if cancel_check is not None and cancel_check():
        raise TranscriptionError("Transcription cancelled by user.")


@dataclass(frozen=True)
class AsrBackendConfig:
    device: str
    compute_type: str
    reason: str
    cuda_device_count: int = 0


def detect_best_backend() -> AsrBackendConfig:
    """Detect best hardware backend using CTranslate2."""
    try:
        import ctranslate2
        count = int(ctranslate2.get_cuda_device_count())
        if count > 0:
            return AsrBackendConfig(
                device="cuda",
                compute_type="float16",
                reason="CUDA detected by CTranslate2",
                cuda_device_count=count,
            )
    except Exception as exc:
        logger.debug("CTranslate2 CUDA detection exception: %s", exc)

    return AsrBackendConfig(
        device="cpu",
        compute_type="int8",
        reason="No usable CUDA device detected by CTranslate2",
        cuda_device_count=0,
    )


def detect_best_device() -> str:
    """Return 'cuda' if CTranslate2 detects CUDA GPU, else 'cpu'."""
    return detect_best_backend().device


DEFAULT_VAD_PARAMETERS: Dict[str, Any] = {
    "threshold": 0.35,
    "min_speech_duration_ms": 250,
    "max_speech_duration_s": float("inf"),
    "min_silence_duration_ms": 1500,
    "speech_pad_ms": 500,
}


@dataclass
class TranscriptionOptions:
    model_size: str = "large-v3-turbo"
    language: Optional[str] = None
    device: Optional[str] = None
    compute_type: Optional[str] = None
    beam_size: int = 5
    vad_filter: bool = True
    vad_parameters: Optional[Dict[str, Any]] = field(default=None)
    word_timestamps: bool = False
    asr_audio_speed: float = 1.0
    batch_size: int = 8
    strict_coverage: bool = False
    subtitle_sync_offset_ms: float = 0.0
    recovery_pass_enabled: bool = True

    def __post_init__(self) -> None:
        if self.vad_parameters is None:
            self.vad_parameters = dict(DEFAULT_VAD_PARAMETERS)

        if self.device is None:
            backend = detect_best_backend()
            self.device = backend.device
            if self.compute_type is None:
                self.compute_type = backend.compute_type
        elif self.compute_type is None:
            self.compute_type = "float16" if self.device == "cuda" else "int8"

        if self.device not in ("cuda", "cpu"):
            raise TranscriptionError(f"Unsupported device: '{self.device}'. Valid options are 'cuda' or 'cpu'.")
        if not self.compute_type or not isinstance(self.compute_type, str):
            raise TranscriptionError("compute_type must be a non-empty string.")


def detect_speech_regions(wav_path: Path) -> List[Dict[str, float]]:
    """Detect speech regions in audio file."""
    return []


# ── Thread-Safe Model Cache ──────────────────────────────────────────────────
_MODEL_CACHE: Dict[Tuple[str, str, str], Any] = {}
_MODEL_CACHE_LOCK = threading.Lock()


def clear_whisper_model_cache() -> None:
    """Clear cached Whisper models and release GPU/system memory."""
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE.clear()
    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass


PRESETS: Dict[str, str] = {
    "fast": "base",
    "balanced": "small",
    "accurate": "medium",
    "best": "large-v3"
}


def model_size_from_preset(preset: str) -> str:
    """Map preset string to whisper model size."""
    preset_lower = preset.lower()
    if preset_lower not in PRESETS:
        raise TranscriptionError(
            f"Invalid preset '{preset}'. Valid options are: {', '.join(sorted(PRESETS.keys()))}"
        )
    return PRESETS[preset_lower]


def _is_cuda_runtime_error(exc: Exception) -> bool:
    """Check if exception indicates CUDA / GPU runtime or driver failure."""
    msg = str(exc).lower()
    keywords = (
        "cuda", "cublas", "cudnn", "gpu", "driver", "nvcuda", "dll",
        "out of memory", "out_of_memory", "alloc", "device", "unsupported compute type",
        "invalid device", "cufft"
    )
    return any(k in msg for k in keywords)


def load_whisper_model(options: TranscriptionOptions) -> Any:
    """Lazy load faster-whisper model with thread-safe caching and CUDA->CPU fallback."""
    target_device = options.device or "cpu"
    target_compute = options.compute_type or ("float16" if target_device == "cuda" else "int8")
    cache_key = (options.model_size, target_device, target_compute)

    with _MODEL_CACHE_LOCK:
        cached_model = _MODEL_CACHE.get(cache_key)
        if cached_model is not None:
            logger.info("[ASR] Using cached Whisper model on %s / %s", target_device, target_compute)
            return cached_model

    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise TranscriptionError(
            "The 'faster-whisper' package is not installed. "
            "Please run: pip install faster-whisper"
        ) from e

    try:
        model = WhisperModel(
            options.model_size,
            device=target_device,
            compute_type=target_compute
        )
        setattr(model, "_actual_device", target_device)
        setattr(model, "_actual_compute_type", target_compute)
        logger.info("[ASR] Whisper model loaded on %s / %s", target_device, target_compute)
        with _MODEL_CACHE_LOCK:
            _MODEL_CACHE[cache_key] = model
        return model
    except Exception as e:
        if target_device == "cuda" and _is_cuda_runtime_error(e):
            logger.warning("[ASR] CUDA load failed: %s. Falling back to CPU / int8", e)
            cpu_key = (options.model_size, "cpu", "int8")
            with _MODEL_CACHE_LOCK:
                cpu_cached = _MODEL_CACHE.get(cpu_key)
                if cpu_cached is not None:
                    logger.info("[ASR] Using cached Whisper model on CPU / int8 after CUDA fallback")
                    return cpu_cached
            try:
                cpu_model = WhisperModel(
                    options.model_size,
                    device="cpu",
                    compute_type="int8"
                )
                setattr(cpu_model, "_actual_device", "cpu")
                setattr(cpu_model, "_actual_compute_type", "int8")
                logger.info("[ASR] Whisper model loaded on CPU / int8 after CUDA fallback")
                with _MODEL_CACHE_LOCK:
                    _MODEL_CACHE[cpu_key] = cpu_model
                return cpu_model
            except Exception as cpu_err:
                raise TranscriptionError(f"Failed to load Whisper model on CUDA ({e}) and CPU fallback ({cpu_err})") from cpu_err
        else:
            raise TranscriptionError(f"Failed to load Whisper model '{options.model_size}': {e}") from e


def _do_inference(
    model: Any,
    transcription_source: Path,
    options: TranscriptionOptions,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> List[TranscriptSegment]:
    """Execute Faster Whisper inference and build TranscriptSegments."""
    _raise_if_cancelled(cancel_check)
    actual_dev = getattr(model, "_actual_device", options.device or "cpu")
    actual_comp = getattr(model, "_actual_compute_type", options.compute_type or "int8")
    logger.info("[ASR] Transcription running on %s / %s", actual_dev, actual_comp)

    vad_kwargs = {}
    if options.vad_filter:
        vad_kwargs["vad_filter"] = True
        if options.vad_parameters:
            vad_kwargs["vad_parameters"] = options.vad_parameters

    if options.batch_size > 1:
        from faster_whisper import BatchedInferencePipeline
        pipeline = BatchedInferencePipeline(model)
        segments_iterable, _ = pipeline.transcribe(
            str(transcription_source),
            language=options.language,
            beam_size=options.beam_size,
            word_timestamps=options.word_timestamps,
            batch_size=options.batch_size,
            **vad_kwargs,
        )
    else:
        segments_iterable, _ = model.transcribe(
            str(transcription_source),
            language=options.language,
            beam_size=options.beam_size,
            word_timestamps=options.word_timestamps,
            **vad_kwargs,
        )

    segments = []
    for idx, seg in enumerate(segments_iterable):
        _raise_if_cancelled(cancel_check)
        text_str = str(seg.text).strip()
        if not text_str:
            continue

        seg_start = float(seg.start)
        seg_end = float(seg.end)

        if options.asr_audio_speed != 1.0:
            seg_start = seg_start * options.asr_audio_speed
            seg_end = seg_end * options.asr_audio_speed

        words_list = None
        if options.word_timestamps and getattr(seg, "words", None) is not None:
            words_list = []
            for w in seg.words:
                w_start = float(w.start)
                w_end = float(w.end)
                if options.asr_audio_speed != 1.0:
                    w_start = w_start * options.asr_audio_speed
                    w_end = w_end * options.asr_audio_speed
                words_list.append({
                    "word": w.word,
                    "start": w_start,
                    "end": w_end,
                    "probability": getattr(w, "probability", 0.0)
                })

        segments.append(
            TranscriptSegment(
                start=seg_start,
                end=seg_end,
                text=text_str,
                index=idx + 1,
                words=words_list
            )
        )

    _raise_if_cancelled(cancel_check)

    # ── Secondary Gap Recovery Pass ──────────────────────────────────────────
    if options.recovery_pass_enabled and segments:
        segments = _run_gap_recovery_pass(model, transcription_source, segments, options, cancel_check)

    for new_idx, seg in enumerate(segments):
        seg.index = new_idx + 1

    return segments


def _run_gap_recovery_pass(
    model: Any,
    transcription_source: Path,
    existing_segments: List[TranscriptSegment],
    options: TranscriptionOptions,
    cancel_check: Optional[Callable[[], bool]] = None,
    min_gap_sec: float = 3.5,
) -> List[TranscriptSegment]:
    """Scan for long silence gaps (> min_gap_sec) and re-transcribe gaps with higher VAD sensitivity."""
    if len(existing_segments) < 1:
        return existing_segments

    gaps = []
    for i in range(len(existing_segments) - 1):
        prev_end = existing_segments[i].end
        next_start = existing_segments[i + 1].start
        if (next_start - prev_end) >= min_gap_sec:
            gaps.append((prev_end, next_start))

    if not gaps:
        return existing_segments

    logger.info("[ASR Recovery] Found %d gap(s) >= %.1fs to re-scan", len(gaps), min_gap_sec)
    recovered_segments = list(existing_segments)

    # Ultra-sensitive VAD for gap recovery pass
    recovery_vad = {
        "threshold": 0.18,
        "min_speech_duration_ms": 200,
        "min_silence_duration_ms": 1000,
        "speech_pad_ms": 600,
    }

    for gap_start, gap_end in gaps:
        _raise_if_cancelled(cancel_check)
        try:
            # Re-scan gap with model.transcribe (clip_timestamps or clip window)
            gap_iterable, _ = model.transcribe(
                str(transcription_source),
                language=options.language,
                beam_size=options.beam_size,
                word_timestamps=options.word_timestamps,
                vad_filter=True,
                vad_parameters=recovery_vad,
                clip_timestamps=f"{gap_start},{gap_end}",
            )
            for seg in gap_iterable:
                text_str = str(seg.text).strip()
                if not text_str:
                    continue
                s_start = float(seg.start)
                s_end = float(seg.end)
                if s_end <= s_start:
                    continue
                # Ensure segment falls within gap
                if s_start >= gap_start - 0.5 and s_end <= gap_end + 0.5:
                    logger.info("[ASR Recovery] Recovered missing segment in gap [%.2fs - %.2fs]: %s", s_start, s_end, text_str)
                    recovered_segments.append(
                        TranscriptSegment(
                            start=s_start,
                            end=s_end,
                            text=text_str,
                            index=len(recovered_segments) + 1,
                        )
                    )
        except Exception as exc:
            logger.warning("[ASR Recovery] Gap recovery failed for [%.2fs - %.2fs]: %s", gap_start, gap_end, exc)

    recovered_segments.sort(key=lambda x: x.start)
    return recovered_segments


def transcribe_media(
    input_path: Path,
    options: Optional[TranscriptionOptions] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> List[TranscriptSegment]:
    """Transcribe a media file to a list of TranscriptSegment with cancellation & CUDA fallback."""
    _raise_if_cancelled(cancel_check)

    if options is None:
        options = TranscriptionOptions()

    from core.language_options import resolve_language_code
    try:
        options.language = resolve_language_code(options.language)
    except ValueError as e:
        raise TranscriptionError(str(e)) from e

    try:
        input_path_obj = validate_input_file(input_path)
    except MediaImportError as e:
        raise TranscriptionError(f"Invalid input file: {e}") from e

    if options.asr_audio_speed < 0.5 or options.asr_audio_speed > 2.0:
        raise TranscriptionError(f"ASR audio speed must be between 0.5 and 2.0. Received: {options.asr_audio_speed}")

    temp_speed_path = None
    transcription_source = input_path_obj

    if options.asr_audio_speed != 1.0:
        import tempfile
        from core.ffmpeg_runner import run_ffmpeg, FFmpegError

        temp_fd, temp_path_str = tempfile.mkstemp(suffix=".wav")
        os.close(temp_fd)
        temp_speed_path = Path(temp_path_str)

        args = [
            "-y",
            "-i", str(input_path_obj),
            "-filter:a", f"atempo={options.asr_audio_speed}",
            str(temp_speed_path)
        ]
        try:
            run_ffmpeg(args)
            transcription_source = temp_speed_path
        except FFmpegError as e:
            if temp_speed_path.exists():
                try:
                    os.unlink(temp_speed_path)
                except Exception:
                    pass
            raise TranscriptionError(f"Failed to create speed-adjusted audio for transcription: {e}") from e

    _raise_if_cancelled(cancel_check)
    model = load_whisper_model(options)
    _raise_if_cancelled(cancel_check)

    try:
        try:
            return _do_inference(model, transcription_source, options, cancel_check)
        except TranscriptionError:
            raise
        except Exception as exc:
            actual_dev = getattr(model, "_actual_device", options.device or "cpu")
            if actual_dev == "cuda" and _is_cuda_runtime_error(exc):
                logger.warning("[ASR] CUDA inference failed: %s. Falling back to CPU / int8", exc)
                _raise_if_cancelled(cancel_check)
                cpu_options = TranscriptionOptions(
                    model_size=options.model_size,
                    language=options.language,
                    device="cpu",
                    compute_type="int8",
                    beam_size=options.beam_size,
                    vad_filter=options.vad_filter,
                    word_timestamps=options.word_timestamps,
                    asr_audio_speed=options.asr_audio_speed,
                    batch_size=options.batch_size,
                    strict_coverage=options.strict_coverage,
                    subtitle_sync_offset_ms=options.subtitle_sync_offset_ms,
                    recovery_pass_enabled=options.recovery_pass_enabled,
                )
                cpu_model = load_whisper_model(cpu_options)
                _raise_if_cancelled(cancel_check)
                try:
                    return _do_inference(cpu_model, transcription_source, cpu_options, cancel_check)
                except TranscriptionError:
                    raise
                except Exception as cpu_exc:
                    raise TranscriptionError(f"Error during audio transcription after CUDA ({exc}) and CPU fallback ({cpu_exc})") from cpu_exc
            else:
                raise TranscriptionError(f"Error during audio transcription: {exc}") from exc
    finally:
        if temp_speed_path is not None and temp_speed_path.exists():
            try:
                os.unlink(temp_speed_path)
            except Exception:
                pass


def transcribe_to_dicts(
    input_path: Path,
    options: Optional[TranscriptionOptions] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> List[Dict[str, Any]]:
    """Transcribe media file, returning a list of dictionaries with standard keys."""
    segments = transcribe_media(input_path, options, cancel_check=cancel_check)
    return [
        {
            "index": seg.index,
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "words": seg.words
        }
        for seg in segments
    ]

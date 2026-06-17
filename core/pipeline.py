import os
import re
import datetime
import shutil
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional

from core.ffmpeg_runner import run_ffmpeg, FFmpegError
from core.importer import validate_input_file, MediaImportError
from core.merger import merge_audio_files, MergeOptions, AudioMergeError
from core.volume_leveler import level_volume, VolumeLevelingOptions, VolumeLevelingError
from core.silence_shortener import shorten_silence, SilenceShortenerOptions, options_from_preset, SilenceShortenerError
from core.transcriber import transcribe_media, TranscriptionOptions, model_size_from_preset, TranscriptionError
from core.subtitle_exporter import export_all_subtitles
from core.sentence_splitter import split_segments_by_sentence, SentenceSplitOptions, SentenceSplitError
from core.audio_cutter import cut_audio_by_sentences, AudioCutOptions, AudioCutError
from core.metadata_exporter import build_project_metadata, export_project_json
from core.voice_cleaner import clean_voice, VoiceCleanerError
from core.social_optimizer import optimize_social_audio, SocialOptimizerError
from core.subtitle_optimizer import optimize_subtitles, SubtitleOptimizerError

class PipelineError(Exception):
    """Exception raised for errors during pipeline processing."""
    pass


@dataclass
class PipelineOptions:
    merge_first: bool = False
    enable_voice_cleanup: bool = False
    enable_volume_leveling: bool = True
    enable_silence_shortening: bool = True
    enable_social_optimize: bool = False
    enable_transcription: bool = False
    enable_subtitle_export: bool = False
    output_format: str = "wav"
    project_name: str = "audio_project"
    overwrite: bool = True
    merge_gap_seconds: float = 0.0
    volume_preset: str = "natural"
    silence_preset: str = "natural"
    transcription_preset: str = "balanced"
    subtitle_base_name: str = "subtitles"
    language: Optional[str] = None
    whisper_model: str = "large-v3-turbo"
    asr_audio_speed: float = 1.0
    batch_size: int = 8
    target_video_format: str = "horizontal"
    subtitle_lines: int = 1
    # Keep deprecated options for compatibility
    enable_sentence_split: bool = False
    enable_audio_cutting: bool = False


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


def prepare_output_dirs(output_dir: Path) -> Dict[str, Path]:
    """
    Return output subdirectories: final, subtitles, metadata, work.
    Creates them initially.
    """
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)
    
    dirs = {
        "final": output_dir_obj / "final",
        "subtitles": output_dir_obj / "subtitles",
        "metadata": output_dir_obj / "metadata",
        "work": output_dir_obj / "work"
    }
    
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
        
    return dirs


def run_audio_pipeline(
    input_paths: List[Path],
    output_dir: Path,
    options: Optional[PipelineOptions] = None
) -> PipelineResult:
    """
    Run the end-to-end audio processing pipeline on input files.
    """
    if options is None:
        options = PipelineOptions()
        
    validated_inputs = validate_pipeline_inputs(input_paths)
    
    # Early language validation
    from core.language_options import resolve_language_code
    try:
        options.language = resolve_language_code(options.language)
    except ValueError as e:
        raise PipelineError(str(e)) from e
        
    output_dir_obj = Path(output_dir)
    
    # 1. Resolve final project directory with safety suffix increments
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
    if final_project_dir.exists() and not options.overwrite:
        suffix = 1
        while True:
            candidate = Path(output_dir) / f"{proj_folder_name}_{suffix:02d}"
            if not candidate.exists():
                final_project_dir = candidate
                break
            suffix += 1

    # Update options.project_name to match resolved folder name
    options.project_name = final_project_dir.name

    dirs = prepare_output_dirs(final_project_dir)
    
    # Tracking variables for metadata compilation
    merged_file_path = None
    cleaned_files = []
    leveled_files = []
    shortened_files = []
    optimized_files = []
    final_audio_paths = []
    subtitle_files_dict = {}

    # Check if merge_first is enabled
    if options.merge_first:
        if len(validated_inputs) > 1:
            merged_file = dirs["work"] / f"merged.{options.output_format}"
            merge_opts = MergeOptions(
                gap_seconds=options.merge_gap_seconds,
                output_format=options.output_format,
                overwrite=options.overwrite
            )
            try:
                current_audio = merge_audio_files(validated_inputs, merged_file, merge_opts)
                merged_file_path = current_audio
            except AudioMergeError as e:
                raise PipelineError(f"Failed in merger step: {e}") from e
        else:
            print("Merge requested but only one input file provided. Skipping merge step safely.")
            current_audio = validated_inputs[0]
            merged_file_path = None
            
        # Process the single/merged audio linearly
        # A. Voice Cleanup
        if options.enable_voice_cleanup:
            cleaned_file = dirs["work"] / f"cleaned.{options.output_format}"
            try:
                current_audio = clean_voice(current_audio, cleaned_file, overwrite=options.overwrite)
                cleaned_files = [current_audio]
            except VoiceCleanerError as e:
                raise PipelineError(f"Failed in voice cleaner step: {e}") from e
                
        # B. Volume Leveling
        if options.enable_volume_leveling:
            leveled_file = dirs["work"] / f"leveled.{options.output_format}"
            vol_opts = VolumeLevelingOptions(
                preset=options.volume_preset,
                overwrite=options.overwrite
            )
            try:
                current_audio = level_volume(current_audio, leveled_file, vol_opts)
                leveled_files = [current_audio]
            except VolumeLevelingError as e:
                raise PipelineError(f"Failed in volume leveling step: {e}") from e
                
        # C. Natural Silence Shortening
        if options.enable_silence_shortening:
            shortened_file = dirs["work"] / f"shortened.{options.output_format}"
            try:
                sil_opts = options_from_preset(options.silence_preset)
                sil_opts.overwrite = options.overwrite
                current_audio = shorten_silence(current_audio, shortened_file, sil_opts)
                shortened_files = [current_audio]
            except SilenceShortenerError as e:
                raise PipelineError(f"Failed in silence shortening step: {e}") from e
                
        # D. Social Media Audio Optimization
        if options.enable_social_optimize:
            optimized_file = dirs["work"] / f"optimized.{options.output_format}"
            try:
                current_audio = optimize_social_audio(current_audio, optimized_file, overwrite=options.overwrite)
                optimized_files = [current_audio]
            except SocialOptimizerError as e:
                raise PipelineError(f"Failed in social optimizer step: {e}") from e
                
        # Export final audio
        final_audio_path = dirs["final"] / f"final_audio.{options.output_format}"
        if current_audio.suffix.lower() == f".{options.output_format}":
            if final_project_dir in current_audio.parents:
                shutil.copy2(current_audio, final_audio_path)
            else:
                args = ["-y", "-i", str(current_audio)]
                ext = options.output_format.lower()
                if ext == "wav":
                    args += ["-c:a", "pcm_s16le"]
                elif ext == "mp3":
                    args += ["-c:a", "libmp3lame"]
                elif ext == "m4a":
                    args += ["-c:a", "aac"]
                args.append(str(final_audio_path))
                try:
                    run_ffmpeg(args)
                except Exception as e:
                    raise PipelineError(f"Failed to export final audio: {e}") from e
        else:
            args = ["-y", "-i", str(current_audio)]
            ext = options.output_format.lower()
            if ext == "wav":
                args += ["-c:a", "pcm_s16le"]
            elif ext == "mp3":
                args += ["-c:a", "libmp3lame"]
            elif ext == "m4a":
                args += ["-c:a", "aac"]
            args.append(str(final_audio_path))
            try:
                run_ffmpeg(args)
            except Exception as e:
                raise PipelineError(f"Failed to export final audio: {e}") from e
        final_audio_paths = [final_audio_path]
        
        # E. Auto Sub
        if options.enable_transcription:
            try:
                model_size = options.whisper_model if options.whisper_model else model_size_from_preset(options.transcription_preset)
                trans_opts = TranscriptionOptions(
                    model_size=model_size,
                    language=options.language,
                    asr_audio_speed=options.asr_audio_speed,
                    batch_size=options.batch_size,
                    word_timestamps=options.enable_subtitle_export
                )
                segments = transcribe_media(final_audio_path, trans_opts)
                
                if options.enable_subtitle_export and segments:
                    optimized_segments = optimize_subtitles(
                        segments,
                        video_format=options.target_video_format,
                        max_lines=options.subtitle_lines
                    )
                    sub_files = export_all_subtitles(optimized_segments, dirs["subtitles"], options.subtitle_base_name)
                    subtitle_files_dict = {k: Path(v).as_posix() for k, v in sub_files.items()}
                else:
                    subtitle_files_dict = None
            except Exception as e:
                raise PipelineError(f"Failed in transcription/subtitle step: {e}") from e
        else:
            subtitle_files_dict = None

    else:
        # Merge OFF - process each input separately
        for input_path in validated_inputs:
            current_audio = input_path
            
            # A. Voice Cleanup
            if options.enable_voice_cleanup:
                cleaned_file = dirs["work"] / f"{input_path.stem}_cleaned.{options.output_format}"
                try:
                    current_audio = clean_voice(current_audio, cleaned_file, overwrite=options.overwrite)
                    cleaned_files.append(current_audio)
                except VoiceCleanerError as e:
                    raise PipelineError(f"Failed in voice cleaner step on file '{input_path}': {e}") from e
                    
            # B. Volume Leveling
            if options.enable_volume_leveling:
                leveled_file = dirs["work"] / f"{input_path.stem}_leveled.{options.output_format}"
                vol_opts = VolumeLevelingOptions(
                    preset=options.volume_preset,
                    overwrite=options.overwrite
                )
                try:
                    current_audio = level_volume(current_audio, leveled_file, vol_opts)
                    leveled_files.append(current_audio)
                except VolumeLevelingError as e:
                    raise PipelineError(f"Failed in volume leveling step on file '{input_path}': {e}") from e
                    
            # C. Natural Silence Shortening
            if options.enable_silence_shortening:
                shortened_file = dirs["work"] / f"{input_path.stem}_shortened.{options.output_format}"
                try:
                    sil_opts = options_from_preset(options.silence_preset)
                    sil_opts.overwrite = options.overwrite
                    current_audio = shorten_silence(current_audio, shortened_file, sil_opts)
                    shortened_files.append(current_audio)
                except SilenceShortenerError as e:
                    raise PipelineError(f"Failed in silence shortening step on file '{input_path}': {e}") from e
                    
            # D. Social Media Audio Optimization
            if options.enable_social_optimize:
                optimized_file = dirs["work"] / f"{input_path.stem}_optimized.{options.output_format}"
                try:
                    current_audio = optimize_social_audio(current_audio, optimized_file, overwrite=options.overwrite)
                    optimized_files.append(current_audio)
                except SocialOptimizerError as e:
                    raise PipelineError(f"Failed in social optimizer step on file '{input_path}': {e}") from e
                    
            # Export final audio
            final_audio_path = dirs["final"] / f"{input_path.stem}_final.{options.output_format}"
            if current_audio.suffix.lower() == f".{options.output_format}":
                if final_project_dir in current_audio.parents:
                    shutil.copy2(current_audio, final_audio_path)
                else:
                    args = ["-y", "-i", str(current_audio)]
                    ext = options.output_format.lower()
                    if ext == "wav":
                        args += ["-c:a", "pcm_s16le"]
                    elif ext == "mp3":
                        args += ["-c:a", "libmp3lame"]
                    elif ext == "m4a":
                        args += ["-c:a", "aac"]
                    args.append(str(final_audio_path))
                    try:
                        run_ffmpeg(args)
                    except Exception as e:
                        raise PipelineError(f"Failed to export final audio for '{input_path}': {e}") from e
            else:
                args = ["-y", "-i", str(current_audio)]
                ext = options.output_format.lower()
                if ext == "wav":
                    args += ["-c:a", "pcm_s16le"]
                elif ext == "mp3":
                    args += ["-c:a", "libmp3lame"]
                elif ext == "m4a":
                    args += ["-c:a", "aac"]
                args.append(str(final_audio_path))
                try:
                    run_ffmpeg(args)
                except Exception as e:
                    raise PipelineError(f"Failed to export final audio for '{input_path}': {e}") from e
            final_audio_paths.append(final_audio_path)
            
            # E. Auto Sub
            if options.enable_transcription:
                try:
                    model_size = options.whisper_model if options.whisper_model else model_size_from_preset(options.transcription_preset)
                    trans_opts = TranscriptionOptions(
                        model_size=model_size,
                        language=options.language,
                        asr_audio_speed=options.asr_audio_speed,
                        batch_size=options.batch_size,
                        word_timestamps=options.enable_subtitle_export
                    )
                    segments = transcribe_media(final_audio_path, trans_opts)
                    
                    if options.enable_subtitle_export and segments:
                        optimized_segments = optimize_subtitles(
                            segments,
                            video_format=options.target_video_format,
                            max_lines=options.subtitle_lines
                        )
                        sub_files = export_all_subtitles(optimized_segments, dirs["subtitles"], input_path.stem)
                        subtitle_files_dict[input_path.stem] = {k: Path(v).as_posix() for k, v in sub_files.items()}
                except Exception as e:
                    raise PipelineError(f"Failed in transcription/subtitle step on file '{input_path}': {e}") from e

    # 7. Metadata Export
    metadata_file = dirs["metadata"] / "project_metadata.json"
    processing_options_dict = {
        "merge_first": options.merge_first,
        "merge_gap_seconds": options.merge_gap_seconds,
        "volume_preset": options.volume_preset,
        "silence_preset": options.silence_preset,
        "transcription_preset": options.transcription_preset,
        "language": options.language,
        "enable_voice_cleanup": options.enable_voice_cleanup,
        "enable_social_optimize": options.enable_social_optimize,
        "whisper_model": options.whisper_model,
        "asr_audio_speed": options.asr_audio_speed,
        "batch_size": options.batch_size,
        "target_video_format": options.target_video_format,
        "subtitle_lines": options.subtitle_lines
    }
    
    proj_meta = build_project_metadata(
        project_name=options.project_name,
        input_files=validated_inputs,
        output_dir=final_project_dir,
        chunks=[],
        processing_options=processing_options_dict,
        subtitle_files=subtitle_files_dict if subtitle_files_dict else None,
        merged_file=merged_file_path,
        cleaned_file=cleaned_files[0] if len(cleaned_files) == 1 else (cleaned_files if cleaned_files else None),
        leveled_file=leveled_files[0] if len(leveled_files) == 1 else (leveled_files if leveled_files else None),
        shortened_file=shortened_files[0] if len(shortened_files) == 1 else (shortened_files if shortened_files else None)
    )
    
    try:
        export_project_json(proj_meta, metadata_file)
    except Exception as e:
        raise PipelineError(f"Failed to export final project metadata: {e}") from e
        
    return PipelineResult(
        project_name=options.project_name,
        output_dir=final_project_dir.as_posix(),
        input_files=[p.as_posix() for p in validated_inputs],
        working_audio=final_audio_paths[0].as_posix() if len(final_audio_paths) == 1 else [p.as_posix() for p in final_audio_paths],
        merged_file=merged_file_path.as_posix() if merged_file_path else None,
        leveled_file=leveled_files[0].as_posix() if len(leveled_files) == 1 else ([p.as_posix() for p in leveled_files] if leveled_files else None),
        shortened_file=shortened_files[0].as_posix() if len(shortened_files) == 1 else ([p.as_posix() for p in shortened_files] if shortened_files else None),
        subtitle_files=subtitle_files_dict if subtitle_files_dict else None,
        chunks=None,
        metadata_file=metadata_file.as_posix()
    )


def run_batch_pipeline(
    input_paths: List[Path],
    output_dir: Path,
    options: Optional[PipelineOptions] = None
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
        output_format=options.output_format,
        project_name=options.project_name,
        overwrite=options.overwrite,
        merge_gap_seconds=options.merge_gap_seconds,
        volume_preset=options.volume_preset,
        silence_preset=options.silence_preset,
        transcription_preset=options.transcription_preset,
        subtitle_base_name=options.subtitle_base_name,
        language=options.language,
        whisper_model=options.whisper_model,
        asr_audio_speed=options.asr_audio_speed,
        batch_size=options.batch_size,
        target_video_format=options.target_video_format,
        subtitle_lines=options.subtitle_lines
    )
    
    full_result = run_audio_pipeline(input_paths, output_dir, batch_options)
    
    results = []
    validated_inputs = validate_pipeline_inputs(input_paths)
    for path in validated_inputs:
        final_audio = Path(full_result.output_dir) / "final" / f"{path.stem}_final.{batch_options.output_format}"
        
        individual_subs = None
        if full_result.subtitle_files and path.stem in full_result.subtitle_files:
            individual_subs = full_result.subtitle_files[path.stem]
            
        leveled = Path(full_result.output_dir) / "work" / f"{path.stem}_leveled.{batch_options.output_format}"
        shortened = Path(full_result.output_dir) / "work" / f"{path.stem}_shortened.{batch_options.output_format}"
        
        results.append(
            PipelineResult(
                project_name=path.stem,
                output_dir=full_result.output_dir,
                input_files=[path.as_posix()],
                working_audio=final_audio.as_posix(),
                merged_file=None,
                leveled_file=leveled.as_posix() if leveled.exists() else None,
                shortened_file=shortened.as_posix() if shortened.exists() else None,
                subtitle_files=individual_subs,
                chunks=None,
                metadata_file=full_result.metadata_file
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


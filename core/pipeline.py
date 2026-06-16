import os
import re
import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional

from core.importer import validate_input_file, MediaImportError
from core.merger import merge_audio_files, MergeOptions, AudioMergeError
from core.volume_leveler import level_volume, VolumeLevelingOptions, VolumeLevelingError
from core.silence_shortener import shorten_silence, SilenceShortenerOptions, options_from_preset, SilenceShortenerError
from core.transcriber import transcribe_media, TranscriptionOptions, model_size_from_preset, TranscriptionError
from core.subtitle_exporter import export_all_subtitles
from core.sentence_splitter import split_segments_by_sentence, SentenceSplitOptions, SentenceSplitError
from core.audio_cutter import cut_audio_by_sentences, AudioCutOptions, AudioCutError
from core.metadata_exporter import build_project_metadata, export_project_json

class PipelineError(Exception):
    """Exception raised for errors during pipeline processing."""
    pass


@dataclass
class PipelineOptions:
    merge_first: bool = False
    enable_volume_leveling: bool = True
    enable_silence_shortening: bool = True
    enable_transcription: bool = False
    enable_subtitle_export: bool = False
    enable_sentence_split: bool = False
    enable_audio_cutting: bool = False
    output_format: str = "wav"
    project_name: str = "audio_project"
    overwrite: bool = True
    merge_gap_seconds: float = 0.0
    volume_preset: str = "natural"
    silence_preset: str = "natural"
    transcription_preset: str = "balanced"
    subtitle_base_name: str = "subtitles"
    language: Optional[str] = None


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
    Return output subdirectories: merged, processed, subtitles, chunks, shortened, metadata.
    Creates the base directory and metadata directory initially.
    """
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)
    
    dirs = {
        "merged": output_dir_obj / "merged",
        "processed": output_dir_obj / "processed",
        "subtitles": output_dir_obj / "subtitles",
        "chunks": output_dir_obj / "chunks",
        "shortened": output_dir_obj / "shortened",
        "metadata": output_dir_obj / "metadata"
    }
    
    # Always create metadata directory
    dirs["metadata"].mkdir(parents=True, exist_ok=True)
    
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
    output_dir_obj = Path(output_dir)
    
    if len(validated_inputs) > 1 and not options.merge_first:
        raise PipelineError(
            "Multiple input files provided, but merge_first is False. "
            "Please enable merge_first or use run_batch_pipeline to process files individually."
        )
        
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
    
    current_audio = validated_inputs[0]
    merged_file = None
    leveled_file = None
    shortened_file = None
    sub_files = None
    chunks_meta = None
    
    # 1. Merge if merge_first is enabled and there are multiple inputs
    if options.merge_first:
        if len(validated_inputs) > 1:
            merged_file = dirs["merged"] / f"merged.{options.output_format}"
            merge_opts = MergeOptions(
                gap_seconds=options.merge_gap_seconds,
                output_format=options.output_format,
                overwrite=options.overwrite
            )
            try:
                current_audio = merge_audio_files(validated_inputs, merged_file, merge_opts)
            except AudioMergeError as e:
                raise PipelineError(f"Failed in merger step: {e}") from e
        else:
            print("Merge requested but only one input file provided. Skipping merge step safely.")
            merged_file = None
            
    # 2. Volume Leveling
    if options.enable_volume_leveling:
        leveled_file = dirs["processed"] / f"leveled.{options.output_format}"
        vol_opts = VolumeLevelingOptions(
            preset=options.volume_preset,
            overwrite=options.overwrite
        )
        try:
            current_audio = level_volume(current_audio, leveled_file, vol_opts)
        except VolumeLevelingError as e:
            raise PipelineError(f"Failed in volume leveling step: {e}") from e
            
    # Define Main Processed Source
    main_processed_source = current_audio
            
    # 3. Silence Shortening (independent branch)
    if options.enable_silence_shortening:
        shortened_file = dirs["shortened"] / f"shortened.{options.output_format}"
        try:
            sil_opts = options_from_preset(options.silence_preset)
            sil_opts.overwrite = options.overwrite
            shorten_silence(main_processed_source, shortened_file, sil_opts)
        except SilenceShortenerError as e:
            raise PipelineError(f"Failed in silence shortening step: {e}") from e
            
    # 4. Transcription
    segments = None
    if options.enable_transcription:
        try:
            model_size = model_size_from_preset(options.transcription_preset)
            trans_opts = TranscriptionOptions(model_size=model_size, language=options.language)
            segments = transcribe_media(main_processed_source, trans_opts)
        except TranscriptionError as e:
            raise PipelineError(f"Failed in transcription step: {e}") from e
            
        # 5. Subtitle Export
        if options.enable_subtitle_export and segments:
            sub_base = dirs["subtitles"] / options.subtitle_base_name
            sub_files = export_all_subtitles(segments, dirs["subtitles"], options.subtitle_base_name)
            
        # 6. Sentence Splitting & Audio Cutting
        if options.enable_sentence_split and segments:
            try:
                sentences = split_segments_by_sentence(segments)
                if options.enable_audio_cutting and sentences:
                    cut_opts = AudioCutOptions(
                        output_format=options.output_format,
                        overwrite=options.overwrite
                    )
                    chunks_meta = cut_audio_by_sentences(main_processed_source, sentences, dirs["chunks"], cut_opts)
            except (SentenceSplitError, AudioCutError) as e:
                raise PipelineError(f"Failed in splitting/cutting step: {e}") from e
                
    # 7. Metadata Export
    metadata_file = dirs["metadata"] / "project_metadata.json"
    processing_options_dict = {
        "merge_first": options.merge_first,
        "merge_gap_seconds": options.merge_gap_seconds,
        "volume_preset": options.volume_preset,
        "silence_preset": options.silence_preset,
        "transcription_preset": options.transcription_preset,
        "language": options.language
    }
    
    subtitles_dict_str = {k: Path(v).as_posix() for k, v in sub_files.items()} if sub_files else None
    
    proj_meta = build_project_metadata(
        project_name=options.project_name,
        input_files=validated_inputs,
        output_dir=final_project_dir,
        chunks=chunks_meta if chunks_meta else [],
        processing_options=processing_options_dict,
        subtitle_files=subtitles_dict_str,
        merged_file=merged_file,
        cleaned_file=leveled_file if leveled_file else (merged_file if merged_file else validated_inputs[0]),
        leveled_file=leveled_file,
        shortened_file=shortened_file
    )
    
    try:
        export_project_json(proj_meta, metadata_file)
    except Exception as e:
        raise PipelineError(f"Failed to export final project metadata: {e}") from e
        
    return PipelineResult(
        project_name=options.project_name,
        output_dir=final_project_dir.as_posix(),
        input_files=[p.as_posix() for p in validated_inputs],
        working_audio=main_processed_source.as_posix(),
        merged_file=merged_file.as_posix() if merged_file else None,
        leveled_file=leveled_file.as_posix() if leveled_file else None,
        shortened_file=shortened_file.as_posix() if shortened_file else None,
        subtitle_files=subtitles_dict_str,
        chunks=chunks_meta,
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
        
    validated_inputs = validate_pipeline_inputs(input_paths)
    output_dir_obj = Path(output_dir)
    
    def sanitize_folder_name(name: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', '_', name).strip()

    # Determine parent batch directory name
    if not options.project_name or options.project_name.strip() == "":
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        parent_name = f"batch_project_{timestamp}"
    else:
        parent_name = sanitize_folder_name(options.project_name)

    parent_batch_dir = output_dir_obj / parent_name
    parent_batch_dir.mkdir(parents=True, exist_ok=True)
    
    results = []
    for path in validated_inputs:
        single_options = PipelineOptions(
            merge_first=False,
            enable_volume_leveling=options.enable_volume_leveling,
            enable_silence_shortening=options.enable_silence_shortening,
            enable_transcription=options.enable_transcription,
            enable_subtitle_export=options.enable_subtitle_export,
            enable_sentence_split=options.enable_sentence_split,
            enable_audio_cutting=options.enable_audio_cutting,
            output_format=options.output_format,
            project_name=path.stem,
            overwrite=options.overwrite,
            volume_preset=options.volume_preset,
            silence_preset=options.silence_preset,
            transcription_preset=options.transcription_preset,
            language=options.language,
            subtitle_base_name=options.subtitle_base_name
        )
        
        try:
            res = run_audio_pipeline([path], parent_batch_dir, single_options)
            results.append(res)
        except Exception as e:
            raise PipelineError(f"Pipeline failed on file '{path}': {e}") from e
            
    return results


def pipeline_result_to_dict(result: PipelineResult) -> Dict[str, Any]:
    """
    Convert PipelineResult object to JSON-safe dictionary.
    """
    try:
        return asdict(result)
    except Exception as e:
        raise PipelineError(f"Failed to serialize PipelineResult: {e}") from e

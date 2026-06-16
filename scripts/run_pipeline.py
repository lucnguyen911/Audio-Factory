import argparse
import sys
from pathlib import Path

# Add the project root to sys.path to run from any location
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from core.pipeline import (
    run_audio_pipeline,
    run_batch_pipeline,
    PipelineOptions,
    PipelineResult,
    PipelineError
)


def parse_arguments(args_list=None):
    """
    Parse command line arguments.
    """
    parser = argparse.ArgumentParser(
        description="Audio Factory CLI Pipeline Runner"
    )
    
    # Input & Output
    parser.add_argument(
        "--input",
        nargs="+",
        required=True,
        help="One or more input audio/video file paths."
    )
    parser.add_argument(
        "--output",
        default="output/cli_run",
        help="Directory to store pipeline output files."
    )
    
    # Workflow Flags
    parser.add_argument(
        "--merge-first",
        action="store_true",
        help="Merge all input files into a single audio file before processing."
    )
    parser.add_argument(
        "--volume",
        action="store_true",
        help="Enable volume leveling (EBU R128 standard)."
    )
    parser.add_argument(
        "--silence",
        action="store_true",
        help="Enable shortening silence intervals."
    )
    parser.add_argument(
        "--transcribe",
        action="store_true",
        help="Enable speech-to-text transcription."
    )
    parser.add_argument(
        "--subtitles",
        action="store_true",
        help="Enable subtitle export (requires --transcribe)."
    )
    parser.add_argument(
        "--split-sentences",
        action="store_true",
        help="Enable splitting transcription into sentence segments (requires --transcribe)."
    )
    parser.add_argument(
        "--cut-audio",
        action="store_true",
        help="Enable cutting audio into chunks by sentence segments (requires --split-sentences)."
    )
    
    # Presets & Options
    parser.add_argument(
        "--project-name",
        default="audio_project",
        help="Project name for metadata compiler."
    )
    parser.add_argument(
        "--merge-gap",
        type=float,
        default=0.0,
        help="Silence gap between merged files in seconds."
    )
    parser.add_argument(
        "--volume-preset",
        choices=["natural", "strong", "aggressive"],
        default="natural",
        help="Volume leveling preset style."
    )
    parser.add_argument(
        "--silence-preset",
        choices=["natural", "fast", "hard"],
        default="natural",
        help="Silence shortening preset configuration."
    )
    parser.add_argument(
        "--transcription-preset",
        choices=["fast", "balanced", "accurate", "best"],
        default="balanced",
        help="Speech-to-text transcription model preset."
    )
    parser.add_argument(
        "--language",
        default=None,
        help="Language code for transcription (e.g. 'vi', 'en'). None for auto-detect."
    )
    parser.add_argument(
        "--output-format",
        default="wav",
        help="Output audio format extension (e.g. wav, mp3)."
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="Do not overwrite existing files (raise error instead)."
    )
    
    # Batch mode
    parser.add_argument(
        "--batch",
        action="store_true",
        help="Process multiple files individually in batch mode."
    )
    
    return parser.parse_args(args_list)


def print_result(result: PipelineResult, prefix: str = ""):
    """
    Print formatted pipeline execution result.
    """
    indent = "  " if prefix else ""
    if prefix:
        print(prefix)
    print(f"{indent}Project Name: {result.project_name}")
    print(f"{indent}Output Dir: {result.output_dir}")
    print(f"{indent}Working Audio: {result.working_audio}")
    
    if result.subtitle_files:
        print(f"{indent}Subtitle Files:")
        for fmt, path in result.subtitle_files.items():
            print(f"{indent}  - {fmt.upper()}: {path}")
            
    if result.chunks is not None:
        print(f"{indent}Chunks Count: {len(result.chunks)}")
        
    if result.metadata_file:
        print(f"{indent}Metadata File: {result.metadata_file}")


def main():
    args = parse_arguments()
    
    # Map CLI arguments to PipelineOptions
    options = PipelineOptions(
        merge_first=args.merge_first,
        enable_volume_leveling=args.volume,
        enable_silence_shortening=args.silence,
        enable_transcription=args.transcribe,
        enable_subtitle_export=args.subtitles,
        enable_sentence_split=args.split_sentences,
        enable_audio_cutting=args.cut_audio,
        output_format=args.output_format,
        project_name=args.project_name,
        overwrite=not args.no_overwrite,
        merge_gap_seconds=args.merge_gap,
        volume_preset=args.volume_preset,
        silence_preset=args.silence_preset,
        transcription_preset=args.transcription_preset,
        language=args.language,
        subtitle_base_name="subtitles"
    )
    
    # Parse inputs to pathlist
    input_paths = [Path(p) for p in args.input]
    output_dir = Path(args.output)
    
    try:
        if args.batch:
            print(f"Starting batch pipeline runner on {len(input_paths)} files...")
            results = run_batch_pipeline(input_paths, output_dir, options)
            print("=" * 60)
            print(f"Batch Processing Completed Successfully. Results:")
            for idx, res in enumerate(results, 1):
                print_result(res, prefix=f"--- File {idx}/{len(results)} ---")
                print()
        else:
            print("Starting pipeline runner...")
            result = run_audio_pipeline(input_paths, output_dir, options)
            print("=" * 60)
            print("Pipeline Completed Successfully. Result:")
            print_result(result)
            
        sys.exit(0)
        
    except PipelineError as e:
        print(f"Pipeline Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected Error during pipeline execution: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

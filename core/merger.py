import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from core.ffmpeg_runner import run_ffmpeg, FFmpegError
from core.importer import validate_input_file, MediaImportError

class AudioMergeError(Exception):
    """Exception raised for errors during audio merging."""
    pass


@dataclass
class MergeOptions:
    gap_seconds: float = 0.0
    output_format: str = "wav"
    sample_rate: int = 44100
    channels: int = 2
    overwrite: bool = True


def validate_merge_inputs(input_paths: List[Path]) -> List[Path]:
    """
    Validate the list of input files.
    Ensures list is not empty, and validates each file exists and is supported.
    """
    if not input_paths:
        raise AudioMergeError("Input path list is empty.")
        
    validated_paths = []
    for path in input_paths:
        try:
            validated = validate_input_file(path)
            validated_paths.append(validated)
        except MediaImportError as e:
            raise AudioMergeError(f"Invalid input file '{path}': {e}") from e
            
    return validated_paths


def create_silence_file(
    output_path: Path,
    duration_seconds: float,
    sample_rate: int = 44100,
    channels: int = 2
) -> Path:
    """
    Create a silence audio file of the specified duration using FFmpeg's anullsrc filter.
    """
    if duration_seconds <= 0:
        raise AudioMergeError(f"Silence duration must be greater than 0. Received: {duration_seconds}")
        
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    cl = "mono" if channels == 1 else "stereo"
    
    args = [
        "-y",
        "-f", "lavfi",
        "-i", f"anullsrc=r={sample_rate}:cl={cl}",
        "-t", f"{duration_seconds:.6f}",
        str(output_path_obj)
    ]
    
    try:
        run_ffmpeg(args)
        return output_path_obj
    except FFmpegError as e:
        raise AudioMergeError(f"Failed to create silence file: {e}") from e


def build_concat_list_file(input_paths: List[Path], list_file_path: Path) -> Path:
    """
    Generate the list file for FFmpeg concat demuxer.
    Each path is converted using as_posix() and single quotes are escaped.
    """
    list_file_path_obj = Path(list_file_path)
    list_file_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    lines = []
    for path in input_paths:
        abs_posix = Path(path).absolute().as_posix()
        escaped = abs_posix.replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
        
    try:
        list_file_path_obj.write_text("\n".join(lines), encoding="utf-8")
        return list_file_path_obj
    except Exception as e:
        raise AudioMergeError(f"Failed to write concat list file: {e}") from e


def merge_audio_files(
    input_paths: List[Path],
    output_path: Path,
    options: Optional[MergeOptions] = None
) -> Path:
    """
    Merge multiple audio files into a single output file.
    Supports inserting a silent gap between files.
    """
    if options is None:
        options = MergeOptions()
        
    validated_inputs = validate_merge_inputs(input_paths)
    output_path_obj = Path(output_path)
    
    if output_path_obj.exists() and not options.overwrite:
        raise AudioMergeError(f"Output file already exists and overwrite is False: {output_path_obj}")
        
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    ext = output_path_obj.suffix.lower().lstrip(".")
    if not ext:
        ext = options.output_format.lower().lstrip(".")
        output_path_obj = output_path_obj.with_suffix(f".{ext}")
        
    if ext == "wav":
        codec_args = ["-c:a", "pcm_s16le"]
    elif ext == "mp3":
        codec_args = ["-c:a", "libmp3lame"]
    elif ext == "m4a":
        codec_args = ["-c:a", "aac"]
    else:
        codec_args = []
        
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        merge_list = []
        
        for i, input_file in enumerate(validated_inputs):
            merge_list.append(input_file)
            
            if options.gap_seconds > 0.0 and i < len(validated_inputs) - 1:
                silence_file = temp_dir / f"silence_{i}.wav"
                create_silence_file(
                    silence_file,
                    duration_seconds=options.gap_seconds,
                    sample_rate=options.sample_rate,
                    channels=options.channels
                )
                merge_list.append(silence_file)
                
        overwrite_flag = "-y" if options.overwrite else "-n"
        args = [overwrite_flag]
        for media_path in merge_list:
            args += ["-i", str(media_path)]

        # Inputs may legitimately be a mix of pcm_f32le (normalised/copy
        # path) and pcm_s16le (silence-shortened path or inserted gap).  The
        # concat demuxer assumes identical codecs and can misread such a list.
        # Decode and normalise every stream in one filter graph before joining.
        channel_layout = "mono" if options.channels == 1 else "stereo"
        normalizers = [
            (
                f"[{index}:a]aresample={options.sample_rate},"
                f"aformat=sample_fmts=fltp:sample_rates={options.sample_rate}:"
                f"channel_layouts={channel_layout}[a{index}]"
            )
            for index in range(len(merge_list))
        ]
        concat_inputs = "".join(f"[a{index}]" for index in range(len(merge_list)))
        filter_complex = ";".join(
            normalizers
            + [f"{concat_inputs}concat=n={len(merge_list)}:v=0:a=1[merged_audio]"]
        )
        args += [
            "-filter_complex", filter_complex,
            "-map", "[merged_audio]",
        ] + codec_args + [
            "-ar", str(options.sample_rate),
            "-ac", str(options.channels),
            str(output_path_obj)
        ]
        
        try:
            run_ffmpeg(args)
            return output_path_obj
        except FFmpegError as e:
            raise AudioMergeError(f"Failed to merge audio files: {e}") from e

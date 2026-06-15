import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

from core.ffmpeg_runner import run_ffmpeg, FFmpegError
from core.importer import validate_input_file, MediaImportError
from core.sentence_splitter import SentenceSegment

class AudioCutError(Exception):
    """Exception raised for errors during audio cutting."""
    pass


@dataclass
class AudioCutOptions:
    output_format: str = "wav"
    padding_before: float = 0.08
    padding_after: float = 0.12
    filename_mode: str = "index"
    max_words_in_filename: int = 6
    overwrite: bool = True


VALID_FILENAME_MODES = {"index", "index_text", "index_time"}


def validate_filename_mode(mode: str) -> str:
    """
    Check if the filename mode is supported.
    Raises AudioCutError if invalid.
    """
    mode_lower = mode.lower()
    if mode_lower not in VALID_FILENAME_MODES:
        raise AudioCutError(
            f"Invalid filename mode '{mode}'. Valid modes are: {', '.join(sorted(VALID_FILENAME_MODES))}"
        )
    return mode_lower


def sanitize_filename_text(text: str, max_words: int = 6) -> str:
    """
    Clean and sanitize text for use in a file name.
    Removes Windows forbidden characters and joins words with hyphens.
    """
    # Remove Windows forbidden characters: <>:"/\|?*
    cleaned = re.sub(r'[<>:"/\\|?*]', '', text).strip()
    
    # Replace punctuation with spaces
    words_raw = re.sub(r'[.,;!()[\]{}]', ' ', cleaned)
    words = [w for w in words_raw.split() if w]
    
    if not words:
        return "untitled"
        
    words = words[:max_words]
    filename_part = "-".join(words).lower()
    
    return filename_part if filename_part else "untitled"


def build_output_filename(sentence: SentenceSegment, options: AudioCutOptions) -> str:
    """
    Generate output filename for a SentenceSegment based on AudioCutOptions.
    """
    mode = validate_filename_mode(options.filename_mode)
    ext = options.output_format.lower().lstrip(".")
    
    if mode == "index":
        return f"{sentence.index:03d}.{ext}"
    elif mode == "index_text":
        sanitized = sanitize_filename_text(sentence.text, options.max_words_in_filename)
        return f"{sentence.index:03d}_{sanitized}.{ext}"
    else:  # index_time
        return f"{sentence.index:03d}_{sentence.start:.2f}-{sentence.end:.2f}.{ext}"


def normalize_cut_segments(segments: List[Union[SentenceSegment, Dict[str, Any]]]) -> List[SentenceSegment]:
    """
    Normalize segment list (dataclasses or dicts) to SentenceSegments and validates properties.
    """
    normalized = []
    
    for idx, item in enumerate(segments):
        if isinstance(item, SentenceSegment):
            index = item.index
            start = item.start
            end = item.end
            text = item.text
            source_indices = item.source_segment_indexes
        elif isinstance(item, dict):
            if "index" not in item or "start" not in item or "end" not in item or "text" not in item:
                raise AudioCutError(f"Missing required keys in segment dict at index {idx}: {item}")
            index = item["index"]
            start = item["start"]
            end = item["end"]
            text = item["text"]
            source_indices = item.get("source_segment_indexes")
        else:
            raise AudioCutError(f"Invalid segment type at index {idx}: {type(item)}")
            
        try:
            index_int = int(index)
            start_f = float(start)
            end_f = float(end)
        except (ValueError, TypeError) as e:
            raise AudioCutError(f"Invalid non-numeric values at index {idx}: {e}") from e
            
        if index_int < 1:
            raise AudioCutError(f"Index must be greater than or equal to 1 at index {idx}: {index_int}")
            
        if start_f < 0:
            raise AudioCutError(f"Start timestamp cannot be negative at index {idx}: {start_f}")
            
        if end_f <= start_f:
            raise AudioCutError(f"End timestamp must be strictly greater than start timestamp at index {idx}: {start_f} -> {end_f}")
            
        text_str = str(text).strip()
        if not text_str:
            raise AudioCutError(f"Text cannot be empty or whitespace at index {idx}")
            
        normalized.append(
            SentenceSegment(
                index=index_int,
                start=start_f,
                end=end_f,
                text=text_str,
                source_segment_indexes=source_indices
            )
        )
        
    return normalized


def cut_audio_segment(
    input_path: Path,
    output_path: Path,
    start: float,
    end: float,
    overwrite: bool = True
) -> Path:
    """
    Cut a single audio chunk from the input file using FFmpeg.
    """
    output_path_obj = Path(output_path)
    if output_path_obj.exists() and not overwrite:
        raise AudioCutError(f"Output file already exists and overwrite is set to False: {output_path_obj}")
        
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    ext = output_path_obj.suffix.lower().lstrip(".")
    if ext == "wav":
        codec_args = ["-c:a", "pcm_s16le"]
    elif ext == "mp3":
        codec_args = ["-c:a", "libmp3lame"]
    elif ext == "m4a":
        codec_args = ["-c:a", "aac"]
    else:
        codec_args = ["-c:a", "copy"]
        
    overwrite_flag = "-y" if overwrite else "-n"
    args = [
        overwrite_flag,
        "-i", str(input_path),
        "-ss", f"{start:.6f}",
        "-to", f"{end:.6f}"
    ] + codec_args + [
        str(output_path_obj)
    ]
    
    try:
        run_ffmpeg(args)
        return output_path_obj
    except FFmpegError as e:
        raise AudioCutError(f"Failed to cut audio segment: {e}") from e


def cut_audio_by_sentences(
    input_path: Path,
    sentences: List[Union[SentenceSegment, Dict[str, Any]]],
    output_dir: Path,
    options: Optional[AudioCutOptions] = None
) -> List[Dict[str, Any]]:
    """
    Cut the input audio file into multiple sentence-based audio chunks.
    """
    if options is None:
        options = AudioCutOptions()
        
    try:
        input_path_obj = validate_input_file(input_path)
    except MediaImportError as e:
        raise AudioCutError(f"Invalid input file: {e}") from e
        
    norm_sentences = normalize_cut_segments(sentences)
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)
    
    metadata = []
    for sent in norm_sentences:
        # Apply padding parameters safely
        padded_start = max(0.0, sent.start - options.padding_before)
        padded_end = sent.end + options.padding_after
        
        filename = build_output_filename(sent, options)
        output_path = output_dir_obj / filename
        
        try:
            cut_audio_segment(
                input_path_obj,
                output_path,
                start=padded_start,
                end=padded_end,
                overwrite=options.overwrite
            )
            metadata.append(
                {
                    "index": sent.index,
                    "start": sent.start,
                    "end": sent.end,
                    "text": sent.text,
                    "file": filename
                }
            )
        except Exception as e:
            raise AudioCutError(f"Failed to process cut for sentence index {sent.index}: {e}") from e
            
    return metadata

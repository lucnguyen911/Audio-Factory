import csv
import json
import datetime
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

class MetadataExportError(Exception):
    """Exception raised for errors during metadata exporting."""
    pass


@dataclass
class AudioChunkMetadata:
    index: int
    text: str
    start: float
    end: float
    file: str
    source_segment_indexes: Optional[List[int]] = None


@dataclass
class ProjectMetadata:
    project_name: str
    input_files: List[str]
    output_dir: str
    created_at: str
    processing_options: Dict[str, Any]
    chunks: List[AudioChunkMetadata]
    subtitle_files: Optional[Dict[str, str]] = None
    merged_file: Optional[str] = None
    cleaned_file: Optional[str] = None


def normalize_chunk_metadata(chunks: List[Union[AudioChunkMetadata, Dict[str, Any]]]) -> List[AudioChunkMetadata]:
    """
    Normalize list of chunks (dataclasses or dicts) to AudioChunkMetadata, validating properties.
    """
    normalized = []
    
    for idx, item in enumerate(chunks):
        if isinstance(item, AudioChunkMetadata):
            index = item.index
            text = item.text
            start = item.start
            end = item.end
            filename = item.file
            source_indices = item.source_segment_indexes
        elif isinstance(item, dict):
            if "index" not in item or "text" not in item or "start" not in item or "end" not in item or "file" not in item:
                raise MetadataExportError(f"Missing required keys in chunk dict at index {idx}: {item}")
            index = item["index"]
            text = item["text"]
            start = item["start"]
            end = item["end"]
            filename = item["file"]
            source_indices = item.get("source_segment_indexes")
        else:
            raise MetadataExportError(f"Invalid chunk type at index {idx}: {type(item)}")
            
        try:
            index_int = int(index)
            start_f = float(start)
            end_f = float(end)
        except (ValueError, TypeError) as e:
            raise MetadataExportError(f"Invalid non-numeric values at index {idx}: {e}") from e
            
        if index_int < 1:
            raise MetadataExportError(f"Index must be greater than or equal to 1 at index {idx}: {index_int}")
            
        if start_f < 0:
            raise MetadataExportError(f"Start timestamp cannot be negative at index {idx}: {start_f}")
            
        if end_f <= start_f:
            raise MetadataExportError(f"End timestamp must be strictly greater than start timestamp at index {idx}: {start_f} -> {end_f}")
            
        text_str = str(text).strip()
        if not text_str:
            raise MetadataExportError(f"Text cannot be empty or whitespace at index {idx}")
            
        file_str = str(filename).strip()
        if not file_str:
            raise MetadataExportError(f"Filename cannot be empty or whitespace at index {idx}")
            
        normalized.append(
            AudioChunkMetadata(
                index=index_int,
                text=text_str,
                start=start_f,
                end=end_f,
                file=file_str,
                source_segment_indexes=source_indices
            )
        )
        
    return normalized


def project_metadata_to_dict(metadata: ProjectMetadata) -> Dict[str, Any]:
    """
    Convert ProjectMetadata dataclass recursively to a JSON-safe dictionary.
    """
    try:
        return asdict(metadata)
    except Exception as e:
        raise MetadataExportError(f"Failed to serialize ProjectMetadata: {e}") from e


def export_project_json(metadata: ProjectMetadata, output_path: Path) -> Path:
    """
    Export project metadata to a JSON file (UTF-8, preserving Unicode).
    """
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    data = project_metadata_to_dict(metadata)
    
    try:
        with open(output_path_obj, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return output_path_obj
    except Exception as e:
        raise MetadataExportError(f"Failed to export project JSON: {e}") from e


def export_chunks_json(chunks: List[Union[AudioChunkMetadata, Dict[str, Any]]], output_path: Path) -> Path:
    """
    Export chunk metadata list to a JSON file.
    """
    norm_chunks = normalize_chunk_metadata(chunks)
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    data = [asdict(c) for c in norm_chunks]
    
    try:
        with open(output_path_obj, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return output_path_obj
    except Exception as e:
        raise MetadataExportError(f"Failed to export chunks JSON: {e}") from e


def export_chunks_csv(chunks: List[Union[AudioChunkMetadata, Dict[str, Any]]], output_path: Path) -> Path:
    """
    Export chunk metadata to a CSV file (UTF-8 with BOM for Excel compatibility).
    """
    norm_chunks = normalize_chunk_metadata(chunks)
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(output_path_obj, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["index", "start", "end", "duration", "text", "file", "source_segment_indexes"])
            for chunk in norm_chunks:
                duration = chunk.end - chunk.start
                source_seg_str = json.dumps(chunk.source_segment_indexes) if chunk.source_segment_indexes is not None else ""
                writer.writerow([
                    chunk.index,
                    chunk.start,
                    chunk.end,
                    duration,
                    chunk.text,
                    chunk.file,
                    source_seg_str
                ])
        return output_path_obj
    except Exception as e:
        raise MetadataExportError(f"Failed to export chunks CSV: {e}") from e


def build_project_metadata(
    project_name: str,
    input_files: List[Union[Path, str]],
    output_dir: Union[Path, str],
    chunks: List[Union[AudioChunkMetadata, Dict[str, Any]]],
    processing_options: Optional[Dict[str, Any]] = None,
    subtitle_files: Optional[Dict[str, Union[Path, str]]] = None,
    merged_file: Optional[Union[Path, str]] = None,
    cleaned_file: Optional[Union[Path, str]] = None
) -> ProjectMetadata:
    """
    Build a ProjectMetadata object, auto-generating the ISO timestamp.
    """
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    norm_inputs = [Path(f).as_posix() for f in input_files]
    norm_output_dir = Path(output_dir).as_posix()
    norm_chunks = normalize_chunk_metadata(chunks)
    
    norm_subtitles = None
    if subtitle_files is not None:
        norm_subtitles = {k: Path(v).as_posix() for k, v in subtitle_files.items()}
        
    norm_merged = Path(merged_file).as_posix() if merged_file is not None else None
    norm_cleaned = Path(cleaned_file).as_posix() if cleaned_file is not None else None
    
    return ProjectMetadata(
        project_name=project_name,
        input_files=norm_inputs,
        output_dir=norm_output_dir,
        created_at=created_at,
        processing_options=processing_options if processing_options is not None else {},
        chunks=norm_chunks,
        subtitle_files=norm_subtitles,
        merged_file=norm_merged,
        cleaned_file=norm_cleaned
    )

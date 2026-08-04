import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

class SubtitleExportError(Exception):
    """Exception raised for errors during subtitle exporting."""
    pass


@dataclass
class TranscriptSegment:
    start: float
    end: float
    text: str
    index: Optional[int] = None
    words: Optional[List[Dict[str, Any]]] = None


def _split_seconds(seconds: float) -> tuple:
    """Helper to convert float seconds into (hours, minutes, seconds, milliseconds) tuple."""
    total_ms = int(round(seconds * 1000))
    if total_ms < 0:
        total_ms = 0
        
    hours = total_ms // 3600000
    total_ms %= 3600000
    minutes = total_ms // 60000
    total_ms %= 60000
    secs = total_ms // 1000
    ms = total_ms % 1000
    
    return hours, minutes, secs, ms


def format_srt_timestamp(seconds: float) -> str:
    """Format seconds into SRT timestamp format: HH:MM:SS,mmm"""
    hours, minutes, secs, ms = _split_seconds(seconds)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def format_vtt_timestamp(seconds: float) -> str:
    """Format seconds into VTT timestamp format: HH:MM:SS.mmm"""
    hours, minutes, secs, ms = _split_seconds(seconds)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{ms:03d}"


def normalize_segments(segments: List[Union[TranscriptSegment, Dict[str, Any]]]) -> List[TranscriptSegment]:
    """
    Normalize a list of segments (dataclasses or dicts) into a list of TranscriptSegment.
    Performs constraints checking and automatically assigns sequential indices starting from 1.
    """
    normalized = []
    
    for idx, item in enumerate(segments):
        if isinstance(item, TranscriptSegment):
            start = item.start
            end = item.end
            text = item.text
            words = item.words
        elif isinstance(item, dict):
            if "start" not in item or "end" not in item or "text" not in item:
                raise SubtitleExportError(f"Missing required keys in segment dict at index {idx}: {item}")
            start = item["start"]
            end = item["end"]
            text = item["text"]
            words = item.get("words")
        else:
            raise SubtitleExportError(f"Invalid segment type at index {idx}: {type(item)}")
            
        try:
            start_f = float(start)
            end_f = float(end)
        except (ValueError, TypeError) as e:
            raise SubtitleExportError(f"Invalid non-numeric start/end timestamps at index {idx}: {e}") from e
            
        if start_f < 0:
            raise SubtitleExportError(f"Start timestamp cannot be negative at index {idx}: {start_f}")
            
        if end_f <= start_f:
            raise SubtitleExportError(f"End timestamp must be strictly greater than start timestamp at index {idx}: {start_f} -> {end_f}")
            
        text_str = str(text).strip()
        if not text_str:
            raise SubtitleExportError(f"Text cannot be empty or only whitespace at index {idx}")
            
        normalized.append(
            TranscriptSegment(
                start=start_f,
                end=end_f,
                text=text_str,
                index=idx + 1,
                words=words
            )
        )
        
    return normalized


def export_srt(
    segments: List[Union[TranscriptSegment, Dict[str, Any]]],
    output_path: Path,
    strict: bool = False,
    **kwargs
) -> Path:
    """Export segments to a SubRip (.srt) subtitle file."""
    normalized = normalize_segments(segments)
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    lines = []
    for seg in normalized:
        lines.append(str(seg.index))
        lines.append(f"{format_srt_timestamp(seg.start)} --> {format_srt_timestamp(seg.end)}")
        lines.append(seg.text)
        lines.append("")
        
    try:
        output_path_obj.write_text("\n".join(lines), encoding="utf-8-sig")
        return output_path_obj
    except Exception as e:
        raise SubtitleExportError(f"Failed to write SRT file to '{output_path_obj}': {e}") from e


def export_vtt(segments: List[Union[TranscriptSegment, Dict[str, Any]]], output_path: Path) -> Path:
    """Export segments to a WebVTT (.vtt) subtitle file."""
    normalized = normalize_segments(segments)
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    lines = ["WEBVTT", ""]
    for seg in normalized:
        lines.append(str(seg.index))
        lines.append(f"{format_vtt_timestamp(seg.start)} --> {format_vtt_timestamp(seg.end)}")
        lines.append(seg.text)
        lines.append("")
        
    try:
        output_path_obj.write_text("\n".join(lines), encoding="utf-8")
        return output_path_obj
    except Exception as e:
        raise SubtitleExportError(f"Failed to write VTT file to '{output_path_obj}': {e}") from e


def export_txt(
    segments: List[Union[TranscriptSegment, Dict[str, Any]]],
    output_path: Path,
    include_timestamps: bool = False
) -> Path:
    """Export segments to a plain text (.txt) file, optionally including timestamps."""
    normalized = normalize_segments(segments)
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    lines = []
    for seg in normalized:
        if include_timestamps:
            ts_start = format_vtt_timestamp(seg.start)
            ts_end = format_vtt_timestamp(seg.end)
            lines.append(f"[{ts_start} --> {ts_end}] {seg.text}")
        else:
            lines.append(seg.text)
            
    try:
        output_path_obj.write_text("\n".join(lines), encoding="utf-8-sig")
        return output_path_obj
    except Exception as e:
        raise SubtitleExportError(f"Failed to write TXT file to '{output_path_obj}': {e}") from e


def export_json(segments: List[Union[TranscriptSegment, Dict[str, Any]]], output_path: Path) -> Path:
    """Export segments to a JSON file (UTF-8, formatted)."""
    normalized = normalize_segments(segments)
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    serialized = [asdict(seg) for seg in normalized]
    
    try:
        with open(output_path_obj, "w", encoding="utf-8") as f:
            json.dump(serialized, f, indent=2, ensure_ascii=False)
        return output_path_obj
    except Exception as e:
        raise SubtitleExportError(f"Failed to write JSON file to '{output_path_obj}': {e}") from e


def export_all_subtitles(
    segments: List[Union[TranscriptSegment, Dict[str, Any]]],
    output_dir: Path,
    base_name: str
) -> Dict[str, Path]:
    """Export segments into all four formats (SRT, VTT, TXT, JSON) inside output_dir."""
    normalized = normalize_segments(segments)
    output_dir_obj = Path(output_dir)
    output_dir_obj.mkdir(parents=True, exist_ok=True)
    
    return {
        "srt": export_srt(normalized, output_dir_obj / f"{base_name}.srt"),
        "vtt": export_vtt(normalized, output_dir_obj / f"{base_name}.vtt"),
        "txt": export_txt(normalized, output_dir_obj / f"{base_name}.txt"),
        "json": export_json(normalized, output_dir_obj / f"{base_name}.json")
    }

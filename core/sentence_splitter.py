import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

from core.subtitle_exporter import TranscriptSegment, normalize_segments, SubtitleExportError

class SentenceSplitError(Exception):
    """Exception raised for errors during sentence splitting."""
    pass


@dataclass
class SentenceSegment:
    index: int
    start: float
    end: float
    text: str
    source_segment_indexes: Optional[List[int]] = None


@dataclass
class SentenceSplitOptions:
    min_sentence_duration: float = 1.0
    max_sentence_duration: float = 12.0
    pause_split_threshold: float = 0.65
    min_chars: int = 3
    force_split_long_segments: bool = True


def is_sentence_ending(text: str) -> bool:
    """
    Check if the text ends with a sentence-ending punctuation.
    """
    stripped = text.strip()
    if not stripped:
        return False
    return stripped[-1] in {".", "?", "!", "…"} or stripped.endswith("...")


def normalize_text(text: str) -> str:
    """
    Remove redundant whitespaces, strip input, preserving Unicode characters.
    """
    return " ".join(text.strip().split())


def split_text_into_sentences(text: str) -> List[str]:
    """
    Split a text block into individual sentences based on ending punctuations,
    preserving the ending punctuation at the end of each sentence.
    """
    normalized = normalize_text(text)
    # Split using lookbehind for ?!… and dots that are not part of a consecutive dot sequence
    parts = re.split(r"(?<=[?!…])\s*|(?<!\.)\.(?!\.)\s*|(?<=\.{3})\s*", normalized)
    result = []
    for part in parts:
        part_str = part.strip()
        if part_str:
            result.append(part_str)
    return result


def _split_long_segment_by_comma(seg: TranscriptSegment, max_duration: float) -> List[TranscriptSegment]:
    """
    Heuristically split a long TranscriptSegment into multiple shorter ones at comma/semicolon/dash
    boundaries, estimating the time split point proportionally to character lengths.
    """
    duration = seg.end - seg.start
    if duration <= max_duration:
        return [seg]
        
    text = seg.text
    # Find all split characters
    commas = [i for i, char in enumerate(text) if char in {",", ";", "-", "–"}]
    if not commas:
        return [seg]
        
    # Find the split point closest to the text center to maintain balanced chunks
    center = len(text) / 2
    best_comma_idx = min(commas, key=lambda idx: abs(idx - center))
    
    part1_text = text[:best_comma_idx + 1].strip()
    part2_text = text[best_comma_idx + 1:].strip()
    
    if not part1_text or not part2_text:
        return [seg]
        
    len1 = len(part1_text)
    len2 = len(part2_text)
    ratio = len1 / (len1 + len2)
    
    split_time = seg.start + ratio * duration
    
    seg1 = TranscriptSegment(start=seg.start, end=split_time, text=part1_text, index=seg.index)
    seg2 = TranscriptSegment(start=split_time, end=seg.end, text=part2_text, index=seg.index)
    
    # Recursively split if still exceeding max_duration
    return _split_long_segment_by_comma(seg1, max_duration) + _split_long_segment_by_comma(seg2, max_duration)


def split_segments_by_sentence(
    segments: List[Union[TranscriptSegment, Dict[str, Any]]],
    options: Optional[SentenceSplitOptions] = None
) -> List[SentenceSegment]:
    """
    Group and split transcript segments into SentenceSegments.
    """
    if options is None:
        options = SentenceSplitOptions()
        
    try:
        norm_segs = normalize_segments(segments)
    except SubtitleExportError as e:
        raise SentenceSplitError(f"Invalid input segments: {e}") from e
        
    if not norm_segs:
        return []
        
    # Phase 1: Pre-split excessively long segments if option is enabled
    preprocessed_segs = []
    for seg in norm_segs:
        if options.force_split_long_segments and (seg.end - seg.start) > options.max_sentence_duration:
            preprocessed_segs.extend(_split_long_segment_by_comma(seg, options.max_sentence_duration))
        else:
            preprocessed_segs.append(seg)
            
    # Phase 2: Group segments into sentences based on punctuation, pauses, and max duration
    grouped_sentences_segs = []
    current_group = []
    
    for i, seg in enumerate(preprocessed_segs):
        if not current_group:
            current_group.append(seg)
        else:
            # Check if adding this segment would exceed max duration
            added_duration = seg.end - current_group[0].start
            if options.force_split_long_segments and added_duration > options.max_sentence_duration:
                grouped_sentences_segs.append(current_group)
                current_group = [seg]
            else:
                current_group.append(seg)
                
        # Determine if we should split after the current segment is added
        should_split = False
        
        # 1. Punctuation ending
        if is_sentence_ending(seg.text):
            should_split = True
            
        # 2. Pause threshold
        if i + 1 < len(preprocessed_segs):
            next_seg = preprocessed_segs[i + 1]
            gap = next_seg.start - seg.end
            if gap >= options.pause_split_threshold:
                should_split = True
                
        if should_split and current_group:
            grouped_sentences_segs.append(current_group)
            current_group = []
            
    if current_group:
        grouped_sentences_segs.append(current_group)
        
    # Convert groups to SentenceSegment objects
    initial_sentences = []
    for seg_list in grouped_sentences_segs:
        text_content = normalize_text(" ".join(s.text for s in seg_list))
        initial_sentences.append(
            SentenceSegment(
                index=0,
                start=seg_list[0].start,
                end=seg_list[-1].end,
                text=text_content,
                source_segment_indexes=[s.index for s in seg_list if s.index is not None]
            )
        )
        
    # Phase 3: Merge short sentences forward or backward if duration < min_sentence_duration
    merged_sentences = []
    i = 0
    while i < len(initial_sentences):
        curr = initial_sentences[i]
        duration = curr.end - curr.start
        
        if duration < options.min_sentence_duration:
            # Try merging forward first
            if i + 1 < len(initial_sentences):
                next_sent = initial_sentences[i + 1]
                merged_duration = next_sent.end - curr.start
                if merged_duration <= options.max_sentence_duration:
                    merged_sent = SentenceSegment(
                        index=0,
                        start=curr.start,
                        end=next_sent.end,
                        text=normalize_text(curr.text + " " + next_sent.text),
                        source_segment_indexes=curr.source_segment_indexes + next_sent.source_segment_indexes
                    )
                    initial_sentences[i + 1] = merged_sent
                    i += 1
                    continue
            # Try merging backward next
            if merged_sentences:
                prev = merged_sentences[-1]
                merged_duration = curr.end - prev.start
                if merged_duration <= options.max_sentence_duration:
                    merged_sentences[-1] = SentenceSegment(
                        index=0,
                        start=prev.start,
                        end=curr.end,
                        text=normalize_text(prev.text + " " + curr.text),
                        source_segment_indexes=prev.source_segment_indexes + curr.source_segment_indexes
                    )
                    i += 1
                    continue
                    
        merged_sentences.append(curr)
        i += 1
        
    # Phase 4: Re-assign sequential indices starting from 1
    for idx, sent in enumerate(merged_sentences):
        sent.index = idx + 1
        
    return merged_sentences


def sentences_to_dicts(sentences: List[SentenceSegment]) -> List[Dict[str, Any]]:
    """
    Convert a list of SentenceSegment objects to standardized dictionaries.
    """
    return [
        {
            "index": sent.index,
            "start": sent.start,
            "end": sent.end,
            "text": sent.text,
            "source_segment_indexes": sent.source_segment_indexes
        }
        for sent in sentences
    ]

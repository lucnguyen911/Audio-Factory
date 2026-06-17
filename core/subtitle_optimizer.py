import re
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple

class SubtitleOptimizerError(Exception):
    """Exception raised for errors during subtitle optimization."""
    pass


@dataclass
class OptimizerPreset:
    max_chars_per_line: int
    target_chars_per_line: int
    max_words_per_cue: int
    max_duration: float
    avoid_orphan_words: bool
    balance_lines: bool


PRESETS = {
    ("horizontal", 1): OptimizerPreset(42, 36, 8, 3.5, True, False),
    ("horizontal", 2): OptimizerPreset(38, 32, 14, 4.5, True, True),
    ("horizontal", 3): OptimizerPreset(34, 28, 18, 5.5, True, True),
    ("vertical", 1): OptimizerPreset(32, 28, 6, 2.6, True, False),
    ("vertical", 2): OptimizerPreset(28, 24, 10, 3.2, True, True),
    ("vertical", 3): OptimizerPreset(24, 20, 13, 4.0, True, True),
}

VI_CONJUNCTIONS = {"và", "nhưng", "rồi", "vì", "nên", "hoặc"}
EN_CONJUNCTIONS = {"and", "but", "so", "because", "while", "when", "that"}
CONJUNCTIONS = VI_CONJUNCTIONS.union(EN_CONJUNCTIONS)


def is_sentence_ending(word: str) -> bool:
    """Check if the word ends with a sentence-ending punctuation."""
    stripped = word.strip()
    if not stripped:
        return False
    return stripped[-1] in {".", "?", "!", "…"} or stripped.endswith("...")


def is_phrase_ending(word: str) -> bool:
    """Check if the word ends with a phrase punctuation or is a conjunction."""
    stripped = word.strip()
    if not stripped:
        return False
    if stripped[-1] in {",", ";", ":"}:
        return True
    return stripped.lower() in CONJUNCTIONS


def wrap_to_lines(
    words: List[str],
    max_chars: int,
    max_lines: int,
    balance_lines: bool,
    avoid_orphan: bool
) -> List[str]:
    """
    Wrap words into lines according to character length constraints and balancing rules.
    """
    if not words:
        return []
    n = len(words)
    if n == 1:
        return [words[0]]
        
    if max_lines == 1:
        return [" ".join(words)]
        
    best_split = None
    best_score = float("inf")
    
    if max_lines == 2:
        for i in range(1, n):
            line1 = " ".join(words[:i])
            line2 = " ".join(words[i:])
            
            len1, len2 = len(line1), len(line2)
            if len1 > max_chars or len2 > max_chars:
                continue
                
            orphan_penalty = 0
            if avoid_orphan:
                # Penalize splitting that leaves a single word on a line
                if i == 1 or i == n - 1:
                    orphan_penalty = 1000
                    
            diff = abs(len1 - len2) if balance_lines else 0
            score = diff + orphan_penalty
            
            if score < best_score:
                best_score = score
                best_split = [line1, line2]
                
    elif max_lines == 3:
        for i in range(1, n - 1):
            for j in range(i + 1, n):
                line1 = " ".join(words[:i])
                line2 = " ".join(words[i:j])
                line3 = " ".join(words[j:])
                
                len1, len2, len3 = len(line1), len(line2), len(line3)
                if len1 > max_chars or len2 > max_chars or len3 > max_chars:
                    continue
                    
                orphan_penalty = 0
                if avoid_orphan:
                    if i == 1 or (j - i) == 1 or (n - j) == 1:
                        orphan_penalty = 1000
                        
                if balance_lines:
                    diff = max(len1, len2, len3) - min(len1, len2, len3)
                else:
                    diff = 0
                    
                score = diff + orphan_penalty
                if score < best_score:
                    best_score = score
                    best_split = [line1, line2, line3]
                    
    if best_split is not None:
        return best_split
        
    # Greedy fallback wrap if no optimal split satisfies limits
    lines = []
    current_line = []
    current_len = 0
    for w in words:
        w_len = len(w)
        if current_line and (current_len + 1 + w_len > max_chars) and len(lines) < max_lines - 1:
            lines.append(" ".join(current_line))
            current_line = [w]
            current_len = w_len
        else:
            current_line.append(w)
            current_len += (1 + w_len) if current_len > 0 else w_len
    if current_line:
        lines.append(" ".join(current_line))
    return lines


def optimize_subtitles(
    segments: List[Dict[str, Any]],
    video_format: str = "horizontal",
    max_lines: int = 1
) -> List[Dict[str, Any]]:
    """
    Optimize raw segments into subtitle cues conforming to the selected layout and line counts.
    """
    preset_key = (video_format.lower().strip(), max_lines)
    if preset_key not in PRESETS:
        raise SubtitleOptimizerError(f"Unsupported layout/line count configuration: {preset_key}")
        
    preset = PRESETS[preset_key]
    
    # 1. Parse segments into word sequence with word timestamps if available, else proportional timestamps
    word_seq = []
    for seg in segments:
        if isinstance(seg, dict):
            text = str(seg.get("text", "")).strip()
            start_t = float(seg.get("start", 0.0))
            end_t = float(seg.get("end", 0.0))
            seg_words = seg.get("words")
        else:
            text = str(getattr(seg, "text", "")).strip()
            start_t = float(getattr(seg, "start", 0.0))
            end_t = float(getattr(seg, "end", 0.0))
            seg_words = getattr(seg, "words", None)
            
        if not text:
            continue
            
        if seg_words:
            for w_obj in seg_words:
                if isinstance(w_obj, dict):
                    w_text = w_obj.get("word") or w_obj.get("text", "")
                    w_start = float(w_obj.get("start", start_t))
                    w_end = float(w_obj.get("end", end_t))
                else:
                    w_text = getattr(w_obj, "word", "") or getattr(w_obj, "text", "")
                    w_start = float(getattr(w_obj, "start", start_t))
                    w_end = float(getattr(w_obj, "end", end_t))
                w_text = str(w_text).strip()
                if not w_text:
                    continue
                word_seq.append({
                    "text": w_text,
                    "start": w_start,
                    "end": w_end,
                    "has_sentence_end": is_sentence_ending(w_text),
                    "has_phrase_end": is_phrase_ending(w_text)
                })
        else:
            words = text.split()
            if not words:
                continue
                
            duration = max(0.0, end_t - start_t)
            
            word_lens = [len(w) + 1 for w in words]
            total_len = sum(word_lens)
            
            cum_len = 0
            for idx, w in enumerate(words):
                w_start = start_t + (cum_len / total_len) * duration
                cum_len += word_lens[idx]
                w_end = start_t + (cum_len / total_len) * duration
                
                word_seq.append({
                    "text": w,
                    "start": w_start,
                    "end": w_end,
                    "has_sentence_end": is_sentence_ending(w),
                    "has_phrase_end": is_phrase_ending(w)
                })
            
    if not word_seq:
        return []
        
    # 2. Group words into optimized cues
    cues = []
    current_cue = []
    
    for w in word_seq:
        if not current_cue:
            current_cue.append(w)
            continue
            
        test_words = [item["text"] for item in current_cue] + [w["text"]]
        wrapped_lines = wrap_to_lines(
            test_words,
            preset.max_chars_per_line,
            max_lines,
            preset.balance_lines,
            preset.avoid_orphan_words
        )
        
        # Check constraints violations
        exceeds_lines = len(wrapped_lines) > max_lines
        exceeds_line_chars = any(len(line) > preset.max_chars_per_line for line in wrapped_lines)
        exceeds_word_count = len(test_words) > preset.max_words_per_cue
        exceeds_duration = (w["end"] - current_cue[0]["start"]) > preset.max_duration
        
        # Decide whether to split before adding the current word
        should_split = exceeds_lines or exceeds_line_chars or exceeds_word_count or exceeds_duration
        
        if not should_split:
            prev_w = current_cue[-1]
            # Split on sentence ending
            if prev_w["has_sentence_end"]:
                should_split = True
            # Split on phrase boundary if current cue is sufficiently full
            elif prev_w["has_phrase_end"]:
                total_len_so_far = sum(len(x["text"]) + 1 for x in current_cue) - 1
                if total_len_so_far >= preset.target_chars_per_line or len(current_cue) >= preset.max_words_per_cue // 2:
                    should_split = True
            # Split on long silent pause
            elif w["start"] - prev_w["end"] > 0.8:
                should_split = True
                
        if should_split:
            cues.append(current_cue)
            current_cue = [w]
        else:
            current_cue.append(w)
            
    if current_cue:
        cues.append(current_cue)
        
    # 3. Apply anti-orphan cue re-merging
    if len(cues) > 1 and len(cues[-1]) == 1:
        last_word = cues[-1][0]
        prev_cue = cues[-2]
        test_words = [item["text"] for item in prev_cue] + [last_word["text"]]
        wrapped = wrap_to_lines(
            test_words,
            preset.max_chars_per_line,
            max_lines,
            preset.balance_lines,
            preset.avoid_orphan_words
        )
        # Verify it fits inside limits safely
        if len(wrapped) <= max_lines and len(test_words) <= preset.max_words_per_cue and (last_word["end"] - prev_cue[0]["start"]) <= preset.max_duration:
            cues[-2].append(last_word)
            cues.pop()
            
    # 4. Format cues into optimized segments list
    optimized_segments = []
    for idx, cue_words in enumerate(cues):
        words_list = [item["text"] for item in cue_words]
        wrapped_lines = wrap_to_lines(
            words_list,
            preset.max_chars_per_line,
            max_lines,
            preset.balance_lines,
            preset.avoid_orphan_words
        )
        
        optimized_segments.append({
            "index": idx + 1,
            "start": round(cue_words[0]["start"], 3),
            "end": round(cue_words[-1]["end"], 3),
            "text": "\n".join(wrapped_lines)
        })
        
    # 5. Prevent overlap, enforce positive duration, and handle safe clamping
    min_dur = 0.3
    # Step 5a: Enforce minimum duration and repair zero/negative duration cues
    for i in range(len(optimized_segments)):
        curr = optimized_segments[i]
        if curr["end"] <= curr["start"]:
            # Repair with safe minimum duration
            repaired_end = round(curr["start"] + min_dur, 3)
            if i + 1 < len(optimized_segments):
                nxt = optimized_segments[i+1]
                if repaired_end > nxt["start"]:
                    # Clamp safely to next cue's start to prevent overlap
                    if nxt["start"] > curr["start"]:
                        curr["end"] = nxt["start"]
                    else:
                        curr["end"] = round(curr["start"] + 0.05, 3)
                else:
                    curr["end"] = repaired_end
            else:
                curr["end"] = repaired_end
        elif curr["end"] - curr["start"] < min_dur:
            curr["end"] = round(curr["start"] + min_dur, 3)

    # Step 5b: Resolve overlaps
    for i in range(len(optimized_segments) - 1):
        curr = optimized_segments[i]
        nxt = optimized_segments[i+1]
        if curr["end"] > nxt["start"]:
            if nxt["end"] - curr["end"] >= min_dur:
                nxt["start"] = curr["end"]
            else:
                curr["end"] = nxt["start"]
                if curr["end"] - curr["start"] < min_dur:
                    curr["end"] = round(curr["start"] + min_dur, 3)
                    nxt["start"] = curr["end"]
                    if nxt["end"] - nxt["start"] < min_dur:
                        nxt["end"] = round(nxt["start"] + min_dur, 3)
                        
    return optimized_segments

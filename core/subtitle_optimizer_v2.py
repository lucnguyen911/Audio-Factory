"""Production subtitle segmentation for Audio Factory.

The optimizer in this module deliberately has a small contract:

* preserve every ASR token, in order;
* use global word identifiers at every boundary;
* treat punctuation and long pauses as hard block boundaries;
* treat commas, short pauses and grammar as scoring signals;
* run quality validation on the exact cues returned to the exporter.

It does not perform domain-specific spelling corrections.  Recognition fixes
belong in the ASR layer where confidence and audio evidence are available.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import logging

logger = logging.getLogger(__name__)


class SubtitleV2Error(Exception):
    """Raised when subtitle segmentation cannot preserve its hard invariants."""


@dataclass(frozen=True)
class LayoutProfile:
    format_id: str
    max_lines: int
    target_width: int
    max_width: int
    target_words: int
    max_words: int
    min_duration: float
    target_duration: float
    max_duration: float
    target_cps: float
    max_cps: float
    soft_pause: float
    preferred_pause: float
    hard_pause: float


PROFILES: Dict[Tuple[str, int], LayoutProfile] = {
    ("16:9", 1): LayoutProfile("16:9", 1, 36, 42, 7, 14, 5.0 / 6.0, 2.5, 7.0, 16.0, 20.0, 0.25, 0.45, 0.85),
    ("16:9", 2): LayoutProfile("16:9", 2, 32, 42, 10, 22, 5.0 / 6.0, 3.2, 7.0, 16.0, 20.0, 0.25, 0.45, 0.85),
    ("16:9", 3): LayoutProfile("16:9", 3, 28, 36, 13, 28, 5.0 / 6.0, 3.8, 7.0, 16.0, 20.0, 0.25, 0.45, 0.85),
    ("1:1", 1): LayoutProfile("1:1", 1, 28, 35, 6, 12, 0.9, 2.2, 7.0, 15.0, 19.0, 0.22, 0.40, 0.75),
    ("1:1", 2): LayoutProfile("1:1", 2, 28, 35, 9, 20, 0.9, 2.9, 7.0, 15.0, 19.0, 0.22, 0.40, 0.75),
    ("1:1", 3): LayoutProfile("1:1", 3, 24, 30, 12, 26, 0.9, 3.5, 7.0, 15.0, 19.0, 0.22, 0.40, 0.75),
    ("9:16", 1): LayoutProfile("9:16", 1, 26, 32, 5, 11, 0.8, 1.9, 7.0, 14.0, 18.0, 0.20, 0.35, 0.65),
    ("9:16", 2): LayoutProfile("9:16", 2, 24, 30, 7, 17, 0.8, 2.5, 7.0, 14.0, 18.0, 0.20, 0.35, 0.65),
    ("9:16", 3): LayoutProfile("9:16", 3, 21, 26, 10, 23, 0.8, 3.0, 7.0, 14.0, 18.0, 0.20, 0.35, 0.65),
}


TERMINAL_PUNCTUATION = (".", "?", "!", "…")
CLAUSE_PUNCTUATION = (",", ";", ":")

DETERMINERS = {
    "a", "an", "the", "this", "that", "these", "those", "each", "every",
    "some", "any", "no", "my", "your", "his", "her", "its", "our", "their",
}
PREPOSITIONS = {
    "of", "to", "for", "with", "from", "by", "at", "in", "on", "as", "into",
    "onto", "upon", "under", "over", "between", "among", "about", "through",
    "inside", "outside", "within", "without", "against", "during", "before", "after",
}
AUXILIARIES = {
    "am", "is", "are", "was", "were", "be", "been", "being", "has", "have", "had",
    "do", "does", "did", "will", "would", "can", "could", "may", "might", "must",
    "should", "shall",
}
CONJUNCTIONS = {
    "and", "but", "or", "so", "because", "although", "though", "while", "when",
    "if", "unless", "whether", "yet", "than",
}
RELATIVES = {"that", "which", "who", "whom", "whose", "where", "whether"}
FORBIDDEN_ENDINGS = DETERMINERS | PREPOSITIONS | AUXILIARIES | CONJUNCTIONS | RELATIVES

CLAUSE_STARTERS = {
    "and", "but", "or", "so", "because", "although", "though", "while", "when", "if",
    "unless", "however", "therefore", "meanwhile", "instead", "before", "after", "once",
    "now", "then", "yet",
}

COMPLEMENT_TAKING = {
    "including", "excluding", "containing", "involving", "requiring", "allowing",
    "making", "using", "takes", "took", "needs", "needed", "wants", "wanted",
    "expects", "expected", "means", "meant", "called", "calls", "call", "becomes",
    "unsettle", "unsettles", "unsettled", "prove", "proves", "proved",
}

PRENOMINAL_MODIFIERS = {
    "aging", "different", "separate", "original", "ordinary", "functional", "profitable", "legendary",
    "unprofitable", "real", "actual", "entire", "everyday", "heavy", "repeated", "strong",
    "quiet", "quietly", "genuine", "genuinely", "exact", "exactly", "likely", "unlikely",
    "major", "minor", "first", "last", "next", "previous", "new", "old", "human", "robotic",
    "elderly", "friendly", "early",
}

COMMON_VERBS = AUXILIARIES | {
    "accept", "accepted", "allow", "allows", "allowed", "appear", "appears", "arrive",
    "arrived", "ask", "asked", "become", "became", "believe", "believes", "build",
    "built", "call", "called", "calls", "change", "changed", "come", "comes", "cost",
    "create", "created", "cut", "cuts", "design", "designed", "drive", "drives", "erase",
    "erased", "exist", "exists", "finish", "finished", "get", "gets", "give", "gives",
    "go", "goes", "gone", "help", "helps", "hold", "holds", "keep", "keeps", "know",
    "knows", "leave", "leaves", "look", "looks", "make", "makes", "mean", "means",
    "move", "moves", "need", "needs", "process", "processed", "prove", "proves", "read",
    "replace", "replaced", "run", "runs", "say", "says", "see", "sees", "sit", "sits",
    "sound", "sounds", "start", "starts", "stay", "stays", "take", "takes", "talk",
    "talks", "think", "thinks", "turn", "turns", "use", "uses", "walk", "walked",
    "want", "wants", "watch", "watched", "work", "works",
}

NOUN_THAT_COMPLEMENTS = {
    "proof", "fact", "idea", "reason", "claim", "belief", "evidence", "argument",
    "possibility", "chance", "sign", "promise",
}

SHORT_STANDALONE = {
    "yes", "no", "why", "hello", "hi", "okay", "ok", "stop", "correct", "exactly",
    "absolutely", "thanks", "goodbye", "picture this", "next week",
}

KNOWN_PHRASES = {
    "elon musk", "model s", "model x", "model y", "model 3", "giga texas",
    "model x assembly lines", "assembly lines out of fremont",
    "new york", "san francisco", "general motors", "the boring company",
    "mass production", "production line", "self driving", "self-driving tesla", "talk about",
    "out of", "check in", "care of", "close to", "many of",
    "robot vacuum", "robot vacuums", "working hours", "force limiting", "hive mind",
    "product update", "know how", "dollars per month", "miles per hour", "kilowatt hour",
    "kilowatt hours", "real time", "real-time", "safety net", "strong enough",
    "fully functional", "very first time", "second quarter",
}

MAX_KNOWN_PHRASE_WORDS = 5
SEMANTIC_OVERFLOW_MAX_WIDTH = 50
CONTINUATION_OVERFLOW_MAX_WIDTH = 46
SEMANTIC_OVERFLOW_PENALTY = 12.0

UNIT_WORDS = {
    "percent", "dollar", "dollars", "mile", "miles", "hour", "hours", "day", "days",
    "week", "weeks", "month", "months", "year", "years", "volt", "volts", "watt",
    "watts", "kilowatt", "kilowatts", "pound", "pounds", "lb", "lbs", "kg", "mph",
    "million", "billion", "trillion", "units", "vehicles", "robots",
}

def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in {"W", "F", "A"} else 1 for ch in text)


def _clean_token(text: str) -> str:
    return text.lower().strip(".,;:!?…\"'()[]{} ")


def _visible_chars(text: str) -> int:
    return len(text.replace("\n", ""))


def _join_tokens(tokens: Sequence[str]) -> str:
    """Join ASR word tokens without introducing punctuation-spacing defects."""
    text = " ".join(token.strip() for token in tokens if token.strip())
    text = re.sub(r"\s+([,.;:!?…%])", r"\1", text)
    text = re.sub(r"([$€£])\s+(\d)", r"\1\2", text)
    text = re.sub(r"\s+-\s*", "-", text)
    text = re.sub(r"\s+(['’](?:s|t|re|ve|ll|d|m))\b", r"\1", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _display_token(word: Dict[str, Any]) -> str:
    """Return the editorially safe display form of an unchanged ASR token.

    ``text`` is deliberately kept lossless for grammar scoring, diagnostics and
    the content invariant.  ``display_text`` is used only for punctuation that
    Whisper itself placed in the middle of an uninterrupted lower-case phrase.
    This lets the exported SRT read naturally without pretending that the ASR
    transcript was rewritten.
    """
    return str(word.get("display_text", word["text"]))


def _replace_terminal_for_display(text: str, replacement: str) -> str:
    return re.sub(r"[.?!…]+(?=\s*$)", replacement, text).rstrip()


def _normalise_format(video_format: str) -> str:
    value = video_format.lower().strip()
    return {"horizontal": "16:9", "vertical": "9:16", "square": "1:1"}.get(value, value)


def get_profile(video_format: str, max_lines: int) -> LayoutProfile:
    key = (_normalise_format(video_format), int(max_lines))
    if key not in PROFILES:
        raise SubtitleV2Error(f"Unsupported subtitle layout: {video_format!r}, lines={max_lines}")
    return PROFILES[key]


def _word_text(word_obj: Any) -> str:
    if isinstance(word_obj, dict):
        value = word_obj.get("word") or word_obj.get("text") or ""
    else:
        value = getattr(word_obj, "word", "") or getattr(word_obj, "text", "")
    return re.sub(r"\s+", " ", str(value)).strip()


def _capitalize_subtitle_opening(text: str) -> str:
    """Capitalise only the first alphabetical character of the whole subtitle.

    ASR may return the beginning of a recording as a lower-case continuation.
    That first token is nevertheless the opening of the exported subtitle, so it
    must read as a sentence opening.  Do not infer or alter casing anywhere
    else: apparent mid-stream sentence boundaries can be Whisper punctuation
    errors.
    """
    for index, character in enumerate(text):
        if character.isalpha():
            return f"{text[:index]}{character.upper()}{text[index + 1:]}"
    return text


def _value(obj: Any, key: str, default: Any) -> Any:
    return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)


def build_word_sequence(segments: Sequence[Any]) -> List[Dict[str, Any]]:
    """Convert raw ASR segments into one lossless, globally indexed word stream."""
    result: List[Dict[str, Any]] = []
    for segment_index, segment in enumerate(segments):
        source_boundary_before = bool(_value(segment, "source_boundary_before", False))
        source_file_index = _value(segment, "source_file_index", None)
        first_result_index = len(result)
        text = re.sub(r"\s+", " ", str(_value(segment, "text", ""))).strip()
        start = max(0.0, float(_value(segment, "start", 0.0) or 0.0))
        end = max(start, float(_value(segment, "end", start) or start))
        raw_words = _value(segment, "words", None)

        if raw_words:
            for raw_word in raw_words:
                token = _word_text(raw_word)
                if not token:
                    continue
                if not result:
                    token = _capitalize_subtitle_opening(token)
                word_start = max(0.0, float(_value(raw_word, "start", start) or start))
                word_end = float(_value(raw_word, "end", word_start + 0.05) or (word_start + 0.05))
                if word_end <= word_start:
                    word_end = word_start + 0.05
                probability = _value(raw_word, "probability", None)
                result.append({
                    "id": len(result),
                    "text": token,
                    "start": word_start,
                    "end": word_end,
                    "probability": float(probability) if probability is not None else None,
                    "source_segment": segment_index,
                    "source_file_index": source_file_index,
                    "source_boundary_before": source_boundary_before and len(result) == first_result_index,
                })
            continue

        tokens = text.split()
        if not tokens:
            continue
        weights = [max(1, len(token)) for token in tokens]
        total = float(sum(weights))
        cursor = 0.0
        duration = max(0.05 * len(tokens), end - start)
        for token, weight in zip(tokens, weights):
            if not result:
                token = _capitalize_subtitle_opening(token)
            word_start = start + duration * (cursor / total)
            cursor += weight
            word_end = start + duration * (cursor / total)
            result.append({
                "id": len(result),
                "text": token,
                "start": word_start,
                "end": max(word_start + 0.05, word_end),
                "probability": None,
                "source_segment": segment_index,
                "source_file_index": source_file_index,
                "source_boundary_before": source_boundary_before and len(result) == first_result_index,
            })

    # ASR timestamps can overlap slightly.  IDs remain the authoritative order;
    # never rewrite or discard text to repair timing noise.
    for idx, word in enumerate(result):
        word["id"] = idx
        word["terminal"] = word["text"].rstrip().endswith(TERMINAL_PUNCTUATION)
        word["clause_end"] = word["text"].rstrip().endswith(CLAUSE_PUNCTUATION)
    return result


def _looks_like_verb(token: str) -> bool:
    clean = _clean_token(token)
    if clean in COMMON_VERBS:
        return True
    if len(clean) >= 5 and (clean.endswith("ed") or clean.endswith("ing")):
        return True
    return False


def _is_suspicious_terminal(words: Sequence[Dict[str, Any]], index: int) -> bool:
    if index >= len(words) - 1:
        return False
    current = words[index]
    if not current.get("terminal"):
        return False
    next_word = words[index + 1]
    gap = max(0.0, next_word["start"] - current["end"])
    current_clean = _clean_token(current["text"])
    next_raw = next_word["text"].strip()
    next_clean = _clean_token(next_raw)

    if _looks_like_standalone_title(words, index):
        return False
    if f"{current_clean} {next_clean}" in KNOWN_PHRASES:
        return True
    # "the moment a ..." is a noun phrase, not two sentences.  Whisper often
    # puts a period after "moment" when the following article is capitalised.
    # Require the determiner and a short acoustic gap so a real sentence such
    # as "It was a moment. A ..." remains untouched.
    if (
        current_clean == "moment"
        and next_clean in {"a", "an"}
        and index > 0
        and _clean_token(words[index - 1]["text"]) == "the"
        and gap < 0.45
    ):
        return True
    if next_raw and next_raw[0].islower() and gap < 0.45:
        return True
    if current_clean in NOISY_ABBREVIATIONS:
        return True

    # Whisper occasionally emits a two-word fragment such as "A self." in the
    # middle of an uninterrupted phrase.  Keep the punctuation text, but do not
    # force it to become a hard segment boundary.
    sentence_start = index
    while sentence_start > 0 and not words[sentence_start - 1].get("terminal"):
        sentence_start -= 1
    fragment_length = index - sentence_start + 1
    fragment_phrase = " ".join(_clean_token(word["text"]) for word in words[sentence_start:index + 1])
    if fragment_phrase in SHORT_STANDALONE and gap < 0.45:
        return True
    if fragment_length <= 2 and gap < 0.18 and current_clean not in SHORT_STANDALONE:
        if next_clean not in CLAUSE_STARTERS:
            return True
    if current_clean in UNIT_WORDS and next_clean in {"isn't", "isnt", "wasn't", "wasnt", "aren't", "arent"}:
        if fragment_length <= 2 and gap < 0.35:
            return True
    if re.fullmatch(r"\d+", current_clean) and next_clean in NUMBER_WORDS and gap < 0.35:
        return True
    return False


def _looks_like_standalone_title(words: Sequence[Dict[str, Any]], index: int) -> bool:
    """Recognise a modest title-shaped phrase after a real sentence.

    Whisper commonly lower-cases chapter titles.  They should be capitalised as
    a new cue, not glued to the preceding narration merely because their first
    word is lower-case.  The deliberately narrow pattern avoids treating every
    ``the ...`` continuation as a title.
    """
    following = [_clean_token(word["text"]) for word in words[index + 1:index + 7]]
    if len(following) < 4 or following[0] not in {"the", "a", "an"}:
        return False
    return "that" in following[:4] and any(_looks_like_verb(token) for token in following[2:])


def _false_terminal_display_replacement(words: Sequence[Dict[str, Any]], index: int) -> Optional[str]:
    """Choose a conservative display replacement for a false Whisper period.

    The ASR token itself remains untouched.  Most false terminals separate a
    continuing clause or a list, where silently deleting punctuation creates a
    new grammatical error (``home a hospital``).  Therefore the default is a
    comma.  We remove punctuation only for a verified uninterrupted compound
    such as ``second quarter`` or a verb followed by its preposition such as
    ``opened at``.  Numeric fragments are never guessed or reformatted here.
    """
    if not _is_suspicious_terminal(words, index) or index >= len(words) - 1:
        return None
    current_clean = _clean_token(words[index]["text"])
    next_raw = words[index + 1]["text"].strip()
    next_clean = _clean_token(next_raw)
    if not next_raw or not next_raw[0].islower() or re.fullmatch(r"\d+(?:[.,]\d+)?", current_clean):
        return None
    if _looks_like_standalone_title(words, index):
        return None
    if f"{current_clean} {next_clean}" in KNOWN_PHRASES:
        return ""
    if next_clean in {"at", "to", "of", "for", "in", "on", "into", "onto", "from"}:
        return ""
    return ","


NOISY_ABBREVIATIONS = {"mr", "mrs", "ms", "dr", "prof", "st", "vs", "etc", "e.g", "i.e"}
NUMBER_WORDS = {
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
    "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
    "nineteen", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety",
}


def mark_hard_boundaries(words: List[Dict[str, Any]], profile: LayoutProfile) -> List[int]:
    """Return exclusive global word indexes that partition independent DP blocks."""
    boundaries: List[int] = []
    for word in words:
        word["display_text"] = word["text"]
    for idx, word in enumerate(words):
        is_hard_sentence = bool(word.get("terminal")) and not _is_suspicious_terminal(words, idx)
        word["hard_sentence_end"] = is_hard_sentence
        replacement = _false_terminal_display_replacement(words, idx)
        if replacement is not None:
            word["display_text"] = _replace_terminal_for_display(word["text"], replacement)
        if is_hard_sentence and idx + 1 < len(words):
            # This is a confirmed sentence/block start, unlike a lower-case
            # Whisper continuation rejected above.  Capitalising it fixes both
            # normal sentence starts and standalone chapter titles.
            words[idx + 1]["display_text"] = _capitalize_subtitle_opening(words[idx + 1]["display_text"])
        if idx == len(words) - 1:
            boundaries.append(idx + 1)
            continue
        gap = max(0.0, words[idx + 1]["start"] - word["end"])
        source_boundary = bool(words[idx + 1].get("source_boundary_before"))
        if is_hard_sentence or gap >= profile.hard_pause or source_boundary:
            boundaries.append(idx + 1)
    if not boundaries or boundaries[-1] != len(words):
        boundaries.append(len(words))
    return boundaries


def build_protected_boundary_map(words: Sequence[Dict[str, Any]]) -> Dict[int, str]:
    """Build an O(1) map keyed by *global* exclusive word boundary IDs."""
    protected: Dict[int, str] = {}
    clean = [_clean_token(word["text"]) for word in words]

    for start in range(len(words)):
        for size in range(MAX_KNOWN_PHRASE_WORDS, 1, -1):
            end = start + size
            if end > len(words):
                continue
            if any(words[pos].get("source_boundary_before") for pos in range(start + 1, end)):
                continue
            phrase = " ".join(clean[start:end])
            if phrase in KNOWN_PHRASES:
                for boundary in range(start + 1, end):
                    protected[boundary] = f"protected phrase: {phrase}"
                break

    for idx in range(len(words) - 1):
        left = clean[idx]
        right = clean[idx + 1]
        left_raw = words[idx]["text"].strip()
        right_raw = words[idx + 1]["text"].strip()
        boundary = idx + 1
        if not left or not right:
            continue
        if words[idx + 1].get("source_boundary_before"):
            continue
        # A terminal that the shared classifier has rejected must not suppress
        # grammar protection here.  Otherwise a false Whisper period can make
        # us split a modifier or complement exactly where it should stay joined.
        left_is_terminal = bool(words[idx].get("terminal")) and not _is_suspicious_terminal(words, idx)
        split_token_boundary = right_raw.startswith(("-", ",")) or left_raw.endswith("-")
        compound_number_boundary = (
            left_is_terminal
            and bool(re.fullmatch(r"\d+", left))
            and right in NUMBER_WORDS
            and max(0.0, words[idx + 1]["start"] - words[idx]["end"]) < 0.35
        )
        left_number = bool(re.fullmatch(r"[$€£]?\d[\d,.:/-]*%?", left))
        if split_token_boundary:
            protected[boundary] = "split punctuation or hyphenated token"
        elif compound_number_boundary:
            protected[boundary] = "spoken compound number split by ASR punctuation"
        elif left_number and right in UNIT_WORDS:
            protected[boundary] = "number and unit"
        elif left in {"kilo", "mega", "giga", "tera"} and right in UNIT_WORDS:
            protected[boundary] = "multi-word unit"
        elif left in {"self", "real", "split"} and right in {"driving", "time", "second"}:
            protected[boundary] = "compound modifier"
        elif (
            words[idx]["text"].rstrip().endswith(",")
            and left in PRENOMINAL_MODIFIERS
            and right in PRENOMINAL_MODIFIERS
        ):
            protected[boundary] = "coordinate modifiers"
        elif not left_is_terminal and left in PRENOMINAL_MODIFIERS:
            protected[boundary] = f"modifier with following word: {left}"
        elif (
            not left_is_terminal
            and not words[idx]["text"].rstrip().endswith(CLAUSE_PUNCTUATION)
            and left.endswith("ly")
            and left not in {"elderly", "friendly", "family", "only", "likely", "unlikely", "early"}
            and right not in CLAUSE_STARTERS
        ):
            protected[boundary] = "adverb with following predicate or modifier"
        elif not left_is_terminal and left in COMPLEMENT_TAKING:
            protected[boundary] = f"complement after: {left}"
        elif not left_is_terminal and left in AUXILIARIES:
            protected[boundary] = f"auxiliary with following predicate: {left}"
        elif not left_is_terminal and left in NOUN_THAT_COMPLEMENTS and right in RELATIVES:
            protected[boundary] = f"noun complement with: {right}"
        elif (
            left == "moment"
            and right in {"a", "an"}
            and idx > 0
            and clean[idx - 1] == "the"
        ):
            protected[boundary] = "the moment with following article"
    return protected


def _boundary_features(
    words: Sequence[Dict[str, Any]],
    boundary: int,
    profile: LayoutProfile,
    protected: Dict[int, str],
    *,
    line_wrap: bool = False,
) -> Tuple[float, List[str]]:
    """Cost and reasons for a global boundary between boundary-1 and boundary."""
    if boundary <= 0 or boundary >= len(words):
        return 0.0, ["block edge"]
    if words[boundary].get("source_boundary_before"):
        return -10000.0, ["source file boundary"]
    left = words[boundary - 1]
    right = words[boundary]
    left_clean = _clean_token(left["text"])
    right_clean = _clean_token(right["text"])
    # ``hard_sentence_end`` is the single source of truth.  A raw period that
    # was classified as suspicious cannot receive a sentence-boundary bonus.
    left_is_terminal = bool(left.get("hard_sentence_end"))
    gap = max(0.0, right["start"] - left["end"])
    cost = 160.0
    reasons = ["mid-sentence boundary"]

    if boundary in protected:
        cost += 6000.0
        reasons.append(protected[boundary])

    if left.get("hard_sentence_end"):
        cost -= 1800.0
        reasons.append("sentence end")
    elif left.get("clause_end"):
        cost -= 500.0
        reasons.append("clause punctuation")

    if gap >= profile.preferred_pause:
        cost -= 900.0
        reasons.append("preferred pause")
    elif gap >= profile.soft_pause:
        cost -= 480.0
        reasons.append("soft pause")
    elif gap >= 0.12:
        cost -= 120.0
        reasons.append("micro pause")
    elif gap <= 0.04:
        cost += 120.0
        reasons.append("continuous speech")

    if right_clean in CLAUSE_STARTERS:
        cost -= 320.0
        reasons.append("clause starts at next cue")

    # These endings are almost always incomplete.  A one-line subtitle can be
    # forced to cut before a short subordinate clause because the full thought
    # will not fit in 42 characters.  With two or more lines, however, that
    # same thought normally fits in one readable cue, so keep the grammatical
    # connection intact and let the DP prefer the complete sentence.
    if not left_is_terminal and (left_clean in FORBIDDEN_ENDINGS or left_clean.endswith("'s") or left_clean.endswith("’s")):
        if right_clean in {"before", "after", "when", "while", "because", "if", "although"}:
            if profile.max_lines >= 2 and not line_wrap:
                cost += 5200.0
                reasons.append("function ending kept with subordinate clause")
            else:
                cost += 250.0
                reasons.append("function ending before subordinate clause")
        else:
            cost += 5200.0
            reasons.append(f"forbidden ending: {left_clean}")

    if not left_is_terminal and left_clean in COMPLEMENT_TAKING:
        cost += 1300.0
        reasons.append(f"complement expected after: {left_clean}")
    if not left_is_terminal and left_clean in PRENOMINAL_MODIFIERS:
        cost += 1700.0
        reasons.append(f"modifier should stay with following word: {left_clean}")
    if not left_is_terminal and left_clean.endswith("ly") and left_clean not in {"elderly", "friendly", "family", "only", "likely", "unlikely", "early"} and right_clean not in CLAUSE_STARTERS:
        cost += 1200.0
        reasons.append("adverb should stay with following predicate/modifier")
    if not left_is_terminal and left_clean in NOUN_THAT_COMPLEMENTS and right_clean in RELATIVES:
        cost += 2600.0
        reasons.append(f"noun complement kept with: {right_clean}")
    if not left_is_terminal and _looks_like_verb(right["text"]) and left_clean not in CLAUSE_STARTERS:
        if not left.get("clause_end") and gap < profile.soft_pause:
            cost += 700.0
            reasons.append("possible subject-predicate split")
    return cost, reasons


def _allows_semantic_one_line_overflow(
    cue_words: Sequence[Dict[str, Any]],
    profile: LayoutProfile,
    rendered_text: str,
) -> bool:
    """Allow a rare 16:9 one-line exception for an intact short clause.

    The normal 42-character maximum remains the default.  A few rapid TTS
    passages have no readable 42-character split without tearing a protected
    name or phrase apart.  This exception is deliberately narrow and still
    remains below the conventional 50-character upper limit.
    """
    if profile.format_id != "16:9" or profile.max_lines != 1:
        return False
    if not (profile.max_width < display_width(rendered_text) <= SEMANTIC_OVERFLOW_MAX_WIDTH):
        return False
    first_raw = cue_words[0]["text"].strip()
    first = _clean_token(first_raw)
    last_raw = cue_words[-1]["text"].rstrip()
    return (
        first in DETERMINERS
        and (first != "that" or first_raw[:1].isupper())
        and last_raw.endswith(TERMINAL_PUNCTUATION + CLAUSE_PUNCTUATION)
        and any(_looks_like_verb(word["text"]) for word in cue_words)
    )


def _wrap_words(
    cue_words: Sequence[Dict[str, Any]],
    profile: LayoutProfile,
    protected: Dict[int, str],
) -> Optional[List[str]]:
    texts = [_display_token(word) for word in cue_words]
    if not texts:
        return None
    one_line = _join_tokens(texts)
    if profile.max_lines == 1:
        if display_width(one_line) <= profile.max_width:
            return [one_line]
        if _allows_semantic_one_line_overflow(cue_words, profile, one_line):
            return [one_line]
        return None
    if display_width(one_line) <= profile.target_width or len(cue_words) <= 4:
        return [one_line]

    n = len(cue_words)
    best: Optional[Tuple[float, List[str]]] = None

    def visit(parts: Sequence[Tuple[int, int]]) -> None:
        nonlocal best
        lines = [_join_tokens(texts[a:b]) for a, b in parts]
        widths = [display_width(line) for line in lines]
        if any(width > profile.max_width for width in widths):
            return
        score = float(max(widths) - min(widths)) * 2.0
        for _, end in parts[:-1]:
            global_boundary = cue_words[end]["id"]
            boundary_cost, _ = _boundary_features(cue_words, end, profile, {})
            if global_boundary in protected:
                boundary_cost += 6000.0
            score += max(-300.0, boundary_cost)
        if best is None or score < best[0]:
            best = (score, lines)

    if profile.max_lines == 2:
        for first_end in range(1, n):
            visit(((0, first_end), (first_end, n)))
    else:
        for first_end in range(1, n - 1):
            for second_end in range(first_end + 1, n):
                visit(((0, first_end), (first_end, second_end), (second_end, n)))

    # A short cue does not need to occupy every permitted line.
    if display_width(one_line) <= profile.max_width:
        one_score = abs(display_width(one_line) - profile.target_width) * 0.5
        if best is None or one_score <= best[0]:
            return [one_line]

    if best is None and profile.max_lines > 1:
        # Fallback pass: split words across max_lines even if line width slightly exceeds profile.max_width
        def visit_relaxed(parts: Sequence[Tuple[int, int]]) -> None:
            nonlocal best
            lines = [_join_tokens(texts[a:b]) for a, b in parts]
            widths = [display_width(line) for line in lines]
            score = float(max(widths)) * 100.0 + float(max(widths) - min(widths)) * 2.0
            if best is None or score < best[0]:
                best = (score, lines)

        if profile.max_lines == 2:
            for first_end in range(1, n):
                visit_relaxed(((0, first_end), (first_end, n)))
        elif profile.max_lines >= 3:
            for first_end in range(1, n - 1):
                for second_end in range(first_end + 1, n):
                    visit_relaxed(((0, first_end), (first_end, second_end), (second_end, n)))

    return best[1] if best else [one_line]


def _has_predicate(cue_words: Sequence[Dict[str, Any]]) -> bool:
    return any(_looks_like_verb(word["text"]) for word in cue_words)


def _standalone_is_valid(cue_words: Sequence[Dict[str, Any]]) -> bool:
    phrase = " ".join(_clean_token(word["text"]) for word in cue_words).strip()
    if phrase in SHORT_STANDALONE:
        return True
    if phrase in KNOWN_PHRASES:
        return True
    # A terminal that survived _is_suspicious_terminal is a deliberate short
    # sentence, title, number or spoken emphasis rather than an orphan.
    if cue_words and cue_words[-1].get("hard_sentence_end"):
        return True
    if len(cue_words) == 1:
        token = cue_words[0]["text"].rstrip()
        clean = _clean_token(token)
        if token.endswith(CLAUSE_PUNCTUATION) and (
            clean.endswith("ly")
            or clean in {"however", "meanwhile", "instead", "therefore", "otherwise"}
        ):
            return True
    if len(cue_words) == 2:
        first_raw = cue_words[0]["text"].rstrip()
        first = _clean_token(first_raw)
        second = _clean_token(cue_words[1]["text"])
        coherent_short_phrase = (
            not first_raw.endswith(CLAUSE_PUNCTUATION)
            and first not in FORBIDDEN_ENDINGS
            and first not in CLAUSE_STARTERS
            and not first.endswith("ly")
            and second not in FORBIDDEN_ENDINGS
        )
        if coherent_short_phrase:
            return True
    if len(cue_words) == 2 and cue_words[-1]["text"].rstrip().endswith(TERMINAL_PUNCTUATION):
        subject_contractions = {
            "i'm", "i've", "i'll", "we're", "we've", "we'll", "you're", "you've", "you'll",
            "he's", "he'll", "she's", "she'll", "it's", "it'll", "they're", "they've", "they'll",
            "that's", "this's", "there's",
        }
        if _clean_token(cue_words[0]["text"]) in subject_contractions:
            return True
    return False


def _local_line_boundaries(cue_words: Sequence[Dict[str, Any]], lines: Sequence[str]) -> List[int]:
    """Map rendered lines back to local exclusive token indexes."""
    if len(lines) <= 1:
        return []
    boundaries: List[int] = []
    cursor = 0
    for line in lines[:-1]:
        for end in range(cursor + 1, len(cue_words) + 1):
            if _join_tokens([word["text"] for word in cue_words[cursor:end]]) == line:
                boundaries.append(end)
                cursor = end
                break
    return boundaries


def _line_break_boundaries(cue: Dict[str, Any]) -> List[int]:
    """Return global boundaries used by line wraps inside one cue."""
    lines = str(cue.get("text", "")).splitlines()
    words = cue.get("words", [])
    if len(lines) <= 1 or not words:
        return []
    return [words[boundary]["id"] for boundary in _local_line_boundaries(words, lines)]


def _cue_cost(
    words: Sequence[Dict[str, Any]],
    start: int,
    end: int,
    profile: LayoutProfile,
    protected: Dict[int, str],
    is_block_end: bool,
) -> Tuple[float, Optional[List[str]], Dict[str, Any]]:
    cue_words = words[start:end]
    if not cue_words:
        return math.inf, None, {}
    if len(cue_words) > profile.max_words:
        return math.inf, None, {}
    # Protected boundaries are global exclusive word IDs.  Rejecting them here
    # makes the invariant part of DP itself instead of hoping a late repair can
    # reconstruct the phrase.
    if start in protected or (not is_block_end and end in protected):
        return math.inf, None, {}

    lines = _wrap_words(cue_words, profile, protected)
    if lines is None:
        # A single overlong token must survive; validation reports it as
        # unavoidable instead of deleting or mutating transcript content.
        if len(cue_words) == 1:
            lines = [cue_words[0]["text"]]
        else:
            return math.inf, None, {}

    raw_duration = max(0.05, cue_words[-1]["end"] - cue_words[0]["start"])
    if raw_duration > profile.max_duration + 1e-6:
        return math.inf, None, {}
    text = "\n".join(lines)
    visible_chars = _visible_chars(text)
    widest_line = max(display_width(line) for line in lines)
    cps = visible_chars / raw_duration
    word_count = len(cue_words)

    cost = 0.0
    cost += abs(word_count - profile.target_words) * 7.0
    cost += abs(raw_duration - profile.target_duration) * 16.0
    cost += abs(widest_line - profile.target_width) * 1.5
    if widest_line > profile.max_width:
        # The exception above is reserved for a coherent, protected semantic
        # unit.  It is always more expensive than a normal cue, so it is used
        # only when a conventional split would be worse.
        cost += (widest_line - profile.max_width) ** 2 * SEMANTIC_OVERFLOW_PENALTY

    if cps > profile.target_cps:
        cost += (cps - profile.target_cps) ** 2 * 14.0
    if cps > profile.max_cps:
        cost += 700.0 + (cps - profile.max_cps) ** 2 * 55.0
    if raw_duration < profile.min_duration:
        cost += 700.0 + (profile.min_duration - raw_duration) * 1800.0

    if word_count == 1 and not _standalone_is_valid(cue_words):
        if not is_block_end:
            return math.inf, None, {}
        cost += 6500.0
    elif word_count == 2 and not _standalone_is_valid(cue_words):
        if not is_block_end:
            return math.inf, None, {}
        cost += 3200.0

    first_clean = _clean_token(cue_words[0]["text"])
    last_clean = _clean_token(cue_words[-1]["text"])
    if not is_block_end and not _has_predicate(cue_words):
        if first_clean not in PREPOSITIONS and first_clean not in CLAUSE_STARTERS:
            cost += 420.0
    if last_clean in COMPLEMENT_TAKING and not is_block_end:
        cost += 900.0

    # Feed line-wrap grammar back into the cue DP.  Without this, the cue can
    # satisfy width limits while still ending its first line on "a", "the" or
    # an adjective, and the final validator can only complain after the fact.
    for local_boundary in _local_line_boundaries(cue_words, lines):
        line_cost, _ = _boundary_features(
            cue_words,
            local_boundary,
            profile,
            {},
            line_wrap=True,
        )
        global_boundary = cue_words[local_boundary]["id"]
        if global_boundary in protected:
            line_cost += 6000.0
        cost += max(0.0, line_cost)

    boundary_cost = 0.0
    boundary_reasons: List[str] = []
    if not is_block_end:
        boundary_cost, boundary_reasons = _boundary_features(words, end, profile, protected)
        cost += boundary_cost
    return cost, lines, {
        "cps": cps,
        "duration": raw_duration,
        "boundary_cost": boundary_cost,
        "boundary_reasons": boundary_reasons,
    }


def _segment_block(
    words: Sequence[Dict[str, Any]],
    block_start: int,
    block_end: int,
    profile: LayoutProfile,
    protected: Dict[int, str],
    boundary_debug: Optional[List[Dict[str, Any]]],
) -> List[List[Dict[str, Any]]]:
    count = block_end - block_start
    dp = [math.inf] * (count + 1)
    parent = [-1] * (count + 1)
    chosen_lines: List[Optional[List[str]]] = [None] * (count + 1)
    dp[0] = 0.0

    for local_end in range(1, count + 1):
        global_end = block_start + local_end
        first_local = max(0, local_end - profile.max_words)
        for local_start in range(first_local, local_end):
            if not math.isfinite(dp[local_start]):
                continue
            global_start = block_start + local_start
            cue_cost, lines, details = _cue_cost(
                words,
                global_start,
                global_end,
                profile,
                protected,
                is_block_end=(global_end == block_end),
            )
            if not math.isfinite(cue_cost):
                continue
            total = dp[local_start] + cue_cost
            if total < dp[local_end]:
                dp[local_end] = total
                parent[local_end] = local_start
                chosen_lines[local_end] = lines

    if not math.isfinite(dp[count]):
        raise SubtitleV2Error(
            f"No valid subtitle layout for global words {block_start}:{block_end}; "
            "content was not modified."
        )

    ranges: List[Tuple[int, int]] = []
    cursor = count
    while cursor > 0:
        previous = parent[cursor]
        if previous < 0:
            raise SubtitleV2Error(f"Broken DP parent chain at global word {block_start + cursor}")
        ranges.append((block_start + previous, block_start + cursor))
        cursor = previous
    ranges.reverse()

    if boundary_debug is not None:
        selected = {end for _, end in ranges[:-1]}
        for boundary in range(block_start + 1, block_end):
            score, reasons = _boundary_features(words, boundary, profile, protected)
            boundary_debug.append({
                "word_index": boundary - 1,
                "global_boundary_id": boundary,
                "previous_text": words[boundary - 1]["text"],
                "next_text": words[boundary]["text"],
                "pause": round(max(0.0, words[boundary]["start"] - words[boundary - 1]["end"]), 3),
                "cost": round(score, 2),
                "reasons": reasons,
                "selected": boundary in selected,
            })

    return [list(words[start:end]) for start, end in ranges]


def _merge_safe_fragment_cues(
    cue_groups: Sequence[Sequence[Dict[str, Any]]],
    profile: LayoutProfile,
) -> List[List[Dict[str, Any]]]:
    """Rejoin a dangling continuation only when every display limit survives.

    The global DP deliberately balances many competing candidates.  Its target
    width can nevertheless leave a very short continuation such as ``for 10
    years`` in the next cue even though the joined text is plainly readable.
    This pass is intentionally conservative: it never crosses a real sentence
    or source-file boundary and never accepts a merge that exceeds the existing
    width, duration, word-count, or CPS constraints.
    """
    merged: List[List[Dict[str, Any]]] = []
    for incoming in cue_groups:
        current = list(incoming)
        if not merged:
            merged.append(current)
            continue

        previous = merged[-1]
        joined = previous + current
        previous_last = previous[-1]
        next_first = current[0]
        first_clean = _clean_token(next_first["text"])
        last_clean = _clean_token(previous_last["text"])
        duration = max(0.05, joined[-1]["end"] - joined[0]["start"])
        text = _join_tokens([_display_token(word) for word in joined])
        cps = _visible_chars(text) / duration
        previous_duration = max(0.05, previous[-1]["end"] - previous[0]["start"])
        current_duration = max(0.05, current[-1]["end"] - current[0]["start"])
        dangling_start = first_clean in PREPOSITIONS | RELATIVES | {"and", "or", "but"}
        dangling_end = last_clean in FORBIDDEN_ENDINGS or last_clean in COMPLEMENT_TAKING
        short_fragment = (
            previous_duration < profile.min_duration and not _standalone_is_valid(previous)
        ) or (
            current_duration < profile.min_duration and not _standalone_is_valid(current)
        )
        standard_layout = display_width(text) <= profile.max_width
        continuation_overflow = (
            profile.format_id == "16:9"
            and profile.max_lines == 1
            and display_width(text) <= CONTINUATION_OVERFLOW_MAX_WIDTH
            and cps <= profile.max_cps
            and first_clean in PREPOSITIONS | RELATIVES
            and _has_predicate(previous)
            and (
                _clean_token(previous[0]["text"]) not in PREPOSITIONS | RELATIVES
                or _clean_token(previous[0]["text"]) in {"and", "or", "but"}
            )
        )
        can_merge = (
            not next_first.get("source_boundary_before")
            and not previous_last.get("hard_sentence_end")
            and len(joined) <= profile.max_words
            and (standard_layout or continuation_overflow)
            and duration <= profile.max_duration
            and cps <= profile.max_cps
        )
        if can_merge and (dangling_start or dangling_end or short_fragment):
            if continuation_overflow and not standard_layout:
                # Preserve the narrow authorization for final layout
                # validation; no transcript text or ordering is changed.
                joined[0]["semantic_continuation_overflow"] = True
            merged[-1] = joined
        else:
            merged.append(current)
    return merged


def _audio_duration_from_wav(wav_path: Optional[Path]) -> float:
    if wav_path is None:
        return 0.0
    try:
        import wave

        with wave.open(str(wav_path), "rb") as wav_file:
            return wav_file.getnframes() / float(wav_file.getframerate())
    except Exception:
        # Python's wave module rejects valid IEEE-float PCM WAV files.  Those
        # are used by the DSP pipeline, so fall back to the project's ffprobe
        # path instead of silently disabling the audio-end validation.
        try:
            from core.importer import get_duration_seconds

            return float(get_duration_seconds(wav_path))
        except Exception:
            return 0.0


def _assign_display_times(
    cue_words: Sequence[Sequence[Dict[str, Any]]],
    profile: LayoutProfile,
    audio_duration: float,
    offset_seconds: float,
) -> List[Tuple[float, float]]:
    if not cue_words:
        return []
    starts = []
    for idx, cue in enumerate(cue_words):
        spoken_duration = max(0.0, cue[-1]["end"] - cue[0]["start"])
        available_lead = max(0.0, profile.max_duration - spoken_duration)
        start = max(0.0, cue[0]["start"] - min(0.04, available_lead))
        if idx > 0:
            # In continuous speech there is no room for pre-roll on the next
            # cue.  Keep the previous cue visible through its final word.
            start = max(start, cue_words[idx - 1][-1]["end"])
        starts.append(start)
    ends: List[float] = []

    for idx, cue in enumerate(cue_words):
        voice_end = cue[-1]["end"]
        visible_chars = len(_join_tokens([word["text"] for word in cue]))
        desired_duration = min(
            profile.max_duration,
            max(profile.min_duration, visible_chars / profile.max_cps),
        )
        desired_end = min(
            starts[idx] + profile.max_duration,
            max(voice_end + 0.08, starts[idx] + desired_duration),
        )
        if idx < len(cue_words) - 1:
            next_voice_start = cue_words[idx + 1][0]["start"]
            # Never borrow time from the next spoken word.  A five-millisecond
            # display gap is used only when the ASR words are effectively
            # continuous; otherwise retain a compact 40 ms visual gap.
            voice_gap = next_voice_start - voice_end
            display_gap = 0.04 if voice_gap >= 0.08 else 0.005
            latest_end = next_voice_start - display_gap
            end = max(voice_end, min(desired_end, latest_end))
        else:
            end = desired_end
            if audio_duration > 0.0:
                end = min(audio_duration, end)
        ends.append(end)

    times: List[Tuple[float, float]] = []
    previous_end = 0.0
    for idx, (start, end) in enumerate(zip(starts, ends)):
        start = max(previous_end, start)
        end = max(end, cue_words[idx][-1]["end"], start + 0.05)
        if idx < len(starts) - 1:
            end = min(end, starts[idx + 1])
            end = max(end, start + 0.05)
        unshifted_end = end
        start = max(0.0, start + offset_seconds)
        end = max(start + 0.05, end + offset_seconds)
        if audio_duration > 0.0:
            start = min(start, audio_duration)
            end = min(max(start, end), audio_duration)
        start = round(start, 3)
        end = round(max(start + 0.001, end), 3)
        times.append((start, end))
        # Keep this cursor in the unshifted timeline.  Otherwise a positive
        # sync offset is added again at every following cue.
        previous_end = unshifted_end
    return times


def _canonical_tokens(words: Iterable[Dict[str, Any]]) -> List[str]:
    return [re.sub(r"\s+", " ", str(word["text"])).strip() for word in words]


def validate_final_cues(
    cues: Sequence[Dict[str, Any]],
    source_words: Sequence[Dict[str, Any]],
    profile: LayoutProfile,
    protected: Dict[int, str],
    audio_duration: float,
) -> Dict[str, Any]:
    fatal: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    checks: Dict[str, Any] = {}

    flattened_words = [word for cue in cues for word in cue.get("words", [])]
    source_ids = [word["id"] for word in source_words]
    output_ids = [word["id"] for word in flattened_words]
    content_ok = source_ids == output_ids and _canonical_tokens(flattened_words) == _canonical_tokens(source_words)
    if not content_ok:
        fatal.append({"code": "CONTENT_INVARIANT", "reason": "Word content/order changed during subtitle optimization"})
    checks["content_invariant"] = {"pass": content_ok, "source_words": len(source_words), "output_words": len(flattened_words)}

    rendered_source = _join_tokens([_display_token(word) for word in source_words])
    rendered_output = _join_tokens(
        [part for cue in cues for part in str(cue.get("text", "")).replace("\n", " ").split()]
    )
    rendered_ok = rendered_output == rendered_source
    if not rendered_ok:
        fatal.append({"code": "RENDERED_TEXT_INVARIANT", "reason": "Rendered cue text differs from the source token stream"})
    checks["rendered_text_invariant"] = {"pass": rendered_ok}

    overlap_violations = []
    layout_violations = []
    protected_violations = []
    semantic_violations = []
    line_break_violations = []
    internal_sentence_violations = []
    forbidden_violations = []
    orphan_violations = []
    short_violations = []
    long_violations = []
    cps_violations = []
    low_confidence = []
    source_boundary_violations = []

    cue_boundaries = set()
    for idx, cue in enumerate(cues):
        text = str(cue.get("text", ""))
        lines = text.splitlines() or [text]
        duration = max(0.001, float(cue["end"]) - float(cue["start"]))
        cps = _visible_chars(text) / duration
        words = cue.get("words", [])
        word_count = len(words)
        cue_number = idx + 1
        boundary = words[-1]["id"] + 1 if words else -1
        ends_at_source_boundary = (
            0 < boundary < len(source_words)
            and bool(source_words[boundary].get("source_boundary_before"))
        )

        semantic_overflow = (
            len(lines) == 1
            and _allows_semantic_one_line_overflow(words, profile, text)
        )
        continuation_overflow = (
            len(lines) == 1
            and bool(words and words[0].get("semantic_continuation_overflow"))
            and profile.format_id == "16:9"
            and profile.max_lines == 1
            and display_width(text) <= CONTINUATION_OVERFLOW_MAX_WIDTH
            and cps <= profile.max_cps
        )
        if (
            len(lines) > profile.max_lines
            or any(display_width(line) > profile.max_width for line in lines)
        ) and not (semantic_overflow or continuation_overflow):
            item = {"cue_index": cue_number, "code": "LAYOUT", "text": text}
            layout_violations.append(item)
            warnings.append(item)
        if duration + 0.001 < profile.min_duration and not _standalone_is_valid(words) and not ends_at_source_boundary:
            item = {"cue_index": cue_number, "duration": round(duration, 3), "code": "SHORT_DURATION", "text": text}
            short_violations.append(item)
            warnings.append(item)
        if duration > profile.max_duration + 0.001:
            item = {"cue_index": cue_number, "duration": round(duration, 3), "code": "LONG_DURATION", "text": text}
            long_violations.append(item)
            warnings.append(item)
        # SRT timestamps are rounded to milliseconds.  Ignore only the tiny
        # CPS drift caused by that quantisation (for example 20.00 -> 20.01),
        # while retaining the real 20+ CPS review/fail gate.
        if cps > profile.max_cps + 0.05:
            item = {"cue_index": cue_number, "cps": round(cps, 2), "code": "HIGH_CPS", "text": text}
            cps_violations.append(item)
            warnings.append(item)
        if word_count <= 2 and not _standalone_is_valid(words) and not ends_at_source_boundary:
            item = {"cue_index": cue_number, "word_count": word_count, "code": "ORPHAN", "text": text}
            orphan_violations.append(item)
            warnings.append(item)
        if words:
            cue_boundaries.add(boundary)
            last_clean = _clean_token(words[-1]["text"])
            has_clause_punctuation = words[-1]["text"].rstrip().endswith(TERMINAL_PUNCTUATION + CLAUSE_PUNCTUATION)
            if (
                idx < len(cues) - 1
                and not ends_at_source_boundary
                and last_clean in FORBIDDEN_ENDINGS
                and not has_clause_punctuation
            ):
                next_clean = _clean_token(cues[idx + 1]["words"][0]["text"])
                subordinate_exception = next_clean in {"before", "after", "when", "while", "because", "if", "although"}
                if not subordinate_exception:
                    item = {"cue_index": cue_number, "code": "FORBIDDEN_ENDING", "word": last_clean, "text": text}
                    forbidden_violations.append(item)
                    warnings.append(item)
            if idx < len(cues) - 1:
                semantic_cost, semantic_reasons = _boundary_features(source_words, boundary, profile, protected)
                severe_reasons = [
                    reason for reason in semantic_reasons
                    if reason.startswith("forbidden ending")
                    or reason.startswith("protected phrase")
                    or reason.startswith("complement expected")
                    or reason.startswith("modifier should")
                    or reason.startswith("noun complement")
                    or reason.startswith("adverb should")
                ]
                if semantic_cost >= 1400.0 and severe_reasons:
                    item = {
                        "cue_index": cue_number,
                        "code": "SEMANTIC_BREAK",
                        "boundary": f"{words[-1]['text']} | {cues[idx + 1]['words'][0]['text']}",
                        "reasons": severe_reasons,
                        "text": text,
                    }
                    semantic_violations.append(item)
                    warnings.append(item)
            for line_boundary in _line_break_boundaries(cue):
                line_cost, line_reasons = _boundary_features(source_words, line_boundary, profile, protected)
                severe_line_reasons = [
                    reason for reason in line_reasons
                    if reason.startswith("forbidden ending")
                    or reason.startswith("protected phrase")
                    or reason.startswith("complement expected")
                    or reason.startswith("modifier should")
                    or reason.startswith("noun complement")
                    or reason.startswith("adverb should")
                ]
                if line_cost >= 1400.0 and severe_line_reasons:
                    item = {
                        "cue_index": cue_number,
                        "code": "BAD_LINE_BREAK",
                        "global_boundary_id": line_boundary,
                        "reasons": severe_line_reasons,
                        "text": text,
                    }
                    line_break_violations.append(item)
                    warnings.append(item)
            for word in words:
                probability = word.get("probability")
                if probability is not None and probability < 0.35:
                    low_confidence.append({
                        "cue_index": cue_number,
                        "word_id": word["id"],
                        "word": word["text"],
                        "probability": round(float(probability), 3),
                    })
            internal_hard_ends = [word for word in words[:-1] if word.get("hard_sentence_end")]
            if internal_hard_ends:
                item = {
                    "cue_index": cue_number,
                    "code": "INTERNAL_SENTENCE_END",
                    "words": [word["text"] for word in internal_hard_ends],
                    "text": text,
                }
                internal_sentence_violations.append(item)
                fatal.append(item)

        if idx > 0 and float(cue["start"]) < float(cues[idx - 1]["end"]) - 1e-6:
            item = {"cue_index": cue_number, "code": "OVERLAP"}
            overlap_violations.append(item)
            fatal.append(item)
        if float(cue["end"]) <= float(cue["start"]):
            item = {"cue_index": cue_number, "code": "NON_POSITIVE_DURATION"}
            overlap_violations.append(item)
            fatal.append(item)
        if audio_duration > 0.0 and float(cue["end"]) > audio_duration + 0.001:
            item = {"cue_index": cue_number, "code": "PAST_AUDIO_END"}
            overlap_violations.append(item)
            fatal.append(item)

    for boundary, reason in protected.items():
        if boundary in cue_boundaries:
            item = {"global_boundary_id": boundary, "code": "PROTECTED_SPLIT", "reason": reason}
            protected_violations.append(item)
            fatal.append(item)

    required_source_boundaries = {
        word["id"] for word in source_words
        if word.get("source_boundary_before") and int(word["id"]) > 0
    }
    for boundary in sorted(required_source_boundaries - cue_boundaries):
        item = {
            "global_boundary_id": boundary,
            "code": "SOURCE_BOUNDARY_MISSING",
            "reason": "Subtitle cue crosses an input-file boundary",
        }
        source_boundary_violations.append(item)
        fatal.append(item)

    checks["layout"] = {"pass": not layout_violations, "violations": layout_violations}
    checks["timing"] = {"pass": not overlap_violations, "violations": overlap_violations}
    checks["protected_boundaries"] = {"pass": not protected_violations, "violations": protected_violations}
    checks["semantic_boundaries"] = {"pass": not semantic_violations, "violations": semantic_violations}
    checks["semantic_line_breaks"] = {"pass": not line_break_violations, "violations": line_break_violations}
    checks["internal_sentence_endings"] = {"pass": not internal_sentence_violations, "violations": internal_sentence_violations}
    checks["forbidden_endings"] = {"pass": not forbidden_violations, "violations": forbidden_violations}
    checks["orphan_cues"] = {"pass": not orphan_violations, "violations": orphan_violations}
    checks["minimum_duration"] = {"pass": not short_violations, "violations": short_violations}
    checks["maximum_duration"] = {"pass": not long_violations, "violations": long_violations}
    checks["max_cps"] = {"pass": not cps_violations, "violations": cps_violations}
    checks["low_confidence_words"] = {"pass": not low_confidence, "violations": low_confidence}
    checks["source_file_boundaries"] = {
        "pass": not source_boundary_violations,
        "required": sorted(required_source_boundaries),
        "violations": source_boundary_violations,
    }

    non_cps_warnings = [item for item in warnings if item.get("code") != "HIGH_CPS"]
    high_cps_ratio = len(cps_violations) / max(1, len(cues))
    max_observed_cps = max((float(item["cps"]) for item in cps_violations), default=0.0)
    if fatal or non_cps_warnings:
        release_status = "fail"
    elif cps_violations and (high_cps_ratio > 0.005 or max_observed_cps > 22.0):
        release_status = "fail"
    elif cps_violations:
        release_status = "review"
    else:
        release_status = "pass"

    return {
        "engine": "global_dp_v2",
        "total_cues": len(cues),
        "profile": {
            "format_id": profile.format_id,
            "max_lines": profile.max_lines,
            "max_width": profile.max_width,
            "max_cps": profile.max_cps,
        },
        "checks": checks,
        "fatal_errors": fatal,
        "quality_warnings": warnings,
        "release_gate": {
            "status": release_status,
            "high_cps_ratio": round(high_cps_ratio, 6),
            "max_observed_cps": round(max_observed_cps, 2),
            "allowed_review_ratio": 0.005,
            "allowed_review_max_cps": 22.0,
        },
        "export_allowed": release_status != "fail",
    }


def align_cues_to_audio_onset(
    cues: List[Dict[str, Any]],
    wav_path: Optional[Path],
    min_db_threshold: float = -30.0,
) -> None:
    """
    Ensure subtitle cue start times align with actual spoken voice > min_db_threshold (-30 dBFS).
    Prevents subtitle from appearing early during inhalation/breath intake (< -30 dBFS).
    """
    if not wav_path:
        return
    path_obj = Path(wav_path)
    if not path_obj.is_file():
        return

    try:
        import soundfile as sf
        import numpy as np

        data, sr = sf.read(str(path_obj))
        if data.size == 0 or sr <= 0:
            return

        if data.ndim > 1:
            amplitude = np.max(np.abs(data), axis=1)
        else:
            amplitude = np.abs(data)

        # -30 dBFS corresponds to linear amplitude 10^(-30/20) ≈ 0.0316227766
        linear_threshold = 10.0 ** (min_db_threshold / 20.0)
        total_samples = len(amplitude)

        # Window size of 20ms to measure speech energy
        win_size = max(1, int(sr * 0.02))
        step_size = max(1, int(sr * 0.01))  # 10ms step

        for cue in cues:
            start_sec = cue["start"]
            end_sec = cue["end"]
            start_sample = int(start_sec * sr)

            if start_sample >= total_samples or start_sample < 0:
                continue

            # Check energy around initial start time (20ms window)
            current_energy = float(np.max(amplitude[start_sample : min(total_samples, start_sample + win_size)]))

            # If start time is currently in silence / breath (< -30 dBFS)
            if current_energy < linear_threshold:
                # Search forward for first frame exceeding -30 dBFS (up to end_sec - 0.2s or max +0.8s)
                max_search_sec = min(end_sec - 0.2, start_sec + 0.8)
                max_search_sample = int(max_search_sec * sr)

                curr = start_sample
                found_onset_sample = None
                while curr < max_search_sample and curr < total_samples:
                    win_max = float(np.max(amplitude[curr : min(total_samples, curr + win_size)]))
                    if win_max >= linear_threshold:
                        found_onset_sample = curr
                        break
                    curr += step_size

                if found_onset_sample is not None:
                    refined_start = round(found_onset_sample / float(sr), 3)
                    # Keep a tiny 50ms pre-roll before speech onset for clean visual transition
                    refined_start = max(start_sec, refined_start - 0.05)
                    if refined_start < cue["end"] - 0.2:
                        cue["start"] = refined_start
    except Exception as e:
        logger.warning(f"Failed to align cues to audio onset: {e}")


def optimize_subtitles_v2(
    segments: Sequence[Any],
    video_format: str = "horizontal",
    max_lines: int = 1,
    wav_path: Optional[Path] = None,
    subtitle_sync_offset_ms: float = 0.0,
    debug_boundary_candidates: Optional[List[Dict[str, Any]]] = None,
    debug_dp_report: Optional[Dict[str, Any]] = None,
    debug_validation_report: Optional[Dict[str, Any]] = None,
    strict_subtitle_validation: bool = False,
) -> List[Dict[str, Any]]:
    profile = get_profile(video_format, max_lines)
    words = build_word_sequence(segments)
    if not words:
        if debug_validation_report is not None:
            debug_validation_report.clear()
            debug_validation_report.update({
                "engine": "global_dp_v2",
                "total_cues": 0,
                "checks": {},
                "fatal_errors": [],
                "quality_warnings": [],
                "release_gate": {
                    "status": "pass",
                    "high_cps_ratio": 0.0,
                    "max_observed_cps": 0.0,
                    "allowed_review_ratio": 0.005,
                    "allowed_review_max_cps": 22.0,
                },
                "export_allowed": True,
            })
        return []

    protected = build_protected_boundary_map(words)
    hard_boundaries = mark_hard_boundaries(words, profile)
    all_cue_words: List[List[Dict[str, Any]]] = []
    block_start = 0
    block_report = []
    for block_end in hard_boundaries:
        block_cues = _segment_block(
            words,
            block_start,
            block_end,
            profile,
            protected,
            debug_boundary_candidates,
        )
        all_cue_words.extend(block_cues)
        block_report.append({
            "start_word_id": block_start,
            "end_word_id": block_end,
            "word_count": block_end - block_start,
            "cue_count": len(block_cues),
        })
        block_start = block_end

    all_cue_words = _merge_safe_fragment_cues(all_cue_words, profile)

    audio_duration = _audio_duration_from_wav(Path(wav_path) if wav_path is not None else None)
    display_times = _assign_display_times(
        all_cue_words,
        profile,
        audio_duration,
        float(subtitle_sync_offset_ms) / 1000.0,
    )

    cues: List[Dict[str, Any]] = []
    for index, (cue_words, (start, end)) in enumerate(zip(all_cue_words, display_times), start=1):
        lines = _wrap_words(cue_words, profile, protected)
        if lines is None:
            lines = [_join_tokens([_display_token(word) for word in cue_words])]
        cues.append({
            "index": index,
            "start": start,
            "end": end,
            "text": "\n".join(lines),
            "words": [dict(word) for word in cue_words],
        })

    align_cues_to_audio_onset(cues, wav_path, min_db_threshold=-30.0)

    report = validate_final_cues(cues, words, profile, protected, audio_duration)
    if debug_validation_report is not None:
        debug_validation_report.clear()
        debug_validation_report.update(report)
    if debug_dp_report is not None:
        debug_dp_report.clear()
        debug_dp_report.update({
            "engine": "global_dp_v2",
            "profile": report["profile"],
            "global_word_count": len(words),
            "hard_boundaries": hard_boundaries,
            "protected_boundaries": [
                {"global_boundary_id": boundary, "reason": reason}
                for boundary, reason in sorted(protected.items())
            ],
            "blocks": block_report,
        })

    if report["fatal_errors"]:
        raise SubtitleV2Error(
            f"Final subtitle validation failed with {len(report['fatal_errors'])} hard invariant error(s): "
            f"{report['fatal_errors'][:3]}"
        )
    if strict_subtitle_validation:
        if report["release_gate"]["status"] == "fail":
            raise SubtitleV2Error(
                f"Subtitle release gate failed with {len(report['quality_warnings'])} unresolved quality issue(s)."
            )
        if report["release_gate"]["status"] != "pass":
            raise SubtitleV2Error(
                f"Strict subtitle validation found {len(report['quality_warnings'])} quality warning(s)."
            )
    return cues


__all__ = [
    "LayoutProfile",
    "SubtitleV2Error",
    "build_word_sequence",
    "display_width",
    "get_profile",
    "optimize_subtitles_v2",
    "validate_final_cues",
]

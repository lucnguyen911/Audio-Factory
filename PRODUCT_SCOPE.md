# Product Scope: Audio Cleaner & Auto Subtitle Tool

This document outlines the scope of the Audio Cleaner + Auto Subtitle MVP.

## MVP Focus
This tool acts as an **Audio Cleaner** and **Auto Subtitle Generator** for creators and MMO workflows.
- It cleans raw voice audio by applying noise reduction, gate filters, volume leveling, natural silence shortening, and social media loudness optimization.
- It generates highly readable, layout-optimized local subtitles (SRT, VTT, TXT, JSON) matching the final processed audio.

### Out of Scope (For Future Phases)
- **Audio Sentence Slicing**: Generating separate sentence chunks (like `001.wav`, `002.wav`) is deprecated and removed from this version's normal pipeline.
- **Video Scene Cutting**: Video scene cutting based on subtitle timestamps is out of scope and will be built in a future dedicated video editor tool.

## Key Features

### 1. Audio Processing Pipeline
- **Merge Audio**:
  - **ON**: Multiple files are merged first and processed as a single output (`final/final_audio.wav`).
  - **OFF**: Each file is processed independently, yielding its own final audio (`final/{input_stem}_final.wav`).
- **Voice Cleanup / Noise & Breath Reduction**: FFmpeg-based safe frequency cuts (highpass/lowpass), noise gate (agate), and light noise reduction (afftdn).
- **Volume Leveling**: EBU R128 standard loudness leveling using `dynaudnorm` + `loudnorm`.
- **Natural Silence Shortening**: Safe silence removal to shorten pauses while preserving natural phrasing breaks (default pause retention: ~0.3s).
- **Social Media Audio Optimization**: Dynamic compression and target limiting (-14 LUFS, -1.0 True Peak) to optimize loudness for YouTube, Shorts, TikTok, and Reels.

### 2. Auto Subtitle Engine
- Default local engine: **faster-whisper**.
- Recommended model: **large-v3-turbo**.
- **ASR Audio Speed**: Slows audio (e.g. 0.8x) temporarily for transcription to improve recognition accuracy on fast speech, automatically remapping timestamps back to the final audio timeline.
- **Batch Size**: Speeds up inference by chunking audio segments together during model execution.

### 3. Subtitle Layout & Formatting
- **Video Formats**:
  - **Horizontal**: Formatted for standard wide-screen landscape video (YouTube long-form).
  - **Vertical**: Formatted for short-form portrait video (Shorts, TikTok, Reels).
- **Max Lines**: Restricts subtitles to 1, 2, or 3 lines. If 1 line is selected, no newline characters are present.
- **Optimizer Rules**:
  - Prefers splitting at sentence punctuation (`.`, `?`, `!`, `…`).
  - Splits long sentences at phrase boundaries and common conjunctions.
  - **Anti-Orphan Lines**: Avoids single-word lines.
  - **Anti-Orphan Cues**: Avoids single-word leftover cues.
- **Output Encodings**:
  - SRT / TXT: `utf-8-sig` (with BOM for Windows/Excel compatibility).
  - VTT / JSON: standard `utf-8` (preserving Unicode).

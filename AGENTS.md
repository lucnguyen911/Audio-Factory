# Project Rules: Audio Factory

## Goal

Build a local Windows desktop audio processing tool.

The app must support:
- Import one or multiple audio files.
- Merge files into one long audio.
- Smart volume leveling.
- Shorten silence.
- Generate subtitles locally for free.
- Split audio by spoken sentence.
- Export numbered audio chunks.
- Export metadata JSON and SRT/VTT/TXT.

## Tech Stack

Use:
- Python
- PySide6 for GUI
- FFmpeg for audio processing
- faster-whisper for transcription
- Silero VAD for voice activity detection
- PyInstaller for Windows EXE packaging

Do not use paid APIs unless explicitly requested.

## Architecture

Keep UI and core logic separated.

Recommended structure:
- core/ffmpeg_runner.py
- core/importer.py
- core/merger.py
- core/volume_leveler.py
- core/silence_shortener.py
- core/transcriber.py
- core/sentence_splitter.py
- core/subtitle_exporter.py
- core/metadata_exporter.py
- ui/main_window.py
- scripts/build_exe.ps1
- tests/

## Safety Rules

Never modify files outside the project folder.

Never delete folders recursively without explicit approval.

Never run dangerous commands such as:
- rm -rf
- del /s /q
- rmdir /s /q
- Remove-Item -Recurse -Force
- git clean -fdx

Before major changes:
1. Explain the plan.
2. List files to be modified.
3. Wait for approval.

After changes:
1. Show changed files.
2. Explain how to test.
3. Do not claim success unless tests or commands actually ran.

## Coding Style

Use small modules.
Use type hints.
Use clear error messages.
Prefer subprocess wrappers for FFmpeg.
Do not hardcode absolute paths.
Use pathlib.
Keep functions testable without GUI.
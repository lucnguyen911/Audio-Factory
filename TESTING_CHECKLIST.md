# Testing Checklist

Here are the manual commands for real audio testing of the Audio Factory backend pipeline:

## Manual Verification Commands

### 1. Single File Processing (Volume + Silence)
```powershell
.venv\Scripts\python.exe scripts/run_pipeline.py --input samples/a.wav --output output/ --project-name test_run --volume --silence
```

### 2. Merge Processing
```powershell
.venv\Scripts\python.exe scripts/run_pipeline.py --input samples/a.wav samples/b.wav --output output/ --project-name merge_test --merge-first --volume --silence
```

### 3. Batch Processing
```powershell
.venv\Scripts\python.exe scripts/run_pipeline.py --input samples/a.wav samples/b.wav --output output/ --project-name batch_test --batch --volume --silence
```

### 4. Subtitle Generation
```powershell
.venv\Scripts\python.exe scripts/run_pipeline.py --input samples/a.wav --output output/ --project-name sub_test --volume --transcribe --subtitles --language vi --transcription-preset balanced
```

### 5. Full Pipeline Execution (Volume + Silence + Subtitles + Chunks)
```powershell
.venv\Scripts\python.exe scripts/run_pipeline.py --input samples/a.wav --output output/ --project-name full_test --volume --transcribe --subtitles --split-sentences --cut-audio --language vi --transcription-preset balanced --silence
```

### 6. Overwrite Safety Suffix Check
Run command #1 twice without deleting the folder:
```powershell
.venv\Scripts\python.exe scripts/run_pipeline.py --input samples/a.wav --output output/ --project-name test_run --volume --silence --no-overwrite
```
Verify that `output/test_run_01` (or `test_run_02`) is created.

## Output Inspection Commands

Run these to verify that outputs are correctly structured:

```powershell
Get-ChildItem output/test_run -Recurse
Get-ChildItem output/test_run_01 -Recurse
Get-ChildItem output/merge_test -Recurse
Get-ChildItem output/batch_test -Recurse
Get-ChildItem output/sub_test -Recurse
Get-ChildItem output/full_test -Recurse
```


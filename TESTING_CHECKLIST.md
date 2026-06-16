# Testing Checklist

Here are the manual commands for real audio testing of the Audio Factory backend pipeline:

## Manual Verification Commands

### 1. Single File Processing
```powershell
.venv\Scripts\python.exe scripts/run_pipeline.py --input samples/a.wav --output output/test_run --project-name test_run --volume --silence
```

### 2. Merge Processing
```powershell
.venv\Scripts\python.exe scripts/run_pipeline.py --input samples/a.wav samples/b.wav --output output/merge_test --project-name merge_test --merge-first --volume --silence
```

### 3. Batch Processing
```powershell
.venv\Scripts\python.exe scripts/run_pipeline.py --input samples/a.wav samples/b.wav --output output/batch_test --project-name batch_test --batch --volume --silence
```

### 4. Subtitle Generation
```powershell
.venv\Scripts\python.exe scripts/run_pipeline.py --input samples/a.wav --output output/sub_test --project-name sub_test --volume --transcribe --subtitles --language vi --transcription-preset balanced
```

### 5. Full Pipeline Execution
```powershell
.venv\Scripts\python.exe scripts/run_pipeline.py --input samples/a.wav --output output/full_test --project-name full_test --volume --transcribe --subtitles --split-sentences --cut-audio --language vi --transcription-preset balanced
```

## Output Inspection Commands

Run these to verify that outputs are correctly structured:

```powershell
Get-ChildItem output/test_run -Recurse
Get-ChildItem output/merge_test -Recurse
Get-ChildItem output/batch_test -Recurse
Get-ChildItem output/sub_test -Recurse
Get-ChildItem output/full_test -Recurse
```

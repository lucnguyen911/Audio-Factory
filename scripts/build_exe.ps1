$PSScriptRoot = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "=============================================" -ForegroundColor Green
Write-Host "    Audio Factory Premium Suite Builder      " -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green

$PyinstallerPath = Join-Path $ProjectRoot ".venv\Scripts\pyinstaller.exe"
if (Test-Path $PyinstallerPath) {
    Write-Host "Using virtual environment PyInstaller: $PyinstallerPath" -ForegroundColor Cyan
    & $PyinstallerPath --noconfirm "Audio Factory.spec"
} else {
    Write-Host "Warning: Virtual environment PyInstaller not found at $PyinstallerPath. Trying global path..." -ForegroundColor Yellow
    pyinstaller --noconfirm "Audio Factory.spec"
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "PyInstaller packaging succeeded!" -ForegroundColor Green
    
    # Verify DLL copy
    $InternalDir = Join-Path $ProjectRoot "dist\Audio Factory\_internal"
    if (Test-Path $InternalDir) {
        $Dlls = Get-ChildItem -Path $InternalDir -Filter "*.dll" | Where-Object { $_.Name -like "cublas*" -or $_.Name -like "nv*" -or $_.Name -like "cudart*" -or $_.Name -like "cudnn*" }
        Write-Host "Verification: Found $($Dlls.Count) NVIDIA CUDA DLLs in _internal." -ForegroundColor Green
        if ($Dlls.Count -ge 17) {
            Write-Host "Successfully packaged Audio Factory with GPU acceleration support (17 DLLs verified)!" -ForegroundColor Green
        } else {
            Write-Host "Warning: Found only $($Dlls.Count) CUDA DLLs. 17 required DLLs were expected!" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Error: dist\Audio_Factory\_internal not found!" -ForegroundColor Red
    }
} else {
    Write-Host "PyInstaller packaging failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

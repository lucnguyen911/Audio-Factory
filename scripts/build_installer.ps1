$PSScriptRoot = Split-Path -Parent -Path $MyInvocation.MyCommand.Definition
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Write-Host "=============================================" -ForegroundColor Green
Write-Host "    Audio Factory Commercial Setup Builder    " -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green

# 1. Search for ISCC.exe
$IsccPath = ""
$StandardPaths = @(
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe",
    "$env:USERPROFILE\AppData\Local\Programs\Inno Setup 6\ISCC.exe"
)

foreach ($Path in $StandardPaths) {
    if (Test-Path $Path) {
        $IsccPath = $Path
        break
    }
}

if (-not $IsccPath) {
    # Check if iscc is in PATH
    $IsccCmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($IsccCmd) {
        $IsccPath = $IsccCmd.Source
    }
}

# 2. If not found, attempt to install via winget
if (-not $IsccPath) {
    Write-Host "Inno Setup compiler (ISCC.exe) not found. Attempting install via winget..." -ForegroundColor Yellow
    
    # Run winget installation
    & winget install JRSoftware.InnoSetup --silent --accept-source-agreements --accept-package-agreements
    
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Winget installer completed successfully. Re-checking paths..." -ForegroundColor Green
        # Wait a moment for registration
        Start-Sleep -Seconds 5
        
        foreach ($Path in $StandardPaths) {
            if (Test-Path $Path) {
                $IsccPath = $Path
                break
            }
        }
        
        if (-not $IsccPath) {
            $IsccCmd = Get-Command iscc -ErrorAction SilentlyContinue
            if ($IsccCmd) {
                $IsccPath = $IsccCmd.Source
            }
        }
    } else {
        Write-Host "Winget installation failed with exit code $LASTEXITCODE." -ForegroundColor Red
    }
}

# 3. If still not found, alert
if (-not $IsccPath) {
    Write-Host "Error: Inno Setup compiler (ISCC.exe) could not be found or installed." -ForegroundColor Red
    Write-Host "Please install Inno Setup manually from https://jrsoftware.org/isdl.php" -ForegroundColor Yellow
    exit 1
}

Write-Host "Found Inno Setup compiler at: $IsccPath" -ForegroundColor Cyan
Write-Host "Compiling installer_config.iss..." -ForegroundColor Cyan

# Ensure we are in ProjectRoot to compile
Push-Location $ProjectRoot
try {
    $VersionSource = Get-Content -LiteralPath (Join-Path $ProjectRoot "version.py") -Raw
    if ($VersionSource -notmatch 'APP_VERSION\s*=\s*"([^"]+)"') {
        throw "Cannot read APP_VERSION from version.py"
    }
    $AppVersion = $Matches[1]
    & "$IsccPath" "/DMyAppVersion=$AppVersion" "installer_config.iss"
} finally {
    Pop-Location
}

if ($LASTEXITCODE -eq 0) {
    Write-Host "Setup installer compiled successfully!" -ForegroundColor Green
    $SetupPath = Join-Path $ProjectRoot "dist\Audio_Factory_Premium_Setup_v$AppVersion.exe"
    if (Test-Path $SetupPath) {
        Write-Host "Commercial Installer is ready at: $SetupPath" -ForegroundColor Green
    } else {
        Write-Host "Warning: Compiling succeeded, but installer was not found at: $SetupPath" -ForegroundColor Yellow
    }
} else {
    Write-Host "Inno Setup compiler failed with exit code $LASTEXITCODE" -ForegroundColor Red
    exit $LASTEXITCODE
}

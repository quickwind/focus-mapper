$ErrorActionPreference = "Stop"

# Get script directory and project root
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir/../.."

Write-Host "Building from project root: $ProjectRoot"

if (-not (Test-Path "$ProjectRoot/pyproject.toml")) {
    Write-Host "Could not verify project root."
    exit 1
}

# Change to project root
Push-Location $ProjectRoot

# Check/Install PyInstaller
try {
    python -m PyInstaller --version | Out-Null
} catch {
    Write-Host "PyInstaller not found. Installing..."
    pip install -e ".[build]"
    if ($LASTEXITCODE -ne 0) {
        Write-Host 'Failed to install dependencies. Please install it via command: pip install -e ".[build]"'
        exit 1
    }
}

# Run Build
Write-Host "Running PyInstaller..."
python -m PyInstaller `
    --clean `
    --noconfirm `
    --distpath "$ProjectRoot/dist-win" `
    --workpath "$ProjectRoot/build-win" `
    "$ScriptDir/focus_mapper.spec"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed."
    exit 1
}

Write-Host "`nBuild complete. Executables are in dist-win/"
Pop-Location

@echo off
setlocal

:: Get script directory
set "SCRIPT_DIR=%~dp0"
:: Get project root (2 levels up from tools/windows)
cd /d "%SCRIPT_DIR%..\.."
set "PROJECT_ROOT=%cd%"

echo Building from project root: %PROJECT_ROOT%

if not exist "%PROJECT_ROOT%\pyproject.toml" (
    echo Error: Could not verify project root.
    exit /b 1
)

:: Check for PyInstaller
python -m PyInstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo PyInstaller not found. Installing...
    pip install ".[build]"
    if %errorlevel% neq 0 (
        echo Error: Failed to install dependencies.
        exit /b 1
    )
)

:: Run Build
echo Running PyInstaller...
python -m PyInstaller ^
    --clean ^
    --noconfirm ^
    --distpath "%PROJECT_ROOT%\dist-win" ^
    --workpath "%PROJECT_ROOT%\build-win" ^
    "%SCRIPT_DIR%focus_mapper.spec"

if %errorlevel% neq 0 (
    echo Build failed.
    exit /b 1
)

echo.
echo Build complete. Executables are in dist-win/
endlocal

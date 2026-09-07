@echo off
setlocal

set "SOURCE=%~dp0"
set "SOURCE=%SOURCE:~0,-1%"
set "BACKUP_ROOT=D:\Projects\polygroups\_generator"
set "PAUSE_AT_END=1"
if /I "%~1"=="--no-pause" set "PAUSE_AT_END=0"

for /f %%I in ('powershell.exe -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HH-mm-ss"') do set "STAMP=%%I"

if not defined STAMP (
    echo ERROR: Could not generate a timestamp.
    if "%PAUSE_AT_END%"=="1" pause
    exit /b 1
)

set "TARGET=%BACKUP_ROOT%\%STAMP%"

echo.
echo Backing up:
echo   From: %SOURCE%
echo   To:   %TARGET%
echo.

if not exist "%TARGET%" mkdir "%TARGET%"
if errorlevel 1 (
    echo ERROR: Could not create the backup directory.
    if "%PAUSE_AT_END%"=="1" pause
    exit /b 1
)

robocopy "%SOURCE%" "%TARGET%" /E /COPY:DAT /DCOPY:DAT /R:2 /W:2 /XJ /FFT /NP /TEE /LOG:"%TARGET%\backup.log" /XD "__pycache__" ".pytest_cache" ".mypy_cache" /XF "*.pyc" "*.pyo"
set "ROBOCOPY_EXIT=%ERRORLEVEL%"

echo.
if %ROBOCOPY_EXIT% LSS 8 (
    echo Backup completed successfully.
    echo Snapshot: %TARGET%
    echo Robocopy status: %ROBOCOPY_EXIT%
    if "%PAUSE_AT_END%"=="1" pause
    exit /b 0
)

echo ERROR: Backup failed. Robocopy status: %ROBOCOPY_EXIT%
echo See log: %TARGET%\backup.log
if "%PAUSE_AT_END%"=="1" pause
exit /b %ROBOCOPY_EXIT%

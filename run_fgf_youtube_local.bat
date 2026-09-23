@echo off
setlocal EnableExtensions EnableDelayedExpansion
title FGF YouTube Intelligence - Local Ingestion

echo.
echo ================================================
echo   FGF YouTube Intelligence - Local Ingestion
echo ================================================
echo.
echo This runs on your local machine so YouTube transcript
echo requests use your normal internet connection instead
echo of a GitHub Actions cloud IP.
echo.

where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python launcher ^(py^) was not found.
  echo Install Python 3.12+ and run this file again.
  pause
  exit /b 1
)

if not exist requirements-youtube.txt (
  echo ERROR: Run this file from the FGF-Intelligence repository folder.
  pause
  exit /b 1
)

echo Installing/updating YouTube dependencies...
py -m pip install -r requirements-youtube.txt
if errorlevel 1 (
  echo ERROR: Dependency installation failed.
  pause
  exit /b 1
)

echo.
echo Enter your OpenAI API key when prompted.
echo The key is kept only in this command-session environment.
set /p FGF_LLM_API_KEY=OpenAI API key:
if "%FGF_LLM_API_KEY%"=="" (
  echo ERROR: OpenAI API key is required.
  pause
  exit /b 1
)

echo.
echo Choose execution mode:
echo   1 = Dry run (recommended first)
echo   2 = Apply to Supabase
set /p MODE=Enter 1 or 2:
if "%MODE%"=="1" goto DRYRUN
if "%MODE%"=="2" goto APPLY

echo ERROR: Invalid choice.
pause
exit /b 1

:DRYRUN
echo.
echo Starting first 10 videos as a local dry run...
py scripts/process_video_playlist.py --playlist-id PL2VyftArNQtQ2EbXMAmgwrPH0P4EvBVAR --start 1 --count 10 --batch-size 10 --delay-seconds 3 --dry-run
goto END

:APPLY
echo.
echo Enter the Supabase secret key for FGF-V4-Intelligence.
echo The key is kept only in this command-session environment.
set /p FGF_SUPABASE_SERVICE_ROLE_KEY=Supabase secret key:
if "%FGF_SUPABASE_SERVICE_ROLE_KEY%"=="" (
  echo ERROR: Supabase secret key is required for Apply mode.
  pause
  exit /b 1
)

echo.
echo Starting first 10 videos and persisting candidates to Supabase...
py scripts/process_video_playlist.py --playlist-id PL2VyftArNQtQ2EbXMAmgwrPH0P4EvBVAR --start 1 --count 10 --batch-size 10 --delay-seconds 3 --apply
goto END

:END
echo.
echo ================================================
echo Finished. Review the output above before running
echo the next batch.
echo ================================================
pause
endlocal

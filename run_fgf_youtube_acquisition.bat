@echo off
setlocal EnableExtensions
title FGF YouTube Transcript Acquisition

echo ================================================
echo FGF YouTube Transcript Acquisition
echo ================================================
echo.
echo This PC is used only for YouTube acquisition.
echo GitHub handles AI processing and Supabase claims.
echo.

where py >nul 2>&1
if errorlevel 1 (
  echo ERROR: Python launcher not found.
  pause
  exit /b 1
)

py -m pip install -r requirements-acquisition.txt
if errorlevel 1 (
  echo ERROR: Dependency installation failed.
  pause
  exit /b 1
)

set /p FGF_SUPABASE_SERVICE_ROLE_KEY=Supabase secret key:
if "%FGF_SUPABASE_SERVICE_ROLE_KEY%"=="" (
  echo ERROR: Supabase secret key is required.
  pause
  exit /b 1
)

echo.
set /p FGF_PLAYLIST_INPUT=YouTube playlist URL (or playlist ID):
if "%FGF_PLAYLIST_INPUT%"=="" (
  echo ERROR: Playlist URL/ID is required.
  pause
  exit /b 1
)

echo.
echo Acquiring the selected playlist and uploading transcripts...
echo Local faster-whisper STT is enabled for videos without usable subtitles.
echo Default model: small / CPU / int8.
echo Optional: set FGF_YTDLP_PROXY before starting if a proxy is required.
echo.

py scripts/acquire_and_upload_transcripts.py --playlist-url "%FGF_PLAYLIST_INPUT%" --start 0 --delay-seconds 12 --max-retries 2 --rate-limit-base 45
if errorlevel 1 (
  echo.
  echo Acquisition ended with errors. Review the manifest.
  pause
  exit /b 1
)

echo.
echo Acquisition complete. Transcripts are in Supabase Storage.
echo Next: GitHub Actions -> FGF Transcript Processing.
pause
endlocal

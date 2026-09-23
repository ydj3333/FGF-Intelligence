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

py -m pip install -r requirements-youtube.txt
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
echo Acquiring all 174 playlist videos and uploading transcripts...
echo Optional: set FGF_YTDLP_PROXY before starting if a proxy is required.
echo.

py scripts/acquire_and_upload_transcripts.py --playlist-id PL2VyftArNQtQ2EbXMAmgwrPH0P4EvBVAR --start 0 --count 174
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

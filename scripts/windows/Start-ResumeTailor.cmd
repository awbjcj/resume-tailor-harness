@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-ResumeTailor.ps1" %*
exit /b %ERRORLEVEL%

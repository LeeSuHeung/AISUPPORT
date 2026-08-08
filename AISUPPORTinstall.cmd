@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0AISUPPORTinstall.ps1" %*
set "aisupport_exit=%errorlevel%"

echo.
if "%aisupport_exit%"=="0" (
  echo AISUPPORT installation complete. Restart Codex.
) else (
  echo AISUPPORT installation failed with exit code %aisupport_exit%.
)

if "%~1"=="" pause
exit /b %aisupport_exit%

@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-gemini-mcp.ps1"
set EXITCODE=%ERRORLEVEL%
echo.
if not "%EXITCODE%"=="0" (
  echo Falha na instalacao. Codigo: %EXITCODE%
) else (
  echo Instalacao concluida.
)
echo.
pause
exit /b %EXITCODE%

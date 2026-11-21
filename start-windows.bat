@echo off
setlocal
cd /d "%~dp0"
if not exist "main.py" (echo Fehler: main.py fehlt.& pause & exit /b 1)
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
  if errorlevel 1 (echo Python 3 fehlt oder venv konnte nicht erstellt werden.& pause & exit /b 1)
)
if not exist ".venv\.requirements-installed" goto install
for %%I in ("requirements.txt") do set "REQDATE=%%~tI"
for %%I in (".venv\.requirements-installed") do set "INSTDATE=%%~tI"
if not "%REQDATE%"=="%INSTDATE%" goto install
:run
".venv\Scripts\python.exe" main.py %*
if errorlevel 1 pause
exit /b %errorlevel%
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (echo Installation fehlgeschlagen.& pause & exit /b 1)
copy /b requirements.txt ".venv\.requirements-installed" >nul
goto run
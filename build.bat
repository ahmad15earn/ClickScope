@echo off
REM Builds dist\ClickScope.exe (single file, no console window, with icon).
REM Needs Python 3.10+ installed once (python.org, tick "Add Python to PATH").
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from https://www.python.org/downloads/ and tick "Add Python to PATH".
  pause & exit /b 1
)
python -m pip install --upgrade pyinstaller
if errorlevel 1 ( echo Could not install PyInstaller. & pause & exit /b 1 )
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ClickScope ^
  --icon assets\app.ico --add-data "assets;assets" --paths src src\main.py
if errorlevel 1 ( echo Build failed. & pause & exit /b 1 )
echo.
echo Done! Your app is here: %~dp0dist\ClickScope.exe
pause

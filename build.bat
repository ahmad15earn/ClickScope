@echo off
REM Builds dist\ClickScope.exe (single file, no console window, with icon).
REM Needs Python 3.10+ installed once (python.org, tick "Add Python to PATH").
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from https://www.python.org/downloads/ and tick "Add Python to PATH".
  pause & exit /b 1
)
python -m pip install --upgrade pyinstaller pillow
if errorlevel 1 ( echo Could not install PyInstaller. & pause & exit /b 1 )
python -m PyInstaller --noconfirm --clean --onefile --windowed --name ClickScope ^
  --icon assets\app.ico --add-data "assets;assets" --paths src src\main.py
if errorlevel 1 ( echo Build failed. & pause & exit /b 1 )
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
  set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
) else if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
  set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
) else if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
  set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
)
if defined ISCC (
  "%ISCC%" installer\ClickScope.iss
  echo Installer: %~dp0installer_output\ClickScope-Setup.exe
) else (
  echo [Optional] Install Inno Setup 6 from jrsoftware.org to also build the folder-choosing installer.
)
echo.
echo Done! Your app is here: %~dp0dist\ClickScope.exe
pause

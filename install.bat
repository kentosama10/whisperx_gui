@echo off
echo WhisperX Installation Script
echo ===========================
echo.

:: Check if Python is already installed
python --version > nul 2>&1
if %errorlevel% equ 0 (
    echo Python is already installed
    goto :INSTALL_DEPS
)

:: Download Python 3.10.11
echo Downloading Python 3.10.11...
curl -o python_installer.exe https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe

:: Install Python silently
echo Installing Python...
start /wait python_installer.exe /quiet InstallAllUsers=1 PrependPath=1 Include_test=0 Include_pip=1

:: Clean up installer
del python_installer.exe

:INSTALL_DEPS
:: Install required packages globally
echo Installing WhisperX and dependencies...
python -m pip install --upgrade pip
pip install PyQt5
pip install pyinstaller
pip install pip install whisperx

:: Create executable using PyInstaller
echo Creating executable...
pyinstaller --onefile --noconsole --name whisperx_gui --icon=whisperx.ico whisperx_gui.py

:: Create dist directory if it doesn't exist
if not exist "dist" mkdir dist

:: Copy the executable to dist folder
echo Copying executable to dist folder...
copy whisperx_gui.exe dist\

:: Create shortcut on desktop
echo Creating desktop shortcut...
set SCRIPT="%TEMP%\create_shortcut.vbs"
(
    echo Set oWS = WScript.CreateObject^("WScript.Shell"^)
    echo sLinkFile = oWS.ExpandEnvironmentStrings^("%%USERPROFILE%%\Desktop\WhisperX.lnk"^)
    echo Set oLink = oWS.CreateShortcut^(sLinkFile^)
    echo oLink.TargetPath = "%~dp0dist\whisperx_gui.exe"
    echo oLink.WorkingDirectory = "%~dp0dist"
    echo oLink.Save
) > %SCRIPT%
cscript /nologo %SCRIPT%
del %SCRIPT%

echo.
echo Installation complete! You can now run WhisperX GUI by:
echo 1. Running dist\whisperx_gui.exe
echo 2. Using the desktop shortcut
echo.
pause
@echo off
rem Builds dist\ComputingLock.exe (no camera) and dist\ComputingLock-Camera.exe (with camera).
rem Requires: pip install pyinstaller "opencv-python-headless>=4.8,<5"
cd /d "%~dp0"
set PY=python
if exist "%USERPROFILE%\Python312\python.exe" set PY="%USERPROFILE%\Python312\python.exe"
set COMMON=--noconfirm --onefile --windowed --icon "%CD%\icon.ico" --add-data "%CD%\icon.ico;." --workpath "%TEMP%\lsbuild\work" --specpath "%TEMP%\lsbuild\spec" --distpath dist
%PY% -m PyInstaller %COMMON% --name ComputingLock --exclude-module cv2 --exclude-module numpy lockscreen.py || goto :err
%PY% -m PyInstaller %COMMON% --name ComputingLock-Camera --collect-data cv2 lockscreen.py || goto :err
echo.
echo Done: dist\ComputingLock.exe and dist\ComputingLock-Camera.exe
pause
exit /b 0
:err
echo Build failed.
pause
exit /b 1

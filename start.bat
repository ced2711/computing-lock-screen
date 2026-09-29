@echo off
cd /d "%~dp0"
if exist "%USERPROFILE%\Python312\pythonw.exe" (
    start "" "%USERPROFILE%\Python312\pythonw.exe" lockscreen.py
) else (
    start "" pythonw lockscreen.py
)

#!/usr/bin/env sh
# Builds dist/ComputingLock (no camera) and dist/ComputingLock-Camera (with camera) for Linux.
# Requires: python3 with tkinter, pip install pyinstaller "opencv-python-headless>=4.8,<5"
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
TMP="${TMPDIR:-/tmp}/lsbuild"
COMMON="--noconfirm --onefile --add-data $PWD/icon.png:. --workpath $TMP/work --specpath $TMP/spec --distpath dist"
$PY -m PyInstaller $COMMON --name ComputingLock --exclude-module cv2 --exclude-module numpy lockscreen.py
$PY -m PyInstaller $COMMON --name ComputingLock-Camera --collect-data cv2 lockscreen.py
echo
echo "Done: dist/ComputingLock and dist/ComputingLock-Camera"

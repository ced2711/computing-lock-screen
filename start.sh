#!/usr/bin/env sh
cd "$(dirname "$0")"
nohup "${PYTHON:-python3}" lockscreen.py >/dev/null 2>&1 &

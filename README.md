# Computing Lock Screen

A Windows lock screen for when you step away while long jobs run (vibe coding, training, builds):
a full-screen **"COMPUTING · DO NOT TOUCH"** display, background programs keep running, and a
password unlocks it. Optional camera, keyboard and mouse activity detection. English / 中文.

![Lock screen](docs/screenshot.png)

## Download

Grab an exe from [Releases](../../releases) — no Python needed:

| File | Size | Camera detection |
|---|---|---|
| `ComputingLock.exe` | ~10 MB | no |
| `ComputingLock-Camera.exe` | ~61 MB | yes |

Put the exe in its own folder (for example `%LOCALAPPDATA%\Programs\ComputingLock`) and double-click it;
`config.json`, `captures/` and `logs/` are created next to it. The exe is unsigned, so Windows SmartScreen
may say "Windows protected your PC" the first time: click "More info" → "Run anyway".

## Features

- Custom title / subtitle / note; covers all monitors and stays on top
- Password unlock (PBKDF2 hash stored in `config.json`); wrong attempts are logged but never lock you out
- Camera detection: camera index, check interval (seconds), sensitivity, face detection;
  snapshots saved to `captures/` on alerts
- Keyboard / mouse activity detection (native Windows hooks, throttled to one report per 3 s)
- Blocks Win key, Alt+Tab, Alt+Esc, Alt+F4
- Prevents system sleep / display turning off
- Shows a session summary after unlocking; logs saved to `logs/`

## Snapshots

- **View:** "Open snapshots folder" in the settings window or in the summary after unlocking.
- **Delete:** "Delete all" in the settings window.
- **Auto-delete:** 24 hours after the session ends by default ("Auto-delete after (h)"; 0 = keep forever).
  A tiny background process deletes them on time even if the app is closed; if the PC restarts before
  then, they are deleted the next time the app starts.

## Run from source

Python 3 with tkinter is all that's required. Camera detection is optional:

```
pip install "opencv-python-headless>=4.8,<5"
python lockscreen.py
```

OpenCV must be 4.x: version 5.0 removed the Haar cascade used for face detection.
OpenCV is only loaded when camera detection is turned on.

Build the exes with `build.bat` (needs `pip install pyinstaller` plus OpenCV for the camera build).

## Notes

- **Ctrl+Alt+Del is protected by Windows and cannot be blocked by any program.** Someone could still
  open Task Manager and end this app, so treat it as a "don't touch" deterrent, not a security lock.
  Use Win+L when you need real security.
- Forgot the password: Ctrl+Alt+Del → Task Manager → end the `ComputingLock` process.
- Some antivirus tools flag PyInstaller exes that install keyboard hooks; allow it if that happens.

## License

[MIT](LICENSE)

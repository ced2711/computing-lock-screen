"""
Smoke test: open the real lock screen, feed it input, try a wrong and a right password,
and check the session summary. It covers the screen for a few seconds and unlocks itself.

    python tests/smoke_test.py [screenshot-command...]

On Linux run it inside an X server (CI uses xvfb-run). Any extra arguments are run as a
command while the screen is locked, e.g. `import -window root shot.png` to capture it.
"""

import os
import subprocess
import sys
import tempfile
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lockscreen as ls  # noqa: E402

PWD = "test-1234"


def main():
    tmp = tempfile.mkdtemp(prefix="lockscreen-test-")
    ls.LOG_DIR = os.path.join(tmp, "logs")
    ls.CAPTURE_DIR = os.path.join(tmp, "captures")
    salt = "00" * 16
    cfg = dict(ls.DEFAULT_CONFIG, pwd_salt=salt, pwd_hash=ls.hash_password(PWD, salt), note="smoke test")

    root = tk.Tk()
    ls.pick_fonts(root)
    root.withdraw()
    result, failures = {}, []

    def check(ok, what):
        print(("ok    " if ok else "FAIL  ") + what)
        if not ok:
            failures.append(what)

    def on_unlock(summary):
        result.update(summary)
        root.after(200, root.destroy)

    lock = ls.LockScreen(root, cfg, on_unlock)

    def poke():
        w = lock.win
        w.update()
        vx, vy, vw, vh = lock.vs or (0, 0, w.winfo_screenwidth(), w.winfo_screenheight())
        check(w.winfo_width() == vw and w.winfo_height() == vh,
              f"covers all monitors ({w.winfo_width()}x{w.winfo_height()} vs {vw}x{vh})")
        if not ls.IS_WIN:
            check(w.grab_status() == "global", f"holds a global grab (status={w.grab_status()!r})")
            # on Linux the lock window's own events are the activity source
            w.event_generate("<Motion>", x=50, y=50)
            lock.entry.event_generate("<KeyPress>", keysym="a")
            w.event_generate("<ButtonPress>", button=1, x=60, y=60)
        if len(sys.argv) > 1:
            subprocess.run(sys.argv[1:], check=False)
        lock.pwd_var.set("wrong")
        lock.try_unlock()
        root.after(800, unlock)

    def unlock():
        lock.pwd_var.set(PWD)
        lock.try_unlock()

    root.after(1500, poke)
    root.after(20000, lambda: (failures.append("timed out"), root.destroy()))
    root.mainloop()

    check(bool(result), "unlocked with the right password")
    check(result.get("password") == 1, f"one wrong password counted ({result.get('password')})")
    if not ls.IS_WIN:
        check(result.get("keyboard", 0) >= 1, f"keyboard activity detected ({result.get('keyboard')})")
        check(result.get("mouse", 0) >= 1, f"mouse activity detected ({result.get('mouse')})")
    check(bool(result.get("log_path")) and os.path.exists(result["log_path"]), "session log written")
    check(ls._inhibitor is None, "keep-awake lock released")
    print("\n".join(result.get("log", [])))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

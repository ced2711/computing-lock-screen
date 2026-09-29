"""
Computing Lock Screen (Windows / Linux)

Lock your screen while long jobs (vibe coding / training / builds) keep running
in the background. Optional camera, keyboard and mouse activity detection.

No required dependencies. Windows uses native low-level hooks for keyboard/mouse;
Linux (X11) grabs keyboard and pointer through Tk, like xscreensaver / i3lock do.
Camera detection is optional: pip install "opencv-python-headless<5"
"""

import ctypes
import datetime as dt
import hashlib
import importlib.util
import json
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import font as tkfont, messagebox, ttk

IS_WIN = sys.platform == "win32"
IS_WAYLAND = not IS_WIN and (os.environ.get("XDG_SESSION_TYPE") == "wayland"
                             or bool(os.environ.get("WAYLAND_DISPLAY")))
HAS_CV2 = importlib.util.find_spec("cv2") is not None  # imported lazily, only when the camera is used

APP_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))
CONFIG_PATH = os.path.join(APP_DIR, "config.json")
CAPTURE_DIR = os.path.join(APP_DIR, "captures")
LOG_DIR = os.path.join(APP_DIR, "logs")
# Linux families are resolved to the first installed one in pick_fonts()
UI_FONT = "Segoe UI"
MONO_FONT = "Consolas"
PWD_CHAR = "●" if IS_WIN else "•"

# ---------------------------------------------------------------- strings

STRINGS = {
    "en": {
        "subtitle": "DO NOT TOUCH  ·  Tasks in progress",
        "settings_title": "Computing Lock Screen — Settings",
        "sec_text": "Lock screen text", "title": "Title", "subtitle_lbl": "Subtitle",
        "note": "Note (optional)", "note_hint": "e.g. Back in ~2 hours", "language": "Language",
        "sec_pwd": "Unlock password", "pwd": "Password", "pwd2": "Confirm password",
        "pwd_reuse": "Leave blank to reuse last password",
        "sec_cam": "Camera detection", "cam_enable": "Enable camera detection",
        "cam_missing": 'Camera needs: pip install "opencv-python-headless<5"',
        "cam_missing_exe": "This build has no camera support; use ComputingLock-Camera.exe",
        "cam_index": "Camera index", "cam_index_hint": "0 = default camera",
        "cam_int": "Check interval (s)", "cam_int_hint": "Seconds between analyzed frames",
        "cam_sens": "Sensitivity (%)", "cam_sens_hint": "Alert when this % of the image changes; lower = more sensitive",
        "cam_face": "Also detect faces", "cam_snap": "Save snapshots to captures/ on detection",
        "sec_input": "Keyboard / Mouse", "kb": "Detect key presses", "ms": "Detect mouse movement / clicks",
        "block": "Block Win key, Alt+Tab, Alt+Esc, Alt+F4",
        "block_linux": "Block system shortcuts (grabs keyboard and mouse)",
        "cam_missing_bin": "This build has no camera support; use ComputingLock-Camera",
        "wayland": "Wayland session: shortcuts cannot be blocked and input is only seen while the\n"
                   "lock window has focus. Log in with an X11 session for full protection.",
        "sec_other": "Other", "awake": "Prevent system sleep (recommended, keeps jobs running)",
        "display": "Keep display on", "beep": "Beep when activity is detected",
        "quit": "Quit", "lock": "🔒 Lock screen",
        "pwd_short": "Password must be at least 4 characters", "pwd_mismatch": "Passwords do not match",
        "cam_nan": "Camera settings must be numbers", "settings": "Settings",
        "face_na": "Face detection unavailable (needs OpenCV 4.x); motion detection only",
        "cam_fail": "Could not open camera; camera detection disabled", "cam_started": "Camera started",
        "changed": "{:.1f}% of image changed", "faces": "{} face(s) detected", "camera": "Camera: ",
        "key": "Keyboard: key press detected", "key_blocked": " (system shortcut blocked)",
        "mouse": "Mouse: ", "moved": "moved", "clicked": "clicked", "scrolled": "scrolled",
        "started": "Lock screen started", "mon_cam": "📷 Camera (every {:g}s)", "mon_kb": "⌨ Keyboard",
        "mon_ms": "🖱 Mouse", "monitoring": "Monitoring:  ", "unlock": "Unlock",
        "enter_pwd": "Enter password to unlock", "running": "Running  ",
        "activity": "⚠ Activity detected · ",
        "keep_hours": "Auto-delete after (h)", "keep_hint": "Hours after the session ends; 0 = keep forever",
        "snap_count": "{} snapshot(s) in captures/", "delete_all": "Delete all",
        "delete_confirm": "Permanently delete all {} snapshot(s)?",
        "sum_snaps": "{} snapshot(s) taken.", "sum_expire": "They will be deleted automatically in {:g} h.",
        "sum_keep": "They are kept until you delete them.",
        "wrong_n": "Wrong password (attempt {})", "wrong": "Wrong password", "unlocked": "Unlocked",
        "sum_title": "Lock session log", "sum_dur": "Locked for {}",
        "sum_counts": "Keyboard: {}    Mouse: {}    Camera alerts: {}    Wrong passwords: {}",
        "open_snaps": "Open snapshots folder", "open_log": "Open log", "close": "Close",
    },
    "zh": {
        "subtitle": "DO NOT TOUCH  ·  程序运行中，请勿触碰",
        "settings_title": "Computing Lock Screen — 设置",
        "sec_text": "锁屏显示", "title": "主标题", "subtitle_lbl": "副标题",
        "note": "备注（可选）", "note_hint": "例如：预计 2 小时后结束", "language": "语言",
        "sec_pwd": "解锁密码", "pwd": "密码", "pwd2": "确认密码", "pwd_reuse": "留空=使用上次密码",
        "sec_cam": "摄像头检测", "cam_enable": "启用摄像头检测",
        "cam_missing": '摄像头功能需要：pip install "opencv-python-headless<5"',
        "cam_missing_exe": "此版本不含摄像头功能，请使用 ComputingLock-Camera.exe",
        "cam_index": "摄像头编号", "cam_index_hint": "0 = 默认摄像头",
        "cam_int": "检测频率（秒）", "cam_int_hint": "每隔多少秒拍一帧分析",
        "cam_sens": "灵敏度阈值（%）", "cam_sens_hint": "画面变化超过此比例报警，越小越敏感",
        "cam_face": "同时检测人脸", "cam_snap": "检测到时保存快照到 captures/",
        "sec_input": "键盘 / 鼠标", "kb": "检测键盘按键", "ms": "检测鼠标移动 / 点击",
        "block": "拦截 Win 键、Alt+Tab、Alt+Esc、Alt+F4",
        "block_linux": "拦截系统快捷键（独占键盘和鼠标）",
        "cam_missing_bin": "此版本不含摄像头功能，请使用 ComputingLock-Camera",
        "wayland": "当前是 Wayland 会话：无法拦截系统快捷键，且只有锁屏窗口获得焦点时才能检测键鼠。\n"
                   "需要完整保护请用 X11 会话登录。",
        "sec_other": "其他", "awake": "阻止系统睡眠（推荐，保证任务不中断）",
        "display": "保持屏幕常亮", "beep": "检测到活动时发出提示音",
        "quit": "退出", "lock": "🔒 开始锁屏",
        "pwd_short": "密码至少 4 位", "pwd_mismatch": "两次输入的密码不一致",
        "cam_nan": "摄像头参数必须是数字", "settings": "设置",
        "face_na": "人脸检测不可用（需要 OpenCV 4.x），仅做画面变化检测",
        "cam_fail": "无法打开摄像头，摄像头检测已停用", "cam_started": "摄像头已启动",
        "changed": "画面变化 {:.1f}%", "faces": "检测到 {} 张人脸", "camera": "摄像头：",
        "key": "键盘：检测到按键", "key_blocked": "（已拦截系统快捷键）",
        "mouse": "鼠标：", "moved": "移动", "clicked": "点击", "scrolled": "滚轮",
        "started": "锁屏已启动", "mon_cam": "📷 摄像头（每 {:g}s）", "mon_kb": "⌨ 键盘",
        "mon_ms": "🖱 鼠标", "monitoring": "监测中：", "unlock": "解锁",
        "enter_pwd": "输入密码解锁", "running": "已运行  ",
        "activity": "⚠ 检测到活动 · ",
        "keep_hours": "自动删除（小时）", "keep_hint": "锁屏结束后多少小时删除；0 = 永久保留",
        "snap_count": "captures/ 中有 {} 张快照", "delete_all": "全部删除",
        "delete_confirm": "确定永久删除全部 {} 张快照吗？",
        "sum_snaps": "本次拍下 {} 张快照。", "sum_expire": "将在 {:g} 小时后自动删除。",
        "sum_keep": "会一直保留，直到你手动删除。",
        "wrong_n": "密码错误（第 {} 次）", "wrong": "密码错误", "unlocked": "已解锁",
        "sum_title": "锁屏期间记录", "sum_dur": "锁屏时长 {}",
        "sum_counts": "键盘活动 {} 次    鼠标活动 {} 次    摄像头报警 {} 次    密码错误 {} 次",
        "open_snaps": "打开快照文件夹", "open_log": "打开日志", "close": "关闭",
    },
}
LANG_NAMES = {"en": "English", "zh": "中文"}
_lang = "en"


# Tk on Linux renders through Xft, which crashes (X BadLength) on color-emoji fonts before libXft 2.3.5
_EMOJI = re.compile("[\U0001F300-\U0001FAFF⌨⚠]️? ?")


def T(key, *args):
    s = STRINGS[_lang][key]
    if not IS_WIN:
        s = _EMOJI.sub("", s)
    return s.format(*args) if args else s


DEFAULT_CONFIG = {
    "language": "en",
    "title": "COMPUTING",
    "subtitle": STRINGS["en"]["subtitle"],
    "note": "",
    "camera_enabled": False,
    "camera_index": 0,
    "camera_interval": 5.0,       # seconds
    "camera_sensitivity": 3.0,    # % of changed pixels that triggers an alert; lower = more sensitive
    "camera_face": True,
    "save_snapshots": True,
    "snapshot_retention_hours": 24,  # delete snapshots this long after the session ends; 0 = keep
    "keyboard_enabled": True,
    "mouse_enabled": True,
    "block_shortcuts": True,      # block Win key / Alt+Tab / Alt+Esc / Alt+F4
    "keep_awake": True,
    "keep_display_on": True,
    "beep_on_alert": False,
    "pwd_salt": "",
    "pwd_hash": "",
}

# ---------------------------------------------------------------- helpers

def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg.update(json.load(f))
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg):
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def hash_password(pwd, salt_hex):
    return hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"),
                               bytes.fromhex(salt_hex), 200_000).hex()


def set_dpi_aware():
    if not IS_WIN:
        return  # X11 Tk scales from the X server's DPI on its own
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def pick_fonts(root):
    """Segoe UI / Consolas do not exist on Linux: use the first installed look-alike."""
    global UI_FONT, MONO_FONT
    if IS_WIN:
        return
    have = set(tkfont.families(root))
    UI_FONT = next((f for f in ("Noto Sans", "Ubuntu", "Cantarell", "DejaVu Sans", "Liberation Sans")
                    if f in have), "TkDefaultFont")
    MONO_FONT = next((f for f in ("DejaVu Sans Mono", "Noto Sans Mono", "Ubuntu Mono", "Liberation Mono")
                      if f in have), "TkFixedFont")


def virtual_screen(win):
    """Return (x, y, w, h) covering all monitors."""
    if not IS_WIN:
        return 0, 0, win.winfo_screenwidth(), win.winfo_screenheight()  # one X screen spans them all
    try:
        u = ctypes.windll.user32
        return (u.GetSystemMetrics(76), u.GetSystemMetrics(77),
                u.GetSystemMetrics(78), u.GetSystemMetrics(79))
    except Exception:
        return None


def primary_monitor(win):
    """Return (x, y, w, h) of the primary monitor, in screen coordinates."""
    if not IS_WIN:
        try:
            out = subprocess.run(["xrandr", "--current"], capture_output=True, text=True, timeout=3).stdout
            m = (re.search(r"^\S+ connected primary (\d+)x(\d+)\+(\d+)\+(\d+)", out, re.M)
                 or re.search(r"^\S+ connected (\d+)x(\d+)\+(\d+)\+(\d+)", out, re.M))
            if m:
                w, h, x, y = map(int, m.groups())
                return x, y, w, h
        except (OSError, subprocess.SubprocessError):
            pass
    return 0, 0, win.winfo_screenwidth(), win.winfo_screenheight()


_inhibitor = None


def set_keep_awake(system, display):
    """Windows: thread execution state. Linux: a systemd-inhibit lock held for the session."""
    global _inhibitor
    if IS_WIN:
        try:
            flags = 0x80000000 | (0x1 if system else 0) | (0x2 if display else 0)
            ctypes.windll.kernel32.SetThreadExecutionState(flags)
        except Exception:
            pass
        return
    if _inhibitor:
        try:
            os.killpg(_inhibitor.pid, 15)
        except OSError:
            pass
        _inhibitor = None
    what = ":".join(w for w, on in (("sleep", system), ("idle", display)) if on)
    exe = shutil.which("systemd-inhibit")
    if not (what and exe):
        return
    try:
        # the held command exits with us, so a crash never leaves the lock behind
        _inhibitor = subprocess.Popen(
            [exe, "--what=" + what, "--who=Computing Lock Screen", "--why=Long-running jobs",
             "--mode=block", "tail", f"--pid={os.getpid()}", "-f", "/dev/null"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
    except OSError:
        pass


def open_path(path):
    try:
        if IS_WIN:
            os.startfile(path)
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def list_snapshots():
    try:
        return [os.path.join(CAPTURE_DIR, n) for n in os.listdir(CAPTURE_DIR) if n.lower().endswith(".jpg")]
    except OSError:
        return []


def delete_snapshots(older_than_hours=None):
    """Delete snapshots (all, or those last stamped more than N hours ago). Returns the count."""
    cutoff = None if older_than_hours is None else time.time() - older_than_hours * 3600
    n = 0
    for p in list_snapshots():
        try:
            if cutoff is None or os.path.getmtime(p) < cutoff:
                os.remove(p)
                n += 1
        except OSError:
            pass
    return n


def cleanup_expired(cfg):
    hours = float(cfg.get("snapshot_retention_hours") or 0)
    return delete_snapshots(hours) if hours > 0 else 0


def schedule_cleanup(cfg, snaps):
    """Start a tiny detached process that deletes this session's snapshots when they expire,
    even if the app is closed. (If the PC restarts first, the next app launch cleans up.)"""
    hours = float(cfg.get("snapshot_retention_hours") or 0)
    if not snaps or hours <= 0:
        return
    if getattr(sys, "frozen", False):  # packaged .exe: re-launch itself
        cmd = [sys.executable]
    else:
        exe = sys.executable
        w = os.path.join(os.path.dirname(exe), "pythonw.exe")
        cmd = [w if os.path.exists(w) else exe, os.path.abspath(__file__)]
    if IS_WIN:
        detach = dict(creationflags=0x00000008 | 0x08000000)  # DETACHED_PROCESS | CREATE_NO_WINDOW
    else:
        detach = dict(start_new_session=True, stdin=subprocess.DEVNULL,
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        subprocess.Popen(cmd + ["--cleanup-at", str(time.time() + hours * 3600 + 60)],
                         close_fds=True, cwd=APP_DIR, **detach)
    except Exception:
        pass


def run_cleanup_at(deadline):
    while time.time() < deadline:
        time.sleep(min(600, max(1, deadline - time.time())))
    cleanup_expired(load_config())


def fmt_duration(sec):
    sec = int(sec)
    return f"{sec // 3600:02d}:{sec % 3600 // 60:02d}:{sec % 60:02d}"


# ---------------------------------------------------------------- monitors

class CameraMonitor(threading.Thread):
    """Grab a frame every `interval` seconds and compare it with the previous one (motion / faces)."""

    def __init__(self, cfg, events):
        super().__init__(daemon=True)
        import cv2
        self.cv2 = cv2
        self.cfg, self.events = cfg, events
        self.stop_flag = threading.Event()
        self.prev = None
        self.baseline_left = 2
        self.saved = []  # snapshot paths written this session
        self.face_cascade = None
        if cfg["camera_face"]:
            try:
                path = os.path.join(cv2.data.haarcascades, "haarcascade_frontalface_default.xml")
                self.face_cascade = cv2.CascadeClassifier(path)
                if self.face_cascade.empty():
                    self.face_cascade = None
            except Exception:
                self.face_cascade = None
            if self.face_cascade is None:
                events.put(("info", T("face_na")))

    def run(self):
        cv2 = self.cv2
        cap = cv2.VideoCapture(int(self.cfg["camera_index"]), cv2.CAP_DSHOW if IS_WIN else cv2.CAP_ANY)
        if not cap.isOpened():
            self.events.put(("error", T("cam_fail")))
            return
        self.events.put(("info", T("cam_started")))
        try:
            t0 = time.time()
            while time.time() - t0 < 2.0:  # warm up so auto-exposure settles
                cap.read()
            while not self.stop_flag.is_set():
                for _ in range(4):  # drop stale buffered frames
                    cap.grab()
                ok, frame = cap.read()
                if ok:
                    self.analyze(frame)
                self.stop_flag.wait(max(0.5, float(self.cfg["camera_interval"])))
        finally:
            cap.release()

    def analyze(self, frame):
        cv2 = self.cv2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.GaussianBlur(cv2.resize(gray, (320, 240)), (21, 21), 0)
        reasons = []

        if self.baseline_left > 0:  # first frames only build the baseline, no alerts
            self.baseline_left -= 1
            self.prev = small
            return

        if self.prev is not None:
            diff = cv2.absdiff(self.prev, small)
            _, th = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
            changed = cv2.countNonZero(th) / th.size * 100
            if changed >= float(self.cfg["camera_sensitivity"]):
                reasons.append(T("changed", changed))
        self.prev = small

        if self.face_cascade is not None:
            faces = self.face_cascade.detectMultiScale(
                cv2.resize(gray, (640, 480)), 1.1, 5, minSize=(60, 60))
            if len(faces):
                reasons.append(T("faces", len(faces)))

        if reasons:
            self.events.put(("camera", T("camera") + ", ".join(reasons)))
            if self.cfg["save_snapshots"]:
                self.save(frame, "camera")

    def save(self, frame, tag):
        try:
            os.makedirs(CAPTURE_DIR, exist_ok=True)
            path = os.path.join(CAPTURE_DIR, f"{dt.datetime.now():%Y%m%d_%H%M%S}_{tag}.jpg")
            if self.cv2.imwrite(path, frame):
                self.saved.append(path)
        except Exception:
            pass

    def stop(self):
        self.stop_flag.set()


class InputReporter:
    """Counts keyboard / mouse activity and reports it at most once per 3 seconds."""

    def __init__(self, cfg, events):
        self.cfg, self.events = cfg, events
        self.last_kb = self.last_mouse = 0.0
        self.kb_count = self.mouse_count = 0

    def _on_key(self, blocked=False):
        if not self.cfg["keyboard_enabled"]:
            return
        self.kb_count += 1
        now = time.time()
        if now - self.last_kb > 3:  # throttle: at most one report per 3 seconds
            self.last_kb = now
            self.events.put(("keyboard", T("key") + (T("key_blocked") if blocked else "")))

    def _mouse_event(self, key):
        self.mouse_count += 1
        now = time.time()
        if now - self.last_mouse > 3:
            self.last_mouse = now
            self.events.put(("mouse", T("mouse") + T(key)))


if IS_WIN:
    import ctypes.wintypes as wt

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wt.DWORD), ("scanCode", wt.DWORD), ("flags", wt.DWORD),
                    ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wt.WPARAM, wt.LPARAM)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wt.HINSTANCE, wt.DWORD)
    _user32.SetWindowsHookExW.restype = wt.HHOOK
    _user32.CallNextHookEx.argtypes = (wt.HHOOK, ctypes.c_int, wt.WPARAM, wt.LPARAM)
    _user32.CallNextHookEx.restype = LRESULT
    _user32.UnhookWindowsHookEx.argtypes = (wt.HHOOK,)
    _user32.PostThreadMessageW.argtypes = (wt.DWORD, wt.UINT, wt.WPARAM, wt.LPARAM)
    ctypes.windll.kernel32.GetModuleHandleW.restype = wt.HMODULE


class InputMonitor(InputReporter, threading.Thread):
    """Windows: native low-level keyboard / mouse hooks; can block system shortcuts."""

    WH_KEYBOARD_LL, WH_MOUSE_LL, WM_QUIT = 13, 14, 0x0012
    WM_KEYDOWN, WM_SYSKEYDOWN = 0x0100, 0x0104
    WM_MOUSEMOVE, WM_MOUSEWHEEL = 0x0200, 0x020A
    CLICKS = (0x0201, 0x0204, 0x0207)  # left / right / middle button down
    VK_LWIN, VK_RWIN, VK_TAB, VK_ESC, VK_F4 = 0x5B, 0x5C, 0x09, 0x1B, 0x73
    LLKHF_ALTDOWN = 0x20

    def __init__(self, cfg, events):
        InputReporter.__init__(self, cfg, events)
        threading.Thread.__init__(self, daemon=True)
        self.tid = None
        # keep references so the callbacks are not garbage-collected
        self._kb_proc = HOOKPROC(self._kb_hook)
        self._ms_proc = HOOKPROC(self._ms_hook)

    def run(self):
        self.tid = ctypes.windll.kernel32.GetCurrentThreadId()
        hmod = ctypes.windll.kernel32.GetModuleHandleW(None)
        hooks = []
        if self.cfg["keyboard_enabled"] or self.cfg["block_shortcuts"]:
            hooks.append(_user32.SetWindowsHookExW(self.WH_KEYBOARD_LL, self._kb_proc, hmod, 0))
        if self.cfg["mouse_enabled"]:
            hooks.append(_user32.SetWindowsHookExW(self.WH_MOUSE_LL, self._ms_proc, hmod, 0))
        msg = wt.MSG()
        while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        for h in hooks:
            if h:
                _user32.UnhookWindowsHookEx(h)

    def stop(self):
        if self.tid:
            _user32.PostThreadMessageW(self.tid, self.WM_QUIT, 0, 0)

    # --- keyboard
    def _kb_hook(self, code, wparam, lparam):
        if code == 0:
            data = ctypes.cast(lparam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            vk, alt = data.vkCode, bool(data.flags & self.LLKHF_ALTDOWN)
            down = wparam in (self.WM_KEYDOWN, self.WM_SYSKEYDOWN)
            blocked = self.cfg["block_shortcuts"] and (
                vk in (self.VK_LWIN, self.VK_RWIN)
                or (alt and vk in (self.VK_TAB, self.VK_ESC, self.VK_F4)))
            if down:
                self._on_key(blocked)
            if blocked:
                return 1  # swallow the key
        return _user32.CallNextHookEx(None, code, wparam, lparam)

    # --- mouse
    def _ms_hook(self, code, wparam, lparam):
        if code == 0:
            if wparam == self.WM_MOUSEMOVE:
                self._mouse_event("moved")
            elif wparam in self.CLICKS:
                self._mouse_event("clicked")
            elif wparam == self.WM_MOUSEWHEEL:
                self._mouse_event("scrolled")
        return _user32.CallNextHookEx(None, code, wparam, lparam)


class TkInputMonitor(InputReporter):
    """Linux: the lock window covers every monitor, so its own Tk events are the activity.
    With block_shortcuts it also holds a global keyboard + pointer grab (as xscreensaver and
    i3lock do), so the window manager never sees Super, Alt+Tab, Alt+F4, ... Wayland
    compositors do not honour X grabs, and Ctrl+Alt+F<n> is handled by the kernel."""

    SUPER_KEYS = {"Super_L", "Super_R", "Meta_L", "Meta_R", "Hyper_L", "Hyper_R"}
    ALT_KEYS = {"Tab", "ISO_Left_Tab", "Escape", "F4"}
    ALT_MASK = 0x8  # Mod1

    def __init__(self, cfg, events, win):
        super().__init__(cfg, events)
        self.win = win
        self.stopped = False

    def start(self):
        w = self.win  # bindings on a toplevel also fire for all of its child widgets
        w.bind("<KeyPress>", self._key, add="+")
        w.bind("<Motion>", lambda e: self._mouse("moved"), add="+")
        w.bind("<ButtonPress>", self._button, add="+")
        w.bind("<MouseWheel>", lambda e: self._mouse("scrolled"), add="+")  # Tk 8.7+ wheel
        if self.cfg["block_shortcuts"]:
            self._grab()

    def _grab(self):
        if self.stopped:
            return
        try:
            self.win.grab_set_global()
        except tk.TclError:  # not viewable yet, or another client holds a grab: retry
            self.win.after(250, self._grab)

    def stop(self):
        self.stopped = True
        try:
            self.win.grab_release()
        except tk.TclError:
            pass

    def _key(self, e):
        blocked = (self.cfg["block_shortcuts"] and not IS_WAYLAND
                   and (e.keysym in self.SUPER_KEYS
                        or (e.state & self.ALT_MASK and e.keysym in self.ALT_KEYS)))
        self._on_key(blocked)

    def _button(self, e):
        self._mouse("scrolled" if e.num in (4, 5, 6, 7) else "clicked")  # X11 wheel = buttons 4-7

    def _mouse(self, key):
        if self.cfg["mouse_enabled"]:
            self._mouse_event(key)


# ---------------------------------------------------------------- settings window

class SettingsWindow:
    def __init__(self, root, cfg, on_start):
        self.root, self.cfg, self.on_start = root, cfg, on_start
        root.resizable(False, False)
        try:
            ttk.Style().theme_use("vista" if IS_WIN else "clam")
        except tk.TclError:
            pass
        self.build()

    def build(self):
        global _lang
        cfg, root = self.cfg, self.root
        _lang = cfg["language"] if cfg["language"] in STRINGS else "en"
        root.title(T("settings_title"))
        for child in root.winfo_children():
            child.destroy()

        f = ttk.Frame(root, padding=18)
        f.grid(sticky="nsew")
        r = 0

        def section(text):
            nonlocal r
            ttk.Label(f, text=text, font=(UI_FONT, 11, "bold")).grid(
                row=r, column=0, columnspan=3, sticky="w", pady=(12 if r else 0, 4))
            r += 1

        def row(label, widget, hint=""):
            nonlocal r
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=3)
            widget.grid(row=r, column=1, sticky="we", pady=3)
            if hint:
                ttk.Label(f, text=hint, foreground="#888").grid(row=r, column=2, sticky="w", padx=8)
            r += 1

        def check(text, var, enabled=True):
            nonlocal r
            w = ttk.Checkbutton(f, text=text, variable=var)
            w.grid(row=r, column=0, columnspan=2, sticky="w"); r += 1
            if not enabled:
                w.state(["disabled"]); var.set(False)

        # display text
        section(T("sec_text"))
        self.v_lang = tk.StringVar(value=LANG_NAMES[_lang])
        lang_box = ttk.Combobox(f, textvariable=self.v_lang, values=list(LANG_NAMES.values()),
                                state="readonly", width=12)
        lang_box.bind("<<ComboboxSelected>>", lambda e: self.switch_language())
        row(T("language"), lang_box)
        self.v_title = tk.StringVar(value=cfg["title"])
        self.v_sub = tk.StringVar(value=cfg["subtitle"])
        self.v_note = tk.StringVar(value=cfg["note"])
        row(T("title"), ttk.Entry(f, textvariable=self.v_title, width=38))
        row(T("subtitle_lbl"), ttk.Entry(f, textvariable=self.v_sub, width=38))
        row(T("note"), ttk.Entry(f, textvariable=self.v_note, width=38), T("note_hint"))

        # password
        section(T("sec_pwd"))
        self.v_pwd, self.v_pwd2 = tk.StringVar(), tk.StringVar()
        row(T("pwd"), ttk.Entry(f, textvariable=self.v_pwd, show=PWD_CHAR, width=38),
            T("pwd_reuse") if cfg["pwd_hash"] else "")
        row(T("pwd2"), ttk.Entry(f, textvariable=self.v_pwd2, show=PWD_CHAR, width=38))

        # camera
        section(T("sec_cam"))
        self.v_cam = tk.BooleanVar(value=cfg["camera_enabled"])
        self.v_cam_idx = tk.IntVar(value=cfg["camera_index"])
        self.v_cam_int = tk.DoubleVar(value=cfg["camera_interval"])
        self.v_cam_sens = tk.DoubleVar(value=cfg["camera_sensitivity"])
        self.v_face = tk.BooleanVar(value=cfg["camera_face"])
        self.v_snap = tk.BooleanVar(value=cfg["save_snapshots"])
        check(T("cam_enable"), self.v_cam, HAS_CV2)
        if not HAS_CV2:
            missing = (("cam_missing_exe" if IS_WIN else "cam_missing_bin")
                       if getattr(sys, "frozen", False) else "cam_missing")
            ttk.Label(f, text=T(missing), foreground="#c33").grid(
                row=r, column=0, columnspan=3, sticky="w"); r += 1
        row(T("cam_index"), ttk.Spinbox(f, from_=0, to=5, textvariable=self.v_cam_idx, width=8), T("cam_index_hint"))
        row(T("cam_int"), ttk.Spinbox(f, from_=0.5, to=600, increment=0.5,
                                      textvariable=self.v_cam_int, width=8), T("cam_int_hint"))
        row(T("cam_sens"), ttk.Spinbox(f, from_=0.5, to=50, increment=0.5,
                                       textvariable=self.v_cam_sens, width=8), T("cam_sens_hint"))
        check(T("cam_face"), self.v_face)
        check(T("cam_snap"), self.v_snap)
        keep = float(cfg["snapshot_retention_hours"] or 0)
        self.v_keep = tk.DoubleVar(value=int(keep) if keep.is_integer() else keep)
        row(T("keep_hours"), ttk.Spinbox(f, from_=0, to=720, increment=1,
                                         textvariable=self.v_keep, width=8), T("keep_hint"))
        snap_row = ttk.Frame(f)
        snap_row.grid(row=r, column=0, columnspan=3, sticky="w", pady=(2, 0)); r += 1
        self.snap_count = ttk.Label(snap_row)
        self.snap_count.pack(side="left")
        ttk.Button(snap_row, text=T("open_snaps"), command=self.open_snapshots).pack(side="left", padx=(10, 0))
        ttk.Button(snap_row, text=T("delete_all"), command=self.delete_all).pack(side="left", padx=(6, 0))
        self.refresh_snap_count()

        # keyboard / mouse
        section(T("sec_input"))
        self.v_kb = tk.BooleanVar(value=cfg["keyboard_enabled"])
        self.v_ms = tk.BooleanVar(value=cfg["mouse_enabled"])
        self.v_block = tk.BooleanVar(value=cfg["block_shortcuts"])
        check(T("kb"), self.v_kb)
        check(T("ms"), self.v_ms)
        check(T("block" if IS_WIN else "block_linux"), self.v_block)
        if IS_WAYLAND:
            ttk.Label(f, text=T("wayland"), foreground="#c33").grid(
                row=r, column=0, columnspan=3, sticky="w"); r += 1

        # other
        section(T("sec_other"))
        self.v_awake = tk.BooleanVar(value=cfg["keep_awake"])
        self.v_disp = tk.BooleanVar(value=cfg["keep_display_on"])
        self.v_beep = tk.BooleanVar(value=cfg["beep_on_alert"])
        check(T("awake"), self.v_awake)
        check(T("display"), self.v_disp)
        check(T("beep"), self.v_beep)

        btns = ttk.Frame(f)
        btns.grid(row=r, column=0, columnspan=3, pady=(18, 0), sticky="e")
        ttk.Button(btns, text=T("quit"), command=root.destroy).pack(side="right", padx=(8, 0))
        ttk.Button(btns, text=T("lock"), command=self.start).pack(side="right")

    def refresh_snap_count(self):
        self.snap_count.config(text=T("snap_count", len(list_snapshots())))

    def open_snapshots(self):
        os.makedirs(CAPTURE_DIR, exist_ok=True)
        open_path(CAPTURE_DIR)

    def delete_all(self):
        n = len(list_snapshots())
        if n and messagebox.askyesno(T("delete_all"), T("delete_confirm", n)):
            delete_snapshots()
        self.refresh_snap_count()

    def collect(self):
        """Copy form values into cfg; returns False if they are invalid."""
        try:
            interval = float(self.v_cam_int.get())
            sens = float(self.v_cam_sens.get())
            idx = int(self.v_cam_idx.get())
            keep = max(0.0, float(self.v_keep.get()))
            keep = int(keep) if keep.is_integer() else keep
        except (tk.TclError, ValueError):
            messagebox.showwarning(T("settings"), T("cam_nan"))
            return False
        self.cfg.update(
            title=self.v_title.get().strip() or "COMPUTING",
            subtitle=self.v_sub.get().strip(),
            note=self.v_note.get().strip(),
            camera_enabled=self.v_cam.get(), camera_index=idx,
            camera_interval=max(0.5, interval), camera_sensitivity=max(0.1, sens),
            camera_face=self.v_face.get(), save_snapshots=self.v_snap.get(),
            snapshot_retention_hours=keep,
            keyboard_enabled=self.v_kb.get(), mouse_enabled=self.v_ms.get(),
            block_shortcuts=self.v_block.get(), keep_awake=self.v_awake.get(),
            keep_display_on=self.v_disp.get(), beep_on_alert=self.v_beep.get(),
        )
        return True

    def switch_language(self):
        new = next(k for k, v in LANG_NAMES.items() if v == self.v_lang.get())
        if new == self.cfg["language"] or not self.collect():
            return
        # swap the subtitle too if it is still the other language's default
        if self.cfg["subtitle"] == STRINGS[self.cfg["language"]]["subtitle"]:
            self.cfg["subtitle"] = STRINGS[new]["subtitle"]
        self.cfg["language"] = new
        save_config(self.cfg)
        self.build()

    def start(self):
        p1, p2, cfg = self.v_pwd.get(), self.v_pwd2.get(), self.cfg
        if p1 or p2 or not cfg["pwd_hash"]:
            if len(p1) < 4:
                messagebox.showwarning(T("pwd"), T("pwd_short")); return
            if p1 != p2:
                messagebox.showwarning(T("pwd"), T("pwd_mismatch")); return
        if not self.collect():
            return
        if p1:
            cfg["pwd_salt"] = secrets.token_hex(16)
            cfg["pwd_hash"] = hash_password(p1, cfg["pwd_salt"])
        save_config(cfg)
        self.on_start()


# ---------------------------------------------------------------- lock screen

BG, FG, DIM, ACCENT, ALERT = "#07090d", "#e8ecf1", "#5b6573", "#35d07f", "#ff4d4f"


class LockScreen:
    def __init__(self, root, cfg, on_unlock):
        self.root, self.cfg, self.on_unlock = root, cfg, on_unlock
        self.events = queue.Queue()
        self.log = []
        self.counts = {"keyboard": 0, "mouse": 0, "camera": 0, "password": 0}
        self.start_time = time.time()
        self.fail_count = 0
        self.angle = 0
        self.alert_until = 0.0
        self.last_idle_reset = 0.0
        self.closed = False

        self.win = tk.Toplevel(root)
        w = self.win
        w.configure(bg=BG, cursor="none")
        w.overrideredirect(True)
        self.vs = vs = virtual_screen(w)
        if vs:
            x, y, sw, sh = vs
            w.geometry(f"{sw}x{sh}+{x}+{y}")
        else:
            w.attributes("-fullscreen", True)
        w.attributes("-topmost", True)
        w.protocol("WM_DELETE_WINDOW", lambda: None)
        w.bind("<Alt-F4>", lambda e: "break")
        w.bind("<Motion>", lambda e: w.configure(cursor="arrow"))

        self._build_ui()
        self._add_log("info", T("started"))

        if cfg["keep_awake"] or cfg["keep_display_on"]:
            set_keep_awake(cfg["keep_awake"], cfg["keep_display_on"])

        self.inputs = InputMonitor(cfg, self.events) if IS_WIN else TkInputMonitor(cfg, self.events, w)
        self.inputs.start()
        self.camera = None
        if cfg["camera_enabled"] and HAS_CV2:
            self.camera = CameraMonitor(cfg, self.events)
            self.camera.start()

        self._tick()
        self._spin()
        self._poll_events()
        self._keep_on_top()

    # --- UI
    def _build_ui(self):
        w = self.win
        # center on the primary monitor; ox, oy = its origin relative to this window
        px, py, pw, ph = primary_monitor(w)
        vs = self.vs
        ox, oy = (px - vs[0], py - vs[1]) if vs else (0, 0)

        center = tk.Frame(w, bg=BG)
        center.place(x=ox + pw // 2, y=oy + ph // 2, anchor="center")

        self.canvas = tk.Canvas(center, width=120, height=120, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=(0, 20))
        self.canvas.create_oval(10, 10, 110, 110, outline="#1c232d", width=6)
        self.arc = self.canvas.create_arc(10, 10, 110, 110, start=0, extent=90,
                                          style="arc", outline=ACCENT, width=6)

        tk.Label(center, text=self.cfg["title"], bg=BG, fg=FG, font=(UI_FONT, 64, "bold")).pack()
        tk.Label(center, text=self.cfg["subtitle"], bg=BG, fg=ALERT,
                 font=(UI_FONT, 22, "bold")).pack(pady=(4, 0))
        if self.cfg["note"]:
            tk.Label(center, text=self.cfg["note"], bg=BG, fg=DIM, font=(UI_FONT, 14)).pack(pady=(10, 0))

        self.elapsed_lbl = tk.Label(center, text="", bg=BG, fg=DIM, font=(MONO_FONT, 16))
        self.elapsed_lbl.pack(pady=(24, 0))

        mon = []
        if self.cfg["camera_enabled"] and HAS_CV2:
            mon.append(T("mon_cam", self.cfg["camera_interval"]))
        if self.cfg["keyboard_enabled"]:
            mon.append(T("mon_kb"))
        if self.cfg["mouse_enabled"]:
            mon.append(T("mon_ms"))
        tk.Label(center, text=(T("monitoring") + "   ".join(mon)) if mon else "", bg=BG, fg=DIM,
                 font=(UI_FONT, 11)).pack(pady=(6, 0))

        self.alert_lbl = tk.Label(center, text="", bg=BG, fg=ALERT, font=(UI_FONT, 14, "bold"))
        self.alert_lbl.pack(pady=(18, 0))

        # password box
        box = tk.Frame(center, bg=BG)
        box.pack(pady=(26, 0))
        self.pwd_var = tk.StringVar()
        self.entry = tk.Entry(box, textvariable=self.pwd_var, show=PWD_CHAR, width=22, justify="center",
                              font=(UI_FONT, 16), bg="#131820", fg=FG, insertbackground=FG,
                              relief="flat", highlightthickness=1, highlightbackground="#2a3340",
                              highlightcolor=ACCENT)
        self.entry.pack(side="left", ipady=6)
        self.entry.bind("<Return>", lambda e: self.try_unlock())
        tk.Button(box, text=T("unlock"), command=self.try_unlock, font=(UI_FONT, 12),
                  bg="#1c2530", fg=FG, activebackground=ACCENT, relief="flat",
                  padx=16, cursor="hand2").pack(side="left", padx=(8, 0), ipady=4)
        self.msg_lbl = tk.Label(center, text=T("enter_pwd"), bg=BG, fg=DIM, font=(UI_FONT, 11))
        self.msg_lbl.pack(pady=(8, 0))

        self.clock_lbl = tk.Label(w, text="", bg=BG, fg=DIM, font=(MONO_FONT, 14))
        self.clock_lbl.place(x=ox + pw - 24, y=oy + 20, anchor="ne")

        self.log_lbl = tk.Label(w, text="", bg=BG, fg=DIM, justify="left", anchor="sw",
                                font=(UI_FONT, 10))
        self.log_lbl.place(x=ox + 24, y=oy + ph - 20, anchor="sw")

        self.entry.focus_force()

    # --- timers
    def _tick(self):
        if self.closed:
            return
        self.elapsed_lbl.config(text=T("running") + fmt_duration(time.time() - self.start_time))
        self.clock_lbl.config(text=dt.datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))
        now = time.time()
        if now > self.alert_until and self.alert_lbl.cget("text"):
            self.alert_lbl.config(text="")
        if not IS_WIN and self.cfg["keep_display_on"] and now - self.last_idle_reset > 30:
            self.last_idle_reset = now
            try:
                self.win.tk.call("tk", "inactive", "reset")  # XResetScreenSaver: keeps X11 blanking away
            except tk.TclError:
                pass
        self.win.after(1000, self._tick)

    def _spin(self):
        if self.closed:
            return
        self.angle = (self.angle - 12) % 360
        self.canvas.itemconfig(self.arc, start=self.angle)
        self.win.after(50, self._spin)

    def _keep_on_top(self):
        if self.closed:
            return
        try:
            self.win.attributes("-topmost", True)
            self.win.lift()
            if self.win.focus_get() is None:
                self.win.focus_force()
                self.entry.focus_set()
        except tk.TclError:
            pass
        self.win.after(1000, self._keep_on_top)

    def _poll_events(self):
        if self.closed:
            return
        try:
            while True:
                kind, text = self.events.get_nowait()
                self._add_log(kind, text)
                if kind in self.counts:
                    self.counts[kind] += 1
                    self._alert(text)
        except queue.Empty:
            pass
        self.win.after(300, self._poll_events)

    def _alert(self, text):
        self.alert_lbl.config(text=T("activity") + text)
        self.alert_until = time.time() + 6
        if self.cfg["beep_on_alert"]:
            try:
                if IS_WIN:
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
                else:
                    self.win.bell()
            except Exception:
                pass

    def _add_log(self, kind, text):
        self.log.append(f"[{dt.datetime.now():%H:%M:%S}] {text}")
        self.log_lbl.config(text="\n".join(self.log[-6:]))

    # --- unlock
    def try_unlock(self):
        # no lockout after wrong attempts: someone else must never be able to lock the owner out
        pwd = self.pwd_var.get()
        self.pwd_var.set("")
        if hash_password(pwd, self.cfg["pwd_salt"]) == self.cfg["pwd_hash"]:
            self.unlock()
            return
        self.fail_count += 1
        self.counts["password"] += 1
        self._add_log("password", T("wrong_n", self.fail_count))
        self._alert(T("wrong"))
        self.msg_lbl.config(text=T("wrong"), fg=ALERT)

    def unlock(self):
        self.closed = True
        self._add_log("info", T("unlocked"))
        self.inputs.stop()
        snaps = []
        if self.camera:
            self.camera.stop()
            snaps = self.camera.saved
            # retention counts from the end of the session, so stamp photos with the unlock time
            now = time.time()
            for p in snaps:
                try:
                    os.utime(p, (now, now))
                except OSError:
                    pass
            schedule_cleanup(self.cfg, snaps)
        set_keep_awake(False, False)
        log_path = self._write_log()
        summary = dict(self.counts, duration=fmt_duration(time.time() - self.start_time),
                       log=self.log, log_path=log_path, snapshots=len(snaps),
                       retention=self.cfg["snapshot_retention_hours"])
        self.win.destroy()
        self.on_unlock(summary)

    def _write_log(self):
        try:
            os.makedirs(LOG_DIR, exist_ok=True)
            path = os.path.join(LOG_DIR, f"session_{dt.datetime.fromtimestamp(self.start_time):%Y%m%d_%H%M%S}.txt")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.log))
            return path
        except OSError:
            return ""


# ---------------------------------------------------------------- session summary

def show_summary(root, s):
    win = tk.Toplevel(root)
    win.title(T("sum_title"))
    win.attributes("-topmost", True)
    f = ttk.Frame(win, padding=16)
    f.pack(fill="both", expand=True)
    ttk.Label(f, text=T("sum_dur", s["duration"]), font=(UI_FONT, 13, "bold")).pack(anchor="w")
    ttk.Label(f, text=T("sum_counts", s["keyboard"], s["mouse"], s["camera"], s["password"])).pack(
        anchor="w", pady=(4, 10))
    txt = tk.Text(f, width=70, height=16, font=(MONO_FONT, 10))
    txt.insert("1.0", "\n".join(s["log"]))
    txt.config(state="disabled")
    txt.pack(fill="both", expand=True)
    if s["snapshots"]:
        ttk.Label(f, text=T("sum_snaps", s["snapshots"]) + "  " +
                  (T("sum_expire", s["retention"]) if s["retention"] else T("sum_keep")),
                  foreground="#c33").pack(anchor="w", pady=(8, 0))
    b = ttk.Frame(f)
    b.pack(fill="x", pady=(10, 0))
    if os.path.isdir(CAPTURE_DIR):
        ttk.Button(b, text=T("open_snaps"), command=lambda: open_path(CAPTURE_DIR)).pack(side="left")
    if s["log_path"]:
        ttk.Button(b, text=T("open_log"), command=lambda: open_path(s["log_path"])).pack(side="left", padx=8)
    ttk.Button(b, text=T("close"), command=root.destroy).pack(side="right")
    win.protocol("WM_DELETE_WINDOW", root.destroy)


# ---------------------------------------------------------------- entry point

def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--cleanup-at":
        run_cleanup_at(float(sys.argv[2]))
        return
    set_dpi_aware()
    cfg = load_config()
    cleanup_expired(cfg)  # catch anything whose background cleaner was killed by a restart
    root = tk.Tk()
    pick_fonts(root)
    res_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    try:
        if IS_WIN:
            root.iconbitmap(default=os.path.join(res_dir, "icon.ico"))
        else:
            root.iconphoto(True, tk.PhotoImage(file=os.path.join(res_dir, "icon.png")))
    except tk.TclError:
        pass

    def on_start():
        for child in root.winfo_children():
            child.destroy()
        root.withdraw()
        LockScreen(root, cfg, lambda summary: show_summary(root, summary))

    SettingsWindow(root, cfg, on_start)
    root.mainloop()


if __name__ == "__main__":
    main()

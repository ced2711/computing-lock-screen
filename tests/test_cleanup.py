"""
Tests for snapshot auto-delete: age-based cleanup at startup and the background
process that deletes a session's snapshots when they expire.

    python -m unittest discover tests
"""

import os
import shutil
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lockscreen as ls  # noqa: E402


class CleanupTestCase(unittest.TestCase):
    def setUp(self):
        # a space, an apostrophe and non-ASCII text, to catch quoting mistakes in the shell command
        self.tmp = tempfile.mkdtemp(prefix="lockscreen cleanup ")
        self.captures = os.path.join(self.tmp, "it's 快照")
        os.makedirs(self.captures)
        patcher = mock.patch.object(ls, "CAPTURE_DIR", self.captures)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def snap(self, name, age_hours=0.0):
        path = os.path.join(self.captures, name)
        with open(path, "wb") as f:
            f.write(b"\xff\xd8\xff")
        t = time.time() - age_hours * 3600
        os.utime(path, (t, t))
        return path


class AgeCleanupTests(CleanupTestCase):
    def test_deletes_only_snapshots_older_than_retention(self):
        old = self.snap("20260101_000000_camera.jpg", age_hours=30)
        new = self.snap("20260102_000000_camera.jpg", age_hours=2)
        other = self.snap("notes.txt", age_hours=100)
        self.assertEqual(ls.cleanup_expired({"snapshot_retention_hours": 24}), 1)
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(new))
        self.assertTrue(os.path.exists(other))

    def test_retention_zero_keeps_everything(self):
        old = self.snap("a_camera.jpg", age_hours=1000)
        self.assertEqual(ls.cleanup_expired({"snapshot_retention_hours": 0}), 0)
        self.assertEqual(ls.cleanup_expired({"snapshot_retention_hours": None}), 0)
        self.assertTrue(os.path.exists(old))

    def test_delete_all(self):
        self.snap("a_camera.jpg")
        self.snap("b_camera.JPG", age_hours=5)
        self.assertEqual(ls.delete_snapshots(), 2)
        self.assertEqual(ls.list_snapshots(), [])

    def test_missing_folder_is_fine(self):
        shutil.rmtree(self.captures)
        self.assertEqual(ls.list_snapshots(), [])
        self.assertEqual(ls.cleanup_expired({"snapshot_retention_hours": 24}), 0)


class ScheduledCleanupTests(CleanupTestCase):
    def schedule(self, snaps, seconds):
        proc = ls.schedule_cleanup({"snapshot_retention_hours": seconds / 3600}, snaps)
        self.assertIsNotNone(proc, "cleanup process was not started")
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        return proc

    def test_deletes_session_snapshots_when_they_expire(self):
        mine = [self.snap("20261018_210000_camera.jpg"), self.snap("20261018_210005_camera.jpg")]
        keep = self.snap("from another session_camera.jpg")
        proc = self.schedule(mine, seconds=3)
        time.sleep(1)
        self.assertIsNone(proc.poll(), "cleanup ran before the deadline")
        self.assertTrue(all(os.path.exists(p) for p in mine), "deleted before the deadline")
        self.assertEqual(proc.wait(timeout=60), 0)
        self.assertFalse(any(os.path.exists(p) for p in mine), "snapshots were not deleted")
        self.assertTrue(os.path.exists(keep), "deleted a file that was not part of the session")

    def test_survives_app_exit(self):
        """The cleanup process must not depend on the app: it runs a system shell, not the exe."""
        cmd = ls.cleanup_command([self.snap("x_camera.jpg")], time.time() + 60)
        exe = os.path.basename(cmd[0]).lower()
        self.assertIn(exe, ("powershell.exe", "sh"))
        self.assertNotIn(os.path.abspath(sys.executable).lower(), [c.lower() for c in cmd])

    def test_nothing_scheduled_when_keeping_forever_or_no_snapshots(self):
        snap = self.snap("a_camera.jpg")
        self.assertIsNone(ls.schedule_cleanup({"snapshot_retention_hours": 0}, [snap]))
        self.assertIsNone(ls.schedule_cleanup({"snapshot_retention_hours": 24}, []))
        self.assertIsNone(ls.schedule_cleanup({"snapshot_retention_hours": 24},
                                              [os.path.join(self.captures, "gone.jpg")]))

    def test_pyinstaller_variables_are_not_inherited(self):
        """A child that inherits these believes it is part of the onefile app and shares its
        temporary folder, which made the bootloader fail to remove it on exit."""
        env = {"_PYI_ARCHIVE_FILE": "x", "_PYI_APPLICATION_HOME_DIR": "x",
               "_PYI_PARENT_PROCESS_LEVEL": "1", "_MEIPASS2": "x",
               "LD_LIBRARY_PATH": "/tmp/_MEIabc", "LD_LIBRARY_PATH_ORIG": "/usr/local/lib",
               "PATH": os.environ.get("PATH", "")}
        with mock.patch.dict(os.environ, env, clear=True):
            clean = ls._clean_env()
        self.assertFalse([k for k in clean if k.startswith(("_PYI_", "_MEI"))])
        self.assertEqual(clean["LD_LIBRARY_PATH"], "/usr/local/lib")
        self.assertIn("PATH", clean)


if __name__ == "__main__":
    unittest.main()

"""Tests for lock screen wording: elapsed time and migrating configs off the 1.x defaults."""

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lockscreen as ls  # noqa: E402


class ElapsedTests(unittest.TestCase):
    def test_minutes_and_hours(self):
        with mock.patch.object(ls, "_lang", "en"):
            self.assertEqual(ls.fmt_elapsed(59), "less than a minute")
            self.assertEqual(ls.fmt_elapsed(60), "1 min")
            self.assertEqual(ls.fmt_elapsed(3599), "59 min")
            self.assertEqual(ls.fmt_elapsed(3600), "1 h 0 min")
            self.assertEqual(ls.fmt_elapsed(3 * 3600 + 12 * 60 + 5), "3 h 12 min")


class ConfigMigrationTests(unittest.TestCase):
    def load(self, data):
        path = os.path.join(tempfile.mkdtemp(), "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        with mock.patch.object(ls, "CONFIG_PATH", path):
            return ls.load_config()

    def test_old_defaults_get_new_wording(self):
        cfg = self.load({"language": "zh", "title": "COMPUTING",
                         "subtitle": "DO NOT TOUCH  ·  程序运行中，请勿触碰"})
        self.assertEqual(cfg["title"], ls.STRINGS["zh"]["title_default"])
        self.assertEqual(cfg["subtitle"], ls.STRINGS["zh"]["subtitle"])

    def test_custom_text_is_kept(self):
        cfg = self.load({"title": "Training run #4", "subtitle": "Ask me before touching"})
        self.assertEqual(cfg["title"], "Training run #4")
        self.assertEqual(cfg["subtitle"], "Ask me before touching")


if __name__ == "__main__":
    unittest.main()

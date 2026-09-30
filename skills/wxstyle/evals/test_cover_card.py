"""封面文字卡脚本：尺寸、安全区（转发时裁成中间 1:1 不能切到字）、缺 Pillow 时的提示。"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "make_cover_card.py"

try:
    import PIL  # noqa: F401
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False


def run(*args):
    p = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "PYTHONUTF8": "1"})
    return p.returncode, json.loads(p.stdout or "null")


@unittest.skipUnless(HAVE_PIL, "需要 Pillow")
class CoverCardTests(unittest.TestCase):
    def test_makes_a_900x383_card_and_a_square_preview(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "cover.png"
            code, data = run("--big", "85%", "--small", "官方示例", "--out", str(out))
            self.assertEqual(code, 0)
            self.assertEqual(Image.open(out).size, (900, 383))
            self.assertEqual(Image.open(data["square_preview"]).size, (383, 383))

    def test_big_text_stays_inside_the_square_safe_zone(self):
        with tempfile.TemporaryDirectory() as d:
            code, data = run("--big", "85%", "--out", str(Path(d) / "c.png"))
            self.assertEqual(code, 0)
            self.assertLessEqual(data["big_text_width"], 383 - 2 * 30)

    def test_long_text_is_rejected_not_silently_shrunk_to_nothing(self):
        with tempfile.TemporaryDirectory() as d:
            code, data = run("--big", "这是一段非常非常长的封面文字放不下", "--out", str(Path(d) / "c.png"))
            self.assertEqual(code, 2)
            self.assertIn("error", data)

    def test_rejects_more_than_ten_characters_in_total(self):
        with tempfile.TemporaryDirectory() as d:
            code, data = run("--big", "85%", "--small", "这是官方文档里的一个示例数字", "--out", str(Path(d) / "c.png"))
            self.assertEqual(code, 2)


@unittest.skipUnless(HAVE_PIL, "需要 Pillow")
class CoverBackgroundTests(unittest.TestCase):
    def make_bg(self, d, size=(1536, 1024)):
        from PIL import Image
        p = Path(d) / "bg.png"
        Image.new("RGB", size, (30, 90, 160)).save(p)
        return p

    def test_background_image_is_cropped_to_900x383(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "c.png"
            code, data = run("--bg", str(self.make_bg(d)), "--out", str(out))
            self.assertEqual(code, 0)
            self.assertEqual(Image.open(out).size, (900, 383))
            self.assertEqual(Image.open(data["square_preview"]).size, (383, 383))

    def test_text_is_optional_on_a_background(self):
        with tempfile.TemporaryDirectory() as d:
            code, _ = run("--bg", str(self.make_bg(d)), "--out", str(Path(d) / "c.png"))
            self.assertEqual(code, 0)

    def test_text_on_background_still_respects_limits(self):
        with tempfile.TemporaryDirectory() as d:
            code, _ = run("--bg", str(self.make_bg(d)), "--big", "这是一段非常非常长的封面文字放不下", "--out", str(Path(d) / "c.png"))
            self.assertEqual(code, 2)

    def test_missing_background_file_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            code, data = run("--bg", str(Path(d) / "no.png"), "--out", str(Path(d) / "c.png"))
            self.assertEqual(code, 2)
            self.assertIn("error", data)

    def test_too_small_background_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            code, data = run("--bg", str(self.make_bg(d, (300, 200))), "--out", str(Path(d) / "c.png"))
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()

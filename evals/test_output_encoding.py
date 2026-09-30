"""Every script must print UTF-8 JSON even when PYTHONUTF8 is not set (Windows pipes default to GBK)."""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
ENV = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}


def run_bytes(script, *args):
    p = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, env=ENV)
    return p.stdout, p.stderr, p.returncode


class OutputEncodingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.article = d / "文章.md"
        self.article.write_text("## 章节\n\n这不是升级，而是革命。我亲测了三天，速度提升了300%。\n", encoding="utf-8")
        self.other = d / "参照.md"
        self.other.write_text("这是一篇完全不同的参照文章，用来检查相似度脚本的输出编码。\n", encoding="utf-8")
        self.profile = d / "target_测试号.json"
        self.profile.write_text(json.dumps({"profile_type": "target", "account_name": "测试号", "confidence": "low", "sample_count": 1,
                                            "title": {"formulas": ["判断式：一个很长的说明"]}}, ensure_ascii=False), encoding="utf-8")
        raw = d / "raw"
        raw.mkdir()
        (raw / "a.md").write_text("第一段内容。\n\n第二段内容。\n", encoding="utf-8")
        self.raw = raw
        self.art_dir = d / "文章目录"
        self.art_dir.mkdir()
        (self.art_dir / "article.md").write_text("正文。\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, script, *args):
        out, err, _ = run_bytes(script, *args)
        text = out.decode("utf-8")          # 必须是合法 UTF-8，GBK 输出会在这里失败
        data = json.loads(text)
        self.assertTrue(re.search(r"[一-鿿]", text), f"{script} 的输出里没有中文，测试没有意义")
        self.assertNotIn(b"Traceback", err)
        return data

    def test_ai_tell_check(self):
        self.check("ai_tell_check.py", "--file", self.article)

    def test_check_layout(self):
        self.check("check_layout.py", "--file", self.article)

    def test_claim_check(self):
        self.check("claim_check.py", "--file", self.article)

    def test_similarity_check(self):
        self.check("similarity_check.py", "--generated", self.article, "--reference", self.other)

    def test_validate_profile(self):
        self.check("validate_profile.py", self.profile)

    def test_render_profile_summary(self):
        self.check("render_profile_summary.py", self.profile)

    def test_profile_stats(self):
        self.check("profile_stats.py", "--dir", self.raw)

    def test_check_delivery(self):
        self.check("check_delivery.py", self.art_dir)


if __name__ == "__main__":
    unittest.main()

"""Titles live in review.md, not article.md, so claim_check needs a way to check them too."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "claim_check.py"
ENV = {**os.environ, "PYTHONUTF8": "1"}


def run(*args):
    p = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, encoding="utf-8", env=ENV)
    return json.loads(p.stdout), p.returncode


class TitleCheckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.body = Path(self.tmp.name) / "article.md"
        self.body.write_text("## 章节\n\n这是一段没有问题的正文。\n", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def title_rules(self, *titles):
        args = ["--file", self.body]
        for t in titles:
            args += ["--title", t]
        data, _ = run(*args)
        return {(i["rule"], i.get("source")) for i in data["issues"]}

    def test_extreme_word_in_title(self):
        self.assertIn(("extreme_claim", "title"), self.title_rules("全网最强的AI工具"))

    def test_clickbait_title(self):
        self.assertIn(("clickbait_title", "title"), self.title_rules("震惊！这个AI不看后悔"))

    def test_unattributed_number_in_title(self):
        self.assertIn(("unattributed_number", "title"), self.title_rules("快40倍的AI模型来了"))

    def test_heat_word_in_title(self):
        self.assertIn(("unsupported_heat", "title"), self.title_rules("这个功能刷屏了"))

    def test_attributed_number_in_title_is_fine(self):
        self.assertEqual(self.title_rules("官方称快40倍：Jev是什么"), set())

    def test_clean_titles_pass(self):
        self.assertEqual(self.title_rules("Jev：一个故意不会写字的AI模型", "有个AI模型，故意不会写字"), set())

    def test_titles_are_read_from_review_md_legacy_list_format(self):
        review = Path(self.tmp.name) / "review.md"
        review.write_text("# 审核\n\n## 标题与摘要\n\n标题候选：\n1. 一个正常的标题\n2. 全网最强的AI工具\n3. 另一个正常的标题\n\n摘要：无。\n", encoding="utf-8")
        data, code = run("--file", self.body, "--review", review)
        hits = [(i["rule"], i["text"]) for i in data["issues"] if i.get("source") == "title"]
        self.assertEqual([r for r, _ in hits], ["extreme_claim"])
        self.assertIn("全网最强", hits[0][1])
        self.assertEqual(code, 1)

    def test_titles_are_read_from_the_real_table_template(self):
        # 真实案例：review-checklist-template.md 早就改成表格了，claim_check 的
        # --review 解析器一直没跟上，用真实生成过的 review.md 复现这个问题。
        review = Path(self.tmp.name) / "review.md"
        review.write_text(
            "## 标题\n\n"
            "| 候选标题 | 写法 | 推荐 |\n"
            "|---|---|---|\n"
            "| 一个正常的标题 | 判断式 | 推荐 |\n"
            "| 全网最强的AI工具 | 反差式 | 备选 |\n"
            "| 另一个正常的标题 | 场景式 | 备选 |\n\n"
            "摘要：无。\n", encoding="utf-8")
        data, code = run("--file", self.body, "--review", review)
        hits = [(i["rule"], i["text"]) for i in data["issues"] if i.get("source") == "title"]
        self.assertEqual([r for r, _ in hits], ["extreme_claim"])
        self.assertIn("全网最强", hits[0][1])
        self.assertEqual(code, 1)

    def test_titles_are_read_from_the_full_template_with_more_columns(self):
        # 完整模板版本：候选标题 | 写法 | 为什么会被点 | 风险 | 推荐，以及空白占位行要跳过
        review = Path(self.tmp.name) / "review.md"
        review.write_text(
            "## 标题与封面\n\n"
            "按标题与封面填。标题3—5个，封面一个方案。\n\n"
            "| 候选标题 | 写法 | 为什么会被点 | 风险 | 推荐 |\n"
            "|---|---|---|---|---|\n"
            "| | | | | |\n"
            "| 一个正常的标题 | 判断式 | 有依据 | 无 | 推荐 |\n"
            "| 震惊！这个AI不看后悔 | 标题党 | 太夸张 | 高 | 不推荐 |\n\n"
            "封面方案：无。\n", encoding="utf-8")
        data, code = run("--file", self.body, "--review", review)
        hits = {(i["rule"], i["text"]) for i in data["issues"] if i.get("source") == "title"}
        self.assertIn(("clickbait_title", "震惊！这个AI不看后悔"), hits)

    def test_body_check_is_unchanged_without_title_args(self):
        data, code = run("--file", self.body)
        self.assertEqual((data["issues"], code), ([], 0))


if __name__ == "__main__":
    unittest.main()

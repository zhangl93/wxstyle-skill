"""hot_list.py：解析百度热搜页面里的 s-data 数据块。测试一律用本地样本，不联网。

样本 fixtures/baidu_hot_sample.html 的结构照抄 2026-10-08 的真实页面，条目内容是编的：
一条“视频系 AI 生成”（AI 联系是新闻重点）、一条只顺带提到大模型（不该进候选，但关键词会命中）。
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "hot_list.py"
SAMPLE = ROOT / "evals" / "fixtures" / "baidu_hot_sample.html"


def run(*args):
    p = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, encoding="utf-8")
    return p.returncode, json.loads(p.stdout)


class HotListTests(unittest.TestCase):
    def test_parses_rank_score_and_pinned(self):
        code, d = run("--file", SAMPLE)
        self.assertEqual(code, 0)
        self.assertEqual(d["item_count"], 4)
        pinned, first = d["items"][0], d["items"][1]
        self.assertTrue(pinned["pinned"])
        self.assertIsNone(pinned["rank"])
        self.assertEqual((first["rank"], first["hot_score"]), (1, 8000000))
        self.assertRegex(d["fetched_at"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")
        self.assertRegex(d["page_update_time"], r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$")

    def test_keyword_hit_is_only_a_prefilter(self):
        # 两条都会命中：判断哪条有真正的 AI 角度是模型的事，脚本不替它判断
        code, d = run("--file", SAMPLE)
        hits = [x["word"] for x in d["ai_keyword_hits"]]
        self.assertEqual(hits, ["某景区网传视频系编造", "某车企副业收入破纪录"])
        self.assertIn("初筛", d["note"])

    def test_page_without_data_block_is_an_error_not_an_empty_list(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "verify.html"
            f.write_text("<html><body>请完成安全验证</body></html>", encoding="utf-8")
            code, d = run("--file", f)
            self.assertEqual(code, 2)
            self.assertIn("s-data", d["error"])

    def test_missing_file_is_reported(self):
        code, d = run("--file", "/nonexistent/hot.html")
        self.assertEqual(code, 2)
        self.assertIn("文件不存在", d["error"])


if __name__ == "__main__":
    unittest.main()

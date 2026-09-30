"""Deterministic regression tests for claim_check, check_layout, ai_tell_check, similarity near-duplicates,
profile consistency and profile_stats. Tests only mechanical behavior, not article quality."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import similarity_check as sim


def run(script, *args):
    # Windows 下重定向的子进程默认按 GBK 输出，强制 UTF-8 才能稳定解析 JSON
    p = subprocess.run([sys.executable, str(SCRIPTS / script), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
    return p.returncode, json.loads(p.stdout or "null"), p.stderr


class TempMixin:
    def write(self, name, text):
        p = Path(self.tmp.name) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.tmp.cleanup()


class ClaimCheckTests(TempMixin, unittest.TestCase):
    def rules(self, text, *extra):
        _, data, _ = run("claim_check.py", "--file", self.write("a.md", text), *extra)
        return {i["rule"] for i in data["issues"]}

    def test_fabricated_experience_and_numbers(self):
        pad = "\n\n".join(["过渡。"] * 4)
        got = self.rules("我亲测了三天，效果很稳定。\n\n" + pad + "\n\n速度提升了300%。\n\n" + pad + "\n\n这是全网最强的工具。\n")
        self.assertTrue({"first_person_experience", "unattributed_number", "extreme_claim"} <= got)

    def test_attributed_text_and_hypothetical_examples_are_clean(self):
        got = self.rules("官方称，Jev 快40到200倍。\n\n从文档看，它更适合做判断，不适合写长文。\n\n举一个我编的例子：每天300条工单。\n")
        self.assertEqual(got, set())

    def test_first_person_disclaimers_are_flagged(self):
        # 作者要求：正文不写“我没试过”，既然写了文章就用来源归属的写法
        for s in ("我没有实际用过 Jev，下面是根据资料做的判断。", "先交代一句：我还没试过这个功能。",
                  "本文没有包含我自己的实测。", "我没测过，只能转述官方的说法。"):
            self.assertIn("self_disclaimer", self.rules(s + "\n"), s)

    def test_source_attributed_sentences_are_not_disclaimers(self):
        for s in ("官方文档写的是，网页端要先登录。", "这个数字是官方自测的，还没有独立复现。", "社区里有人测过，条件见下表。"):
            self.assertNotIn("self_disclaimer", self.rules(s + "\n"), s)

    def test_hands_on_flag_suppresses_experience_only(self):
        pad = "\n\n".join(["过渡。"] * 4)
        text = "我亲测了三天。\n\n" + pad + "\n\n速度提升了300%。\n"
        self.assertNotIn("first_person_experience", self.rules(text, "--hands-on"))
        self.assertIn("unattributed_number", self.rules(text, "--hands-on"))

    def test_unsourced_quote_needs_link(self):
        self.assertIn("unsourced_quote", self.rules("评论区有人说：“太强了”。\n"))
        self.assertNotIn("unsourced_quote", self.rules("评论区有人说：“太强了”（[原帖](https://a.com/x)）。\n"))

    def test_promise_on_behalf_of_author_is_pending(self):
        # 行为测试里真实出现过的写法：替作者承诺去测、承诺写下一篇
        for s in ("我挑几个真实需求自己去跑一遍，把花了多少钱都记下来。",
                  "写在留言区，我挑几个常见的，下一篇试着拆成 Jev 的问题。",
                  "我会挑几个拿去试试。"):
            self.assertIn("author_promise", self.rules(s + "\n"), s)

    def test_non_promises_are_clean(self):
        for s in ("官方说会在第四季度支持中文。", "如果你拿到了入口，可以先试三五条工单。", "我没有实际用过 Jev。", "觉得有用，点个关注，我会继续跟进 Jev 的实际用法。"):
            self.assertNotIn("author_promise", self.rules(s + "\n"), s)

    def test_duration_phrases_about_others_are_not_author_experience(self):
        # 真实文章里的误报：写别人或写平台规则的“用了11天”“可以用5到6天”
        for s in ("一个研究团队宣布，Claude AI 用了11天终于完成了证明。", "额度以前每周可以用5到6天，现在只能用2天。"):
            self.assertNotIn("first_person_experience", self.rules(s + "\n"), s)

    def test_duration_phrases_by_the_author_still_count(self):
        for s in ("我用了三天，效果很稳定。", "我自己试用了两周。"):
            self.assertIn("first_person_experience", self.rules(s + "\n"), s)

    def test_long_title_is_flagged_for_truncation(self):
        long = "TypeSafe 发布新模型 Jev：一个只做判断不写字还会告诉你有几成把握的AI到底能用在哪些工作里"
        _, data, _ = run("claim_check.py", "--file", self.write("a.md", "正文。"), "--title", long)
        self.assertIn("title_length", {i["rule"] for i in data["issues"]})
        _, data, _ = run("claim_check.py", "--file", self.write("a.md", "正文。"), "--title", "Jev：一个会说“我有几成把握”的AI")
        self.assertNotIn("title_length", {i["rule"] for i in data["issues"]})

    def test_unsupported_generalization_is_flagged(self):
        # 真实文章里出现的问题：拿一个没有数据支撑的“大多数/很少有”断言给自己的观点撑场面
        for s in ("这份坦诚本身就值得留意——大多数产品发布不会这么写。", "很少有创业公司愿意公开自己的局限。",
                  "没有厂商会主动承认这一点。", "市面上大多数同类产品都不会这么老实。"):
            self.assertIn("unsupported_generalization", self.rules(s + "\n"), s)

    def test_generalization_not_excused_by_unrelated_attribution_earlier_in_sentence(self):
        # 真实文章里的漏网之鱼：同一句前半句提到“官方”是为了别的主张，不能让后半句的断言搭便车免检
        s = "官方主动列出了局限，这份坦诚值得留意——大多数产品发布不会这么写。"
        self.assertIn("unsupported_generalization", self.rules(s + "\n"), s)

    def test_attributed_or_absent_generalizations_are_clean(self):
        for s in ("据一份行业调研，多数产品发布不会披露局限。", "官方在这篇文章里比大多数同行更愿意认错。",
                  "这份坦诚值得留意，我没见过几家同类产品这么写（个人观察，没有统计）。"):
            self.assertNotIn("unsupported_generalization", self.rules(s + "\n"), s)

    def test_missing_file(self):
        code, data, err = run("claim_check.py", "--file", Path(self.tmp.name) / "no.md")
        self.assertEqual(code, 2)
        self.assertNotIn("Traceback", err)


class LayoutTests(TempMixin, unittest.TestCase):
    def rules(self, text):
        _, data, _ = run("check_layout.py", "--file", self.write("a.md", text))
        return {i["rule"] for i in data["issues"]}

    def test_setext_and_html_detected(self):
        got = self.rules("## 章节\n\n文字\n---\n\n<br>正文\n")
        self.assertTrue({"setext_heading", "html_tag"} <= got)

    def test_table_without_outer_pipes_and_hard_break_are_valid(self):
        self.assertEqual(self.rules("## 章节\n\n列一 | 列二\n--- | ---\na | b\n\n第一行  \n第二行\n"), set())

    def test_bom_heading_recognized(self):
        p = Path(self.tmp.name) / "bom.md"
        p.write_bytes("﻿## 标题\n\n正文。\n".encode("utf-8"))
        _, data, _ = run("check_layout.py", "--file", p)
        self.assertEqual(data["stats"]["h2"], 1)

    def test_fill_in_placeholder_is_an_error(self):
        _, data, _ = run("check_layout.py", "--file", self.write("a.md", "## 章节\n\n正文。\n\n【填：你的判断】\n"))
        levels = {i["rule"]: i["level"] for i in data["issues"]}
        self.assertEqual(levels.get("placeholder"), "error")

    def test_bold_punctuation_boundary(self):
        self.assertIn("bold_closing", self.rules("## 章节\n\n这是**重点。**后面\n"))
        self.assertNotIn("bold_closing", self.rules("## 章节\n\n这是**重点**。后面\n"))


class AiTellTests(TempMixin, unittest.TestCase):
    def hits(self, text):
        _, data, _ = run("ai_tell_check.py", "--file", self.write("a.txt", text))
        return data["hit_count"]

    def test_new_families_detected(self):
        # 强信号单独出现就计数；“首先……其次……”是弱信号，规则见 test_ai_tell_tiers.py
        for s in ("在AI飞速发展的今天，机会很多。", "综上所述，值得关注。", "它将赋能千行百业。"):
            self.assertGreaterEqual(self.hits(s), 1, s)

    def test_plain_human_sentences_not_flagged(self):
        self.assertEqual(self.hits("我昨天把配置改了三遍，还是连不上，最后发现是端口被占了。\n"), 0)


class SimilarityNearDuplicateTests(unittest.TestCase):
    def test_every_few_chars_edited_sentence_is_found(self):
        ref = "分布式系统里最难处理的从来不是节点故障本身，而是故障之后各个节点对现状认识不一致。"
        edited = "".join("某" if i % 4 == 3 else c for i, c in enumerate(ref))
        found, total = sim.near_duplicate_sentences(edited, [("r.md", ref)])
        self.assertEqual(total, 1)
        self.assertLess(sim.longest_common_run(sim.normalize(edited), sim.normalize(ref)), 15)

    def test_shared_links_and_urls_are_not_copying(self):
        gen = "参见 [公告](https://openclaw.ai/blog/openclaw-2-accidentally) 了解详情。"
        ref = "本周发布了 [2.0版](https://openclaw.ai/blog/openclaw-2-accidentally)，改动很多。"
        self.assertLess(sim.check_against_reference(gen, ref)["longest_common_run"], 15)

    def test_unrelated_sentences_not_found(self):
        found, total = sim.near_duplicate_sentences("今天下午三点开会讨论下个季度的预算安排和人员调整。",
                                                     [("r.md", "缓存失效之所以困难是因为你很难知道数据什么时候已经过期。")])
        self.assertEqual(total, 0)


class ProfileTests(TempMixin, unittest.TestCase):
    def test_sample_count_vs_raw_cache_and_confidence(self):
        raw = Path(self.tmp.name) / "_raw" / "target_x"
        raw.mkdir(parents=True)
        for i in range(3):
            (raw / f"{i}.md").write_text("样本" * 50, encoding="utf-8")
        prof = self.write("target_x.json", json.dumps({"profile_type": "target", "account_name": "x", "confidence": "high", "sample_count": 25}))
        _, data, _ = run("validate_profile.py", prof)
        self.assertTrue(any("_raw" in w for w in data[0]["warnings"]))   # 计数25，缓存只有3个
        prof = self.write("target_x.json", json.dumps({"profile_type": "target", "account_name": "x", "confidence": "high", "sample_count": 3}))
        _, data, _ = run("validate_profile.py", prof)
        self.assertTrue(any("confidence=high" in w for w in data[0]["warnings"]))   # 3篇不足以标high

    def test_profile_stats_counts_files_and_paragraphs(self):
        d = Path(self.tmp.name) / "raw"
        d.mkdir()
        (d / "a.md").write_text("## 标题\n\n第一段内容。\n\n第二段内容比较长一些。\n", encoding="utf-8")
        (d / "b.md").write_text("只有一段。\n", encoding="utf-8")
        code, data, _ = run("profile_stats.py", "--dir", d)
        self.assertEqual(code, 0)
        self.assertEqual((data["file_count"], data["paragraphs"]), (2, 3))

    def test_summary_is_short(self):
        prof = self.write("p.json", json.dumps({"profile_type": "target", "account_name": "x", "confidence": "low", "sample_count": 2,
            "title": {"formulas": ["判断式：" + "很长的说明" * 30]}, "opening": {"hook_types": ["时事引入（约1/3）：" + "细节" * 50]}}, ensure_ascii=False))
        _, data, _ = run("render_profile_summary.py", prof)
        self.assertLess(len(data["summary"]), 200)


if __name__ == "__main__":
    unittest.main()

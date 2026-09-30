"""Tests for the tiered AI-tell checker: strong vs weak tells, quote skipping, structural tells.
Design borrowed from blader/humanizer's ideas: weak tells count only when clustered; quoted text is left alone."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ai_tell_check.py"


def check(text):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "a.md"
        p.write_text(text, encoding="utf-8")
        r = subprocess.run([sys.executable, str(SCRIPT), "--file", str(p)], capture_output=True, text=True,
                           encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
        return json.loads(r.stdout), r.returncode


def cats(data, key="hits"):
    return [h["category"] for h in data[key]]


class StrongWeakTests(unittest.TestCase):
    def test_strong_tell_counts_alone(self):
        data, code = check("这不是一次升级，而是一场革命。\n")
        self.assertEqual(data["hit_count"], 1)
        self.assertEqual(data["hits"][0]["level"], "strong")
        self.assertEqual(code, 1)

    def test_weak_tell_alone_is_not_counted_but_listed(self):
        data, code = check("首先要看预算，其次要看团队。\n")
        self.assertEqual(data["hit_count"], 0)
        self.assertEqual(cats(data, "weak_alone"), ["enumeration"])
        self.assertEqual(code, 0)

    def test_weak_tells_count_when_they_share_a_passage(self):
        data, _ = check("首先要看预算，其次要看团队。\n\n这套办法能全方位提升效率。\n")
        self.assertGreaterEqual(data["hit_count"], 2)
        self.assertTrue(all(h["level"] == "weak" for h in data["hits"]))

    def test_far_apart_weak_tells_stay_uncounted(self):
        topics = ["天气", "地铁", "早饭", "会议", "邮件", "预算", "排期", "测试", "文档", "账单", "周报", "招聘"]
        filler = "\n".join(f"{t}这件事今天有了新的进展，细节放在后面再说。" for t in topics)
        data, _ = check("首先要看预算，其次要看团队。\n" + filler + "\n这套办法能全方位提升效率。\n")
        self.assertEqual(data["hit_count"], 0)
        self.assertEqual(len(data["weak_alone"]), 2)

    def test_previous_strong_families_still_detected(self):
        for s in ("在AI飞速发展的今天，机会很多。", "综上所述，值得关注。", "它将赋能千行百业。", "总而言之，这很重要。"):
            self.assertGreaterEqual(check(s + "\n")[0]["hit_count"], 1, s)

    def test_plain_human_sentence_not_flagged(self):
        data, _ = check("我昨天把配置改了三遍，还是连不上，最后发现是端口被占了。\n")
        self.assertEqual((data["hit_count"], len(data["weak_alone"])), (0, 0))


class QuoteSkipTests(unittest.TestCase):
    def test_blockquote_lines_are_skipped(self):
        data, _ = check("> 官方称：这不是升级，而是革命。\n")
        self.assertEqual(data["hit_count"], 0)
        self.assertEqual(data["skipped"]["blockquote_lines"], 1)

    def test_text_inside_quotation_marks_is_skipped(self):
        data, _ = check("他说“这不是升级，而是革命”，我不同意。\n")
        self.assertEqual(data["hit_count"], 0)

    def test_same_text_outside_quotes_is_flagged(self):
        data, _ = check("这不是升级，而是革命。他说“不同意”。\n")
        self.assertEqual(data["hit_count"], 1)

    def test_book_title_marks_are_skipped(self):
        data, _ = check("《不是A，而是B》这本书值得一读。\n")
        self.assertEqual(data["hit_count"], 0)

    def test_code_fence_is_skipped(self):
        data, _ = check("```\n这不是升级，而是革命。\n```\n")
        self.assertEqual(data["hit_count"], 0)


class StructureTellTests(unittest.TestCase):
    def test_four_consecutive_paragraphs_with_same_opening_is_strong(self):
        data, _ = check("官方称速度很快。\n\n官方称价格很低。\n\n官方称格式固定。\n\n官方称能并行。\n\n另外还有一点。\n")
        self.assertIn("repeated_openings", cats(data))
        self.assertEqual(data["hits"][0]["level"], "strong")

    def test_three_consecutive_paragraphs_with_same_opening_is_only_weak(self):
        data, _ = check("官方称速度很快。\n\n官方称价格很低。\n\n官方称格式固定。\n\n另外还有一点。\n")
        self.assertEqual(data["hit_count"], 0)
        self.assertIn("repeated_openings", cats(data, "weak_alone"))

    def test_varied_openings_are_fine(self):
        data, _ = check("官方称速度很快。\n\n价格很低。\n\n据教程，格式固定。\n\n另外还有一点。\n")
        self.assertNotIn("repeated_openings", cats(data) + cats(data, "weak_alone"))

    def test_bold_labels_in_a_list(self):
        data, _ = check("- **速度**：很快\n- **价格**：很低\n- **格式**：固定\n")
        self.assertIn("bold_labels", cats(data))

    def test_plain_labels_in_a_list_are_fine(self):
        data, _ = check("- 速度：很快\n- 价格：很低\n- 格式：固定\n")
        self.assertNotIn("bold_labels", cats(data) + cats(data, "weak_alone"))

    def test_every_section_ends_with_a_one_line_closer(self):
        sec = "## {}\n\n第一段写了一些具体的内容，说明了情况。\n\n第二段继续补充数字和条件。\n\n第三段给出限制和例外。\n\n这才是重点。\n\n"
        data, _ = check("".join(sec.format(n) for n in ("甲", "乙", "丙")))
        self.assertIn("one_line_closers", cats(data))

    def test_sections_ending_normally_are_fine(self):
        sec = "## {}\n\n第一段写了一些具体的内容，说明了情况。\n\n第二段继续补充数字和条件，并给出来源和限制说明。\n\n"
        data, _ = check("".join(sec.format(n) for n in ("甲", "乙", "丙")))
        self.assertNotIn("one_line_closers", cats(data) + cats(data, "weak_alone"))

    def test_closer_saying_pattern(self):
        data, _ = check("把判断拆出来，这才是真正的关键。\n")
        self.assertIn("closer_saying", cats(data))

    def test_emoji_heading(self):
        data, _ = check("## 🚀 发布阶段\n\n正文。\n")
        self.assertIn("decorative_headings", cats(data))

    def test_plain_heading_is_fine(self):
        data, _ = check("## 发布阶段\n\n正文写的是别的内容。\n")
        self.assertNotIn("decorative_headings", cats(data) + cats(data, "weak_alone"))

    def test_heading_repeated_in_first_sentence_is_weak(self):
        data, _ = check("## 官方给的数字\n\n官方给的数字有三个，下面逐个说。\n")
        self.assertIn("heading_echo", cats(data, "weak_alone"))
        self.assertEqual(data["hit_count"], 0)


class ChineseAiSayingTests(unittest.TestCase):
    """Patterns found by testing against independently written AI articles (2026-09-21 evaluation)."""

    def test_truly_x_is_y_saying(self):
        data, _ = check("工具终究只是工具。真正决定笔记有没有价值的，是你有没有持续记录的习惯。\n")
        self.assertIn("closer_saying", cats(data))

    def test_truly_without_is_is_fine(self):
        data, _ = check("我真正用过的只有两个软件，其余都是试了一天就卸载。\n")
        self.assertEqual(data["hit_count"], 0)

    def test_better_than_any_feature(self):
        data, _ = check("这一点比任何炫酷功能都重要。\n")
        self.assertIn("comparative_payoff", cats(data))

    def test_bold_lead_paragraphs(self):
        text = "**第一，记录几乎没有门槛。** 打开就是空白页。\n\n**第二，双向链接很克制。** 底部列出谁提到了我。\n\n**第三，本地优先。** 笔记存在自己的设备上。\n"
        data, _ = check(text)
        self.assertIn("bold_labels", cats(data))

    def test_bold_inside_a_sentence_is_fine(self):
        data, _ = check("这个功能叫**回声**，过几天会把旧笔记翻出来。另一个叫**标签**，可以手动加。还有一个叫**链接**。\n")
        self.assertNotIn("bold_labels", cats(data) + cats(data, "weak_alone"))

    def test_sequence_markers_are_weak_alone(self):
        data, _ = check("首先是生态还很年轻。\n\n其次是协作比较弱。\n\n还有就是价格。\n")
        self.assertIn("sequence_markers", cats(data, "weak_alone"))
        self.assertEqual(data["hit_count"], 0)

    def test_ultimately_it_comes_down_to_is_weak(self):
        data, _ = check("说到底，这是一个选择问题。\n")
        self.assertEqual(data["hit_count"], 0)
        self.assertIn("assertive_filler", cats(data, "weak_alone"))


class StockFrameTests(unittest.TestCase):
    """中文公众号AI稿常见的套路框架：各自单独出现只是弱信号，扎堆时才计入。"""

    def all_cats(self, data):
        return cats(data) + cats(data, "weak_alone")

    def test_stock_frames_are_weak(self):
        for s in ("这件事没有统一答案。", "关键看你的使用场景。", "与其纠结要不要买，不如先去试驾。",
                  "想清楚这两个问题，答案自然就出来了。", "最近身边不少朋友都在问这个问题。", "总结一下：适合就好。"):
            data, _ = check(s + "\n")
            self.assertEqual(data["hit_count"], 0, s)
            self.assertIn("stock_frame", cats(data, "weak_alone"), s)

    def test_stock_frames_cluster_and_count(self):
        data, _ = check("最近身边不少朋友都在纠结。其实这件事没有统一答案，关键看你的使用场景。\n")
        self.assertGreaterEqual(data["hit_count"], 1)

    def test_engagement_bait_is_weak(self):
        data, _ = check("你更适合哪一种？欢迎在评论区聊聊你的真实感受。\n")
        self.assertIn("engagement_bait", cats(data, "weak_alone"))

    def test_template_headings(self):
        for h in ("写在最后", "先说结论：没有标准答案", "结语"):
            data, _ = check(f"## {h}\n\n正文一段。\n")
            self.assertIn("template_heading", self.all_cats(data), h)

    def test_ordinary_headings_are_fine(self):
        data, _ = check("## 我的看法\n\n正文一段。\n\n## 怎么试\n\n正文。\n")
        self.assertNotIn("template_heading", self.all_cats(data))

    def test_numbered_paragraph_openings_count_as_sequence(self):
        text = "第一，省下了通勤。\n\n第二，深度工作更容易。\n\n第三，倒逼结果导向。\n"
        self.assertIn("sequence_markers", self.all_cats(check(text)[0]))

    def test_quoted_stock_frame_is_skipped(self):
        data, _ = check("他说“没有统一答案，关键看场景”，我不同意。\n")
        self.assertNotIn("stock_frame", self.all_cats(data))

    def test_ordinary_usage_not_flagged(self):
        data, _ = check("关键词是 confidence，文档第三节讲了它的算法。\n")
        self.assertNotIn("stock_frame", self.all_cats(data))


class ReframeVariantTests(unittest.TestCase):
    """真实案例：用ChatGPT重写Jev文章时，"不是A，是B"被绕过写成"不只是A，而是B"
    "不在于A，而在于B"，原regex只认"不是……是"，这两种变体漏检。"""

    def test_catches_bu_zhi_shi_variant(self):
        data, _ = check("所以很多时候，我们真正想知道的，不只是AI选了什么，而是它自己到底有多确定。\n")
        self.assertIn("reframe", cats(data))

    def test_catches_bu_zai_yu_variant(self):
        data, _ = check("这对企业来说，意义可能不在于让AI全自动做决定，而在于终于可以画出一条线。\n")
        self.assertIn("reframe", cats(data))

    def test_original_bu_shi_shi_pattern_still_works(self):
        data, _ = check("这不是一次升级，而是一场革命。\n")
        self.assertIn("reframe", cats(data))


class FragmentedParagraphsTests(unittest.TestCase):
    """真实案例：ChatGPT重写稿216段、均长19字，几乎每句话独占一段——一种我们
    自己的短段落风格分不清的AI腔调，需要单独识别（不是"段落短"本身的问题，
    是"短到失去意义、大量堆积"）。"""

    def test_many_one_sentence_paragraphs_is_flagged(self):
        # 26个短句各自成段，模拟拆到极致的稿子
        paras = "\n\n".join(f"这是第{i}句独立成段的话。" for i in range(26))
        data, _ = check(paras + "\n")
        self.assertIn("fragmented_paragraphs", cats(data))

    def test_our_own_short_paragraph_style_is_not_flagged(self):
        # 正常的短段落写法：段落短但没有碎到一句一段、数量也不夸张
        text = "\n\n".join([
            "官方给了一个思路：把把握程度分成三档，每档对应不同的做法。",
            "界线画在哪，要看出错的代价。",
            "具体门槛要用自己的数据测，从保守的数字开始。",
            "我的判断是：以后碰到宣称用AI做判断的产品，可以问三件事。",
        ])
        data, _ = check(text + "\n")
        self.assertNotIn("fragmented_paragraphs", cats(data) + cats(data, "weak_alone"))


class HumanizerBorrowedTests(unittest.TestCase):
    """借自 blader/humanizer 的几类：聊天残留、写文章本身、拔高意义、无来源权威、缺具体细节、按作者习惯放行。"""

    def all_cats(self, data):
        return cats(data) + cats(data, "weak_alone")

    def test_chatbot_residue_is_strong(self):
        for s in ("当然可以！以下是为你写好的文章。", "希望这篇文章对你有帮助，如需进一步调整请告诉我。",
                  "作为一个AI，我无法亲自体验这款产品。", "截至我的知识截止日期，这个功能还没有发布。"):
            data, _ = check(s + "\n")
            self.assertIn("chatbot_residue", cats(data), s)

    def test_writing_about_the_document_is_weak(self):
        data, _ = check("本文将从三个方面介绍这个工具。\n")
        self.assertIn("doc_meta", cats(data, "weak_alone"))

    def test_inflated_significance_is_weak(self):
        for s in ("这标志着行业进入了新的篇章。", "数据质量至关重要。", "这为后续发展奠定了坚实基础。"):
            data, _ = check(s + "\n")
            self.assertIn("inflated_significance", self.all_cats(data), s)

    def test_specific_uses_are_not_inflation(self):
        data, _ = check("这个按钮的位置在右上角，点一下就能导出。\n")
        self.assertNotIn("inflated_significance", self.all_cats(data))

    def test_text_without_any_specifics_is_flagged(self):
        para = "很多人都在思考这个问题，答案其实取决于具体的情况和个人的选择，需要综合考虑各种因素，才能做出比较合适的决定。"
        data, _ = check("## 标题\n\n" + "\n\n".join([para] * 14) + "\n")
        self.assertIn("no_specifics", cats(data))

    def test_text_with_numbers_or_asides_is_not_flagged(self):
        para = "我上周用它处理了 37 张发票（都是扫描件），出错 2 张，比我想的好。"
        data, _ = check("## 标题\n\n" + "\n\n".join([para] * 14) + "\n")
        self.assertNotIn("no_specifics", self.all_cats(data))

    def test_short_text_is_not_judged_for_specifics(self):
        data, _ = check("这是一个很短的说明，没有数字。\n")
        self.assertNotIn("no_specifics", self.all_cats(data))

    def test_allow_flag_skips_author_habits(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.md"
            p.write_text("你更适合哪一种？欢迎在评论区聊聊你的真实感受。\n", encoding="utf-8")
            r = subprocess.run([sys.executable, str(SCRIPT), "--file", str(p), "--allow", "engagement_bait"],
                               capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONUTF8": "1"})
            data = json.loads(r.stdout)
            self.assertNotIn("engagement_bait", cats(data) + cats(data, "weak_alone"))
            self.assertEqual(data["allowed"], ["engagement_bait"])


if __name__ == "__main__":
    unittest.main()

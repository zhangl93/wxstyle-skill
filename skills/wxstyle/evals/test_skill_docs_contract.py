"""Contract tests for SKILL.md, the trigger set and the profile schema doc.

Read this before adding another test here: most classes below check that a specific
sentence exists in a specific doc (a "did I remember to write this down" test). That
proves the fix was written, not that a model reading the skill will actually behave
differently — real behavior evidence comes from evals/fixture_benchmark (script-level)
and evals/workflow_cases.json (end-to-end, run manually per workflow-evaluation.md).
A handful of classes here do more than string-matching (ProfileSchemaTests actually
calls validate_profile.py; TriggerSetTests checks the real eval_set.json). When you
add a new class, prefer wiring it to a real script/behavior check over a bare
assertIn if one is available; if it's just documentation-phrasing, that's fine too,
just don't mistake a green run here for "the model will do this."
"""
import json
import re
import subprocess
import sys
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]  # README.md 在仓库根，skill 本体在 skills/wxstyle/ 下
sys.path.insert(0, str(ROOT / "scripts"))
import validate_profile as vp  # noqa: E402


def skill_md():
    return (ROOT / "SKILL.md").read_text(encoding="utf-8")


class SkillMdTests(unittest.TestCase):
    def test_no_wall_of_text_lines(self):
        long = [(i + 1, len(l)) for i, l in enumerate(skill_md().splitlines()) if len(l) > 500]
        self.assertEqual(long, [], "SKILL.md 有过长的行，细节应挪到 references/")

    def test_description_is_scoped_to_wechat_official_accounts(self):
        head = skill_md().split("---")[1]
        desc = re.search(r"description:\s*(.+)", head).group(1)
        self.assertIn("微信公众号", desc)
        self.assertNotIn("图文自媒体", desc)
        self.assertIn("wxstyle-", desc)

    def test_description_covers_plain_wechat_writing(self):
        desc = re.search(r"description:\s*(.+)", skill_md().split("---")[1]).group(1)
        self.assertTrue(desc.startswith("为微信公众号写文章"), "description 应以写公众号文章开头，而不是以画像分析开头")
        self.assertIn("推文", desc)

    def test_final_reply_format_is_defined(self):
        text = skill_md()
        self.assertIn("最终回复", text)
        self.assertIn("最多3个问题", text)
        self.assertIn("一字不差", text)

    def test_default_article_directory_is_defined(self):
        text = skill_md()
        self.assertIn("articles/", text)
        self.assertIn("../wxstyle-articles/", text, "工作目录就是skill目录时要有回退位置")

    def test_routing_table_covers_small_and_edit_requests(self):
        text = skill_md()
        self.assertIn("改稿", text)
        self.assertIn("只要标题", text)

    def test_tool_strategy_has_failure_rules(self):
        text = skill_md()
        for word in ("打不开", "查不到", "冲突", "未运行"):
            self.assertIn(word, text)

    def test_edit_route_forbids_adding_or_dropping_facts(self):
        self.assertIn("不新增原稿没有的事实", skill_md())

    def test_author_habits_can_be_allowed(self):
        self.assertIn("--allow", skill_md())

    def test_profile_naming_avoids_duplicates(self):
        text = skill_md()
        self.assertIn("同一账号", text)
        self.assertIn("公众号后台显示的名称", text)

    def test_definition_of_done_is_a_checklist(self):
        text = skill_md()
        self.assertIn("## 完成标准", text)
        self.assertGreaterEqual(text.split("## 完成标准")[1].count("- [ ]"), 6)

    def test_check_details_live_in_references(self):
        self.assertTrue((ROOT / "references" / "checks.md").exists())
        self.assertIn("references/checks.md", skill_md())


class TriggerSetTests(unittest.TestCase):
    def setUp(self):
        self.items = json.loads((ROOT / "evals" / "eval_set.json").read_text(encoding="utf-8"))

    def test_size_and_balance(self):
        self.assertGreaterEqual(len(self.items), 30)
        self.assertGreaterEqual(sum(1 for x in self.items if x["should_trigger"]), 12)
        self.assertGreaterEqual(sum(1 for x in self.items if not x["should_trigger"]), 12)

    def test_covers_current_main_uses(self):
        text = "\n".join(x["query"] for x in self.items if x["should_trigger"])
        for word in ("标题", "画像", "核对", "AI味", "评论"):
            self.assertIn(word, text, f"触发集缺少“{word}”相关的请求")

    def test_other_platforms_are_negative(self):
        xhs = [x for x in self.items if "小红书" in x["query"]]
        self.assertTrue(xhs)
        self.assertTrue(all(not x["should_trigger"] for x in xhs))


class ProfileSchemaTests(unittest.TestCase):
    def run_validate(self, profile):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "target_x.json"
            p.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_profile.py"), str(p)], capture_output=True,
                               env={**os.environ, "PYTHONUTF8": "1"})
            return json.loads(r.stdout.decode("utf-8"))[0]

    base = {"profile_type": "target", "account_name": "x", "confidence": "low", "sample_count": 1}

    def test_unknown_top_level_key_warns_but_stays_valid(self):
        r = self.run_validate({**self.base, "my_own_field": 1})
        self.assertTrue(r["valid"])
        self.assertTrue(any("my_own_field" in w for w in r["warnings"]))

    def test_documented_optional_keys_do_not_warn(self):
        r = self.run_validate({**self.base, "notes": ["备注"], "observation_basis": {"scope": "x"}, "non_transferable_identity": ["自称"]})
        self.assertFalse([w for w in r["warnings"] if "字段" in w])

    def test_every_allowed_key_is_documented_in_the_schema(self):
        doc = (ROOT / "references" / "style-profile-schema.md").read_text(encoding="utf-8")
        missing = [k for k in vp.ALLOWED_TOP_LEVEL_KEYS if k not in doc]
        self.assertEqual(missing, [])

    def test_real_profiles_have_no_unknown_field_warnings(self):
        paths = sorted((ROOT / "profiles").glob("*.json"))
        self.assertTrue(paths)
        for p in paths:
            r = subprocess.run([sys.executable, str(ROOT / "scripts" / "validate_profile.py"), str(p)], capture_output=True,
                               env={**os.environ, "PYTHONUTF8": "1"})
            data = json.loads(r.stdout.decode("utf-8"))[0]
            self.assertFalse([w for w in data["warnings"] if "字段" in w], f"{p.name}: {data['warnings']}")


class WorkflowCaseFileTests(unittest.TestCase):
    def test_cases_are_well_formed_and_portable(self):
        cases = json.loads((ROOT / "evals" / "workflow_cases.json").read_text(encoding="utf-8"))
        ids = [c["id"] for c in cases]
        self.assertEqual(len(ids), len(set(ids)), "用例 id 重复")
        self.assertGreaterEqual(len(cases), 20)
        for c in cases:
            self.assertTrue(c["request"].strip() and c["criteria"], c["id"])
            self.assertNotIn("D:\\", c["request"], f"{c['id']} 的请求里有本机绝对路径")


class EngagementGuidanceTests(unittest.TestCase):
    def doc(self):
        return (ROOT / "references" / "engagement.md").read_text(encoding="utf-8")

    def test_skill_links_the_guidance_from_the_writing_flow(self):
        text = skill_md()
        self.assertIn("references/engagement.md", text)
        self.assertIn("结尾问题", text)

    def test_guidance_has_criteria_and_examples(self):
        d = self.doc()
        for word in ("好回答", "自己的经历", "不问表态", "差：", "好："):
            self.assertIn(word, d)

    def test_guidance_does_not_promise_on_behalf_of_the_author(self):
        d = self.doc()
        self.assertIn("不替作者承诺", d)
        self.assertIn("回复留言", d)

    def test_review_template_has_a_comment_question_section(self):
        tpl = (ROOT / "references" / "review-checklist-template.md").read_text(encoding="utf-8")
        self.assertIn("## 留言问题", tpl)

    def test_guidance_is_linked_from_readme(self):
        self.assertIn("engagement", (REPO_ROOT / "README.md").read_text(encoding="utf-8"))


class StructuralPriorityTests(unittest.TestCase):
    """来自2026-09-30的读者反馈：文章证据和局限堆在前面，读完拼不出“这是什么”。"""

    def test_editorial_checks_tells_writers_to_lead_with_what_it_is(self):
        d = (ROOT / "references" / "editorial-checks.md").read_text(encoding="utf-8")
        self.assertIn("先让读者看懂", d)
        self.assertIn("一句话说出", d)

    def test_editorial_checks_tells_writers_to_pick_relatable_examples_first(self):
        d = (ROOT / "references" / "editorial-checks.md").read_text(encoding="utf-8")
        self.assertIn("最贴近读者处境", d)


class CaveatScopeAndListCountTests(unittest.TestCase):
    """来自2026-09-30对Jev文章的独立复核：引用官方自我保留时要看清它针对哪些主张，
    压缩官方编号列表时“共X条”的计数要点数确认覆盖。"""

    # 1.11.0 起两条都从 SKILL.md 挪到 editorial-checks.md（只来自一次事故，不必每次全文读）
    def editorial(self):
        return (ROOT / "references" / "editorial-checks.md").read_text(encoding="utf-8")

    def test_editorial_checks_warns_about_caveat_scope(self):
        text = self.editorial()
        self.assertIn("自我保留", text)
        self.assertIn("针对文中的哪些具体主张", text)

    def test_editorial_checks_warns_about_list_count_claims(self):
        self.assertIn("共X条", self.editorial())


class NoPlaceholderNoDisclaimerTests(unittest.TestCase):
    """作者要求：正文不留【填】占位，没数据就删段；正文不写“我没试过”，也不编“我试了”。"""

    def test_skill_no_longer_tells_writers_to_leave_fill_in_placeholders(self):
        text = skill_md()
        self.assertNotIn("用 `【填", text)
        self.assertNotIn("并列进待办", text)
        self.assertIn("正文里不留 `【填：…】`", text)
        self.assertIn("没有数据就删掉这段", text)

    def test_skill_bans_first_person_disclaimers_but_keeps_the_no_fabrication_rule(self):
        text = skill_md()
        self.assertIn("不写“我没用过”“我没试过”", text)
        self.assertIn("只有作者给了记录才能写“我测了”", text)

    def test_source_voice_is_explained(self):
        # 唯一权威版本在 SKILL.md（1.6.0起）；evidence-and-delivery.md 不再重复一份
        d = skill_md()
        self.assertIn("来源归属", d)
        self.assertIn("官方文档写的是", d)

    def test_done_checklist_requires_no_placeholder_left(self):
        done = skill_md().split("## 完成标准")[1]
        self.assertIn("没有 `【填", done)


class ReaderPsychologyTests(unittest.TestCase):
    """有选择地借用认知心理学：能让文章更好懂、更好记的原理采用并点名依据；
    能提高转化但要靠误导才有效的技巧（虚假社会认同、损失厌恶恐吓、稀缺话术）明确列为不用。"""

    def doc(self):
        return (ROOT / "references" / "editorial-checks.md").read_text(encoding="utf-8")

    def test_adopts_named_cognitive_principles(self):
        d = self.doc()
        for word in ("工作记忆", "峰终", "锚定"):
            self.assertIn(word, d)

    def test_explicitly_rejects_manipulative_techniques(self):
        d = self.doc()
        self.assertIn("不用的心理", d)
        for word in ("虚假的社会认同", "损失厌恶", "稀缺"):
            self.assertIn(word, d)

    def test_anchor_effect_is_tied_to_the_existing_sourcing_rule(self):
        # 锚定效应本身是中性的，锚点必须来自有来源的真实数字，不能是编的
        d = self.doc()
        self.assertIn("锚点", d)
        self.assertIn("来源", d)

    def test_analogy_guidance_requires_a_follow_up_precise_statement(self):
        # 类比能降低理解门槛，但类比是简化：给完类比要接准确说法，不能让类比替代机制解释
        d = self.doc()
        self.assertIn("类比", d)
        self.assertIn("简化", d)

    def test_topic_framing_favors_reader_impact_over_feature_list(self):
        # 选题和角度要写"这对读者的工作意味着什么"，不是单纯的产品能力清单
        d = self.doc()
        self.assertIn("对读者", d)
        self.assertIn("功能清单", d)

    def test_empathetic_opening_is_bounded_against_fabricated_anxiety(self):
        # 开头可以先说读者正在经历的真实处境，但不能是编出来的焦虑，且不能滑向已禁止的恐吓话术
        d = self.doc()
        self.assertIn("读者正在经历", d)
        self.assertIn("不是编出来的", d)

    def test_narrative_case_structure_is_bounded_to_real_material(self):
        # 叙事结构（遇到问题→旧办法→引入AI→踩坑→调整→结果）只用在真实案例上，没有真实材料不能为了叙事编一个人的故事
        d = self.doc()
        self.assertIn("踩坑", d)
        self.assertIn("不为了叙事", d)


class AiTellRuleDocsSyncTests(unittest.TestCase):
    """和 claim_check 那条同步测试对称：ai_tell_check.py 的26个类别现在也逐条
    列进了 checks.md，防止以后加新类别时又只改脚本、忘了改文档。"""

    def test_every_category_in_the_script_is_listed_in_checks_md(self):
        script = (ROOT / "scripts" / "ai_tell_check.py").read_text(encoding="utf-8")
        m = re.search(r"CATEGORY_LABELS = \{(.*?)\n\}", script, re.S)
        names = re.findall(r'"([a-z_]+)":', m.group(1))
        self.assertGreaterEqual(len(names), 20, "没解析到类别名，先检查 CATEGORY_LABELS 的写法")
        checks_doc = (ROOT / "references" / "checks.md").read_text(encoding="utf-8")
        missing = [n for n in names if n not in checks_doc]
        self.assertEqual(missing, [], f"ai_tell_check.py 里有但 checks.md 没提到的类别：{missing}")


class ClaimCheckRuleDocsSyncTests(unittest.TestCase):
    """真实发生过：claim_check.py 加了 unsupported_generalization 规则，
    脚本docstring里写了，但 checks.md 给用户/模型看的说明里忘了提，
    两处对不上，人读 checks.md 不会知道这条规则存在。"""

    def test_every_rule_in_the_script_docstring_is_mentioned_in_checks_md(self):
        script = (ROOT / "scripts" / "claim_check.py").read_text(encoding="utf-8")
        rule_names = re.findall(r"^- ([a-z_]+)：", script, re.MULTILINE)
        self.assertGreaterEqual(len(rule_names), 5, "没从docstring里解析到规则名，先检查脚本注释格式")
        checks_doc = (ROOT / "references" / "checks.md").read_text(encoding="utf-8")
        missing = [r for r in rule_names if r not in checks_doc]
        self.assertEqual(missing, [], f"claim_check.py 里写了但 checks.md 没提到的规则：{missing}")


class ChecklistHierarchyTests(unittest.TestCase):
    """四张清单（证据规则表/完成标准/内容与素材/改稿回归）本来各自重复定义同一批规则；
    现在明确证据规则表是唯一权威，其余三处只做"再查一遍"，不重新定义。"""

    def test_completion_checklist_points_to_the_evidence_table(self):
        self.assertIn("唯一权威定义是上面的「证据规则」表", skill_md())

    def test_review_checklist_points_to_skill_md(self):
        d = (ROOT / "references" / "review-checklist-template.md").read_text(encoding="utf-8")
        self.assertIn("权威定义在 SKILL.md「证据规则」", d)

    def test_editorial_checks_points_to_skill_md(self):
        d = (ROOT / "references" / "editorial-checks.md").read_text(encoding="utf-8")
        self.assertIn("权威定义在 SKILL.md「证据规则」", d)


class ClaimCategoryConsistencyTests(unittest.TestCase):
    """SKILL.md的证据规则表是主张类别的唯一权威列表；evidence-and-delivery.md
    曾经重复列了一份不完整、不同步的类别子集，容易和主表脱节。"""

    def test_evidence_and_delivery_points_to_skill_md_instead_of_relisting_categories(self):
        d = (ROOT / "references" / "evidence-and-delivery.md").read_text(encoding="utf-8")
        self.assertNotRegex(d, r"官方主张、可核验事实、社区自述、作者实测、推断")
        self.assertIn("SKILL.md", d)


class LowEvidenceLabelTests(unittest.TestCase):
    """低验证内容要在文档开头明说验证次数，提醒以后的自己别在没有新证据前继续扩展。"""

    def test_low_evidence_docs_are_labeled(self):
        for name in ("explainer-structure.md", "cover-testing.md"):
            d = (ROOT / "references" / name).read_text(encoding="utf-8")
            self.assertIn("验证次数", d, name)
            self.assertIn("不要在没有新证据前继续扩展", d, name)


class ExplainerStructureTests(unittest.TestCase):
    """用户提议的固定六段结构（问题→反常识判断→案例→原理→边界→行动）：
    作为机制讲解类文章的可选参考采纳，不作为强制模板，且两处最容易导致造假的环节
    （反常识判断、具体案例）要有明确的证据门槛。"""

    def doc(self):
        return (ROOT / "references" / "explainer-structure.md").read_text(encoding="utf-8")

    def test_is_scoped_to_one_article_type_not_mandatory_for_all(self):
        text = skill_md()
        self.assertIn("references/explainer-structure.md", text)
        d = self.doc()
        self.assertIn("不是所有文章", d)
        self.assertIn("机制", d)

    def test_counterintuitive_judgment_requires_real_support(self):
        d = self.doc()
        self.assertIn("反常识", d)
        self.assertIn("证据只支持一个平常的判断", d)

    def test_concrete_case_step_forbids_fabrication_when_no_material(self):
        d = self.doc()
        self.assertIn("没有真实材料", d)
        self.assertIn("不能为了填这一步", d)

    def test_keeps_the_mnemonic_for_memorability(self):
        d = self.doc()
        self.assertIn("标题卖问题", d)
        self.assertIn("案例卖可信度", d)


class CoverToolPathTests(unittest.TestCase):
    """tools-guide.md 在 1.11.0 删掉了（验证次数低），唯一验证过的路径并进了 title-and-cover.md。"""

    def test_verified_cover_path_kept_in_title_and_cover(self):
        d = (ROOT / "references" / "title-and-cover.md").read_text(encoding="utf-8")
        for word in ("ChatGPT", "make_cover_card.py", "唯一真正验证过的路径", "只在一个工具里改"):
            self.assertIn(word, d)


class CoverRealSceneTests(unittest.TestCase):
    """1.15.0：作者要求生图提示词尽量在真实场景中构图，不默认用抽象的编辑示意图。"""

    def test_prompt_template_asks_for_a_real_scene(self):
        d = (ROOT / "references" / "title-and-cover.md").read_text(encoding="utf-8")
        self.assertIn("生图先从真实场景构图", d)
        self.assertIn("场景：[", d)
        self.assertIn("要有人在做事", d)


class ReviewAndDeliveryLoopTests(unittest.TestCase):
    """1.11.0：三篇文章每篇都要作者另外喊“审查”才查出 6—8 处错，错误集中在限定词、术语翻译、
    范围说法和网页总结；三篇都没封面图、交付后也没写回画像。"""

    def test_claim_table_has_original_wording_column(self):
        self.assertIn("原文措辞", skill_md())
        tpl = (ROOT / "references" / "review-checklist-template.md").read_text(encoding="utf-8")
        self.assertIn("| 主张 | 类别 | 来源 | 原文措辞 |", tpl)

    def test_self_review_checks_the_four_recurring_error_types(self):
        text = skill_md()
        for word in ("限定词", "术语译得对不对", "范围说法", "网页总结"):
            self.assertIn(word, text)

    def test_delivery_writes_back_to_self_profile(self):
        text = skill_md()
        self.assertIn("写回画像", text)
        self.assertIn("article_history", text)

    def test_publish_data_has_a_route(self):
        self.assertIn("记一下数据", skill_md())
        self.assertIn("performance_log", skill_md())

    def test_cover_has_a_text_card_fallback(self):
        text = skill_md()
        self.assertIn("封面保底", text)
        self.assertIn("cover-card.png", text)


class CoverPromptTests(unittest.TestCase):
    def test_review_template_asks_for_cover_prompt(self):
        tpl = (ROOT / "references" / "review-checklist-template.md").read_text(encoding="utf-8")
        self.assertIn("封面提示词", tpl)


class TitleAndCoverGuidanceTests(unittest.TestCase):
    def doc(self):
        return (ROOT / "references" / "title-and-cover.md").read_text(encoding="utf-8")

    def test_skill_links_it_and_shows_the_title_in_the_reply(self):
        text = skill_md()
        self.assertIn("references/title-and-cover.md", text)
        self.assertRegex(text, r"推荐标题")

    def test_title_guidance_has_tests_and_forbidden_moves(self):
        d = self.doc()
        for word in ("对谁", "得到什么", "为什么可信", "标题党", "截断", "差：", "好："):
            self.assertIn(word, d)

    def test_review_template_has_title_and_cover_section(self):
        tpl = (ROOT / "references" / "review-checklist-template.md").read_text(encoding="utf-8")
        self.assertIn("## 标题与封面", tpl)


if __name__ == "__main__":
    unittest.main()

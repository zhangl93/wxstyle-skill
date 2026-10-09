"""Deterministic regression tests, not an editorial-quality evaluation."""
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import similarity_check as sim
import check_delivery as delivery
import validate_profile as profiles


def brute(a, b):
    best = 0
    for i in range(len(a)):
        for j in range(len(b)):
            k = 0
            while i+k < len(a) and j+k < len(b) and a[i+k] == b[j+k]:
                k += 1
            best = max(best, k)
    return best


class SimilarityTests(unittest.TestCase):
    def test_tail_beyond_old_limit(self):
        phrase = "sharedtailaftereightthousand"
        result = sim.check_against_reference("a"*9000+phrase, "b"*9000+phrase)
        self.assertEqual(result["longest_common_run"], len(phrase))
        self.assertEqual(result["generated_match"]["start_offset"], 9000)

    def test_exact_match_against_independent_oracle(self):
        rng = random.Random(41)
        for _ in range(120):
            a = "".join(rng.choices("abcde", k=rng.randrange(30)))
            b = "".join(rng.choices("abcde", k=rng.randrange(30)))
            size, ai, bi = sim.longest_match(a, b)
            self.assertEqual(size, brute(a, b))
            if size:
                self.assertEqual(a[ai:ai+size], b[bi:bi+size])

    def test_offsets_after_normalization(self):
        result = sim.check_against_reference("头\n相 同，文字", "相同文字")
        self.assertEqual(result["longest_common_run"], 4)
        self.assertEqual(result["generated_match"]["start_line"], 2)
        self.assertEqual(result["generated_match"]["excerpt"], "相 同，文字")

    def test_empty_reference_rejected(self):
        with self.assertRaises(ValueError):
            sim.check_against_reference("valid article", "，！\n")

    def test_recursive_scan_and_invalid_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            article = root / "article.md"
            article.write_text("abcdefghijklmno", encoding="utf-8")
            refs = root / "refs"
            (refs / "nested").mkdir(parents=True)
            (refs / "nested" / "ref.md").write_text("abcdefghijklmno", encoding="utf-8")
            result = sim.audit(article, refs)
            self.assertEqual(result["valid_reference_count"], 1)
            self.assertFalse(result["passed_run_check"])
            (refs / "empty.txt").write_text("", encoding="utf-8")
            result = sim.audit(article, refs)
            self.assertFalse(result["inspection_complete"])
            self.assertFalse(result["overall_pass"])
            self.assertIsNone(result["passed_run_check"])

    def test_empty_directory_not_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            article = root / "article.md"
            article.write_text("some text", encoding="utf-8")
            result = sim.audit(article, root)
            self.assertEqual(result["valid_reference_count"], 0)
            self.assertFalse(result["overall_pass"])


CLAIMS_OK = "## 主张表\n\n| 主张 | 类别 |\n|---|---|\n| 某数字 | 官方主张 |\n"
REVIEW_OK = ("## 独立审查\n\n| 问题 | 级别 | 原文依据 | 处理 |\n|---|---|---|---|\n"
             "| 漏了限定 | 必须改 | 原句 | 已改 |\n\n" + CLAIMS_OK)


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.article = self.root / "article.md"
        self.article.write_text("# Title\n\nArticle.", encoding="utf-8")
        (self.root / "images").mkdir()
        (self.root / "images" / "cover-card.png").write_bytes(b"cover")
        self.review = self.root / "review.md"
        self.review.write_text(REVIEW_OK, encoding="utf-8")
        digest = delivery.file_hash(self.article)
        self.data = {"article_type": "introduction", "text_status": "complete", "visual_status": "not_requested",
                     "review_status": "complete", "article_sha256": digest, "reviewed_article_sha256": digest,
                     "assets": [], "pending_items": []}

    def run_audit(self):
        (self.root / "delivery.json").write_text(json.dumps(self.data), encoding="utf-8")
        return delivery.audit(self.root)

    def test_complete_text_then_stale_revision(self):
        self.assertTrue(self.run_audit()["ready_for_delivery"])
        self.article.write_text("# Changed\nChanged content", encoding="utf-8")
        self.assertFalse(self.run_audit()["structural_pass"])

    def test_missing_visual_is_not_delivery_complete(self):
        self.data.update(visual_status="pending", pending_items=["capture screenshot"], assets=[
            {"id": "home", "kind": "official_screenshot", "status": "pending", "purpose": "product identity", "note": "browser unavailable"}])
        result = self.run_audit()
        self.assertTrue(result["structural_pass"])
        self.assertFalse(result["ready_for_delivery"])

    def test_actual_image_and_manifest(self):
        # File existence is the invariant; this checker deliberately does not decode images.
        (self.root / "image.png").write_bytes(b"test-asset")
        self.article.write_text("# Article\n![example](image.png)", encoding="utf-8")
        digest = delivery.file_hash(self.article)
        self.data.update(visual_status="complete", article_sha256=digest, reviewed_article_sha256=digest,
                         assets=[{"id": "img", "status": "ready", "kind": "official_screenshot", "path": "image.png",
                                  "purpose": "identity", "source_url": "https://example.com"}])
        self.assertTrue(self.run_audit()["ready_for_delivery"])
        (self.root / "image.png").unlink()
        self.assertFalse(self.run_audit()["structural_pass"])

    def test_stale_review_even_when_delivery_hash_updated(self):
        self.article.write_text("# New content", encoding="utf-8")
        self.data["article_sha256"] = delivery.file_hash(self.article)
        self.assertFalse(self.run_audit()["structural_pass"])

    def test_remote_or_reference_style_not_silently_accepted(self):
        for markup in ("![remote](https://example.com/a.png)", "![ref][image]\n[image]: image.png", '<img src="image.png">'):
            self.article.write_text(markup, encoding="utf-8")
            self.data.update(article_sha256=delivery.file_hash(self.article), reviewed_article_sha256=delivery.file_hash(self.article))
            self.assertFalse(self.run_audit()["structural_pass"])


    def test_missing_cover_blocks_ready_but_not_structure(self):
        (self.root / "images" / "cover-card.png").unlink()
        (self.root / "images" / "_cover-card-square-preview.png").write_bytes(b"preview")
        (self.root / "images" / "cover-raw.png").write_bytes(b"uncropped generated image")
        result = self.run_audit()
        self.assertTrue(result["structural_pass"])
        self.assertFalse(result["ready_for_delivery"])
        self.assertIsNone(result["cover"])
        self.assertTrue(any("封面" in w for w in result["warnings"]))

    def test_missing_independent_review_blocks_ready(self):
        self.review.write_text(CLAIMS_OK, encoding="utf-8")
        result = self.run_audit()
        self.assertTrue(result["structural_pass"])
        self.assertFalse(result["ready_for_delivery"])
        self.assertTrue(any("独立审查" in w for w in result["warnings"]))

    def test_empty_review_table_or_claim_table_blocks_ready(self):
        self.review.write_text("## 独立审查\n\n| 问题 | 级别 |\n|---|---|\n| | |\n\n## 主张表\n\n| 主张 | 类别 |\n|---|---|\n",
                               encoding="utf-8")
        warnings = self.run_audit()["warnings"]
        self.assertTrue(any("独立审查" in w and "空" in w for w in warnings))
        self.assertTrue(any("主张表" in w for w in warnings))

    def test_reused_review_note_counts(self):
        self.review.write_text("## 独立审查\n\n改动未涉及事实，沿用上次独立审查。\n\n" + CLAIMS_OK, encoding="utf-8")
        self.assertTrue(self.run_audit()["ready_for_delivery"])

    def audit_with_profile(self, status):
        rows = [{"article_id": self.root.resolve().name, "updated_at": "2026-10-09", "hook": "h", "status": status}] if status else []
        path = self.root / "self.json"
        path.write_text(json.dumps({"self_only_fields": {"article_history": rows}}), encoding="utf-8")
        (self.root / "delivery.json").write_text(json.dumps(self.data), encoding="utf-8")
        return delivery.audit(self.root, path)

    def test_profile_write_back_is_checked_when_given(self):
        self.assertTrue(self.audit_with_profile("delivered")["ready_for_delivery"])
        draft = self.audit_with_profile("draft")
        self.assertFalse(draft["ready_for_delivery"])
        self.assertFalse(draft["profile_written_back"])
        missing = self.audit_with_profile(None)
        self.assertFalse(missing["ready_for_delivery"])
        self.assertTrue(any("article_history" in w for w in missing["warnings"]))

    def test_profile_not_checked_without_flag(self):
        self.assertIsNone(self.run_audit()["profile_written_back"])


class ProfileAndPhraseTests(unittest.TestCase):
    def test_same_hook_different_articles_allowed_duplicate_id_rejected(self):
        rows = [{"article_id": str(i), "updated_at": "2026-09-20", "hook": "same", "status": "draft"} for i in range(3)]
        data = {"profile_type": "self", "account_name": "author", "confidence": "bootstrap", "sample_count": 0,
                "self_only_fields": {"article_history": rows}}
        self.assertEqual(profiles.validate(data), [])
        rows[1]["article_id"] = "0"
        self.assertTrue(profiles.validate(data))

    def test_old_dual_hook_paths_rejected(self):
        data = {"profile_type": "self", "account_name": "author", "confidence": "bootstrap", "sample_count": 0,
                "recent_hook_types": [], "self_only_fields": {"recent_hook_types": []}}
        self.assertTrue(profiles.validate(data))

    def test_phrase_precheck_does_not_approve_editorial_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            article = Path(tmp) / "article.md"
            article.write_text("A bland repetitive paragraph. "*20, encoding="utf-8")
            run = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/ai_tell_check.py"), "--file", str(article)], capture_output=True, encoding="utf-8")
            self.assertEqual(run.returncode, 0)
            result = json.loads(run.stdout)
            self.assertTrue(result["editorial_review_required"])
            self.assertNotIn("overall_pass", result)


if __name__ == "__main__":
    unittest.main()

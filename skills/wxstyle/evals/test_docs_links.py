"""Docs must not point at files or scripts that do not exist, and must say where paths start."""
import re
import unittest
from pathlib import Path

# 仓库布局：<repo>/README.md 等给人看的文档在根目录，skill 本体在 skills/wxstyle/ 下
# （方便 `npx skills add` 这类跨 agent 安装工具按约定找到它）。ROOT 指 skill 本体，
# REPO_ROOT 指仓库根——两者分开是因为 README.md 引用 SKILL.md 等文件时，
# 路径要从 REPO_ROOT 算，而 SKILL.md 引用 references/ 时路径要从 ROOT 算。
ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]


class DocsTests(unittest.TestCase):
    def read(self, name, root=ROOT):
        return (root / name).read_text(encoding="utf-8")

    def test_markdown_links_in_docs_resolve(self):
        docs_with_root = [("skills/wxstyle/SKILL.md", REPO_ROOT), ("README.md", REPO_ROOT)]
        docs_with_root += [(f"references/{p.name}", ROOT) for p in (ROOT / "references").glob("*.md")]
        for doc, root in docs_with_root:
            base = (root / doc).parent
            for target in re.findall(r"\]\(([^)#\s]+\.md)\)", self.read(doc, root)):
                if target.startswith("http"):
                    continue
                self.assertTrue((base / target).exists(), f"{doc} 链接到不存在的 {target}")

    def test_scripts_named_in_docs_exist(self):
        for doc, root in [("skills/wxstyle/SKILL.md", REPO_ROOT), ("README.md", REPO_ROOT)]:
            text = self.read(doc, root)
            for script in set(re.findall(r"scripts/([a-z_]+\.py)", text)) | set(re.findall(r"`([a-z_]+\.py)`", text)):
                if script.startswith("package_") or script in ("run_loop.py",):
                    continue
                self.assertTrue((ROOT / "scripts" / script).exists(), f"{doc} 提到不存在的脚本 {script}")

    def test_skill_md_says_paths_start_at_the_skill_directory(self):
        text = self.read("SKILL.md")
        self.assertIn("基准目录", text)

    def test_skill_md_stays_lean(self):
        self.assertLess(len(self.read("SKILL.md").splitlines()), 150)

    def test_every_reference_file_is_linked_from_somewhere(self):
        # 孤儿文档：没人指路，模型永远不会去读它。真实发生过：imagegen-prompt-template.md
        # 曾经从 SKILL.md 里被拿掉链接，但文件本身留着，16行说明谁都读不到。
        # 链接写法有两种：SKILL.md 里用 references/xxx.md；references/ 内部互相链接省略前缀，直接 xxx.md。
        docs = ["SKILL.md", *[f"references/{p.name}" for p in (ROOT / "references").glob("*.md")]]
        link_targets = set()
        for d in docs:
            link_targets |= set(re.findall(r"\]\(([^)#\s]+\.md)\)", self.read(d)))
        for ref in (ROOT / "references").glob("*.md"):
            self.assertTrue(f"references/{ref.name}" in link_targets or ref.name in link_targets,
                             f"{ref.name} 没有被任何文档链接，是孤儿文件")


if __name__ == "__main__":
    unittest.main()

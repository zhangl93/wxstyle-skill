# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`wxstyle` is an agent skill (Claude Code / Codex) for writing WeChat Official Account (微信公众号) articles: build style profiles from benchmark accounts, write in the author's own voice, fact-check, pick real images, convert layout, and review before the author publishes by hand. There is no app to build. The "product" is the prompt docs plus a set of stdlib-only Python check scripts. Docs, code comments and commit history are in Chinese, so match that when editing them.

Layout follows the `npx skills add` convention:
- Repo root (`README.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `LICENSE`, `examples/`) is for humans.
- `skills/wxstyle/` is the skill itself. `SKILL.md` is the entry point the model reads. `references/*.md` are loaded on demand from links in SKILL.md and are written for the model, not as human architecture docs. `scripts/` holds the mechanical checks. `profiles/` holds style profiles. `evals/` holds tests.

## Commands

Python 3.10+ with only the standard library (`make_cover_card.py` and its tests need Pillow).

```bash
# Full test suite (the one hard requirement before a PR)
python -m unittest discover -s skills/wxstyle/evals -p "test_*.py"

# A single file / class / test (run from the evals dir so module names resolve)
cd skills/wxstyle/evals && python -m unittest test_title_check
cd skills/wxstyle/evals && python -m unittest test_skill_docs_contract.AiTellRuleDocsSyncTests

# Fixture benchmark (~90 assertions, includes a holdout set); --skill <old dir> compares against an older version.
# Needs the gitignored corpus profiles/_raw/target_阮一峰
python skills/wxstyle/evals/fixture_benchmark/run.py
```

`make_cover_card.py` picks a Simplified Chinese font per OS from `BOLD_CANDIDATES` / `REGULAR_CANDIDATES`, which pair each path with a `.ttc` face index (some collections put Traditional Chinese or Japanese at index 0). If no candidate exists it exits 2; pass `--font-bold` / `--font` (face index 0) to override.

Script usage (flags, how to read the output) is documented in the README script table and in `references/checks.md`. All scripts print JSON and take file paths as passed, relative to the cwd. Only the tests and `fixture_benchmark/run.py` locate the skill through `Path(__file__).resolve().parents[N]`.

## How the pieces are coupled

- **Scripts ↔ `references/checks.md`**: `test_skill_docs_contract.py` (`ClaimCheckRuleDocsSyncTests`, `AiTellRuleDocsSyncTests`) parses the rule names in the `claim_check.py` docstring and the `CATEGORY_LABELS` in `ai_tell_check.py`, then fails if any of them is missing from `checks.md`. Adding a rule: implement it with a clear `rule` name → add a row to the `checks.md` table naming it in backticks → add unit tests for both "should hit" and "should not hit" → run the fixture benchmark.
- **Docs-contract tests**: most of `test_skill_docs_contract.py` asserts that certain sentences or links exist in SKILL.md, the references and the README (scoped description, routing table, no `【填：…】` placeholders, and so on). Rewording those docs can break these tests, so check the test before you rephrase. Passing them shows the rule is written down, not that the model follows it. Behavioral evidence lives in the fixture benchmark and `evals/workflow_cases.json` (run manually per `workflow-evaluation.md`).
- **`test_docs_links.py`** checks relative links in both `skills/wxstyle/SKILL.md` and `README.md`. It distinguishes the skill root from the repo root, because README links point into `skills/wxstyle/...`.
- **Templates ↔ parsers**: `claim_check.py --review` parses the title table in `references/review-checklist-template.md` (`titles_from_review()`). It once silently checked 0 titles after the template changed while unit tests stayed green (CHANGELOG 1.9.1). When you change a template, a review.md structure or the profile schema, find the scripts that parse it and run them on a real or realistic sample, not just the hand-written fixtures.
- **Profile schema**: `validate_profile.py` holds the allowed keys; `references/style-profile-schema.md` must document every key (enforced by `ProfileSchemaTests`). Committed profiles are only `profiles/target_*.json`. `profiles/_raw/` (others' original articles) and `profiles/self_*.json` (personal data) are gitignored and must never be committed.
- **Counts in the README** (trigger-set size 43 = 24 positive + 19 negative, 30 workflow cases, "约 90 条断言" for the fixture benchmark) are kept in sync by hand. Update them when you add cases. Unit-test totals appear only in CHANGELOG entries, not in the README.

## Versioning and change discipline

- Any change to SKILL.md, the references or script behavior bumps `metadata.version` in `skills/wxstyle/SKILL.md`: bump the middle digit for flow or rule changes, the last digit for script details or doc-only changes. Also add a CHANGELOG entry and create and push a matching annotated tag (`git tag -a vX.Y.Z`). The README version badge reads the latest git tag. Repo-only changes that don't touch the skill keep the version and get their own CHANGELOG section.
- "Rule of 3" from the README: a new writing principle or structure template goes into a short section of an existing doc the first time it is adopted. Do not create a new file or long prose for it. It earns its own reference file only after 3+ real uses. Docs that haven't reached that mark carry a "验证次数" note at the top.
- `references/checks.md` policy: regex detection of cliché phrasing has a ceiling. Don't keep chasing one-off variants. Rules about content truthfulness (fabricated hands-on claims, unsourced numbers) take priority over phrasing rules.
- SKILL.md has a no-wall-of-text test (`test_no_wall_of_text_lines`), so keep its lines short. Put detail in `references/` and link to it.

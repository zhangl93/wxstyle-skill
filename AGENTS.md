# Repository Guidelines

## Project Structure & Module Organization

`wxstyle` is an agent skill for writing and reviewing WeChat Official Account articles, not a standalone application. Read `README.md`, `CONTRIBUTING.md`, and `skills/wxstyle/SKILL.md` before changing behavior.

- `skills/wxstyle/SKILL.md`: skill entry point and workflow routing.
- `skills/wxstyle/references/`: instructions, schemas, and review templates loaded on demand.
- `skills/wxstyle/scripts/`: Python checks and utilities.
- `skills/wxstyle/profiles/target_*.json`: public benchmark-account profiles.
- `skills/wxstyle/evals/`: regression tests, fixtures, and behavioral evaluation cases.
- `examples/`: sample articles, source records, reviews, and delivery manifests.

## Build, Test, and Development Commands

Use Python 3.10+. Scripts use the standard library except cover-card generation and its tests, which require Pillow (`python -m pip install Pillow`). There is no application build or development server.

```bash
python -m unittest discover -s skills/wxstyle/evals -p "test_*.py"
```

Run the full regression suite before every PR.

```bash
cd skills/wxstyle/evals
python -m unittest test_title_check
```

Run a focused test module while developing.

```bash
python skills/wxstyle/evals/fixture_benchmark/run.py
```

Run from the repository root after changing checks; this benchmark requires the ignored corpus at `skills/wxstyle/profiles/_raw/target_阮一峰`.

## Coding Style & Naming Conventions

Follow existing Python style: four-space indentation, `snake_case` functions and variables, and uppercase constants. Preserve UTF-8 Chinese text; existing documentation, comments, and commit messages are primarily Chinese. No formatter or linter is configured. Keep SKILL.md lines short and place detailed guidance in linked references.

Synchronize check rules with `references/checks.md` and profile fields with `references/style-profile-schema.md`; contract tests enforce these relationships.

## Testing Guidelines

Use `unittest`, with files named `test_*.py` and methods named `test_*`. New detection rules need both matching and nonmatching cases. No numeric coverage threshold is specified; the full suite must pass. Validate template, parser, and schema changes against realistic samples. Follow `evals/workflow-evaluation.md` for behavioral evaluation.

## Commit & Pull Request Guidelines

History uses concise Chinese descriptions, often ending with a version such as `（1.22.1）`. Describe the concrete change. PRs should explain the problem, resulting behavior, and validation performed; include reproducible input for check failures. Discuss substantial ideas in an issue first.

Skill behavior or documentation changes require a metadata version bump, CHANGELOG entry, and matching annotated release tag. Repository-only changes keep the skill version.

## Data Privacy

Never commit `profiles/_raw/`, `profiles/self_*.json`, or generated `articles/`; these contain copyrighted source material or personal data and are gitignored.

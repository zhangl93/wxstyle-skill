#!/usr/bin/env python3
"""对标样本的可复现统计：从 profiles/_raw/{账号}/ 里的原文算出段长、句长、配图、加粗等数字。

画像里的数字（avg_paragraph_length、bold_keyword_freq 等）应来自这个脚本，而不是凭阅读估计；
风格判断（语气、开头类型）仍需人读。统计口径是整篇文章，需要只看某一部分（如周刊头条）时，
先把该部分另存成单独文件再统计。
"""
import argparse
import json
import re
import statistics
import sys
from pathlib import Path


def strip_md(text):
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\((?:[^()\"]|\"[^\"]*\")*\)", r"\1", text)
    return re.sub(r"[*_`]", "", text)


def analyze_file(path):
    raw = path.read_text(encoding="utf-8-sig")
    stripped = strip_md(raw)      # 去掉图片和链接语法，避免把 ![]( 的感叹号、网址里的问号算进去
    paras, sentences = [], []
    counts = {"images": len(re.findall(r"!\[", raw)), "bold": len(re.findall(r"\*\*[^*\n]+\*\*", raw)),
              "question_marks": stripped.count("？") + stripped.count("?"), "exclamations": stripped.count("！") + stripped.count("!"),
              "quote_lines": 0, "list_lines": 0, "table_lines": 0, "h2": 0, "links": len(re.findall(r"\]\(https?://", raw)),
              "numbered_points": len(re.findall(r"^（[1-9]）|^\s*\d+[、.]\s*\S", raw, flags=re.M))}
    in_code = False
    for line in raw.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line.strip():
            continue
        if line.startswith("#"):
            counts["h2"] += 1 if line.startswith("## ") else 0
            continue
        if line.lstrip().startswith(">"):
            counts["quote_lines"] += 1
            continue
        if re.match(r"^\s*([-*+]|\d+\.)\s+", line):
            counts["list_lines"] += 1
            continue
        if line.lstrip().startswith("|"):
            counts["table_lines"] += 1
            continue
        plain = strip_md(line).strip()
        if not plain:
            continue
        paras.append(len(plain))
        sentences += [len(s.strip()) for s in re.split(r"[。！？!?]", plain) if s.strip()]
    chars = len(re.sub(r"\s", "", strip_md(raw)))
    return chars, paras, sentences, counts


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dir", required=True, help="样本目录，如 profiles/_raw/target_xxx")
    args = ap.parse_args()
    root = Path(args.dir)
    if not root.is_dir():
        print(json.dumps({"error": f"目录不存在：{args.dir}"}, ensure_ascii=False))
        return 2
    files = sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".md"})
    if not files:
        print(json.dumps({"error": "目录里没有 .txt/.md 样本"}, ensure_ascii=False))
        return 2
    all_paras, all_sents, total_chars = [], [], 0
    totals, per_file = {}, []
    for f in files:
        chars, paras, sents, counts = analyze_file(f)
        total_chars += chars
        all_paras += paras
        all_sents += sents
        for k, v in counts.items():
            totals[k] = totals.get(k, 0) + v
        per_file.append({"file": f.name, "chars": chars, "paragraphs": len(paras), **counts})
    n = len(files)
    p90 = sorted(all_sents)[int(len(all_sents) * 0.9)] if all_sents else 0
    out = {
        "file_count": n, "total_chars": total_chars, "avg_chars_per_file": round(total_chars / n),
        "paragraphs": len(all_paras),
        "avg_paragraph_chars": round(statistics.mean(all_paras)) if all_paras else 0,
        "median_paragraph_chars": round(statistics.median(all_paras)) if all_paras else 0,
        "short_paragraph_share": round(sum(1 for x in all_paras if x <= 40) / len(all_paras), 3) if all_paras else 0,
        "long_paragraph_share": round(sum(1 for x in all_paras if x > 100) / len(all_paras), 3) if all_paras else 0,
        "avg_sentence_chars": round(statistics.mean(all_sents)) if all_sents else 0,
        "p90_sentence_chars": p90,
        **{k: totals.get(k, 0) for k in ("images", "bold", "question_marks", "exclamations", "quote_lines", "list_lines",
                                        "table_lines", "links", "numbered_points")},
        "chars_per_image": round(total_chars / totals["images"]) if totals.get("images") else None,
        "bold_per_file": round(totals.get("bold", 0) / n, 1),
        "question_marks_per_file": round(totals.get("question_marks", 0) / n, 1),
        "files_with_numbered_points": sum(1 for x in per_file if x["numbered_points"] >= 2),
        "per_file": per_file,
        "note": "整篇统计；风格判断（语气、开头类型、结尾方式）仍需人读样本，不由本脚本给出",
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    # Windows 下重定向的输出默认是 GBK，统一改成 UTF-8，调用方不用设环境变量
    import sys as _sys
    for _stream in (_sys.stdout, _sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    sys.exit(main())

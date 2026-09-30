#!/usr/bin/env python3
"""全文N-gram及连续重合机械预检；不判断原创性或侵权。"""
import argparse
import difflib
import json
import re
from collections import defaultdict
from pathlib import Path


def mask_markup(text):
    """把图片、链接目标、裸网址替换成等长空格（保持偏移不变），只比较正文文字。
    否则两篇文章只是引用了同一个链接（Playground](https://…）也会凑出十几字的“连续重合”。"""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group())
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", blank, text)
    text = re.sub(r"\]\((?:[^()\"]|\"[^\"]*\")*\)", blank, text)
    return re.sub(r"https?://[^\s)>\]]+", blank, text)


def normalized_with_offsets(text):
    pairs = [(m.group(), m.start()) for m in re.finditer(r"\w", text)]
    return "".join(c for c, _ in pairs), [i for _, i in pairs]


def normalize(text):
    return re.sub(r"[^\w]", "", text)


def ngrams(text, n):
    if n < 1:
        raise ValueError("ngram-size必须为正数")
    return {text} if len(text) < n and text else {text[i:i+n] for i in range(len(text)-n+1)}


def jaccard_similarity(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def longest_match(a, b):
    """后缀自动机：全文精确最长公共子串，线性状态数，无截断。"""
    states = [{"next": {}, "link": -1, "length": 0, "end": -1}]
    last = 0
    for index, char in enumerate(a):
        cur = len(states)
        states.append({"next": {}, "link": 0, "length": states[last]["length"] + 1, "end": index})
        p = last
        while p >= 0 and char not in states[p]["next"]:
            states[p]["next"][char] = cur
            p = states[p]["link"]
        if p >= 0:
            q = states[p]["next"][char]
            if states[p]["length"] + 1 == states[q]["length"]:
                states[cur]["link"] = q
            else:
                clone = len(states)
                states.append({"next": states[q]["next"].copy(), "link": states[q]["link"],
                               "length": states[p]["length"] + 1, "end": states[q]["end"]})
                while p >= 0 and states[p]["next"].get(char) == q:
                    states[p]["next"][char] = clone
                    p = states[p]["link"]
                states[q]["link"] = states[cur]["link"] = clone
        last = cur
    v = length = best = 0
    a_start = b_start = None
    for index, char in enumerate(b):
        while v and char not in states[v]["next"]:
            v = states[v]["link"]
            length = states[v]["length"]
        if char in states[v]["next"]:
            v = states[v]["next"][char]
            length += 1
        else:
            v = length = 0
        if length > best:
            best = length
            a_start = states[v]["end"] - best + 1
            b_start = index - best + 1
    return best, a_start, b_start


def longest_common_run(a, b):
    return longest_match(a, b)[0]


def location(text, offsets, start, length):
    if start is None or not length:
        return None
    lo, hi = offsets[start], offsets[start + length - 1] + 1
    return {"start_offset": lo, "end_offset": hi,
            "start_line": text.count("\n", 0, lo) + 1,
            "excerpt": text[lo:hi][:240], "excerpt_truncated": hi - lo > 240}


def split_sentences(text, min_len=16):
    """按句号、问号、换行切句，去标点后长度不足 min_len 的丢弃（短句撞车没有意义）。"""
    out = []
    for raw in re.split(r"[。！？!?；;\n]", text):
        norm = normalize(raw)
        if len(norm) >= min_len:
            out.append((raw.strip(), norm))
    return out


def near_duplicate_sentences(generated, references, ratio_threshold=0.7, min_len=16, limit=20):
    """逐句找与参照句高度相似但不完全相同的句子，补 N-gram 和连续重合的盲区：
    每隔几个字改一个字的改写，连续重合很短，N-gram 也接近 0，但整句仍是同一句。"""
    index = defaultdict(set)      # 字二元组 -> {(参照序号, 句序号)}
    ref_sents = []
    for ref_id, (path, text) in enumerate(references):
        for raw, norm in split_sentences(mask_markup(text), min_len):
            sid = len(ref_sents)
            ref_sents.append((path, raw, norm))
            for i in range(len(norm) - 1):
                index[norm[i:i + 2]].add(sid)
    found = []
    for raw, norm in split_sentences(mask_markup(generated), min_len):
        grams = [norm[i:i + 2] for i in range(len(norm) - 1)]
        votes = defaultdict(int)
        for g in grams:
            for sid in index.get(g, ()):
                votes[sid] += 1
        best = None
        for sid, v in sorted(votes.items(), key=lambda x: -x[1])[:6]:
            if v < len(grams) * 0.4:
                break
            ref_norm = ref_sents[sid][2]
            matcher = difflib.SequenceMatcher(None, norm, ref_norm, autojunk=False)
            ratio = matcher.ratio()
            if ratio >= ratio_threshold and (best is None or ratio > best[0]):
                best = (ratio, sid)
        if best:
            path, ref_raw, ref_norm = ref_sents[best[1]]
            found.append({"generated": raw[:120], "reference": ref_raw[:120], "reference_file": str(path),
                          "ratio": round(best[0], 3), "exact": norm == ref_norm})
    found.sort(key=lambda x: -x["ratio"])
    return found[:limit], len(found)


def check_against_reference(generated, reference, n=8):
    generated, reference = mask_markup(generated), mask_markup(reference)
    a, ai = normalized_with_offsets(generated)
    b, bi = normalized_with_offsets(reference)
    if not a or not b:
        raise ValueError("正文或参照没有有效文字，不能进行相似度检查")
    length, a_start, b_start = longest_match(a, b)
    return {"similarity": jaccard_similarity(ngrams(a, n), ngrams(b, n)),
            "longest_common_run": length,
            "generated_match": location(generated, ai, a_start, length),
            "reference_match": location(reference, bi, b_start, length),
            "generated_characters": len(a), "reference_characters": len(b)}


def audit(generated_path, reference_path, n=8, similarity_threshold=0.15, run_threshold=15):
    generated_path, reference_path = Path(generated_path), Path(reference_path)
    generated = generated_path.read_text(encoding="utf-8-sig")
    if not normalize(generated):
        raise ValueError("正文没有有效文字")
    if not reference_path.exists():
        raise ValueError("参照路径不存在")
    files = ([reference_path] if reference_path.is_file() else
             sorted(p for p in reference_path.rglob("*") if p.is_file() and p.suffix.lower() in {".txt", ".md"}))
    files = [p for p in files if p.resolve() != generated_path.resolve()]
    results, invalid, ref_texts = [], [], []
    for path in files:
        try:
            ref_text = path.read_text(encoding="utf-8-sig")
            result = check_against_reference(generated, ref_text, n)
            ref_texts.append((path, ref_text))
            results.append({"reference": str(path), **result})
        except (OSError, UnicodeError, ValueError) as error:
            invalid.append({"reference": str(path), "reason": str(error)})
    best_sim = max(results, key=lambda r: r["similarity"], default=None)
    best_run = max(results, key=lambda r: r["longest_common_run"], default=None)
    complete = bool(results) and not invalid
    max_sim = best_sim["similarity"] if best_sim else None
    max_run = best_run["longest_common_run"] if best_run else None
    sim_pass = max_sim < similarity_threshold if complete else None
    run_pass = max_run < run_threshold if complete else None
    percent = None if max_sim is None else ("<0.01%" if 0 < max_sim < 0.0001 else f"{max_sim:.2%}")
    near, near_total = near_duplicate_sentences(generated, ref_texts) if complete else ([], 0)
    # 判定：至少2句近似，或有1句高度近似（≥0.85）就不通过；单句撞车只列出，不判失败
    near_pass = None if not complete else not (near_total >= 2 or any(x["ratio"] >= 0.85 for x in near))
    return {"check_type": "mechanical_similarity", "coverage": "full_text_no_truncation",
            "candidate_reference_count": len(files), "valid_reference_count": len(results),
            "invalid_references": invalid, "inspection_complete": complete,
            "max_similarity": max_sim, "similarity_display": percent,
            "similarity_threshold": similarity_threshold, "passed_similarity": sim_pass,
            "longest_common_run": max_run, "run_threshold": run_threshold, "passed_run_check": run_pass,
            "flagged_reference_similarity": best_sim["reference"] if complete and not sim_pass else None,
            "flagged_reference_run": best_run["reference"] if complete and not run_pass else None,
            "near_duplicate_sentences": near, "near_duplicate_total": near_total,
            "passed_near_duplicate_check": near_pass,
            "overall_pass": complete and sim_pass and run_pass and near_pass, "references": results,
            "limitation": "仅比对列出的本地样本；阈值不是原创性或法律结论；换了说法但骨架相同的仿写脚本查不出，需人工看结构"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generated", required=True)
    parser.add_argument("--reference", required=True)
    parser.add_argument("--ngram-size", type=int, default=8)
    parser.add_argument("--similarity-threshold", type=float, default=0.15)
    parser.add_argument("--run-threshold", type=int, default=15)
    args = parser.parse_args()
    if args.ngram_size < 1 or args.run_threshold < 1 or not 0 <= args.similarity_threshold <= 1:
        parser.error("阈值范围无效")
    try:
        output = audit(args.generated, args.reference, args.ngram_size, args.similarity_threshold, args.run_threshold)
    except (OSError, UnicodeError, ValueError) as error:
        print(json.dumps({"error": str(error), "inspection_complete": False, "overall_pass": False}, ensure_ascii=False))
        return 2
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["overall_pass"] else (1 if output["inspection_complete"] else 2)


if __name__ == "__main__":
    # Windows 下重定向的输出默认是 GBK，统一改成 UTF-8，调用方不用设环境变量
    import sys as _sys
    for _stream in (_sys.stdout, _sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())


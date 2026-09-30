#!/usr/bin/env python3
"""公众号Markdown排版与文字机械检查（规则见 references/wechat-layout.md）。

只检查语法层面的疑点：会导致排版出错的写法记为 error，需要人判断的记为 warn，
发布前还要处理的事项记为 pending。零 error 不代表排版好看，也不代表内容合格。
"""
import argparse
import json
import re
import sys

CJK = r"[　-〿㐀-鿿＀-￯]"
PUNCT = "。！？，；：、）」』”\"'）)…—"


# 链接括号部分；标题里允许出现括号，如 [文字](网址 "来源（含括号）")
LINK_TAIL = r"\]\((?:[^()\"]|\"[^\"]*\")*\)"


def strip_link_urls(text):
    return re.sub(LINK_TAIL, "]()", text)


def main():
    ap = argparse.ArgumentParser(description="公众号Markdown排版机械检查")
    ap.add_argument("--file", required=True, help="Markdown 正文文件")
    ap.add_argument("--max-para", type=int, default=100, help="段落字数提示阈值，默认100")
    args = ap.parse_args()

    try:
        with open(args.file, encoding="utf-8-sig") as f:
            lines = f.read().split("\n")
    except (OSError, UnicodeDecodeError) as e:
        print(json.dumps({"error": f"无法读取文件：{e}"}, ensure_ascii=False))
        return 2

    issues = []

    def add(level, no, rule, msg):
        issues.append({"level": level, "line": no, "rule": rule, "message": msg})

    in_code = False
    prev_heading = 0
    stats = {"h2": 0, "h3": 0, "quote": 0, "ul": 0, "ol": 0, "table": 0, "image": 0, "bold": 0, "link": 0}
    long_paras = 0
    para_lengths = []
    prev_text_line = None  # 上一行是否为普通正文行
    prev_hard_break = False  # 上一行以两个空格或反斜杠结尾：这是有意的硬换行，不算并段
    prev_was_table = False

    # 预扫描：不写外侧竖线的表格（`a | b` 加 `--- | ---`）也是合法表格，先标出表格行号（从1起）
    sep = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
    table_rows = set()
    for i, text in enumerate(lines):
        if "|" in text and sep.match(text):
            if i > 0 and "|" in lines[i - 1]:
                table_rows.add(i)
            table_rows.add(i + 1)
            j = i + 1
            while j < len(lines) and lines[j].strip() and "|" in lines[j]:
                table_rows.add(j + 1)
                j += 1

    for no, raw in enumerate(lines, 1):
        line = raw.rstrip()
        if re.match(r"^\s*```", line):
            if not in_code:
                if not re.match(r"^\s*```\s*\S", line):
                    add("warn", no, "code_no_lang", "代码块没有标注语言，将无法使用微信高亮配色")
            in_code = not in_code
            prev_text_line = None
            continue
        if in_code:
            continue
        if not line.strip():
            prev_text_line = None
            prev_was_table = False
            continue

        m = re.match(r"^(#{1,6})\s+\S", line)
        is_table = line.lstrip().startswith("|") or no in table_rows
        is_list = bool(re.match(r"^\s*([-*+]|\d+\.)\s+", line))
        is_quote = line.lstrip().startswith(">")
        is_image = bool(re.match(r"^!\[", line))

        if m:
            level = len(m.group(1))
            if level == 1:
                add("error", no, "h1_in_body", "正文含一级标题 #；示例工具正文从 ## 开始，文章标题填公众号后台标题栏")
            elif prev_heading == 0 and level > 2:
                add("warn", no, "heading_start", "第一个标题不是 ##")
            if prev_heading and level - prev_heading > 1:
                add("error", no, "heading_skip", f"标题从{prev_heading}级跳到{level}级")
            if level == 2:
                stats["h2"] += 1
            if level == 3:
                stats["h3"] += 1
            prev_heading = level
            prev_text_line = None
            continue

        prev_line = lines[no - 2].strip() if no >= 2 else ""
        if re.match(r"^\s*(-+|=+)\s*$", line) and prev_line and not re.match(r"^(#|>|[-*+]\s|\d+\.\s|\|)", prev_line):
            add("error", no, "setext_heading", "文字下一行紧跟 --- 或 ===，Markdown 会把上一行当成标题；中间加空行，或删掉分隔线")
            prev_text_line = None
            continue
        if re.match(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", line):
            add("warn", no, "divider", "分隔线：转换后没有样式，粘贴到公众号多半看不见，改用 ## 小标题分节")
            prev_text_line = None
            continue

        if is_table:
            if not prev_was_table:
                stats["table"] += 1
                nxt = lines[no] if no < len(lines) else ""
                if not re.match(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$", nxt):
                    add("error", no, "table_no_separator", "表格表头下一行缺少 --- 分隔行")
                cols = len([c for c in line.strip().strip("|").split("|")])
                if cols > 4:
                    add("warn", no, "table_wide", f"表格有{cols}列，手机上难读")
            prev_was_table = True
            prev_text_line = None
            continue
        prev_was_table = False

        if is_quote:
            stats["quote"] += 1
        elif is_list:
            stats["ul" if re.match(r"^\s*[-*+]\s", line) else "ol"] += 1
        if is_image:
            stats["image"] += 1
            am = re.match(r"^!\[(.*?)\]\((.*?)\)", line)
            if am:
                if not am.group(1).strip():
                    add("warn", no, "image_no_alt", "图片没有 alt 文字")
                if not re.match(r"https?://", am.group(2)):
                    add("pending", no, "image_local", "本地图片路径仅用于预览，发布时需在公众号后台插入或换成图床/微信媒体库 URL")

        # 相邻正文行会被并成一段
        if not (is_list or is_quote or is_image):
            if prev_text_line is not None and not prev_hard_break:
                add("error", no, "merged_lines", "与上一行之间没有空行，渲染时会并入同一段")
            prev_text_line = no
            prev_hard_break = raw.endswith("  ") or raw.endswith("\\")
        else:
            prev_text_line = None

        body = strip_link_urls(line)
        stats["link"] += len(re.findall(r"\]\(https?://", line))
        stats["bold"] += len(re.findall(r"\*\*[^*\n]+\*\*", body))

        # 加粗边界：标点紧贴 ** 时，严格 Markdown 渲染器可能不生效
        for bm in re.finditer(r"\*\*([^*\n]+)\*\*", body):
            inner, s, e = bm.group(1), bm.start(), bm.end()
            after = body[e] if e < len(body) else ""
            before = body[s - 1] if s > 0 else ""
            if inner[-1] in PUNCT and after and not after.isspace() and after not in PUNCT:
                add("error", no, "bold_closing", f"加粗以标点结尾且后面紧跟文字（“{inner[-6:]}**{after}”），星号可能显示成字符；把标点移到星号外")
            if inner[0] in PUNCT + "（(“\"「『" and before and not before.isspace() and before not in PUNCT:
                add("error", no, "bold_opening", f"加粗以标点开头且前面紧跟文字（“{before}**{inner[:4]}”），星号可能显示成字符；把标点移到星号外")

        # 中文正文里的直引号
        if '"' in body and re.search(CJK, body):
            add("warn", no, "straight_quote", "中文正文里用了直引号 \"，统一改成弯引号 “ ”")
        # 相对时间词
        if re.search(r"本周|上周|下周|今天|昨天|明天|最近|刚刚|这两天", body):
            add("warn", no, "relative_time", "相对时间词会随发布日期失真，改成具体日期，或确认发布日期后保留")

        # HTML 标签（转换工具未必处理，手机端可能原样显示）
        if re.search(r"</?[A-Za-z][A-Za-z0-9]*(\s[^<>]*)?/?>", body):
            add("warn", no, "html_tag", "正文含 HTML 标签，转换或粘贴后可能原样显示；改用 Markdown 写法")

        # 裸网址（不在 Markdown 链接里）
        if re.search(r"https?://", body):
            add("warn", no, "bare_url", "正文出现裸网址；公众号正文里不可点击，改成带标题的 Markdown 链接")

        # 注音语法
        if re.search(CJK + r"\s*(【[^】]*】|\{[^}]*\})", body):
            add("error", no, "ruby_syntax", "汉字后紧跟 【…】 或 {…}，会被转换成注音；改用（）或「」")
        if "{" in body and "}" in body:
            add("warn", no, "braces", "含花括号，可能触发注音语法")
        if re.search(r"【填[:：]", body):
            add("error", no, "placeholder", "正文里不留【填：…】占位符：没有数据就删掉这一段，不要留给作者补")

        # 段落长度（正文行，不含列表/引用/图片）
        if not (is_list or is_quote or is_image):
            plain = re.sub(r"\[([^\]]*)" + LINK_TAIL, r"\1", raw)
            plain = re.sub(r"[*_`]", "", plain)
            n = len(plain.strip())
            para_lengths.append(n)
            if n > args.max_para:
                long_paras += 1
                add("warn", no, "long_para", f"段落{n}字，超过{args.max_para}字，手机上一屏显示不完，考虑拆分")

    if in_code:
        add("error", len(lines), "code_unclosed", "代码块没有闭合")

    # 重复短语：同一段文字（7-12个汉字）出现3次及以上，只是提示
    text_only = "\n".join(l for l in lines if not l.startswith(("|", "```", "!", "*图注")))
    text_only = re.sub(LINK_TAIL, "]", text_only)
    runs = re.findall(r"[一-鿿]+", text_only)
    grams = {}
    for r in runs:
        for n in range(12, 6, -1):
            for i in range(len(r) - n + 1):
                g = r[i:i + n]
                grams[g] = grams.get(g, 0) + 1
    reported = []
    for g, c in sorted(grams.items(), key=lambda x: (-len(x[0]), -x[1])):
        # 跳过已报告短语的错位变体（首尾各错开几个字）
        if c >= 3 and not any(any(g[k:k + len(g) - 3] in r for k in range(4)) for r in reported):
            reported.append(g)
            add("warn", 0, "repeated_phrase", f"“{g}”出现{c}次，检查是否重复表达")
    # 正文字数：去掉代码块、表格、图片、链接目标和 Markdown 符号后的非空白字符数。
    # 用它报字数，不要用 wc -c（按字节算，中文会被放大约3倍）。
    body_lines, fenced = [], False
    for text in lines:
        if text.strip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced and not text.lstrip().startswith("|"):
            body_lines.append(text)
    body_text = re.sub(r"!\[[^\]]*\]" + LINK_TAIL[2:], "", "\n".join(body_lines))
    body_text = re.sub(r"\[([^\]]*)" + LINK_TAIL, r"\1", body_text)
    body_text = re.sub(r"https?://\S+", "", body_text)
    body_text = re.sub(r"^\s*(#{1,6}|>|[-*+]|\d+\.)\s+", "", body_text, flags=re.M)
    stats["body_chars"] = len(re.sub(r"[\s*_`]", "", body_text))
    stats["paragraphs"] = len(para_lengths)
    stats["avg_paragraph_chars"] = round(sum(para_lengths) / len(para_lengths)) if para_lengths else 0
    stats["long_paragraphs"] = long_paras

    errors = [i for i in issues if i["level"] == "error"]
    result = {
        "issues": issues,
        "issue_count": {
            "error": len(errors),
            "warn": len([i for i in issues if i["level"] == "warn"]),
            "pending": len([i for i in issues if i["level"] == "pending"]),
        },
        "stats": stats,
        "check_type": "layout_syntax_precheck",
        "mechanical_pass": not errors,
        "limitation": "只检查语法层面的排版疑点；没有 error 不代表版式好看，也不替代手机预览",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    # Windows 下重定向的输出默认是 GBK，统一改成 UTF-8，调用方不用设环境变量
    import sys as _sys
    for _stream in (_sys.stdout, _sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    sys.exit(main())

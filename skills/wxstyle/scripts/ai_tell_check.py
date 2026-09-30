#!/usr/bin/env python3
"""
AI味特征机械预检（分强弱两档）

用于 wxstyle-write 质量自评阶段的"声音真实感"检查：先机械扫一遍已知的AI高频句式和结构，
标出可疑行的行号和原文，再交给LLM或作者判断要不要改。只做模式匹配，命中不代表一定要删。

分档思路借自 blader/humanizer：
- 强信号（strong）：认真的作者很少有意这样写，见一次就列出。
- 弱信号（weak）：认真的作者也会有意用，单独出现不计入 hits，只列在 weak_alone；
  同一段落附近（前后5行内）还有别的信号时，才计入 hits。
- 引用块、引号“”「」内、书名号《》内、代码块里的文字不检查（引用别人的话不是作者自己的AI味）。

用法：
    python ai_tell_check.py --file <生成稿>

返回 JSON：
    {
      "hits": [{"line": 22, "category": "reframe", "level": "strong", "text": "……"}],
      "weak_alone": [...],          # 单独出现、不计数的弱信号
      "hit_count": 1,
      "skipped": {"blockquote_lines": 0, "quoted_segments": 0},
      "mechanical_pass": false
    }
"""

import argparse
import json
import re
import sys
from pathlib import Path

# (类别, 正则, 强弱)
PHRASE_PATTERNS = [
    ("reframe", re.compile(r"不是.{1,20}?，(而)?是|不只是.{1,20}?，?而是|不在于.{1,20}?，?而在于"), "strong"),
    ("comparative_payoff", re.compile(r"比.{1,15}?(更(重要|关键|值钱|有价值)|重要多了|值钱多了)|比任何.{1,12}都(?:重要|关键|有用)"), "strong"),
    ("boilerplate_transition", re.compile(r"总而言之|值得注意的是|不仅(?:仅)?是.{0,15}?更是|与其说.{0,15}?不如说"), "strong"),
    ("grand_opening", re.compile(r"在.{1,12}(的今天|的时代|的浪潮下|的背景下)|随着.{1,20}的(不断)?(发展|普及|进步|深入)"), "strong"),
    ("summary_closer", re.compile(r"综上(?:所述)?[，,：:]|总的来说|希望(这篇|本文|以上|这些).{0,12}(帮助|启发|参考)"), "strong"),
    ("empty_phrases", re.compile(r"赋能|开启.{0,4}新篇章|深入探讨|值得一提的是|不难发现|让我们一起|让我们来|不可否认"), "strong"),
    ("closer_saying", re.compile(r"这(?:才|就)是(?:真正的?)?.{0,12}?(?:关键|答案|真谛|本质|价值所在)|真正[^，。！？\n]{0,15}?(?:的|之处)?，?(?:是|在于)"), "strong"),
    # 弱信号：认真的作者也会有意用，只有和别的信号同现才计数
    ("enumeration", re.compile(r"首先.{0,60}其次|一方面.{0,60}另一方面"), "weak"),
    ("sweeping_inclusion", re.compile(r"无论.{1,15}?(?:还是|或者).{1,15}?都"), "weak"),
    ("assertive_filler", re.compile(r"毫无疑问|毋庸置疑|不言而喻|终究只是|说到底|归根结底|归根到底"), "weak"),
    ("buzzwords", re.compile(r"显著提升|事半功倍|全方位|多维度|一站式|无缝(?:衔接|集成|连接)|双刃剑"), "weak"),
    ("stock_frame", re.compile(r"没有(?:统一|标准|唯一)的?答案|关键(?:还是|就)?(?:要)?看你|答案自然|(?<!与其说)与其[^，。！？\n]{1,20}，?不如"
                               r"|身边(?:不少|很多|好多)朋友|总结一下[：:，]"), "weak"),
    ("chatbot_residue", re.compile(r"^(?:当然可以[！!]|好的[！!]|没问题[！!]|以下是(?:为你|为您|我为你)|下面是(?:为你|为您))|如需(?:进一步|更多)?(?:调整|修改|补充)|(?:请|随时)告诉我|希望(?:这|以上)?.{0,8}对你有(?:所)?帮助|作为(?:一个|一名)?(?:AI|人工智能|语言模型)|截至我的(?:知识|训练)|我无法(?:亲自|直接)"), "strong"),
    ("doc_meta", re.compile(r"本文(?:将|旨在|主要)|文章将(?:从|围绕)|接下来[，,]?(?:我们|让我)(?:将|来|会)|下面(?:我们|让我们)(?:来|就)"), "weak"),
    ("inflated_significance", re.compile(r"(?:标志着|意味着).{0,14}(?:新(?:的)?(?:时代|篇章|阶段|纪元)|里程碑|转折点)|至关重要|不可或缺|举足轻重|具有.{0,4}(?:深远|重大)的?(?:意义|影响)|(?:奠定|夯实)了?.{0,8}基础|注入.{0,4}新(?:的)?(?:动力|活力)"), "weak"),
    ("engagement_bait", re.compile(r"欢迎(?:在)?(?:评论区|留言区|留言)|你(?:更)?(?:怎么看|站哪边)"), "weak"),
]
TEMPLATE_HEADING = re.compile(r"^(?:写在最后|最后的话|最后想说|结语|尾声|先说结论|一句话总结|总结一下)")

CATEGORY_LABELS = {
    "reframe": "「不是A，是B」重新框定句",
    "comparative_payoff": "「X比Y更重要/更值钱」比较收尾句",
    "boilerplate_transition": "AI高频过渡词/框架句（总而言之/值得注意的是/不仅是……更是……）",
    "grand_opening": "「在……的今天/时代」「随着……的发展」式宏大开场",
    "summary_closer": "「综上所述/总的来说/希望对你有帮助」式收尾套话",
    "empty_phrases": "空泛动词与套话（赋能/深入探讨/值得一提的是/不难发现/让我们一起）",
    "closer_saying": "「这才是真正的关键」式假装深刻的收尾金句",
    "enumeration": "「首先……其次……」「一方面……另一方面……」式机械并列",
    "sweeping_inclusion": "「无论……还是……都」式全覆盖表述",
    "assertive_filler": "「毫无疑问/毋庸置疑」式加重语气的空话",
    "buzzwords": "AI常用词（显著提升/事半功倍/全方位/多维度/一站式/双刃剑）",
    "sequence_markers": "段首连用“首先是/其次是/还有就是”式顺序词",
    "repeated_openings": "连续多段用同一个词开头",
    "bold_labels": "列表项用加粗小标签开头（**速度**：……）",
    "bold_density": "加粗过密",
    "one_line_closers": "每一节都以一句话短句收尾",
    "decorative_headings": "标题里带 emoji 等装饰符号",
    "heading_echo": "小标题的原话又在下一段第一句重复一遍",
    "fragmented_paragraphs": "大量一句话独占一段，段落多且平均很短",
    "stock_frame": "套路框架句（没有统一答案/关键看你/与其……不如/身边不少朋友/答案自然）",
    "engagement_bait": "「欢迎在评论区聊聊」式互动收尾",
    "chatbot_residue": "聊天助手残留（当然可以/以下是为你/如需调整请告诉我/作为AI）",
    "doc_meta": "写文章本身而不是内容（本文将从……几个方面）",
    "inflated_significance": "拔高意义（标志着新篇章/至关重要/奠定基础）",
    "no_specifics": "整体缺少具体细节：没有数字、括号补充或第一人称经历",
    "template_heading": "模板化小标题（写在最后/结语/先说结论）",
}

EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿⭐⬆➡]")
QUOTE_SPANS = [
    re.compile(r"“[^”\n]*”"), re.compile(r"‘[^’\n]*’"), re.compile(r"「[^」\n]*」"), re.compile(r"『[^』\n]*』"),
    re.compile(r"《[^》\n]*》"), re.compile(r'"[^"\n]*"'),
]
NEAR_LINES = 5  # 弱信号附近多少行内有别的信号才计数


def mask_quotes(line: str):
    """把引号、书名号里的文字换成空格（保持长度），返回（处理后的行，被屏蔽的段数）。"""
    count = 0
    for pattern in QUOTE_SPANS:
        def blank(m):
            nonlocal count
            count += 1
            return " " * len(m.group())
        line = pattern.sub(blank, line)
    return line, count


def plain(text: str) -> str:
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\((?:[^()\"]|\"[^\"]*\")*\)", r"\1", text)
    return re.sub(r"[*_`]", "", text).strip()


def analyze(text: str, allow=()) -> dict:
    lines = text.splitlines()
    tells = []  # {"line","category","level","text"}
    skipped = {"blockquote_lines": 0, "quoted_segments": 0}
    paragraphs = []   # (行号, 纯文本)，只含正文段落
    sections = []     # 每节的正文段落 [(行号, 纯文本)]
    headings = []     # (行号, 标题文字)
    bold_total = 0
    bold_lead_lines = []   # 以加粗短语开头的行（**第一，……**、- **速度**：……）
    sequence_lines = []    # 以“首先是/其次是/还有就是”开头的行
    list_bold_runs = []   # 连续的“加粗小标签”列表项
    run = []
    in_code = False

    def flush_run():
        nonlocal run
        if len(run) >= 3:
            list_bold_runs.append(run[0])
        run = []

    for no, raw in enumerate(lines, 1):
        stripped = raw.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            flush_run()
            continue
        if in_code:
            continue
        if not stripped:
            flush_run()
            continue
        head = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if head:
            flush_run()
            title = head.group(2).strip()
            headings.append((no, title))
            if EMOJI.search(title):
                tells.append({"line": no, "category": "decorative_headings", "level": "strong", "text": stripped[:120]})
            if TEMPLATE_HEADING.match(title):
                tells.append({"line": no, "category": "template_heading", "level": "weak", "text": stripped[:120]})
            if len(head.group(1)) == 2:
                sections.append([])
            continue
        if stripped.startswith(">"):
            skipped["blockquote_lines"] += 1
            flush_run()
            continue

        is_list = bool(re.match(r"^([-*+]|\d+\.)\s+", stripped))
        if is_list and re.match(r"^([-*+]|\d+\.)\s+\*\*[^*]+\*\*\s*[：:]", stripped):
            run.append(no)
        else:
            flush_run()
        bold_total += len(re.findall(r"\*\*[^*\n]+\*\*", raw))
        # 加粗短语后面还有正文才算“加粗领句”；整行只有加粗（作小标题用）不算
        if re.match(r"^(?:[-*+]\s+|\d+\.\s+)?\*\*[^*\n]{1,25}\*\*\s*\S", stripped):
            bold_lead_lines.append(no)
        if re.match(r"^(?:首先|其次|再次|最后|还有就是|第[一二三四五][，,、])", stripped):
            sequence_lines.append(no)
        is_special = is_list or stripped.startswith(("|", "![", "*图注", "*配图"))

        masked, n = mask_quotes(raw)
        skipped["quoted_segments"] += n
        for category, pattern, level in PHRASE_PATTERNS:
            # 强信号每行记一次；弱信号按出现次数记，同一行扎堆的几个弱信号可以互相作证
            found = len(pattern.findall(masked)) if level == "weak" else int(bool(pattern.search(masked)))
            for _ in range(found):
                tells.append({"line": no, "category": category, "level": level, "text": stripped[:120]})

        if not is_special:
            para = plain(stripped)
            if para:
                paragraphs.append((no, para))
                if sections:
                    sections[-1].append((no, para))
    flush_run()

    # --- 结构信号 ---
    # 连续段落同一开头
    def opening(t):
        return t[:2]

    usable = [(no, t) for no, t in paragraphs if re.match(r"^[^\W\d_]", t) and len(t) >= 2]

    # 大量一句成段：不是"段落短"本身的问题（我们自己的文章段落也短），
    # 是"短到失去意义、还堆得特别多"——真实案例：ChatGPT改稿216段，均长19字。
    if len(paragraphs) >= 15:
        avg_len = sum(len(t) for _, t in paragraphs) / len(paragraphs)
        if avg_len <= 25:
            tells.append({"line": paragraphs[0][0], "category": "fragmented_paragraphs", "level": "strong",
                          "text": f"{len(paragraphs)}段正文，平均每段{avg_len:.0f}字，多半是一句话独占一段"})

    i, in_run = 0, set()
    while i < len(usable):
        j = i
        while j + 1 < len(usable) and opening(usable[j + 1][1]) == opening(usable[i][1]):
            j += 1
        if j - i + 1 >= 3:
            # 连续4段起算强信号；3段是弱信号（清单式的文字里“一个……”“一篇……”开头很常见）
            level = "strong" if j - i + 1 >= 4 else "weak"
            tells.append({"line": usable[i][0], "category": "repeated_openings", "level": level,
                          "text": f"连续{j - i + 1}段以“{opening(usable[i][1])}”开头"})
            in_run.add(opening(usable[i][1]))
        i = j + 1
    if len(usable) >= 8:
        counts = {}
        for no, t in usable:
            counts.setdefault(opening(t), []).append(no)
        for word, nos in counts.items():
            if word not in in_run and len(nos) >= 4 and len(nos) / len(usable) >= 0.12:
                tells.append({"line": nos[0], "category": "repeated_openings", "level": "weak",
                              "text": f"{len(nos)}/{len(usable)}段以“{word}”开头"})

    # 加粗小标签列表、加粗密度
    for first_line in list_bold_runs:
        tells.append({"line": first_line, "category": "bold_labels", "level": "strong", "text": lines[first_line - 1].strip()[:120]})
    if len(bold_lead_lines) >= 3 and not list_bold_runs:
        tells.append({"line": bold_lead_lines[0], "category": "bold_labels", "level": "strong",
                      "text": f"{len(bold_lead_lines)}处以加粗短语开头：{lines[bold_lead_lines[0] - 1].strip()[:60]}"})
    if len(sequence_lines) >= 3:
        tells.append({"line": sequence_lines[0], "category": "sequence_markers", "level": "weak",
                      "text": f"{len(sequence_lines)}处段首顺序词：{lines[sequence_lines[0] - 1].strip()[:40]}"})
    body_chars = len(re.sub(r"\s", "", plain(text)))
    if bold_total >= 5 and body_chars and bold_total / body_chars * 1000 > 4:
        tells.append({"line": 1, "category": "bold_density", "level": "weak", "text": f"加粗{bold_total}处，约每千字{bold_total / body_chars * 1000:.1f}处"})

    # 每节一句话收尾
    eligible, closers = 0, []
    for sec in sections:
        if len(sec) >= 3:
            eligible += 1
            no, para = sec[-1]
            if len(para) <= 15 and para[-1] in "。！？!?":
                closers.append(no)
    if len(closers) >= 3 or (len(closers) == 2 and eligible and len(closers) / eligible >= 0.5):
        level = "strong" if len(closers) >= 3 else "weak"
        tells.append({"line": closers[0], "category": "one_line_closers", "level": level,
                      "text": f"{eligible}节里有{len(closers)}节以一句短句收尾"})

    # 小标题在下一段第一句重复
    for hno, title in headings:
        if len(title) >= 4:
            nxt = next(((no, t) for no, t in paragraphs if no > hno), None)
            if nxt and nxt[1].startswith(title):
                tells.append({"line": nxt[0], "category": "heading_echo", "level": "weak", "text": f"“{title}”"})

    # 整体缺具体细节：够长的正文里没有数字、括号补充、第一人称经历（真人语料0/25，AI默认稿约1/3）
    prose = "\n".join(p for _, p in paragraphs)
    prose_chars = len(re.sub(r"\s", "", prose))
    if prose_chars >= 600:
        digits = len(re.findall(r"\d+", prose))
        asides = len(re.findall(r"（[^）]{2,30}）|\([^)]{2,30}\)", prose))
        first = len(re.findall(r"我(?:觉得|认为|的(?:判断|看法|感觉)|个人|自己|之前|上周|昨天|当时|试过|用过|不太|其实)", prose))
        if digits / prose_chars * 1000 < 8 and asides == 0 and first == 0:
            tells.append({"line": 1, "category": "no_specifics", "level": "strong",
                          "text": f"约{prose_chars}字里数字{digits}处、括号补充0处、第一人称经历0处"})

    tells = [x for x in tells if x["category"] not in allow]

    # --- 计数：强信号直接计，弱信号附近有别的信号才计 ---
    counted, weak_alone = [], []
    for tell in tells:
        item = dict(tell, category_label=CATEGORY_LABELS[tell["category"]])
        if tell["level"] == "strong":
            counted.append(item)
            continue
        near = any(o is not tell and abs(o["line"] - tell["line"]) <= NEAR_LINES for o in tells)
        (counted if near else weak_alone).append(item)
    counted.sort(key=lambda h: h["line"])
    weak_alone.sort(key=lambda h: h["line"])
    return {"hits": counted, "weak_alone": weak_alone, "skipped": skipped,
            "chars": len(re.sub(r"\s", "", text))}


def check_text(text: str) -> list:
    """兼容旧接口：只返回计入统计的命中。"""
    return analyze(text)["hits"]


def main():
    parser = argparse.ArgumentParser(description="AI味高频句式与结构机械预检（强弱两档）")
    parser.add_argument("--file", required=True, help="生成稿文本文件路径")
    parser.add_argument("--allow", default="", help="逗号分隔的类别，作者自己的写作习惯里本来就有的，不检查（如 engagement_bait）")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print(json.dumps({"error": f"文件不存在: {args.file}"}, ensure_ascii=False))
        sys.exit(1)

    allow = [x.strip() for x in args.allow.split(",") if x.strip()]
    result = analyze(path.read_text(encoding="utf-8-sig"), allow)
    hits = result["hits"]
    chars = result["chars"]
    output = {
        "hits": hits,
        "hit_count": len(hits),
        "strong_count": sum(1 for h in hits if h["level"] == "strong"),
        "weak_counted": sum(1 for h in hits if h["level"] == "weak"),
        "hits_per_1000_chars": round(len(hits) / chars * 1000, 3) if chars else 0.0,
        "weak_alone": result["weak_alone"],
        "allowed": allow,
        "skipped": result["skipped"],
        "check_type": "phrase_precheck",
        "mechanical_pass": len(hits) == 0,
        "editorial_review_required": True,
        "limitation": "零命中不代表自然、原创或质量合格；命中不表示必须删除；弱信号单独出现只列出不计数",
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    sys.exit(0 if output["mechanical_pass"] else 1)


if __name__ == "__main__":
    # Windows 下重定向的输出默认是 GBK，统一改成 UTF-8，调用方不用设环境变量
    import sys as _sys
    for _stream in (_sys.stdout, _sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    main()

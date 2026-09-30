# 留出集：开发检查脚本时没看过的写法，用来估计泛化，而不是重复验证已修好的问题。
# 由 harness.py 用 exec 载入，可直接使用其中的 run/write/rules/missing/sim_run/ref_paragraphs 等。

HOLD_AI = [
    "在数字化转型的浪潮下，企业亟需拥抱变化。", "首先要看预算；其次要看团队；最后要看时间。", "这不仅是一个工具，更是一种全新的工作方式。",
    "让我们一起拥抱AI时代吧！", "无论你是新手还是专家，都能从中受益。", "通过这些方法，你可以显著提升效率，实现事半功倍的效果。",
    "AI不是替代人类，而是增强人类的能力。", "这就像一把双刃剑，既带来机遇，也带来挑战。", "综上，我们可以得出以下结论：",
    "值得一提的是，它还支持多语言。", "毫无疑问，这将成为未来的趋势。", "希望本文能给你带来一些启发。",
]
HOLD_HUMAN = [
    "我昨天把配置改了三遍，还是连不上，最后发现是端口被占了。", "这个功能上线以后，客服的投诉少了一半左右，具体数字要看后台。",
    "他是我见过最认真的程序员之一，改一行代码要先写半页说明。", "如果预算只有五千块，我会先买显示器，再考虑别的。",
    "这篇文章讲的是缓存怎么失效，以及为什么失效比命中更难处理。", "会议开到一半，服务器突然挂了，大家一起盯着屏幕发呆。",
]


def holdout_aitell():
    if not (SKILL / "scripts" / "ai_tell_check.py").exists():
        return missing("ai_tell_check.py", ["AI味检查脚本存在"]), {}
    det, fp = [], []
    for s_ in HOLD_AI:
        r = run("ai_tell_check.py", "--file", write("h.txt", s_ + "\n"))
        det.append(bool((r["json"] or {}).get("hits") or (r["json"] or {}).get("weak_alone")))
    for s_ in HOLD_HUMAN:
        r = run("ai_tell_check.py", "--file", write("h.txt", s_ + "\n"))
        fp.append(bool((r["json"] or {}).get("hits")))
    miss = [t for t, d in zip(HOLD_AI, det) if not d]
    return [("留出的12句新写法AI套话召回率不低于70%", sum(det) / len(det) >= 0.7, f"{sum(det)}/12，漏掉：{miss}"),
            ("6句真人口语写法零误报", not any(fp), f"误报{sum(fp)}句")], {}


HOLD_FAB = ["我体验了一周，感觉非常流畅。", "亲身试过，稳定得很。", "我把它接进了我们的系统，跑了一晚上没出问题。", "上手用了两天，效果超出预期。",
            "响应时间缩短了80%。", "用户增长到500万。", "成本只有原来的三分之一。", "永远不会出错。", "万无一失，绝对可靠。",
            "这个产品已经火出圈了，在社交媒体上疯传。"]
HOLD_OK = ["据官方博客，响应时间缩短了80%。", "2026年9月发布，共3种规格。", "我读了官方文档，下面按文档整理。", "我猜大概需要三步。",
           "假如每天处理500条工单，这套办法就能省不少事。", "Pydantic 文档写到，上限为64k token。", "他称成本降低了一半。", "先把问题写清楚，再交给它。"]


def holdout_claims():
    if not (SKILL / "scripts" / "claim_check.py").exists():
        return missing("claim_check.py", ["内容真实性检查脚本存在"]), {}
    det, fp = [], []
    pad = "\n\n".join(["过渡段。"] * 4)
    for s_ in HOLD_FAB:
        r = run("claim_check.py", "--file", write("f.md", s_ + "\n\n" + pad + "\n"))
        det.append(bool((r["json"] or {}).get("issues")))
    for s_ in HOLD_OK:
        r = run("claim_check.py", "--file", write("o.md", s_ + "\n"))
        fp.append(bool((r["json"] or {}).get("issues")))
    miss = [t for t, d in zip(HOLD_FAB, det) if not d]
    bad = [t for t, d in zip(HOLD_OK, fp) if d]
    return [("留出的10句夸大或编造写法召回率不低于50%", sum(det) / len(det) >= 0.5, f"{sum(det)}/10，漏掉：{miss}"),
            ("留出的8句正常写法误报不超过1句", sum(fp) <= 1, f"误报：{bad}")], {}


def holdout_layout():
    if not (SKILL / "scripts" / "check_layout.py").exists():
        return missing("check_layout.py", ["排版检查脚本存在"]), {}
    out = []
    r = run("check_layout.py", "--file", write("h1.md", "## 章节\n\n文字一行\n===\n\n结束。\n"))
    out.append(("“===”紧跟文字会变标题，被标出", "setext_heading" in rules(r), f"{sorted(rules(r))}"))
    guards = {
        "两列表格不写外侧竖线（合法 GFM 写法）不误报": "## 章节\n\n列一 | 列二\n--- | ---\na | b\n\n结束。\n",
        "行尾两个空格的硬换行不误报并段": "## 章节\n\n第一行  \n第二行\n\n结束。\n",
        "连续引用行、嵌套列表、带标题的图片不误报": "## 章节\n\n> 引用第一行\n> 引用第二行\n\n- 父项\n  - 子项\n\n![说明](https://a.com/x.png \"标题\")\n\n结束。\n",
        "标题后带收尾 # 不误报": "## 章节 ##\n\n结束。\n",
    }
    for text, body in guards.items():
        r = run("check_layout.py", "--file", write("g.md", body))
        errs = [(i["rule"], i["line"]) for i in (r["json"] or {}).get("issues", []) if i["level"] in ("error", "warn")]
        out.append((text, not errs, f"误报：{errs}" if errs else "零误报"))
    return out, {}


def holdout_similarity():
    if not (SKILL / "scripts" / "similarity_check.py").exists():
        return missing("similarity_check.py", ["相似度脚本存在"]), {}
    paras = ref_paragraphs()
    base = ARTICLE.read_text(encoding="utf-8")
    out = []
    src = paras[5]
    fancy = "**" + src[:12] + "**  " + src[12:30] + "\n" + src[30:]
    r = sim_run(base + "\n\n" + fancy)
    out.append(("照搬原文但夹杂加粗、空格、换行仍被判为不通过", (r["json"] or {}).get("overall_pass") is False, f"run={(r['json'] or {}).get('longest_common_run')}"))
    shuffled = []
    for para in paras[3:9]:
        for sent in re.split(r"(?<=[。！？])", para):
            clauses = [c for c in re.split(r"[，,]", sent.rstrip("。！？")) if c]
            if clauses:
                shuffled.append("，".join(reversed(clauses)) + "。")
    r = sim_run(base + "\n\n" + "\n".join(shuffled))
    j = r["json"] or {}
    out.append(("把每句的分句顺序倒过来的改写被标为疑点", j.get("overall_pass") is False or bool(j.get("near_duplicate_sentences")),
                f"run={j.get('longest_common_run')} near={len(j.get('near_duplicate_sentences') or [])} sim={j.get('similarity_display')}"))
    single = RAW / "target_阮一峰" / "issue-411.md"
    r = sim_run(base + "\n\n" + src + "\n", ref=single, name="single.md")
    out.append(("参照给的是单个文件（不是目录）也能检出照搬", (r["json"] or {}).get("overall_pass") is False, f"rc={r['rc'] if r else None}"))
    link = "[OpenClaw 2.0 发布公告](https://openclaw.ai/blog/openclaw-2-accidentally)，另见 https://github.com/openclaw/openclaw/releases/tag/v2026.8.1"
    r = sim_run(base + "\n\n" + link + "\n", name="links.md")
    out.append(("只是引用了对标文章里同一个链接和网址（含 Markdown 链接语法）不判为照搬（取自真实交付稿的一次误报）",
                (r["json"] or {}).get("overall_pass") is True, f"run={(r['json'] or {}).get('longest_common_run')}"))
    r = sim_run(HOLD_AI[0] + "\n" + "\n".join(HOLD_HUMAN) + "\nClaude Code 是 Anthropic 推出的命令行工具。\n", name="short.md")
    out.append(("与对标只共享产品名等短词的短稿通过", (r["json"] or {}).get("overall_pass") is True, f"run={(r['json'] or {}).get('longest_common_run')}"))
    return out, {}


HOLDOUT_CASES = [
    ("holdout-aitell", "留出集·去AI味：没见过的套话写法", holdout_aitell),
    ("holdout-claims", "留出集·真实性：没见过的夸大与编造写法", holdout_claims),
    ("holdout-layout", "留出集·排版：没见过的合法与非法写法", holdout_layout),
    ("holdout-similarity", "留出集·相似度：夹杂格式的照搬和分句倒序改写", holdout_similarity),
]

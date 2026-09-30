#!/usr/bin/env python3
"""wxstyle skill 确定性评测：对同一批夹具运行某个版本的 scripts/，逐条核对断言。

用法：
    python evals/fixture_benchmark/run.py                     # 评测当前 skill，看汇总
    python evals/fixture_benchmark/run.py --skill <旧版目录>   # 评测另一份 skill（比如改动前的快照）做新旧对比
    python evals/fixture_benchmark/run.py --out <目录> --config new_skill   # 同时写出每条断言的 grading.json，可交给 skill-creator 的查看器

不评价文章好不好，只验证机械检查是否可靠：该报的报出来，不该报的不报，异常输入不崩溃。
语料取自 profiles/_raw（对标原文缓存），干净稿取自 evals/fixtures/clean_article.md。任何一条断言没过，退出码为1。
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_ap = argparse.ArgumentParser(description="wxstyle 夹具评测")
_ap.add_argument("--skill", default=str(REPO), help="被评测的 skill 目录，默认是当前这份")
_ap.add_argument("--out", default=None, help="写出 grading.json 等结果的目录；不给就只打印汇总")
_ap.add_argument("--config", default="current", help="结果里的配置名")
_args = _ap.parse_args()
SKILL = Path(_args.skill).resolve()
ITER = Path(_args.out).resolve() if _args.out else None
CONFIG = _args.config
LIVE = REPO           # 语料和干净稿统一取自当前这份 skill，保证不同版本吃同样的输入
RAW = LIVE / "profiles" / "_raw"
ARTICLE = REPO / "evals" / "fixtures" / "clean_article.md"
if not (RAW / "target_阮一峰").is_dir():
    sys.exit("缺少 profiles/_raw/target_阮一峰（对标原文缓存），夹具评测需要它做语料，请先恢复或补充语料")
ENV = dict(os.environ, PYTHONUTF8="1")
TMP = Path(tempfile.mkdtemp(prefix="wxeval_"))


def run(script, *args, timeout=120):
    path = SKILL / "scripts" / script
    if not path.exists():
        return None
    p = subprocess.run([sys.executable, str(path), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=ENV, timeout=timeout)
    try:
        data = json.loads(p.stdout)
    except ValueError:
        data = None
    return {"rc": p.returncode, "stdout": p.stdout, "stderr": p.stderr, "json": data}


def write(name, text, encoding="utf-8", newline="\n"):
    p = TMP / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding=encoding, newline=newline) as f:
        f.write(text)
    return p


def rules(result):
    if not result or not result["json"]:
        return set()
    return {i["rule"] for i in result["json"].get("issues", [])}


def missing(script, checks):
    return [(t, False, f"scripts/{script} 不存在") for t in checks]


def corpus_text(name):
    return {f: open(f, encoding="utf-8-sig").read() for f in sorted(glob.glob(str(RAW / f"target_{name}" / "*")))}


# --------------------------------------------------------------- 排版

BAD_LAYOUT = """# 一级标题
#### 跳级标题

第一行文字
第二行紧跟没有空行

这是**重点。**后面紧跟文字。

字**（括号开头）**结束。

网址 https://example.com/a 出现在正文。

世界【せかい】和食べる{たべる}。

他说"你好"，很直接。

本周发布了新版本。

![](a.png)

![有图](images/a.png)

```
no lang
```

| A | B |
| 1 | 2 |

下面这行会变成标题
---

<br>正文里用了HTML标签<span style="color:red">红字</span>。

【填：占位】

""" + "很长的段落" + "字" * 130 + "\n"

GOOD_GUARDS = """## 章节

（2）**颠覆还早**。官方的速度和价格是自测。

- **速度**：官方称确实这么快。
- **价格**：定价公开。

[Pydantic 的集成文档](https://pydantic.dev/x "Pydantic AI 文档《TypeSafe (Jev)》")写到，上限是 64k token。

> 引用里有“弯引号”，没有问题。

| 列一 | 列二 | 列三 |
| --- | --- | --- |
| a | b | c |

*图注：官方文章“Evidence”一节，2026年9月20日截取。*

1. 第一步
2. 第二步

```python
# 最近的注释 "quoted" 【填】 世界{せかい} https://example.com
print("hi")
```

9月15日发布，不含相对时间。
"""


def layout_defects():
    r = run("check_layout.py", "--file", write("bad.md", BAD_LAYOUT))
    if r is None:
        return missing("check_layout.py", ["排版检查脚本存在"]), {}
    got = rules(r)
    want = {
        "h1_in_body": "正文含一级标题 # 被标出",
        "heading_skip": "标题跳级（1级直接到4级）被标出",
        "merged_lines": "相邻两行无空行会并段，被标出",
        "bold_closing": "加粗以标点结尾且紧跟汉字，被标出",
        "bold_opening": "加粗以标点开头且紧接前文，被标出",
        "bare_url": "正文裸网址被标出",
        "ruby_syntax": "汉字后紧跟【】或{}会被转注音，被标出",
        "straight_quote": "中文正文直引号被标出",
        "relative_time": "“本周”等相对时间词被标出",
        "image_no_alt": "无 alt 的图片被标出",
        "image_local": "本地图片路径记为待办",
        "code_no_lang": "代码块缺语言标注被标出",
        "table_no_separator": "表格缺分隔行被标出",
        "setext_heading": "文字下一行紧跟 --- 会变成标题，被标出",
        "html_tag": "正文含 HTML 标签被标出",
        "placeholder": "【填：】占位符记为待办",
        "long_para": "超长段落被标出",
    }
    return [(t, k in got, f"命中规则：{sorted(got)}" if k not in got else "已命中") for k, t in want.items()], {"result": r["json"]}


def layout_guards():
    r = run("check_layout.py", "--file", write("guards.md", GOOD_GUARDS))
    if r is None:
        return missing("check_layout.py", ["排版检查脚本存在"]), {}
    j = r["json"] or {}
    issues = [(i["level"], i["rule"], i["line"]) for i in j.get("issues", []) if i["level"] in ("error", "warn")]
    return [("合法写法（标点在星号外、链接标题含括号、代码块内的【】和引号、三列表格、弯引号）零误报",
             not issues, f"误报：{issues}" if issues else "零误报")], {"result": j}


def layout_robust():
    out, results = [], {}
    cases = {
        "BOM 开头的文件能识别 ## 标题": ("bom.md", "\ufeff## 标题\n\n正文一。\n", "utf-8", "\n"),
        "CRLF 换行的文件不误报并段": ("crlf.md", "## 标题\r\n\r\n正文一。\r\n\r\n正文二。\r\n", "utf-8", "\r\n"),
        "空文件不崩溃": ("empty.md", "", "utf-8", "\n"),
        "无末尾换行的文件不崩溃": ("nonl.md", "## 标题\n\n正文", "utf-8", "\n"),
    }
    for text, (name, body, enc, nl) in cases.items():
        if enc == "utf-8" and name == "crlf.md":
            p = TMP / name
            p.write_bytes(body.encode("utf-8"))
        elif name == "bom.md":
            p = TMP / name
            p.write_bytes(body.encode("utf-8"))
        else:
            p = write(name, body, enc, nl)
        r = run("check_layout.py", "--file", p)
        if r is None:
            return missing("check_layout.py", ["排版检查脚本存在"]), {}
        j = r["json"] or {}
        ok = "Traceback" not in r["stderr"] and r["json"] is not None
        if name == "bom.md":
            ok = ok and j.get("stats", {}).get("h2") == 1
        if name == "crlf.md":
            ok = ok and j.get("issue_count", {}).get("error") == 0
        out.append((text, ok, f"rc={r['rc']} stderr={r['stderr'][:80]!r} stats={j.get('stats')}"))
    r = run("check_layout.py", "--file", TMP / "nonexistent.md")
    out.append(("文件不存在时返回错误 JSON，不抛异常",
                r is not None and "Traceback" not in r["stderr"] and r["json"] is not None and r["rc"] != 0,
                f"rc={r['rc']} out={r['stdout'][:80]!r}" if r else "脚本不存在"))
    return out, results


def layout_real():
    r = run("check_layout.py", "--file", ARTICLE)
    if r is None:
        return missing("check_layout.py", ["排版检查脚本存在"]), {}
    j = r["json"] or {}
    c = j.get("issue_count", {})
    return [("当前 Jev 交付稿排版检查 0 error", c.get("error") == 0, str(c)),
            ("当前 Jev 交付稿排版检查 0 warn", c.get("warn") == 0, str(c))], {"result": j}


# --------------------------------------------------------------- 去AI味

AI_FAMILIES = {
    "reframe": ["它省下的不是时间，而是你做决定的力气。", "真正的问题不是技术，是认知。"],
    "comparative": ["对普通人来说，方向比努力更重要。", "理解比记忆更关键。"],
    "boilerplate": ["总而言之，AI正在改变世界。", "值得注意的是，成本也在快速下降。"],
    "enumeration": ["首先，我们要明确目标。其次，要选对工具。最后，持续复盘。", "一方面成本在下降，另一方面能力在上升。"],
    "grand_opening": ["在AI飞速发展的今天，每个人都面临新的机遇与挑战。", "随着人工智能技术的不断发展，越来越多的企业开始尝试。"],
    "summary_closer": ["综上所述，这是一个值得关注的方向。", "希望这篇文章对你有所帮助。"],
    "empty_verbs": ["它将赋能千行百业，开启全新篇章。", "下面我们深入探讨一下，不难发现结论很清楚。"],
}


def aitell_recall():
    out = []
    for fam, sents in AI_FAMILIES.items():
        p = write(f"ai_{fam}.txt", "\n".join(sents) + "\n")
        r = run("ai_tell_check.py", "--file", p)
        if r is None:
            return missing("ai_tell_check.py", ["AI味检查脚本存在"]), {}
        hits = (r["json"] or {}).get("hits", []) + (r["json"] or {}).get("weak_alone", [])   # 弱信号单独出现也算“被列出”
        out.append((f"典型「{fam}」套话被标出（{len(sents)}句里至少命中1句）", len(hits) >= 1, f"命中{len(hits)}处"))
    hit_lines = 0
    total = sum(len(s) for s in AI_FAMILIES.values())
    for fam, sents in AI_FAMILIES.items():
        for s in sents:
            r = run("ai_tell_check.py", "--file", write("one.txt", s + "\n"))
            hit_lines += 1 if ((r["json"] or {}).get("hits") or (r["json"] or {}).get("weak_alone")) else 0
    out.append((f"14句典型AI套话整体召回率不低于80%", hit_lines / total >= 0.8, f"{hit_lines}/{total}"))
    return out, {}


def aitell_false_positive():
    out = []
    dens, tot = {}, {}
    for name in ["阮一峰", "数字生命卡兹克", "归藏的AI工具箱"]:
        chars = hits = 0
        for f, t in corpus_text(name).items():
            r = run("ai_tell_check.py", "--file", f)
            if r is None:
                return missing("ai_tell_check.py", ["AI味检查脚本存在"]), {}
            hits += (r["json"] or {}).get("hit_count", 0)
            chars += len(re.sub(r"\s", "", t))
        dens[name] = round(hits / chars * 1000, 3) if chars else 0
        tot[name] = (hits, chars)
    pooled = round(sum(v[0] for v in tot.values()) / sum(v[1] for v in tot.values()) * 1000, 3)
    out.append(("真人语料（阮一峰、卡兹克、归藏，共约22万字）合计每千字命中不超过0.3处，不会满屏误报", pooled <= 0.3, f"合计{pooled}；分语料{dens}"))
    r = run("ai_tell_check.py", "--file", ARTICLE)
    out.append(("当前 Jev 交付稿零命中", (r["json"] or {}).get("hit_count") == 0, f"命中{(r['json'] or {}).get('hit_count')}"))
    p = write("empty.txt", "")
    r = run("ai_tell_check.py", "--file", p)
    out.append(("空文件不崩溃", r["json"] is not None and "Traceback" not in r["stderr"], f"rc={r['rc']}"))
    r = run("ai_tell_check.py", "--file", TMP / "nope.txt")
    out.append(("文件不存在时返回错误 JSON", r["json"] is not None and "Traceback" not in r["stderr"], f"rc={r['rc']}"))
    return out, {"density": dens}


# --------------------------------------------------------------- 相似度

def ref_paragraphs():
    text = open(RAW / "target_阮一峰" / "issue-411.md", encoding="utf-8").read()
    seg = text.split("## OpenClaw 2.0 是一个缩影")[1].split("## 没人为你的堆栈辩护")[0]
    paras = [re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", l).strip() for l in seg.splitlines()]
    return [p for p in paras if len(p) > 35 and not p.startswith(("!", ">"))]


SYN = {"发布": "推出", "大家": "很多人", "已经": "早就", "问题": "麻烦", "建议": "提议", "比较": "相对", "可能": "或许",
       "没有": "并没有", "因为": "由于", "所以": "因此", "但是": "不过", "现在": "如今", "这种": "此类", "非常": "特别",
       "需要": "得", "很多": "不少", "仅仅": "才", "根据": "依照", "开始": "着手", "成为": "变成", "而且": "并且"}


def light_rewrite(text):
    for a, b in SYN.items():
        text = text.replace(a, b)
    sents = re.split(r"(?<=[。！？])", text)
    return "".join(("其实" + s if i % 2 else s) for i, s in enumerate(sents))


def sim_run(gen_text, ref="corpus", *extra, name="gen.md"):
    gen = write(name, gen_text)
    ref_path = RAW / "target_阮一峰" if ref == "corpus" else ref
    return run("similarity_check.py", "--generated", gen, "--reference", ref_path, *extra)


def similarity_detection():
    paras = ref_paragraphs()
    base = ARTICLE.read_text(encoding="utf-8")
    out = []
    r = sim_run(base + "\n\n" + paras[4] + "\n")
    if r is None:
        return missing("similarity_check.py", ["相似度脚本存在"]), {}
    j = r["json"] or {}
    out.append(("整段照搬对标原文（≥40字）被判为不通过并指出来源文件", j.get("overall_pass") is False and bool(j.get("flagged_reference_run")),
                f"run={j.get('longest_common_run')} flagged={j.get('flagged_reference_run')}"))
    order = "\n\n".join(paras[6:2:-1])
    r = sim_run(base + "\n\n" + order)
    out.append(("整段照搬但打乱段落顺序仍被判为不通过", (r["json"] or {}).get("overall_pass") is False, f"run={(r['json'] or {}).get('longest_common_run')}"))
    rew = light_rewrite("\n\n".join(paras[3:9]))
    r = sim_run(base + "\n\n" + rew)
    j = r["json"] or {}
    out.append(("同义词替换加插入语的“轻度洗稿”（整段近似复述）被标为疑点", j.get("overall_pass") is False or bool(j.get("near_duplicate_sentences")),
                f"sim={j.get('similarity_display')} run={j.get('longest_common_run')} near={len(j.get('near_duplicate_sentences') or [])}"))
    src = "\n\n".join(paras[3:9])
    cnt = 0
    chars = []
    for c in src:
        if "一" <= c <= "鿿":
            cnt += 1
            chars.append("某" if cnt % 4 == 0 else c)
        else:
            chars.append("x" if c in "aeiouAEIOU" else c)
    dense = "".join(chars)
    r = sim_run(base + "\n\n" + dense, name="dense.md")
    j = r["json"] or {}
    out.append(("每隔约4个字改动一个字的近似复述（连续重合短于阈值）被标为疑点", j.get("overall_pass") is False or bool(j.get("near_duplicate_sentences")),
                f"sim={j.get('similarity_display')} run={j.get('longest_common_run')} pass={j.get('overall_pass')} near={len(j.get('near_duplicate_sentences') or [])}"))
    r = sim_run(base)
    j = r["json"] or {}
    out.append(("与对标毫无关系的当前 Jev 稿通过", j.get("overall_pass") is True, f"sim={j.get('similarity_display')} run={j.get('longest_common_run')}"))
    # 边界：连续 14 字通过，15 字不通过
    chunk = re.sub(r"[^\w]", "", paras[8])  # \u4e0e\u68c0\u67e5\u811a\u672c\u76f8\u540c\u7684\u5f52\u4e00\u5316\uff08\u53bb\u6807\u70b9\uff09\uff0c\u53d6\u8fde\u7eed\u5b57\u7b26
    for n, want in ((14, True), (15, False)):
        r = sim_run(base + "\n\n" + "这是完全无关的过渡句。" + chunk[:n] + "无关的收尾句子在这里结束。\n", name=f"b{n}.md")
        j = r["json"] or {}
        out.append((f"边界：与对标连续重合{n}字时{'通过' if want else '不通过'}", j.get("passed_run_check") is want, f"run={j.get('longest_common_run')}"))
    return out, {}


def similarity_robust():
    out = []
    base = ARTICLE.read_text(encoding="utf-8")
    r = run("similarity_check.py", "--generated", write("g.md", base), "--reference", TMP / "no_such_dir")
    if r is None:
        return missing("similarity_check.py", ["相似度脚本存在"]), {}
    out.append(("参照路径不存在时返回错误，不给“通过”", "Traceback" not in r["stderr"] and r["rc"] != 0 and (r["json"] or {}).get("overall_pass") is not True, f"rc={r['rc']}"))
    d = TMP / "gbkref"
    d.mkdir(exist_ok=True)
    (d / "a.txt").write_bytes("这是一个用GBK编码保存的参照文件，读取应当失败并被报告。".encode("gbk"))
    r = run("similarity_check.py", "--generated", write("g2.md", base), "--reference", d)
    j = r["json"] or {}
    out.append(("参照含无法解码文件时标为检查不完整，不给“通过”", j.get("overall_pass") is not True and bool(j.get("invalid_references")), f"invalid={len(j.get('invalid_references') or [])}"))
    r = run("similarity_check.py", "--generated", write("empty.md", ""), "--reference", RAW / "target_阮一峰")
    out.append(("正文为空时返回错误，不给“通过”", "Traceback" not in r["stderr"] and (r["json"] or {}).get("overall_pass") is not True, f"rc={r['rc']}"))
    big = "\n\n".join([base] * 12)
    t0 = time.time()
    r = run("similarity_check.py", "--generated", write("big.md", big), "--reference", RAW / "target_阮一峰", timeout=180)
    dt = time.time() - t0
    out.append((f"约3万字正文对20篇参照（21万字）在30秒内跑完", r["rc"] in (0, 1) and dt < 30, f"{dt:.1f}s rc={r['rc']}"))
    return out, {}


# --------------------------------------------------------------- 画像

def base_profile(**over):
    p = {"profile_type": "target", "account_name": "测试号", "confidence": "low", "sample_count": 5,
         "last_updated": "2026-09-21", "title": {"formulas": ["数字体"], "avg_length": 18, "uses_emoji": False}}
    p.update(over)
    return p


def profile_validation():
    out = []
    real = sorted(glob.glob(str(LIVE / "profiles" / "*.json")))
    r = run("validate_profile.py", *real)
    if r is None:
        return missing("validate_profile.py", ["画像校验脚本存在"]), {}
    ok = all(x["valid"] for x in (r["json"] or []))
    out.append((f"当前{len(real)}份真实画像全部通过校验", ok, str([(Path(x['path']).name, x['errors']) for x in (r['json'] or []) if not x['valid']])))
    bad = {
        "profile_type 非法值被拒绝": base_profile(profile_type="other"),
        "缺 account_name 被拒绝": {k: v for k, v in base_profile().items() if k != "account_name"},
        "confidence 非法值被拒绝": base_profile(confidence="great"),
        "sample_count 为负数被拒绝": base_profile(sample_count=-1),
        "sample_count 为布尔值被拒绝": base_profile(sample_count=True),
        "对标画像带己方字段被拒绝": base_profile(self_only_fields={"positioning": "x"}),
        "article_history 重复 id 被拒绝": base_profile(profile_type="self", self_only_fields={"article_history": [
            {"article_id": "a", "updated_at": "2026-01-01", "hook": "h", "status": "draft"},
            {"article_id": "a", "updated_at": "2026-01-02", "hook": "h", "status": "draft"}]}),
        "已发布文章缺发布日期被拒绝": base_profile(profile_type="self", self_only_fields={"article_history": [
            {"article_id": "a", "updated_at": "2026-01-01", "hook": "h", "status": "published"}]}),
        "旧 recent_hook_types 字段被拒绝": base_profile(profile_type="self", self_only_fields={"recent_hook_types": ["x"]}),
    }
    for text, prof in bad.items():
        p = write("prof_" + str(abs(hash(text))) + ".json", json.dumps(prof, ensure_ascii=False))
        r = run("validate_profile.py", p)
        out.append((text, r["rc"] == 1 and not r["json"][0]["valid"], f"rc={r['rc']}"))
    p = write("notjson.json", "{not json")
    r = run("validate_profile.py", p)
    out.append(("非 JSON 文件被报告为无效，不抛异常", r["rc"] == 1 and "Traceback" not in r["stderr"], f"rc={r['rc']}"))
    return out, {}


def profile_consistency():
    out = []
    # 夹具目录：模拟 profiles/ 与 profiles/_raw/ 的关系
    d = TMP / "profiles"
    (d / "_raw" / "target_甲号").mkdir(parents=True)
    for i in range(3):
        (d / "_raw" / "target_甲号" / f"a{i}.md").write_text(f"样本{i}的正文。" * 30, encoding="utf-8")
    prof = base_profile(account_name="甲号", confidence="high", sample_count=25)
    (d / "target_甲号.json").write_text(json.dumps(prof, ensure_ascii=False), encoding="utf-8")
    r = run("validate_profile.py", d / "target_甲号.json")
    if r is None:
        return missing("validate_profile.py", ["画像校验脚本存在"]), {}
    j = (r["json"] or [{}])[0]
    text = json.dumps(j, ensure_ascii=False)
    out.append(("sample_count(25) 与 _raw 目录实际样本数(3) 不一致被标出", j.get("valid") is False or bool(j.get("warnings")), text[:160]))
    prof2 = base_profile(account_name="甲号", confidence="high", sample_count=3)
    (d / "target_甲号.json").write_text(json.dumps(prof2, ensure_ascii=False), encoding="utf-8")
    j = (run("validate_profile.py", d / "target_甲号.json")["json"] or [{}])[0]
    out.append(("样本只有3篇却标 confidence=high 被标出", j.get("valid") is False or bool(j.get("warnings")), json.dumps(j, ensure_ascii=False)[:160]))
    real = glob.glob(str(LIVE / "profiles" / "target_*.json"))
    bad = []
    for f in real:
        raw = RAW / Path(f).stem
        prof = json.load(open(f, encoding="utf-8"))
        n = len([x for x in raw.glob("*") if x.is_file()]) if raw.exists() else -1
        if n != prof["sample_count"]:
            bad.append((Path(f).name, prof["sample_count"], n))
    out.append(("真实对标画像的 sample_count 与 _raw 缓存文件数一致", not bad, f"不一致：{bad}" if bad else "全部一致"))
    r = run("profile_stats.py", "--dir", RAW / "target_阮一峰")
    if r is None or not r["json"]:
        out.append(("提供可复现的画像统计脚本，并能复算阮一峰样本数", False, "scripts/profile_stats.py 不存在或无输出"))
    else:
        s = r["json"]
        out.append(("提供可复现的画像统计脚本，并能复算阮一峰样本数", s.get("file_count") == 20, f"file_count={s.get('file_count')}"))
        out.append(("画像统计脚本给出段长、图片、加粗、问号等指标", all(k in s for k in ("avg_paragraph_chars", "images", "bold", "question_marks")), f"keys={sorted(s)[:12]}"))
    return out, {}


def profile_summary():
    out = []
    for f in sorted(glob.glob(str(LIVE / "profiles" / "*.json"))):
        r = run("render_profile_summary.py", f)
        if r is None:
            return missing("render_profile_summary.py", ["画像摘要脚本存在"]), {}
        s = (r["json"] or {}).get("summary", "")
        quoted = re.findall(r"「([^」]*)」", s)
        long_q = [q for q in quoted if len(q) > 40]
        out.append((f"{Path(f).name} 的人话摘要不超过400字，且不整段搬运字段原文",
                    r["rc"] == 0 and len(s) <= 400 and not long_q, f"{len(s)}字，超长引用{len(long_q)}处"))
    p = write("min.json", json.dumps({"profile_type": "target", "account_name": "极简", "confidence": "low", "sample_count": 1}, ensure_ascii=False))
    r = run("render_profile_summary.py", p)
    out.append(("只有必填字段的画像也能生成摘要，不崩溃", r["rc"] == 0 and "Traceback" not in r["stderr"], f"rc={r['rc']} err={r['stderr'][-80:]!r}"))
    return out, {}


# --------------------------------------------------------------- 内容真实性

FAKE_HEAD = """我亲测了三天，效果非常稳定。

我用它跑了100条数据，准确率达到95%。

实测下来，它比 ChatGPT 快很多。

速度提升了300%，成本降低一半。

只需3分钟就能上手。

这是全网最强的AI工具，绝对不会出错。

它已经彻底解决了幻觉问题，100%准确。

这个功能刷屏了，网友都在说太强了。

评论区有人说：“用了就回不去了。”

过渡段一。

过渡段二。

过渡段三。

"""
BENIGN = """官方称，Jev 快40到200倍。

据教程，延迟中位数是每篇256毫秒，作者自述。

举一个我编的例子：客服每天处理300条工单。

从文档看，Jev 更适合做判断，不适合写长文。

我是程序员，读完这些资料，用人话讲一遍。

第一步，写清问题。第一个是 Hassan 的网站。

9月15日发布，2026年9月20日截取。

据 DEV 的一篇教程转述，下面两个都是作者自述。

他先给 1018 篇论文写摘要，花了 3.99 美元。

再让 Jev 选主题，花了 0.08 美元。

Pydantic 的集成文档写到，上限是 64k token。
"""


def claim_checks():
    r = run("claim_check.py", "--file", write("fake.md", FAKE_HEAD))
    checks = ["内容真实性检查脚本存在", "编造的第一人称实测/体验被标出", "无来源的具体数字被标出", "绝对化承诺（最强、绝对、彻底解决、100%）被标出",
              "无数据支撑的热度说法（刷屏、网友都在说）被标出", "无来源的评论引语被标出", "作者提供实测记录时（--hands-on）不再标第一人称体验"]
    if r is None:
        return missing("claim_check.py", checks), {}
    j = r["json"] or {}
    got = rules(r)
    out = [(checks[0], True, "存在"),
           (checks[1], "first_person_experience" in got, f"{sorted(got)}"),
           (checks[2], "unattributed_number" in got, f"{sorted(got)}"),
           (checks[3], "extreme_claim" in got, f"{sorted(got)}"),
           (checks[4], "unsupported_heat" in got, f"{sorted(got)}"),
           (checks[5], "unsourced_quote" in got, f"{sorted(got)}")]
    r2 = run("claim_check.py", "--file", TMP / "fake.md", "--hands-on")
    out.append((checks[6], "first_person_experience" not in rules(r2) and "unattributed_number" in rules(r2), f"{sorted(rules(r2))}"))
    return out, {"result": j}


def claim_guards():
    checks = ["带归因的数字、我编的例子、免责声明、日期、文档转述都不误报", "当前 Jev 交付稿没有真实性疑点"]
    r = run("claim_check.py", "--file", write("benign.md", BENIGN))
    if r is None:
        return missing("claim_check.py", checks), {}
    got = [(i["rule"], i["message"][:30]) for i in (r["json"] or {}).get("issues", [])]
    out = [(checks[0], not got, f"误报：{got}" if got else "零误报")]
    r = run("claim_check.py", "--file", ARTICLE)
    got = [(i["rule"], i["line"]) for i in (r["json"] or {}).get("issues", [])]
    out.append((checks[1], not got, f"疑点：{got}" if got else "零疑点"))
    return out, {}


def article_quality():
    """对当前交付稿做与 skill 版本无关的内容核对（对应 workflow_cases 中的 evidence_intro、integration）。"""
    t = ARTICLE.read_text(encoding="utf-8")
    body = t
    out = []
    out.append(("不写“我没用过”式自我免责，也不留【填】占位", not re.search(r"我(?:还|从)?没有?(?:实际|亲自)?(?:用过|试过|测过|跑过)|没有包含我自己的|【填", body), "无"))
    out.append(("不编第一人称体验：没有“亲测/实测下来/我用它跑了”", not re.search(r"亲测|实测下来|我用它跑|我测试了|我试了", body), "无"))
    plines = [l for l in body.splitlines() if l.strip()]
    nums, unattributed = [], []
    for i, l in enumerate(plines):
        if re.search(r"\d+(\.\d+)?\s*(倍|毫秒|美元|秒)", l) and not l.startswith("|"):
            nums.append(l)
            window = "".join(plines[max(0, i - 2):i + 1])   # 同段或前两段有归因即可
            if not re.search(r"官方|据|教程|自述|他称|文档|写到|价格|定价", window):
                unattributed.append(l[:30])
    out.append(("性能和价格数字都保留厂商或来源归因", not unattributed, f"缺归因：{unattributed}" if unattributed else f"{len(nums)}行均有归因"))
    out.append(("尽早说明接入门槛：前8段内讲清“给开发者用的接口”", "给开发者用的接口" in "\n".join(body.splitlines()[:16]), "开头结论段"))
    out.append(("不宣称开箱即用：全文无“开箱即用/一键/零门槛”", not re.search(r"开箱即用|一键|零门槛|人人都能", body), "无"))
    out.append(("给不同读者可执行的下一步（不写代码的人 / 开发者）", "如果你不写代码" in body and "如果你是开发者" in body, "两类读者建议均在"))
    return out, {}


CASES = [
    ("layout-defects-detected", "排版：已知缺陷是否都能被检出", layout_defects),
    ("layout-false-positive-guards", "排版：合法写法不误报", layout_guards),
    ("layout-robustness", "排版：BOM、CRLF、空文件等异常输入", layout_robust),
    ("layout-real-article", "排版：当前交付稿", layout_real),
    ("aitell-recall", "去AI味：典型套话召回", aitell_recall),
    ("aitell-false-positive", "去AI味：真人语料误报", aitell_false_positive),
    ("similarity-detection", "相似度：照搬、洗稿、边界", similarity_detection),
    ("similarity-robustness", "相似度：异常输入与性能", similarity_robust),
    ("profile-validation", "画像：结构校验", profile_validation),
    ("profile-consistency", "画像：样本数与置信度一致性、统计可复现", profile_consistency),
    ("profile-summary", "画像：人话摘要可读性", profile_summary),
    ("truth-claim-detection", "真实性：编造体验、无来源数字、绝对化、热度", claim_checks),
    ("truth-false-positive-guards", "真实性：归因数字和免责声明不误报", claim_guards),
]


exec(compile(open(Path(__file__).with_name("holdout_cases.py"), encoding="utf-8").read(), "holdout_cases.py", "exec"))
CASES += HOLDOUT_CASES


def main():
    summary = []
    for idx, (cid, title, fn) in enumerate(CASES):
        t0 = time.time()
        try:
            expectations, extra = fn()
        except Exception as e:  # noqa: BLE001
            expectations, extra = [(f"用例执行完成（{type(e).__name__}）", False, str(e)[:200])], {}
        dt = time.time() - t0
        exp = [{"text": t, "passed": bool(p), "evidence": str(e)} for t, p, e in expectations]
        passed = sum(1 for x in exp if x["passed"])
        if ITER is not None:
            run_dir = ITER / f"eval-{idx}-{cid}" / CONFIG / "run-1"
            (run_dir / "outputs").mkdir(parents=True, exist_ok=True)
            grading = {"expectations": exp,
                       "summary": {"passed": passed, "failed": len(exp) - passed, "total": len(exp),
                                   "pass_rate": round(passed / len(exp), 4) if exp else 0.0}}
            (run_dir / "grading.json").write_text(json.dumps(grading, ensure_ascii=False, indent=2), encoding="utf-8")
            (run_dir / "timing.json").write_text(json.dumps({"total_tokens": 0, "duration_ms": int(dt * 1000), "total_duration_seconds": round(dt, 2)}), encoding="utf-8")
            (run_dir / "outputs" / "results.md").write_text(
                f"# {title}\n\n配置：{CONFIG}\n\n" + "\n".join(f"- [{'通过' if x['passed'] else '未通过'}] {x['text']}\n  - {x['evidence']}" for x in exp) + "\n",
                encoding="utf-8")
            if extra:
                (run_dir / "outputs" / "raw.json").write_text(json.dumps(extra, ensure_ascii=False, indent=2), encoding="utf-8")
            meta = ITER / f"eval-{idx}-{cid}" / "eval_metadata.json"
            meta.write_text(json.dumps({"eval_id": idx, "eval_name": cid, "prompt": title,
                                        "assertions": [x["text"] for x in exp]}, ensure_ascii=False, indent=2), encoding="utf-8")
        summary.append((cid, passed, len(exp)))
        print(f"{cid:34s} {passed}/{len(exp)}")
        for x in exp:
            if not x["passed"]:
                print(f"    未通过：{x['text']}\n      {x['evidence']}")
    tp = sum(p for _, p, _ in summary)
    tt = sum(t for _, _, t in summary)
    print(f"TOTAL {CONFIG}: {tp}/{tt} = {tp / tt:.1%}")
    return 0 if tp == tt else 1


if __name__ == "__main__":
    sys.exit(main())

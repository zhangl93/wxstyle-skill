#!/usr/bin/env python3
"""
画像人话摘要生成器

用于 wxstyle-list / wxstyle-analyze 存完画像后：把画像 JSON 的关键字段
模板拼接成2-3句人话摘要，不用每次都靠 LLM 现场组织语言重新翻译一遍。

用法：
    python render_profile_summary.py <画像.json 路径>

返回 JSON：
    {"account_name": "...", "profile_type": "target", "summary": "人话摘要文本"}
"""

import argparse
import json
import sys
from pathlib import Path


def label(text, limit: int = 24) -> str:
    """字段值常是"标签：详细说明"的长句，摘要只取标签部分，并限制长度，避免把整段分析搬进人话摘要。"""
    t = str(text).strip()
    for sep in ("：", ":", "——", "（", "(", "。"):
        t = t.split(sep)[0]
    t = t.strip("'\"“”‘’ ")
    return t if len(t) <= limit else t[:limit] + "…"


def pct_top(argumentation: dict) -> str:
    """argumentation 里占比最高的维度，翻译成人话。"""
    labels = {"story_pct": "讲故事/场景演绎", "data_pct": "摆数据/引证据", "case_pct": "举案例"}
    if not argumentation:
        return ""
    present = {k: v for k, v in argumentation.items() if k in labels and isinstance(v, (int, float))}
    if not present:
        return ""
    top_key = max(present, key=present.get)
    return labels[top_key]


def render_target_or_shared(profile: dict) -> list:
    parts = []

    title = profile.get("title") or {}
    formulas = title.get("formulas")
    if formulas:
        parts.append("标题偏爱" + "、".join(f"「{label(f)}」" for f in formulas[:2]))

    opening = profile.get("opening") or {}
    hooks = opening.get("hook_types")
    if hooks:
        parts.append("开头常用" + "、".join(f"「{label(h)}」" for h in hooks[:2]))

    tone = profile.get("tone") or {}
    person = tone.get("person")
    colloquial = tone.get("colloquial_level")
    tone_bits = []
    if person:
        # person 字段有时是完整描述句（不只是"第一人称"这种短标签），只取第一个分句人话化
        tone_bits.append(label(str(person).split("，")[0]))
    if colloquial is not None:
        tone_bits.append(f"口语化程度{colloquial}/5")
    if tone_bits:
        parts.append("，".join(tone_bits))

    rhetoric = profile.get("rhetoric") or {}
    rq = rhetoric.get("rhetorical_question_freq")
    if rq:
        rq_short = str(rq).split("（")[0].split("(")[0].strip()
        parts.append(f"反问频率{rq_short}")

    arg_top = pct_top(profile.get("argumentation") or {})
    if arg_top:
        parts.append(f"论证上偏爱{arg_top}")

    ending = profile.get("ending") or {}
    ending_style = ending.get("style")
    if ending_style:
        parts.append(f"结尾走「{label(ending_style)}」")

    return parts


def render_self_only(profile: dict) -> list:
    parts = []
    self_fields = profile.get("self_only_fields") or {}

    positioning = self_fields.get("positioning")
    if positioning:
        parts.append(f"定位：{label(positioning, 30)}")

    cta = self_fields.get("cta_style")
    if cta:
        parts.append(f"CTA风格：{label(cta, 30)}")

    depth = self_fields.get("content_depth")
    if depth:
        parts.append(f"内容深度：{label(str(depth).split('，')[0])}")

    for preference in self_fields.get("visual_preferences", []):
        parts.append(f"{preference['scope']}配图优先：{'、'.join(preference['preferred_sources'])}")

    return parts


def render_summary(profile: dict) -> str:
    account = profile.get("account_name", "未命名账号")
    profile_type = profile.get("profile_type", "target")
    confidence = profile.get("confidence", "unknown")
    sample_count = profile.get("sample_count", 0)
    method = profile.get("generation_method")

    header = f"{account}（{'对标' if profile_type == 'target' else '己方'}画像，confidence={confidence}"
    header += f"，{sample_count}篇样本" if sample_count else ""
    header += "）"
    if method and confidence == "bootstrap":
        header += f"——{label(method, 40)}"

    body_parts = render_target_or_shared(profile)
    if profile_type == "self":
        body_parts.extend(render_self_only(profile))

    if not body_parts:
        body = "暂无足够字段生成摘要，建议补充分析样本。"
    else:
        body = "；".join(body_parts) + "。"

    return f"{header}：{body}"


def main():
    parser = argparse.ArgumentParser(description="生成风格画像的人话摘要")
    parser.add_argument("profile_path", help="画像 JSON 文件路径")
    args = parser.parse_args()

    path = Path(args.profile_path)
    if not path.exists():
        print(json.dumps({"error": f"画像文件不存在: {args.profile_path}"}, ensure_ascii=False))
        sys.exit(1)

    try:
        profile = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        print(json.dumps({"error": f"画像文件不是合法JSON: {e}"}, ensure_ascii=False))
        sys.exit(1)

    summary = render_summary(profile)
    output = {
        "account_name": profile.get("account_name"),
        "profile_type": profile.get("profile_type"),
        "summary": summary,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    # Windows 下重定向的输出默认是 GBK，统一改成 UTF-8，调用方不用设环境变量
    import sys as _sys
    for _stream in (_sys.stdout, _sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    main()

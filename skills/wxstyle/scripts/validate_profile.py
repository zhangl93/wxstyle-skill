#!/usr/bin/env python3
"""校验画像的重要约束；只读，不推断旧记录日期或发布状态。"""
import argparse
import json
from pathlib import Path


# 画像顶层允许的字段，与 references/style-profile-schema.md 保持一致；额外的观察写进 notes
ALLOWED_TOP_LEVEL_KEYS = [
    "profile_type", "account_name", "confidence", "sample_count", "last_updated", "recent_topics", "generation_method",
    "title", "opening", "paragraph_rhythm", "tone", "rhetoric", "argumentation", "ending", "visual_rhythm", "layout_details",
    "self_only_fields", "observation_basis", "non_transferable_identity", "notes",
]


def validate(profile):
    errors = []
    if not isinstance(profile, dict):
        return ["画像必须是对象"]
    if profile.get("profile_type") not in {"self", "target"}:
        errors.append("profile_type无效")
    if not isinstance(profile.get("account_name"), str) or not profile["account_name"].strip():
        errors.append("account_name缺失")
    if profile.get("confidence") not in {"low", "medium", "high", "bootstrap"}:
        errors.append("confidence无效")
    count = profile.get("sample_count")
    if type(count) is not int or count < 0:
        errors.append("sample_count须为非负整数")
    fields = profile.get("self_only_fields", {})
    if not isinstance(fields, dict):
        return errors + ["self_only_fields须为对象"]
    if "recent_hook_types" in profile or "recent_hook_types" in fields:
        errors.append("旧recent_hook_types须迁移到article_history；不明历史存入legacy_hook_observations")
    if "image_preference" in fields:
        errors.append("旧image_preference须迁移为按范围记录的visual_preferences")
    if profile.get("profile_type") == "target" and fields:
        errors.append("对标画像不得写入己方字段")
    history = fields.get("article_history", [])
    if not isinstance(history, list):
        return errors + ["article_history须为列表"]
    ids, dates = [], []
    for row in history:
        if not isinstance(row, dict) or not all(isinstance(row.get(k), str) and row[k].strip() for k in ("article_id", "updated_at", "hook")):
            errors.append("article_history记录缺少article_id/updated_at/hook")
            continue
        ids.append(row["article_id"])
        dates.append(row["updated_at"])
        if row.get("status") not in {"draft", "delivered", "published"}:
            errors.append("文章status无效")
        if row.get("status") == "published" and not row.get("published_date"):
            errors.append("已发布文章缺少真实发布日期")
    if len(ids) != len(set(ids)):
        errors.append("同一文章修订必须更新原记录，不可重复article_id")
    if dates != sorted(dates):
        errors.append("article_history须按updated_at从旧到新")
    preferences = fields.get("visual_preferences", [])
    if not isinstance(preferences, list):
        return errors + ["visual_preferences须为列表"]
    for item in preferences:
        if not isinstance(item, dict) or not all(item.get(k) for k in ("scope", "preferred_sources", "basis", "recorded_at")):
            errors.append("配图偏好缺少范围、来源类型、用户依据或记录日期")
        elif not isinstance(item["preferred_sources"], list) or not all(isinstance(x, str) and x for x in item["preferred_sources"]):
            errors.append("preferred_sources须为非空字符串列表")
    return errors


def consistency_warnings(profile, path):
    """结构合法之外的一致性提示：样本数与原文缓存、置信度与样本数。只提示，不判无效。"""
    warnings = []
    if not isinstance(profile, dict):
        return warnings
    count = profile.get("sample_count")
    confidence = profile.get("confidence")
    unknown = [k for k in profile if k not in ALLOWED_TOP_LEVEL_KEYS]
    if unknown:
        warnings.append("画像里有schema未登记的顶层字段：" + "、".join(unknown) + "；额外观察请放进 notes，或先在 style-profile-schema.md 登记")
    if type(count) is int:
        if confidence == "high" and count <= 20:
            warnings.append(f"confidence=high 需要20篇以上样本，当前sample_count={count}")
        elif confidence == "medium" and count < 15:
            warnings.append(f"confidence=medium 需要15篇以上样本，当前sample_count={count}")
        raw = Path(path).resolve().parent / "_raw" / Path(path).stem
        if raw.is_dir():
            actual = len([f for f in raw.rglob("*") if f.is_file() and f.suffix.lower() in {".txt", ".md"}])
            if actual != count:
                warnings.append(f"sample_count={count}，但 _raw/{raw.name} 里只有{actual}个样本文件；重复或修订样本不应增加计数，缺缓存则相似度自检无从比对")
        elif count > 0 and profile.get("profile_type") == "target":
            warnings.append(f"没有找到 _raw/{Path(path).stem} 原文缓存，合规自检的相似度比对会失效")
    return warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profiles", nargs="+")
    args = parser.parse_args()
    results = []
    for name in args.profiles:
        warnings = []
        try:
            data = json.loads(Path(name).read_text(encoding="utf-8-sig"))
            errors = validate(data)
            warnings = consistency_warnings(data, name)
        except (OSError, ValueError) as error:
            errors = [str(error)]
        results.append({"path": name, "errors": errors, "warnings": warnings, "valid": not errors})
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return int(any(not r["valid"] for r in results))


if __name__ == "__main__":
    # Windows 下重定向的输出默认是 GBK，统一改成 UTF-8，调用方不用设环境变量
    import sys as _sys
    for _stream in (_sys.stdout, _sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())

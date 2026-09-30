#!/usr/bin/env python3
"""只读检查图文文件一致性；不替代事实、版权或视觉审核。"""
import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import unquote


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def image_targets(text):
    return re.findall(r'!\[[^\]]*\]\(\s*(<[^>]+>|[^\s)]+)(?:\s+"[^"]*")?\s*\)', text)


def audit(directory):
    directory = Path(directory)
    article = directory / "article.md"
    text = article.read_text(encoding="utf-8-sig")
    data = json.loads((directory / "delivery.json").read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("delivery.json须为对象")
    errors, warnings = [], []
    digest = file_hash(article)
    if not text.strip():
        errors.append("正文为空")
    if data.get("article_sha256") != digest:
        errors.append("正文哈希与交付记录不同，需同步并复核")
    for key, choices in {"text_status": {"draft", "complete"}, "visual_status": {"not_requested", "pending", "complete"}, "review_status": {"pending", "complete"}}.items():
        if data.get(key) not in choices:
            errors.append(f"{key}无效")
    if data.get("review_status") == "complete" and data.get("reviewed_article_sha256") != digest:
        errors.append("审核未覆盖当前正文")
    pending = data.get("pending_items")
    if not isinstance(pending, list) or not all(isinstance(x, str) and x.strip() for x in pending):
        errors.append("pending_items须为非空字符串组成的列表")
        pending = []
    assets = data.get("assets")
    if not isinstance(assets, list):
        raise ValueError("assets须为列表")
    ids, ready_paths = [], set()
    for asset in assets:
        if not isinstance(asset, dict):
            errors.append("素材记录须为对象")
            continue
        if not all(isinstance(asset.get(k), str) and asset[k].strip() for k in ("id", "kind", "purpose")):
            errors.append("素材缺少id/kind/purpose")
        ids.append(str(asset.get("id")))
        status = asset.get("status")
        if status not in {"ready", "pending", "omitted"}:
            errors.append("素材状态无效")
        if status in {"pending", "omitted"} and not asset.get("note"):
            errors.append(f"素材{asset.get('id')}缺少原因")
        if status == "pending" and (data.get("visual_status") != "pending" or not pending):
            errors.append("待补素材与visual_status/pending_items不一致")
        if status == "ready":
            path = asset.get("path")
            if not isinstance(path, str) or not path:
                errors.append("ready素材缺少本地path")
                continue
            resolved = (directory / path).resolve()
            if not resolved.is_file():
                errors.append(f"素材不存在：{path}")
            ready_paths.add(resolved)
            if "screenshot" in str(asset.get("kind")) and not str(asset.get("source_url", "")).startswith(("https://", "http://")):
                errors.append("截图缺少source_url")
    if len(ids) != len(set(ids)):
        errors.append("素材id重复")
    targets = image_targets(text)
    if len(targets) != text.count("![") or re.search(r"<img\b", text, re.I):
        errors.append("存在不支持的图片语法，转为标准Markdown或人工处理")
    for target in targets:
        target = unquote(target.strip("<>"))
        if target.startswith(("https://", "http://", "data:")):
            errors.append("远程/内嵌图片尚未完成本地素材核验")
            continue
        path = (directory / target).resolve()
        if not path.is_file():
            errors.append(f"正文图片缺失：{target}")
        if path not in ready_paths:
            errors.append(f"正文图片没有ready素材记录：{target}")
    if data.get("visual_status") == "complete" and not targets:
        errors.append("图文标完成但正文没有图片")
    if data.get("visual_status") == "not_requested" and (targets or assets):
        errors.append("有素材却标为not_requested")
    if data.get("visual_status") == "pending" and not pending:
        errors.append("图片待补但缺少待办")
    if data.get("review_status") != "complete":
        warnings.append("编辑审核未完成")
    ready = (not errors and not pending and data.get("text_status") == "complete"
             and data.get("visual_status") in {"complete", "not_requested"}
             and data.get("review_status") == "complete")
    return {"article_sha256": digest, "image_count": len(targets), "errors": errors,
            "warnings": warnings, "pending_items": pending, "structural_pass": not errors,
            "ready_for_delivery": ready, "limitation": "不验证线上事实、截图真伪、授权或视觉质量"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory")
    args = parser.parse_args()
    try:
        output = audit(args.directory)
    except (OSError, ValueError, TypeError) as error:
        output = {"errors": [str(error)], "structural_pass": False, "ready_for_delivery": False}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if output["ready_for_delivery"] else (1 if output["structural_pass"] else 2)


if __name__ == "__main__":
    # Windows 下重定向的输出默认是 GBK，统一改成 UTF-8，调用方不用设环境变量
    import sys as _sys
    for _stream in (_sys.stdout, _sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    raise SystemExit(main())

#!/usr/bin/env python3
"""读百度热搜实时榜，输出排名、热度分和摘要，供“找选题”标热度依据。

只读公开、不用登录的页面；页面里找不到数据（改版、返回验证页、网络出错）就报错退出，不重试、不绕过。
热搜不新增候选，只给粗筛留下的候选标热度（SKILL.md“找选题”）。关键词命中只是初筛：摘要里提到“大模型”或“AI生成”不等于这条新闻的主角是 AI。

用法：
    python hot_list.py                      # 实时抓取
    python hot_list.py --file saved.html    # 解析保存下来的页面（测试用，不联网）
"""
import argparse
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

URL = "https://top.baidu.com/board?tab=realtime"
AI_WORDS = re.compile(r"AI|AIGC|人工智能|大模型|智能体|机器人|生成式|深度伪造|换脸|数字人|算法|"
                      r"ChatGPT|OpenAI|DeepSeek|Claude|Gemini|豆包|Kimi|通义|文心", re.I)


def fail(msg):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    return 2


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", errors="replace")


def parse(html):
    m = re.search(r"<!--s-data:(.*?)-->", html, re.S)
    if not m:
        raise ValueError("页面里没有 s-data 数据块：可能改版了，或返回的是验证页")
    card = json.loads(m.group(1))["data"]["cards"][0]
    pinned = {x.get("word") for x in card.get("topContent") or []}
    items = []
    for x in card.get("content") or []:
        word, desc = x.get("word", ""), x.get("desc", "")
        is_pinned = word in pinned
        items.append({
            "rank": None if is_pinned else int(x["index"]) + 1,
            "pinned": is_pinned,
            "word": word,
            "hot_score": int(x["hotScore"]) if str(x.get("hotScore", "")).isdigit() else None,
            "desc": desc,
            "url": x.get("url", ""),
            "ai_keyword_hit": bool(AI_WORDS.search(word + desc)),
        })
    if not items:
        raise ValueError("数据块里没有热搜条目")
    return items, card.get("updateTime")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="解析本地保存的页面，不联网")
    args = ap.parse_args()

    try:
        if args.file:
            html = Path(args.file).read_text(encoding="utf-8")
        else:
            html = fetch(URL)
        items, update_time = parse(html)
    except FileNotFoundError:
        return fail(f"文件不存在：{args.file}")
    except Exception as e:  # 网络、编码、结构变化都在这里报出来，不悄悄返回空列表
        return fail(f"热搜没读到：{e}")

    bj = timezone(timedelta(hours=8))
    fetched_at = datetime.now(bj).strftime("%Y-%m-%d %H:%M")
    if str(update_time).isdigit():
        update_time = datetime.fromtimestamp(int(update_time), bj).strftime("%Y-%m-%d %H:%M")
    print(json.dumps({
        "source": "百度热搜实时榜",
        "url": URL if not args.file else str(args.file),
        "fetched_at": fetched_at,
        "page_update_time": update_time,
        "item_count": len(items),
        "ai_keyword_hits": [x for x in items if x["ai_keyword_hit"]],
        "items": items,
        "note": "关键词命中只是初筛；热搜不新增候选，只给粗筛留下的候选标热度。热度依据写排名、热度分和 fetched_at。",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8")
    sys.exit(main())

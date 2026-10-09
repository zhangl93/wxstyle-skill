#!/usr/bin/env python3
"""生成公众号封面：文字卡（暖色渐变底，一个大字加一行小字），或把 ChatGPT 等生成的图裁成封面尺寸并可叠字。

对应 SKILL.md“输出”的封面保底，和 references/title-and-cover.md“选画面”里的“文字主导”方向。要点：
- 头条大图 900×383；转发和列表里会裁成中间的 383×383，所以大字宽度限制在安全区内，
  同时输出裁切预览（square_preview），检查有没有被切掉。
- 封面上的字合计不超过 10 个，超了直接报错，不悄悄缩小。
- 大字放不进安全区就报错，不缩到看不清。

需要 Pillow（pip install pillow）；其余脚本只用标准库，这个脚本是可选的。字体按系统自动找：Windows 用微软雅黑，
macOS 用冬青黑体（Hiragino Sans GB），Linux 用 Noto Sans CJK 或文泉驿正黑；都找不到时用 --font-bold / --font 指定。

--bg 用一张已有的图（如 ChatGPT 生成的无字插画）当背景：居中裁成 900×383，可选再叠字（叠字时加一层半透明暗色保证可读）。
背景图至少 900×383，比例不对时居中裁切，主体要放在图的中间。

用法：
    python make_cover_card.py --big 85% --small 官方示例 --out images/cover-card.png
    python make_cover_card.py --bg images/cover-raw.png --out images/cover-card.png
    python make_cover_card.py --bg images/cover-raw.png --big 85% --small 官方示例 --out images/cover-card.png
"""
import argparse
import json
import sys
from pathlib import Path

W, H = 900, 383
SAFE_MARGIN = 30          # 中间 383×383 安全区两侧留白
MAX_CHARS = 10
SCALE = 2                 # 2倍渲染再缩小，边缘更平滑
# 按顺序取第一个存在的字体：Windows、macOS、Linux 常见的中文字体。
# 第二项是 .ttc 里的字形序号：Hiragino Sans GB 的 2 是 W6 粗体；Noto Sans CJK 的 2 是简体中文（0 是日文）。
# macOS 的华文黑体 STHeiti 序号 0 是繁体，所以不用它。
BOLD_CANDIDATES = [
    (r"C:\Windows\Fonts\msyhbd.ttc", 0),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 2),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 2),
    ("/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc", 2),
    ("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Bold.ttc", 2),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
]
REGULAR_CANDIDATES = [
    (r"C:\Windows\Fonts\msyh.ttc", 0),
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", 0),
    ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 2),
    ("/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", 2),
    ("/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc", 2),
    ("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 0),
]


def first_existing(candidates):
    return next(((p, i) for p, i in candidates if Path(p).exists()), None)


def fail(msg):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    return 2


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--big", default="", help="大字，如 85%%")
    ap.add_argument("--small", default="", help="小字，如 官方示例")
    ap.add_argument("--bg", default="", help="背景图路径（如 ChatGPT 生成的无字插画）；不给则用暖色渐变文字卡")
    ap.add_argument("--out", required=True, help="输出 PNG 路径")
    ap.add_argument("--font-bold", default=None, help="大字用的粗体字体路径；不给就按系统自动找")
    ap.add_argument("--font", default=None, help="小字用的常规字体路径；不给就按系统自动找")
    args = ap.parse_args()

    if not args.big and not args.bg:
        return fail("至少给 --big（文字卡）或 --bg（背景图）之一")
    total = len((args.big + args.small).replace(" ", ""))
    if total > MAX_CHARS:
        return fail(f"封面上的字合计{total}个，超过{MAX_CHARS}个；缩短，或改用不带字的封面")
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return fail("需要 Pillow：pip install pillow")
    fonts = {}                # attr -> (路径, .ttc 序号)；用户指定的字体用序号 0
    if args.big:
        for attr, candidates in (("font_bold", BOLD_CANDIDATES), ("font", REGULAR_CANDIDATES)):
            given = getattr(args, attr)
            if given is not None:
                if not Path(given).exists():
                    return fail(f"找不到字体：{given}")
                fonts[attr] = (given, 0)
                continue
            found = first_existing(candidates)
            if found is None:
                tried = "、".join(p for p, _ in candidates)
                return fail(f"没找到可用的中文字体（试过：{tried}），用 --font-bold / --font 指定")
            fonts[attr] = found

    on_photo = bool(args.bg)
    if on_photo:
        bgp = Path(args.bg)
        if not bgp.exists():
            return fail(f"找不到背景图：{args.bg}")
        src = Image.open(bgp).convert("RGB")
        if src.width < W or src.height < H:
            return fail(f"背景图{src.width}×{src.height}太小，至少{W}×{H}")
        # 先按宽度缩到 W×SCALE，再居中裁出 H×SCALE 的高度；比目标更扁的图按高度缩放
        scale = max(W * SCALE / src.width, H * SCALE / src.height)
        src = src.resize((round(src.width * scale), round(src.height * scale)), Image.LANCZOS)
        left, top_ = (src.width - W * SCALE) // 2, (src.height - H * SCALE) // 2
        img = src.crop((left, top_, left + W * SCALE, top_ + H * SCALE))
        if args.big:
            img = Image.blend(img, Image.new("RGB", img.size, (0, 0, 0)), 0.35)   # 叠字时压暗，保证可读
    else:
        img = Image.new("RGB", (W * SCALE, H * SCALE))
        px = img.load()
        top, bot = (255, 244, 224), (255, 224, 178)
        for y in range(H * SCALE):
            t = y / (H * SCALE - 1)
            c = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
            for x in range(W * SCALE):
                px[x, y] = c
    d = ImageDraw.Draw(img)

    big_w = 0
    if args.big:
        max_w = H - 2 * SAFE_MARGIN
        size, font = 250, None
        while size >= 60:
            f = ImageFont.truetype(fonts["font_bold"][0], size * SCALE, index=fonts["font_bold"][1])
            b = d.textbbox((0, 0), args.big, font=f)
            if (b[2] - b[0]) <= max_w * SCALE:
                font = f
                break
            size -= 2
        if font is None:
            return fail(f"大字“{args.big}”放不进 {max_w}px 的安全区（字号缩到60仍太宽）；缩短")

        def center(text, fnt, cy, fill):
            b = d.textbbox((0, 0), text, font=fnt)
            w, h = b[2] - b[0], b[3] - b[1]
            d.text(((W * SCALE - w) / 2 - b[0], cy * SCALE - h / 2 - b[1]), text, font=fnt, fill=fill)
            return (b[2] - b[0]) / SCALE

        big_w = center(args.big, font, 168 if args.small else H / 2, (255, 255, 255) if on_photo else (194, 65, 12))
        if args.small:
            center(args.small, ImageFont.truetype(fonts["font"][0], 40 * SCALE, index=fonts["font"][1]), 300, (255, 235, 210) if on_photo else (124, 74, 30))


    img = img.resize((W, H), Image.LANCZOS)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, optimize=True)
    preview = out.with_name("_" + out.stem + "-square-preview.png")
    img.crop(((W - H) // 2, 0, (W - H) // 2 + H, H)).save(preview)
    print(json.dumps({"out": str(out), "size": [W, H], "square_preview": str(preview),
                      "big_text_width": round(big_w), "note": "检查 square_preview：转发卡片会裁成这个1:1，字不能被切"},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8")
    sys.exit(main())

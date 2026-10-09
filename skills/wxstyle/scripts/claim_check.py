#!/usr/bin/env python3
"""内容真实性机械预检：找出最容易出问题的写法，交给人和 LLM 复核来源。

只查表面特征，不能核实事实，也不能证明一句话是真的：
- first_person_experience：出现“我亲测/实测下来/我用它跑了”这类第一人称体验，
  而作者没有提供实测记录（默认视为未提供；有记录时加 --hands-on）
- unattributed_number：带单位的具体数字，本段和前两段里都没有“官方称/据…/自述”等归因
- extreme_claim：最强、绝对、100%、彻底解决等绝对化承诺（广告法风险）
- unsupported_heat：刷屏、爆火、网友都在说等热度说法，同段没有链接或数据
- unsourced_quote：“网友说：……”“评论区有人说：……”这类引语，同段没有来源链接
- self_disclaimer：正文里“我没试过/本文没有我自己的实测”这类自我免责，读者会觉得矛盾，改用来源归属的写法
- unsupported_generalization：“大多数产品都不会这么写”这类没有数据的断言，删掉或换成有来源的说法
- author_promise：替作者向读者许诺具体的后续行动（“我去跑一遍”“下一篇拆给你看”）

标题不在正文里（放在 review.md），用 --title 或 --review 一并检查：绝对化用词、热度词、无归因的数字，
以及标题党用语（clickbait_title）。标题没有上下文可以给数字做归因，所以数字必须在标题里自带来源。

用法：python claim_check.py --file <正文.md> [--hands-on] [--title 标题]... [--review review.md]
"""
import argparse
import json
import re
import sys
from pathlib import Path

ATTRIBUTION = re.compile(r"官方|据|教程|文档|文章|称|自述|表示|报道|数据显示|根据|声称|宣称|写到|写明|注明|原文|论文|研究|发布会|财报|公告|来源|转述|我编|假设|示例|示意|比如|例如|举个例子|举一个|虚构")
HYPOTHETICAL = re.compile(r"我编|假设|假如|倘若|示例|示意|虚构|比如|例如|举个例子|举一个|如果你|如果每")
NUMBER = re.compile(r"[一二三四五六七八九十两]分之[一二三四五六七八九十]|(?<![\d.])\d+(?:\.\d+)?\s*(?:%|％|倍|毫秒|秒钟|分钟|小时|美元|元|万|亿|条|篇|个|次|天|GB|MB|k|K)|百分之[一二三四五六七八九十百\d]+|(?:提升|提高|降低|下降|增长|减少|节省|节约)了?\s*\d")
DATE = re.compile(r"\d+\s*年|\d+\s*月|\d+\s*日|\d+\s*号|第\s*\d+\s*(?:步|期|个|条|种|点)|\d+\s*种|\d+\s*步")
EXPERIENCE = re.compile(r"我(?:亲自|亲)?(?:测试|实测|测了|试了|试用|用了|跑了|体验了|跑通|做了个测试)|亲测|实测(?:下来|结果|发现)|亲身(?:试|用|体验)|(?:我|笔者|本人|自己)(?:也|又|已经)?(?:上手|试用|使用|用)了?[一二三四五六七八九十两\d]+(?:天|周|个月|次|晚|小时)|跑了(?:一晚上|一整晚|一夜|一天)|笔者(?:测试|实测|发现)|我(?:自己)?(?:发现|感觉|觉得)(?:它|这个).{0,6}(?:比|更)")
NEGATED_EXPERIENCE = re.compile(r"(?:没有|没|无|未|尚未|不含|不包含|缺少|暂无|并未)[^，。；]{0,14}(?:实测|测试|跑过|试过|用过|体验)")
EXTREME = re.compile(r"全网第一|行业第一|世界第一|国内第一|业内第一|唯一(?:一个|的)|首个|最(?:强|佳|先进|便宜|安全|稳定|牛)|最快(?!的速度|速度)|史上最|100\s*[%％]|百分之百|绝对|永久|永远|彻底(?:解决|消除|颠覆|取代)|一劳永逸|秒杀|碾压|吊打|完爆|零风险|万无一失|包治|保证(?:有效|成功|不会)")
HEAT = re.compile(r"刷屏|爆火|火遍|火爆全网|全网(?:都在|热议)|网友(?:们)?都在说|大家都在(?:用|说)|刷爆|热搜|疯传|引爆")
HEAT_DATA = re.compile(r"点赞|转发|阅读|播放|数据显示|榜|排名|\]\(http")
QUOTE = re.compile(r"(?:网友|评论区|有人|读者|用户|开发者|粉丝|观众)(?:们)?(?:说|表示|评论|留言|感叹|写道)[：:，,]?\s*[“\"「]")


# 拿一个没有数据支撑的“大多数/很少有/没有人”断言给自己的观点撑场面。有归因（据调研、官方称）时不算。
GENERALIZATION = re.compile(
    r"大多数(?:产品|公司|团队|厂商|同行|人)[^，。！？\n]{0,8}?(?:不会|不这么|不这样|都会)"
    r"|很少有(?:产品|公司|团队|厂商|人|创业公司)[^，。！？\n]{0,6}?(?:会|愿意)"
    r"|没有(?:厂商|公司|团队|人|产品)[^，。！？\n]{0,6}?(?:会|愿意)"
    r"|市面上大多数[^，。！？\n]{0,10}?不"
)

# 替作者向读者许诺具体的后续行动（去测、写下一篇），作者没说过就不能替作者答应。
# “点个关注，我会继续跟进”这类泛泛的号召不算，它是作者画像里的结尾习惯
PROMISE = re.compile(r"我(?:会|将|打算|准备|挑|之后|下次|回头)[^。！？\n]{0,20}?(?:试|测|跑一遍|跑一下|拆|写|更新|分享)|下一篇[^。！？\n]{0,10}(?:试着|来|写|讲|拆|聊)")


# 正文里的第一人称自我免责（“我没试过”“本文没有我自己的实测”）：写了文章却声明自己没用过，读者会觉得矛盾。
# 用来源归属的写法代替（“官方文档写的是……”“社区里有人测过……”），但仍然不能编“我测了”。
SELF_DISCLAIMER = re.compile(r"我(?:还|从)?(?:没有?|未|不曾)(?:实际|亲自|真正|真的)?(?:用过|试过|测过|测试过|使用过|跑过|体验过|上手)|没有包含我自己的(?:实测|测试|体验)|我自己(?:也)?(?:还)?没(?:有)?(?:用过|试过|测过)|本文没有(?:我的|作者的)(?:实测|测试)")


CLICKBAIT = re.compile(r"震惊|吓死|不看后悔|必看|速看|赶紧看|疯了|惊呆|炸裂|重磅|绝了|没想到|不转不|看完.{0,4}沉默")


def titles_from_review(path):
    """读 review.md 里的候选标题。当前模板（title-and-cover.md）写成表格：
    表头某一列是"候选标题"，标题在该列。旧格式（"标题候选："后面跟编号/列表）也继续支持，
    兼容还没升级模板的旧文章。"""
    lines = Path(path).read_text(encoding="utf-8-sig").splitlines()

    # 先找表格：表头行里有"候选标题"这一列
    for i, line in enumerate(lines):
        if "|" not in line or "候选标题" not in line:
            continue
        headers = [h.strip() for h in line.strip().strip("|").split("|")]
        try:
            col = headers.index("候选标题")
        except ValueError:
            continue
        if i + 1 >= len(lines) or not re.match(r"^\s*\|?[\s:-]+\|", lines[i + 1]):
            continue  # 下一行不是分隔行，这行"|候选标题|"只是碰巧同名，不是表头
        titles = []
        for row in lines[i + 2:]:
            if "|" not in row:
                break
            cells = [c.strip() for c in row.strip().strip("|").split("|")]
            if col >= len(cells) or not cells[col]:
                continue  # 空白占位行跳过，不当成一个标题
            titles.append(cells[col])
        if titles:
            return titles

    # 退回旧格式："标题候选"那一行之后连续的编号或列表项
    titles, started = [], False
    for line in lines:
        if not started:
            started = "标题候选" in line
            continue
        m = re.match(r"^\s*(?:\d+[.、）)]|[-*])\s*(.+?)\s*$", line)
        if m:
            titles.append(re.sub(r"（推荐.*?）|（当前）", "", m.group(1)).strip())
        elif titles and line.strip():
            break
        elif titles and not line.strip():
            break
    return titles


def check_title(title):
    """返回 [(规则, 提示)]。"""
    found = []
    attributed = bool(ATTRIBUTION.search(title))
    if EXTREME.search(title) and not attributed:
        found.append(("extreme_claim", "标题里有绝对化用词，无依据不要写"))
    if HEAT.search(title):
        found.append(("unsupported_heat", "标题里有热度词，没有数据支撑"))
    if CLICKBAIT.search(title):
        found.append(("clickbait_title", "标题党用语，容易被认为夸大或误导"))
    if len(title) > 30:
        found.append(("title_length", f"标题{len(title)}字，手机信息流里会被截断；把关键信息放前面，或压到30字内"))
    if NUMBER.search(DATE.sub("", title)) and not attributed and not HYPOTHETICAL.search(title):
        found.append(("unattributed_number", "标题里的具体数字没有来源，标题里没法附归因，要么写“官方称”，要么去掉数字"))
    return found


def sentences(par):
    return [s for s in re.split(r"(?<=[。！？!?；;])", par) if s.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--file", help="正文；只查标题时可以不给")
    ap.add_argument("--hands-on", action="store_true", help="作者已提供真实实测记录，不再标第一人称体验")
    ap.add_argument("--title", action="append", default=[], help="要检查的标题，可重复")
    ap.add_argument("--review", help="review.md 路径，读取其中“标题候选”列出的标题")
    args = ap.parse_args()
    if not args.file and not args.title and not args.review:
        print(json.dumps({"error": "至少给 --file、--title 或 --review 其中一个"}, ensure_ascii=False))
        return 2
    lines = []
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(json.dumps({"error": f"文件不存在: {args.file}"}, ensure_ascii=False))
            return 2
        lines = path.read_text(encoding="utf-8-sig").splitlines()

    # 收集正文段落（跳过代码块、表格、标题、图片、图注），保留行号
    paras = []
    in_code = False
    for no, line in enumerate(lines, 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code or not line.strip() or line.lstrip().startswith(("|", "#", "![", "*图注", "*配图")):
            continue
        paras.append((no, line))

    issues = []

    def add(level, no, rule, text, msg, source="body"):
        issues.append({"level": level, "line": no, "rule": rule, "text": text.strip()[:80], "message": msg, "source": source})

    for idx, (no, par) in enumerate(paras):
        window = "".join(p for _, p in paras[max(0, idx - 2): idx + 1])   # 同段和前两段
        window_has_attr = bool(ATTRIBUTION.search(window))
        for sent in sentences(par):
            plain = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", sent)
            if not args.hands_on and EXPERIENCE.search(plain) and not NEGATED_EXPERIENCE.search(plain):
                add("pending", no, "first_person_experience", plain,
                    "出现第一人称体验或实测，需要作者提供真实记录（环境、输入、输出、日期）；没有就删掉或改成资料转述")
            if SELF_DISCLAIMER.search(plain):
                add("warn", no, "self_disclaimer", plain,
                    "正文里写“我没试过”会让读者觉得矛盾；删掉这句，改用来源归属的写法（官方文档写的是……、社区里有人测过……），仍然不能写“我测了”")
            gm = GENERALIZATION.search(plain)
            if gm and not ATTRIBUTION.search(plain[max(0, gm.start() - 15):gm.end()]):
                # 只看断言前后的小范围，句子前半句里不相关的"官方"不能让这句话的断言免检
                add("warn", no, "unsupported_generalization", plain,
                    "拿“大多数/很少有/没有人”这类没有数据的断言给观点撑场面；删掉，或换成有来源的说法、明确标为个人观察")
            if PROMISE.search(plain):
                add("pending", no, "author_promise", plain,
                    "替作者向读者许诺了以后的行动；作者没说过就删掉，或改成【填：…】让作者决定")
            if EXTREME.search(plain) and not ATTRIBUTION.search(plain):
                add("warn", no, "extreme_claim", plain, "绝对化承诺，无依据不要写；改成有条件、有来源的说法")
            number_hit = NUMBER.search(plain)
            if number_hit and not HYPOTHETICAL.search(plain) and not window_has_attr:
                stripped = DATE.sub("", plain)
                if NUMBER.search(stripped):
                    add("warn", no, "unattributed_number", plain, "具体数字没有来源或归因（官方称/据…/自述）；补来源、标为假设，或删掉")
        if HEAT.search(par) and not HEAT_DATA.search(par):
            add("warn", no, "unsupported_heat", par, "热度说法没有数据或链接支撑；没有互动数据就不要称热门、刷屏或共识")
        if QUOTE.search(par) and not re.search(r"\]\(http", par):
            add("warn", no, "unsourced_quote", par, "引用网友或评论原话，需要原帖链接或截图；没有来源就不能当作真实评论")

    titles = list(args.title)
    if args.review:
        review_path = Path(args.review)
        if not review_path.exists():
            print(json.dumps({"error": f"文件不存在: {args.review}"}, ensure_ascii=False))
            return 2
        titles += titles_from_review(review_path)
    for title in titles:
        for rule, msg in check_title(title):
            add("warn", 0, rule, title, msg, source="title")

    result = {
        "titles_checked": len(titles),
        "issues": issues,
        "issue_count": {"warn": sum(1 for i in issues if i["level"] == "warn"),
                        "pending": sum(1 for i in issues if i["level"] == "pending")},
        "check_type": "claim_precheck",
        "mechanical_pass": not issues,
        "hands_on_record_provided": args.hands_on,
        "limitation": "只查表面写法，不核实事实；零疑点不代表内容真实，仍需对照来源逐条核对",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    # Windows 下重定向的输出默认是 GBK，统一改成 UTF-8，调用方不用设环境变量
    import sys as _sys
    for _stream in (_sys.stdout, _sys.stderr):
        if hasattr(_stream, "reconfigure"):
            _stream.reconfigure(encoding="utf-8")
    sys.exit(main())

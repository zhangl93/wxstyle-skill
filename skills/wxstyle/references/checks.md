# 检查脚本说明

脚本只做机械预检：零命中不代表文章质量合格，也不代表内容真实，命中也不代表必须删除。命中要由人或LLM复核，再决定改不改。路径都相对本skill的基准目录，输出是UTF-8的JSON。

## 写作阶段的三个脚本

```text
python scripts/ai_tell_check.py --file <正文>
python scripts/similarity_check.py --generated <正文> --reference <对标原文目录>
python scripts/claim_check.py --file <正文> [--hands-on] [--review <review.md>]
```

### ai_tell_check：AI味

- 分强弱两档。强信号见一次就计入 hits；弱信号单独出现只列在 weak_alone，附近5行内还有别的信号才计入。weak_alone 也要扫一眼。
- 作者自己的习惯不算AI味：画像写明的写法（如号召式结尾“欢迎评论区聊聊”）用 `--allow engagement_bait` 这类参数放行，输出里的 `allowed` 会记录放行了什么。
- 引用块、引号和书名号里的文字、代码块不检查，引用别人的话不算作者自己的AI味。
- 只提供疑点，不证明自然或原创。靠整体语感的写法（三段式并列、抛问题收尾等）抓不住，最终要靠人读。

全部26个类别：

| 类别 | 说明 |
|---|---|
| `reframe` | 「不是A，是B」重新框定句 |
| `comparative_payoff` | 「X比Y更重要/更值钱」比较收尾句 |
| `boilerplate_transition` | AI高频过渡词/框架句（总而言之/值得注意的是） |
| `grand_opening` | 「在……的今天/时代」式宏大开场 |
| `summary_closer` | 「综上所述/总的来说」式收尾套话 |
| `empty_phrases` | 空泛动词与套话（赋能/深入探讨/不难发现） |
| `closer_saying` | 「这才是真正的关键」式假装深刻的收尾金句 |
| `enumeration` | 「首先……其次……」式机械并列 |
| `sweeping_inclusion` | 「无论……还是……都」式全覆盖表述 |
| `assertive_filler` | 「毫无疑问」式加重语气的空话 |
| `buzzwords` | AI常用词（显著提升/全方位/一站式） |
| `sequence_markers` | 段首连用“首先是/其次是”式顺序词 |
| `repeated_openings` | 连续多段用同一个词开头 |
| `bold_labels` | 列表项用加粗小标签开头 |
| `bold_density` | 加粗过密 |
| `one_line_closers` | 每一节都以一句话短句收尾 |
| `decorative_headings` | 标题里带 emoji 等装饰符号 |
| `heading_echo` | 小标题的原话又在下一段第一句重复一遍 |
| `fragmented_paragraphs` | 大量一句话独占一段，段落多且平均很短（借鉴blader/humanizer） |
| `stock_frame` | 套路框架句（没有统一答案/关键看你/身边不少朋友） |
| `engagement_bait` | 「欢迎在评论区聊聊」式互动收尾 |
| `chatbot_residue` | 聊天助手残留（当然可以/作为AI，借鉴blader/humanizer） |
| `doc_meta` | 写文章本身而不是内容（本文将从……） |
| `inflated_significance` | 拔高意义（标志着新篇章/至关重要） |
| `no_specifics` | 整体缺具体细节：没有数字、括号补充或第一人称经历（借鉴blader/humanizer） |
| `template_heading` | 模板化小标题（写在最后/结语） |

其中 `reframe` 额外覆盖两个变体写法“不只是A，而是B”“不在于A，而在于B”。

**这类正则检测有漏检上限，不再无限追加变体**：套路句式的变体几乎写不完，每发现一个新变体就加一条正则，边际成本会越来越高，而且下一个变体大概率还是漏的。已经覆盖的这几种是真实撞见过的高频写法，值得保留；再遇到新的漏网变体，优先判断值不值得单独加规则——只有反复出现、明显影响可信度的才加，零星一次的不必追。这类检测的真实定位是"抓最常见的几种"，不是"抓所有"，最终还是要靠人读。相比之下，`first_person_experience`、`unattributed_number` 这类涉及内容真实性的规则值得优先维护，句式套路类的规则性价比更低。

### claim_check：内容真实性

- 标出编造的第一人称体验（`first_person_experience`）、正文里的“我没试过”式自我免责（`self_disclaimer`，改用来源归属的写法）、无来源的具体数字（`unattributed_number`）、绝对化承诺（`extreme_claim`）、无数据的热度说法（`unsupported_heat`）、无来源的评论引语（`unsourced_quote`）、没有数据支撑的概括断言（`unsupported_generalization`，“大多数产品都不会这么写”），以及替作者向读者许下的具体承诺（`author_promise`，“我去跑一遍”“下一篇拆给你看”）。
- 作者提供了真实实测记录才加 `--hands-on`；否则第一人称体验一律当待办处理：删掉、改成资料转述，或向作者要记录。
- 标题不在正文里，而在 review.md 的“标题候选”，所以要加 `--review` 一并检查标题（绝对化用词、热度词、标题党用语、没有归因的数字）；也可以用 `--title` 单独传。
- 只查表面写法，零疑点不代表内容真实，仍要对照来源核对。

### similarity_check：相似度

- 除N-gram和连续重合外，还会列出“近似句”：整句相似但连续重合很短，如逐字微调的改写。
- 默认阈值是内部复核提示（N-gram低于15%、连续重合少于15字符），不是法律判断。链接、产品名等重合结合片段判断。
- 缺有效参照标为不可检查，不写通过。
- 骨架相同、只换了说法的仿写，脚本查不出来，要人看结构。
- 相似冲突最多针对性重写两次，仍未解决则保留说明，不无限重试。

## 交付阶段

- `python scripts/check_layout.py --file article.md`：排版语法。error 必须处理，warn 人工判断，pending（占位符、本地图片）写入待办。输出的 `stats.body_chars` 是正文字数，报字数用它，不用按字节计的 `wc -c`（中文会被放大约3倍）。
- `python scripts/check_delivery.py <文章目录>`：只核对文件、哈希和素材清单，不代替事实或视觉审核。

## 画像阶段

- 画像里的数字（段长、句长、配图、加粗、问号等）用 `python scripts/profile_stats.py --dir profiles/_raw/{账号}/` 统计，不凭阅读估计。它按整篇统计，只想看某一部分（如周刊头条）时，先把该部分另存成单独样本文件。语气、开头类型等风格判断仍靠人读，并写明依据的样本。
- `python scripts/validate_profile.py <画像路径>`：error 表示结构无效；warnings 提示样本数与 `_raw` 缓存或置信度不一致、出现未登记的字段，要处理或说明。
- `python scripts/render_profile_summary.py <画像路径>`：给用户看简明摘要，让用户当场判断画像准不准。

## 找选题

- `python scripts/hot_list.py`：读百度热搜实时榜，输出每条的排名、热度分、摘要和抓取时间，`ai_keyword_hits` 列出摘要或标题里有 AI 相关词的条目。`--file 页面.html` 只解析本地文件，不联网。命中关键词只是初筛（摘要顺带提一句“大模型”、或者“某视频系 AI 生成”这类社会新闻也会命中，但主角不是 AI），热搜不新增候选，只用来给粗筛留下的候选标热度，见 SKILL.md“找选题”。页面里没有数据块（改版、验证页、网络出错）时退出码为 2，不会返回空列表冒充“今天没有热点”。

## 封面

- `python scripts/make_cover_card.py --big 85% --small 官方示例 --out images/02-cover.png`：生成封面文字卡（900×383），输出中间 1:1 的裁切预览。`--bg 图片路径` 把 ChatGPT 等生成的无字插画居中裁成封面尺寸，可再叠字。封面字合计超过10个、大字放不进安全区会报错。需要 Pillow（`pip install pillow`），其余脚本不需要；字体按系统自动找（Windows 微软雅黑、macOS 冬青黑体、Linux Noto Sans CJK 或文泉驿正黑），都找不到时用 `--font-bold`、`--font` 指定。生成后要看图，尤其是裁切预览。

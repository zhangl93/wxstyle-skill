# wxstyle

一个写公众号文章的 skill（当前版本见 [CHANGELOG.md](CHANGELOG.md)）：先分析对标账号的写法，再结合作者自己的声音写稿，覆盖资料核实、写作、配图、排版和发布前审核。产出是可以粘贴到公众号后台的 Markdown。发布由作者手动完成，不自动发布。

给 Claude 读的说明在 [SKILL.md](SKILL.md)；这份 README 是写给使用者的。

## 它能做什么

- **分析画像**：从对标账号的文章里提取标题、开头、段落节奏、语气、论证和结尾方式，存成画像。
- **仿写**：学结构和节奏，不学句子；语气和立场用作者自己的画像，不冒用对标作者的署名和口头禅。
- **核实**：正文只写有来源的内容；没测过就不写"实测"；作者编的例子必须标明。
- **配图**：优先真实素材（官网截图、真实界面、有上下文的评论），没有就如实标"待补"，不用无关插图或假界面凑数。
- **标题与封面**：标题的三问和写法、封面方案（文字卡、界面截图裁切、生图）和尺寸，见 [title-and-cover.md](references/title-and-cover.md)。
- **工具分工**：Claude、Codex、ChatGPT 各适合做什么，封面提示词交给 ChatGPT 生成后怎么回来裁切（见 [tools-guide.md](references/tools-guide.md)）。
- **结尾问题**：给出读者凭自己经历就能答的具体问题候选，让留言有理由发生（见 [engagement.md](references/engagement.md)）。
- **排版**：按 Markdown 转公众号工具的语法输出，并做机械检查。
- **审核**：出一份审核清单，含质量自评、机械预检结果和待办。

适用范围是微信公众号。不适用：小红书、抖音等其他平台，一般摘要、翻译，或没有公众号语境的通用写作。

## 安装

**环境**：脚本只用 Python 标准库，没有第三方依赖（只有可选的封面文字卡脚本 `make_cover_card.py` 需要 Pillow）（我在 Python 3.14 上测试过，更低版本没验证）。所有脚本都会把输出固定成 UTF-8，不需要再设环境变量。

**目录名要叫 `wxstyle`**，和 `SKILL.md` 里的 `name` 一致。

### 方式一：Claude Code / Claude 桌面应用的 Code 标签页（推荐）

把 skill 目录链接到个人技能目录，所有项目都能用。用链接而不是复制，画像和原文缓存就只有一份，改了不会两边不一致。

```powershell
New-Item -ItemType Junction -Path "$env:USERPROFILE\.claude\skills\wxstyle" -Target "D:\skill\wxstyle-skill"
```

只想在某个项目里用，就把目标换成该项目的 `.claude\skills\wxstyle`。

装好后**新开一个会话**，在技能列表里应该能看到 `wxstyle`；也可以直接说"wxstyle-list"试一下。我没有在你的环境里验证过加载，如果没出现，先确认目录名和链接路径。

想取消，删掉这个链接即可：

```bat
rmdir "%USERPROFILE%\.claude\skills\wxstyle"
```

`rmdir` 只删链接，不会动 `D:\skill\wxstyle-skill` 里的文件（我在临时目录里验证过创建和删除，源文件保留）。不要用 `rd /s` 或 `Remove-Item -Recurse`，那样可能连内容一起删。

### 方式二：打包成 `.skill` 上传（Claude.ai 等）

在 skill-creator 的目录下运行它自带的 `package_skill.py`（要在那个目录里执行，才能找到 `scripts` 包）：

```bash
python -m scripts.package_skill D:\skill\wxstyle-skill <输出目录>
```

打包会带上 `profiles/`：

- `profiles/_raw/`：对标账号的原文缓存，是别人的文章，别分享出去。相似度检查要用它，但不必随 skill 一起打包。
- `profiles/self_*.json`：你自己的画像，是个人数据，按需决定是否带上。
- 文章产出不放在 skill 目录里（默认在项目的 `articles/`，或 skill 同级的 `wxstyle-articles/`），所以不会被打进包。

`evals/` 默认不会被打进包里。上传后的环境能不能运行脚本、能不能写回 `profiles/`，取决于那个环境，我没有验证过。

### 装好后自检

```bash
python -m unittest discover -s evals -p "test_*.py"
```

全部通过（写这一行时是 184 项），说明脚本本身正常。

## 快速开始

直接用自然语言说，或用 `wxstyle-` 开头的命令。

```text
参考数字生命卡兹克的画像，帮我写一篇 XX 的介绍。资料在这里……，我还没实际用过。
```

```text
wxstyle-review 审查一下这篇稿子
```

最小路径：

1. 给 3—5 篇对标账号的文章（链接或粘贴正文）→ `wxstyle-analyze`，得到一份暂定画像。
2. 说明你自己的声音：有历史文章就分析；没有就用几组同题对比句选择，标为 `bootstrap`。
3. `wxstyle-write`：给标题候选、摘要、正文。
4. `wxstyle-publish-prep`：配图和排版。
5. `wxstyle-review`：出审核清单，你按清单读完再发。

## 命令

| 命令 | 做什么 |
|---|---|
| `wxstyle-analyze` / `--self` | 分析文章，生成或更新对标画像 / 己方画像 |
| `wxstyle-write` | 资料核实、标题、摘要、大纲、正文、自评 |
| `wxstyle-publish-prep` | 真实配图、来源、排版 |
| `wxstyle-review` | 评审现有稿或最终稿 |
| `wxstyle-list` | 列出画像，并给人话摘要 |

## 一篇文章的产物

每篇文章放在自己的目录里。没指定位置时，默认是当前项目下的 `articles/日期-主题/`，不放进 skill 目录：

| 文件 | 内容 |
|---|---|
| `article.md` | 当前正文，以它为准，不含 `#` 一级标题；文章标题填公众号后台标题栏 |
| `review.md` | 标题候选、摘要、主张与来源表、质量自评、机械检查结果、待办 |
| `sources.md` | 完整链接和核对日期（正文里只保留来源名） |
| `delivery.json` | 文字、配图、审核三项状态，以及正文和已审核版本的哈希 |
| `images/` | 图片；本地路径只用于预览，发布时要在后台重新上传 |

正文里不留 `【填：…】` 占位符，也不写“我没用过”：没有数据的部分整段删掉，没有实测就用“官方文档写的是……”这类来源归属的写法。你有真实的实测或评论，发给我，我再加进正文。

## 画像

```text
profiles/
  target_{账号名}.json        对标画像
  self_{账号名}.json          己方画像
  _raw/{target|self}_{账号名}/   分析用的原文缓存，相似度检查要用
```

- 样本少的画像只是暂定观察：15 篇以下 `low`，15—20 篇 `medium`，20 篇以上 `high`，没有历史文章的己方画像是 `bootstrap`。
- 画像里的数字应该用脚本统计，不凭感觉估：`profile_stats.py`。
- 画像顶层字段有固定清单，额外的观察写进 `notes`；出现清单外的字段，`validate_profile.py` 会给警告。
- 超过 60 天没更新的画像，`wxstyle-list` 会提醒你检查是否还适用。

## 脚本

脚本输出统一是 UTF-8 的 JSON。

| 脚本 | 用法 | 检查什么 |
|---|---|---|
| `check_layout.py` | `--file article.md` | 一级标题、标题跳级、并段、加粗边界、注音语法、直引号、相对时间词、HTML 标签、重复短语，并输出 `body_chars` 正文字数 |
| `ai_tell_check.py` | `--file article.md [--allow 类别]` | AI 套话句式和结构：强信号见一次就计入，弱信号单独出现只列出、附近有别的信号才计入；不检查引用和代码；还查聊天残留、“标志着新篇章”式拔高、正文整体缺具体细节，以及“没有统一答案”“欢迎在评论区”这类套路框架；结构上查连续同开头、加粗小标签列表、每节一句话收尾、emoji 标题、“写在最后”式模板小标题 |
| `similarity_check.py` | `--generated article.md --reference profiles/_raw/target_xxx` | N-gram 相似度、连续重合、近似句 |
| `claim_check.py` | `--file article.md [--hands-on] [--review review.md] [--title 标题]` | 编造的第一人称体验、无来源数字、绝对化承诺、无数据的热度说法、无来源评论引语、替作者许下的承诺、无数据支撑的概括断言（“大多数产品都不会”）；加 `--review` 或 `--title` 时也检查标题（绝对化、热度词、标题党、无归因数字） |
| `make_cover_card.py` | `--big 85% --small 官方示例 --out images/02-cover.png`，或 `--bg 图片 --out ...` | 生成封面文字卡（900×383），或把 ChatGPT 生成的图裁成封面并可叠字；限制字数，保证字在转发裁切的中间 1:1 内，输出裁切预览。需要 Pillow |
| `check_delivery.py` | `<文章目录>` | 交付文件、哈希和素材清单是否一致 |
| `validate_profile.py` | `profiles/*.json` | 画像结构，以及样本数与 `_raw` 缓存、置信度是否一致 |
| `render_profile_summary.py` | `profiles/xxx.json` | 生成人话摘要 |
| `profile_stats.py` | `--dir profiles/_raw/target_xxx` | 段长、句长、配图、加粗、问号等统计 |

这些脚本只做机械预检：零命中不代表文章质量合格，也不代表内容真实，命中也不代表必须删除。相似度的阈值只是内部提示，不是法律结论。骨架相同、只换了说法的仿写，脚本查不出来，要人看结构。

## 测试

```bash
python -m unittest discover -s evals -p "test_*.py"
```

- `evals/test_*.py`：脚本的回归测试。
- `evals/eval_set.json`：测 skill 是否被正确触发，40 条请求（22 条该触发、18 条不该触发，含小红书、翻译、技术博客等相近的反例，以及“推送”“公号稿”这类简短说法）。
- `evals/fixture_benchmark/run.py`：夹具评测，约 90 条断言，检查脚本该报的报出来、不该报的不报，含没参与调规则的留出集。改脚本后运行 `python evals/fixture_benchmark/run.py`，用 `--skill <旧版目录>` 可以和旧版做对比；需要 `profiles/_raw/target_阮一峰` 作语料。
- `evals/workflow_cases.json`：27 个行为用例，执行方法见 [workflow-evaluation.md](evals/workflow-evaluation.md)；脚本测试不能代替它。

## 目录

```text
SKILL.md              给 Claude 的主说明
references/           画像 schema、素材与交付、社区素材、标题与封面、工具分工、结尾问题、机制讲解结构、配图规则、排版规则、改稿复核、检查脚本说明、审核模板
scripts/              上面的检查脚本
profiles/             画像和原文缓存
evals/                触发评测、行为评测、回归测试
```

## 改这个skill时的一条纪律

新想法（写作原则、结构模板）第一次采纳时，先放进已有文档的一节里，用简短的篇幅记录，不新开文件、不展开成大段落。只有真实用过3次以上、确认有用，才值得升级成独立参考文件或详细章节。没用够3次的内容，在文档开头写明"验证次数"，提醒下次用到时先判断是否还适用，而不是在没有新证据前继续加码。这条纪律是2026-09-30审查时定的，当时发现好几份参考文档（机制讲解结构、工具分工、社区素材）都只有0—1次真实验证，却已经写得很详细。

## 已知限制

- 不含选题的商业判断，也不保证阅读量或涨粉。
- 画像不能替代作者的真实经历；没有实测就只能写资料稿（用来源归属的写法，不编“我试了”）。
- 排版规则来自一份 Markdown 转公众号工具的示例文档，并在 quaily.com 的在线版里实测过（2026-09-24）：脚注会自动生成，分隔线 `---` 没有样式。换了转换工具要重新核对。粘贴进公众号后台后的最终效果我没法测，发布前用手机预览看一眼。
- 图片型账号（条漫、长图）没有可复制的文字，需要先逐张读图转写，工作量大。

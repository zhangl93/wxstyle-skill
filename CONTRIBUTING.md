# 贡献指南

这是个人维护的 skill，欢迎提 issue 和 PR，但节奏可能不快。改动前建议先开个 issue 说一下想法，避免写完了发现方向不对。

## 改之前

先读 [README.md](README.md) 和 [SKILL.md](skills/wxstyle/SKILL.md)，了解这个 skill 解决什么问题、不解决什么问题（"已知限制"那节）。skill 本体在 `skills/wxstyle/` 下（这个布局是为了让 [`npx skills add`](https://github.com/vercel-labs/skills) 这类跨 agent 安装工具能找到它），仓库根目录只放给人看的文档。`references/` 里的文档是给 Claude 读的，不是给人看的架构说明，但改脚本时通常也要跟着改对应的 reference 文档。

## 跑测试

```bash
python -m unittest discover -s skills/wxstyle/evals -p "test_*.py"
```

这是唯一强制要求：PR 提交前必须全绿。测试内容见 [README「测试」](README.md#测试)一节，包括脚本回归测试、触发评测、行为用例。改了 `scripts/*.py` 里任何一条检查规则，大概率也要同步改 `references/checks.md`——`evals/test_skill_docs_contract.py` 里的 `ClaimCheckRuleDocsSyncTests` / `AiTellRuleDocsSyncTests` 会自动检查两边是不是对得上，忘了同步会直接测试失败，不用自己记。

## 加一条新的检查规则

以 `scripts/claim_check.py` 或 `scripts/ai_tell_check.py` 里加一条新规则为例：

1. 在脚本里加规则本身（正则或逻辑）和一个清晰的 `rule` 名字。
2. 在 `references/checks.md` 对应表格里加一行，用规则名字（反引号包住）而不是重新叙述一遍逻辑。
3. 在 `evals/` 里加对应的单元测试，覆盖"应该命中"和"不应该命中"两种情况——只测应该命中的一半，容易把"总是命中"的规则也判定为通过。
4. 跑一遍 `evals/fixture_benchmark/run.py`，确认没有让已有的夹具用例变红。

## 关于"真实数据验证"

这个仓库里吃过一次亏：`claim_check.py` 的 `--review` 功能在真实模板改版后，静默失效了很久，但对应的单元测试因为用了一份写死的旧格式夹具，一直全绿。详见 CHANGELOG 1.9.1。

教训是：**单元测试全绿只能证明"代码按测试写的方式运行"，不能证明"代码在真实数据上按预期运行"。** 改动会影响真实产出格式的地方（模板解析、review.md 结构、画像 schema），提 PR 前如果能找到一份真实的（或至少贴近真实格式的）样本跑一遍，比多写十个断言更有说服力。

## 新想法先别急着写成大段文档

[README「改这个skill时的一条纪律」](README.md#改这个skill时的一条纪律)这条对贡献者同样适用：一个新的写作原则或结构模板，第一次采纳时先放进已有文档的一节，用几句话记录，不新开文件。真实用过 3 次以上确认有用，才值得展开成独立参考文件。没用够的内容，在文档开头写"验证次数"标签。这是从"文档写得很详细但从没被验证过"这类返工里总结出来的。

## 提 Issue

- Bug：附上触发它的输入（哪篇文章、哪个命令）和实际 vs 期望的输出。
- 误报/漏报（某条机械检查规则）：附一句能复现的正文片段，比描述"感觉不对"更容易处理。
- 新功能：先说清楚要解决的具体问题，这个 skill 的范围只在公众号写作，不打算做成通用写作工具。

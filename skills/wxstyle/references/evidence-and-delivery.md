# 素材与交付

## 类型与事实清单

资料介绍解释公开信息；教程有可复现操作路径；实测记录环境、输入、原始输出、日期、样本范围和失败情况；评论分开证据与推断。混合文章按段落区分。

大纲前记录关键主张，列和写法按 SKILL.md 写作流程第2步，类别按「证据规则」表，表放在 review.md，不要求每句话建档。sources.md 只是链接清单：完整链接、核对日期、怎么读的（curl 原文 / 网页总结 / 没读到）。数字、条数、日期回到原文核对，不采信网页摘要工具的转述；能下载原文就下载后再读。核对价格、访问权限、版本等时效信息，不将厂商评测泛化为普遍收益。

读者定位约束承诺：消费应用、网页体验、API接入和生产部署门槛不同。未验证的按钮不编写；练习案例明确标注。

## 当前版本

沿用已有文章目录和图片目录，不为新约定重命名。正文article.md，审核review.md；来源与素材按需要增加。历史稿明确命名，不能多份都叫最终版。

先同步article.md再交付。审核记录article_sha256；正文变化则审核失效，不能只刷新哈希不复核。UTF-8保存。

每篇都建 delivery.json（封面保底让每篇都有图片目录，`check_delivery.py` 也要读它）：

```json
{
  "article_type": "资料介绍",
  "text_status": "complete",
  "visual_status": "pending",
  "review_status": "pending",
  "article_sha256": "正文文件SHA-256",
  "reviewed_article_sha256": null,
  "assets": [
    {"id": "official-intro", "status": "pending", "kind": "official_screenshot", "path": null, "source_url": "https://example.com", "purpose": "核对产品身份", "note": "页面读取失败"}
  ],
  "pending_items": ["取得并审看官方截图"]
}
```

text_status：draft/complete；visual_status：not_requested/pending/complete；review_status：pending/complete。assets.status：pending/ready/omitted。ready须有存在的本地path、kind、purpose；截图须有source_url，AI图kind为ai_generated且保留提示词。pending须有note，待办写入pending_items。pending_items只记交付前还缺、会影响正文的东西（没取到的素材、没核实的说法）；作者审读、手机预览、可选的作者实测是交付之后的事，写在回复和 review.md 的待办里，不进 pending_items，否则 ready_for_delivery 永远为 false。omitted仅为不再需要的候选并写明原因，不能靠省略消除用户要求。

python scripts/check_delivery.py <目录> [--profile <己方画像>] 检查结构、哈希和本地素材引用；还查 images/ 下有没有封面（文件名含 cover），加 --profile 时查画像里这篇是否已写回且 status 为 delivered/published。这两项只影响 ready_for_delivery，不影响 structural_pass。待办存在可通过一致性检查，但ready_for_delivery为false；ready只代表记录与本地文件满足要求，不保证事实、权利或视觉质量。脚本只支持标准Markdown图片，引用式或HTML图片报告为需人工处理。远程图片不自动下载或验证，转成本地已检查文件后再标完成。

## 审核发布

按审核模板填正文依据、结论和待改项，机械结果与编辑结论分开。独立审查（SKILL.md 写作流程第7步）的“必须改”都处理完，才设 review_status 为 complete、reviewed_article_sha256 为当前正文哈希；之后正文再改，要重新复核受影响的部分再刷新哈希。

最终回复格式见SKILL.md“输出”。本地图片需上传公众号后台，检查手机预览。只有用户提供真实发布数据才记录performance_log。


# 画像字段与迁移

现有通用字段保持兼容：profile_type（self/target）、account_name、confidence、sample_count、last_updated、recent_topics、title、opening、paragraph_rhythm、tone、rhetoric、argumentation、ending、visual_rhythm、layout_details。画像仅存结构化观察，原文存_raw。贴图视觉画像另存 `profiles/visual_{主题}.md`，格式见 title-and-cover.md 的“贴图”。顶层字段以 validate_profile.py 里的 ALLOWED_TOP_LEVEL_KEYS 为准，上面这些再加 generation_method、self_only_fields、observation_basis、non_transferable_identity、notes；出现别的顶层字段，校验会给警告。额外的观察（比如“周刊的整体骨架”）写进 notes（字符串列表），不要自己加新的顶层字段。

confidence：bootstrap用于无可靠历史样本的己方冷启动；1—14篇low，15—20篇medium，21篇起high。样本数量不代表预测效果或每个字段可信度。sample_count=0仅bootstrap；去重后计数。数值统计按有效样本权重合并，文本观察不机械加权；重复样本不加计数。

对标可增加observation_basis（样本范围与限制）、non_transferable_identity（自称、署名、专属表达），这些只供识别，不能迁移到成稿。signature_phrases记录观察，不包含“必须保留”等生成命令。少量样本中出现的模式用“当前样本观察到”，不视为作者永恒规则。

self_only_fields仅用于self画像，target省略或留空：

```json
{
  "positioning": "作者优势、目标读者与工作场景",
  "cta_style": "作者自己的收尾习惯",
  "content_depth": "内容深度与使用门槛",
  "visual_style_anchor": "仅生成插画时采用的风格",
  "visual_preferences": [
    {
      "scope": "AI产品介绍",
      "preferred_sources": ["官网截图", "真实操作截图", "有上下文的社区评论"],
      "illustration_use": "适合的封面或抽象解释，不替代产品证据",
      "basis": "用户明确反馈的原意",
      "recorded_at": "2026-09-20"
    }
  ],
  "article_history": [
    {"article_id": "example", "updated_at": "2026-09-20", "hook": "具体场景", "status": "draft"}
  ],
  "performance_log": []
}
```

article_history按updated_at从旧到新，保留最近20篇；相同hook可重复，同一article_id只保留一条当前记录。修改旧稿后按更新时间重新排序。published仅在已知发布时填写published_date；delivered指正文已交付，不代表配图、发布完成。默认看最近5篇的hook，不能对hook去重。

迁移：删除顶层及self_only_fields.recent_hook_types。能确定对应文章的记录并入article_history；无法确定的原值放self_only_fields.legacy_hook_observations并说明来源，不能编日期、排序或发布状态，不用旧观察统计连续次数。image_preference迁移为有范围、有用户依据的visual_preferences；未知值不推断成偏好。

last_updated记录画像最后修改日，sample_count与confidence只在新增可靠样本时改变。仅保存偏好和文章历史不升级声音置信度。generation_method记录冷启动依据。

performance_log只记录用户提供的topic、format（长文/贴图，同一篇的两种形式各记一条）、published_date、reads、likes、new_followers、note；缺失数据留空，不填0冒充。近期选题recent_topics去重追加，引用既往题目只提取方向，不复用案例。

保存后运行 python scripts/validate_profile.py <文件>。该脚本检查关键状态约束，不是全部统计字段的完整JSON Schema验证。


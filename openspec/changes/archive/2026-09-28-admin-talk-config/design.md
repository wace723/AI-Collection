## Context

当前话术系统（talk-001/talk-002）存在三层硬编码缺口：

1. **固定模板靠 seed 脚本**：6 条默认模板写死在 `seed.py`，管理员无法后台增删改；匹配维度四维 `[风险档 × 账龄段 × 场景 × 用户特征]`，与风险档配置（每档几次触达）松耦合，管理员看不到「每档每轮有没有配话术」。
2. **AI 提示词写死在代码**：`generator.build_prompt` 硬编码 system/user prompt，管理员完全改不了；`scene` 固定枚举 `FIRST/SECOND/THIRD`，撑不住「某档配第 4、5 次触达」。
3. **占位符无校验**：`renderer.render` 纯 `str.replace`，不校验未知占位符；管理员手打 `{标的名称}` 一旦拼错（如 `{标地名称}`），渲染后残留花括号给催收员看。`标的名称`等字段已在 Order 模型存在但不在占位符集里。

当前相关数据模型：
- `talk_templates`：`name/risk_tier/age_bucket/scene/user_feature_tag/content/is_active`（4 维匹配 + 单 content）。
- `collection_schedules`：`risk_tier/day_offset/scene/seq`（风险档配置的触达时点，scene 现为 FIRST/SECOND/THIRD）。
- `task.scene`：从 `collection_schedules.scene` 直接拷贝（batch.py:200）。
- `ai_config`：provider/key/base_url/model/开关（连接配置，非 prompt 内容）。

约束（CLAUDE.md 关键设计约束 #2）：LLM 可降级，AI 失败必须回退模板，不阻断催收。

## Goals / Non-Goals

**Goals:**
- 管理员可在后台对「每个风险档 × 每次触达轮次」配置固定模板与 AI 提示词模板。
- 匹配键收敛为二维 `[风险档 × 轮次]`，账龄段/用户特征降为话术变量，降低矩阵爆炸。
- 话术/AI 模板支持插入特征变量（供应商名称、标的名称、概算金额、历史中标率、账龄段、账龄天数、工程局单位等），保存时校验占位符。
- 覆盖度矩阵可视化：按当前 active risk_config 的 schedules 展开，缺口高亮、可点击直接配；风险档变更后提示复核。
- AI 合规基线不被后台 system prompt 绕过。

**Non-Goals:**
- 不做话术模板的版本化/回滚（沿用 is_active 软删除，风险档配置已有版本化，话术层暂不做）。
- 不把 AI 提示词模板混进 ai_config（ai_config 保持连接配置职责）。
- 不做话术 A/B 测试或多模板排序推荐（保留 matcher 精确匹配，去掉 ANY 兜底）。
- 不改 LLMProvider 抽象与降级机制（talk-002 已稳定）。

## Decisions

### D1：匹配键从四维收敛为二维 `[风险档 × 轮次]`
- **选择**：匹配键 = `(risk_tier, scene=ROUND_N)`，精确匹配，**无 ANY 兜底**。
- **理由**：用户决策「就按轮次匹配，不一定要在话术里说明已逾期 xx 天」。账龄段与轮次高度共线（ROUND_1 ≈ 7 天档），四维冗余；收敛二维后矩阵 = 档 × 轮，清晰可管。
- **替代方案**：保留 ANY 兜底——被否（用户选「不保留，严格按格」，缺格显示「未配话术」，倒逼覆盖度管理）。
- **影响**：`matcher.py` 重写；`talk_templates` 的 `age_bucket`/`user_feature_tag` 列保留但不再参与匹配，仅作存档（或后续清理）。

### D2：scene 统一改 ROUND_N，由 schedules seq 驱动
- **选择**：`scene` 取值改为 `ROUND_1/ROUND_2/...ROUND_N`，N = 该档 schedules 的 seq。无固定枚举上限，支持任意轮次。
- **来源**：`ScheduleIn.scene` 不再由前端传固定枚举，而由 `config_service._insert_version` 按 seq 自动生成 `ROUND_{seq}` 写入 `CollectionSchedule.scene`；`batch.py` 生成 Task 时照搬 `sched.scene`（现有逻辑不变，只是值变了）。
- **理由**：用户决策「统一改 ROUND_N」。彻底消除「第 4 轮无枚举」问题；scene 语义从「第几次催收」对齐 seq，自然有序。
- **替代方案**：前 3 轮沿用 FIRST/SECOND/THIRD，第 4 轮起 FOURTH——被否（用户选统一 ROUND_N，更规整）。
- **迁移**：现有 collection_schedules 的 scene 值需从 FIRST/SECOND/THIRD 映射为 ROUND_1/2/3；现有 tasks 的 scene 同步映射；现有 talk_templates 清空重配（D5）。

### D3：一张 TalkTemplate 表带 template_type
- **选择**：`talk_templates` 加列 `template_type`（FIXED / AI_PROMPT）。FIXED 用 `content`；AI_PROMPT 用 `system_prompt` + `user_prompt`（content 置空或不用）。
- **匹配字段共用**：`risk_tier` + `scene`（ROUND_N）+ `template_type` 唯一定位一条模板（一档一轮一类型最多一条；如允许多条则加 priority，MVP 约束唯一）。
- **理由**：用户决策「一张表带 type 字段」。匹配维度共享，不写两套 matcher；AI_PROMPT 字段冗余可接受（FIXED 行 system_prompt 为 NULL）。
- **替代方案**：新建 ai_prompt_templates 表——被否（两套 matcher 维护成本高）。

### D4：占位符统一注册表 + 保存校验 + 插入按钮
- **选择**：新增 `placeholders.py` 注册表，集中定义所有合法占位符及其取值来源（Order/OrderFeature/Task 字段或派生值）。固定模板与 AI 模板共享。保存模板时校验正文/prompt 里的 `{xxx}` 全部合法，非法拒绝（400）并返回未知占位符列表。
- **占位符集**（在现有 7 个基础上扩展）：
  - 现有保留：`{供应商名称}` `{service_fee_order_no}` `{订单号}` `{风险档}` `{场景}` `{应催日}` `{会员状态}`
  - 新增：`{标的名称}` `{概算金额}` `{历史中标率}` `{账龄段}` `{账龄天数}` `{工程局单位}` `{下属单位}` `{注册省份}` `{轮次}`
- **理由**：防渲染残留花括号给催收员看；把已存在的 Order 字段（标的名称等）纳入变量；后台「插入变量」按钮避免裸打。
- **替代方案**：运行时渲染失败静默留残——被否（UI 层友好性要求，违反「错误处理」规范）。

### D5：丢弃现有 6 条默认话术，清空重配 + 新种子
- **选择**：数据迁移清空 `talk_templates` 表，提供新的默认种子（按 ROUND_N + 二维匹配重写），管理员可在后台覆盖。
- **理由**：用户决策「丢掉重新配」。现有 6 条是 FIRST/SECOND/THIRD + 四维匹配，与新模型不兼容；清空重配最干净，不写复杂的 scene 迁移映射。
- **影响**：BREAKING；seed.py `DEFAULT_TALK_TEMPLATES` 重写为 ROUND_N 二维版本。

### D6：覆盖度矩阵 + 强联动校验提示（不阻断）
- **选择**：
  - 新增 `coverage.py` 纯函数：输入当前 active risk_config snapshot，输出 `[档 × 轮]` 矩阵，每格标记 FIXED/AI_PROMPT 有无（查 talk_templates）。
  - 风险档配置保存（update_config）后，API 响应附加 `coverage_hint`：列出新增/删除的轮次格子、当前缺口。**不阻断保存**（用户决策「校验提示不阻断」）。
  - 前端 Config 页话术面板：按矩阵渲染，缺口高亮，点击格子直接跳模板编辑。
- **理由**：用户决策「强联动+校验提示」+「到配置话术的地方要能一下看得到针对每个风险档每次触达是否有配置话术，可直接点击修改」。
- **替代方案**：强联动强制阻断——被否（改触达次数必须同时配话术会阻塞业务）。
- **解耦**：`coverage.py` 是纯函数，risk_engine config 保存与 talk_engine 前端都可调，避免两 service 互相 import 成环。

### D7：AI 合规基线不可绕过
- **选择**：
  - 后台配的 AI system prompt 为**追加**到内置合规基线之后（base_system + "\n" + user_system），非覆盖。
  - `is_compliant` 输出校验**永远启用**，不可通过配置关闭。
- **理由**：CLAUDE.md 设计约束 #2 + 安全规范；防止管理员在 system prompt 写入「可以承诺免息」绕过合规。
- **影响**：`generator.build_prompt` 从硬编码改为读 AI_PROMPT 模板渲染，但 system 拼接保留合规基线前置。

## Risks / Trade-offs

- **[scene 语义从「第几次催收」变「第几轮」]** → 现有 tasks/collection_schedules 数据需迁移映射（FIRST→ROUND_1 等）。迁移脚本处理，rollback 需回退迁移。
- **[无兜底导致催收员看到「未配话术」]** → 矩阵覆盖度管理是必须的，否则催收员裸奔。Mitigation：覆盖度矩阵缺口高亮 + 保存风险档配置时提示；MVP 提供新默认种子保证常见档×轮有话术。
- **[一档一轮一类型唯一约束]** → 管理员若想为同一格配多条候选话术（A/B）不被支持。Non-Goal 明确不做；后续可加 priority 字段扩展。
- **[AI_PROMPT 模板未配时 AI 链路降级]** → 无匹配 AI 模板时，generator 降级用内置默认 prompt（保证 AI 链路不断，符合约束 #2），但后台会标出该格 AI 缺口。
- **[占位符校验可能误拒合法新变量]** → 注册表是代码维护的，加新变量需改代码。Mitigation：注册表集中单文件，扩展成本低；MVP 变量集已覆盖主要字段。

## Why

当前话术固定模板靠 seed 脚本硬编码、AI 提示词 prompt 写死在 `generator.build_prompt` 里，管理员无法在后台调整。话术匹配维度 `[风险档 × 账龄段 × 场景 × 用户特征]` 与风险档配置（每档几次触达）松耦合，管理员既看不到「每个风险档每次触达有没有配话术」，也无法针对单格配置/快速补缺口。催收场景需要话术具备针对性（按档×轮）与变量填充（供应商名称、标的名称等特征插值），现状均无后台支撑。

## What Changes

- **BREAKING**：话术匹配键从四维 `[风险档 × 账龄段 × 场景 × 用户特征]` 收敛为二维 `[风险档 × 轮次]`；账龄段、用户特征从「匹配维度」降级为「话术正文/AI 提示词的可插入变量」。
- **BREAKING**：`scene` 取值从固定枚举 `FIRST/SECOND/THIRD` 改为 `ROUND_1/ROUND_2/...ROUND_N`，N 由当前 active risk_config 的 schedules seq 决定，支持任意轮次。
- **BREAKING**：丢弃现有 6 条默认话术模板（`FIRST/SECOND/THIRD` + 四维匹配），清空 `talk_templates` 表后由管理员在后台重新配置（提供新默认种子保底）。
- **BREAKING**：不保留全局 ANY 兜底模板。`(风险档 × 轮次)` 未配话术时，催收员工作台显示「该轮次未配话术」，不再静默回退兜底——倒逼覆盖度管理。
- 新增 `template_type` 字段区分 `FIXED`（固定模板，存最终文本 `content`）与 `AI_PROMPT`（AI 提示词模板，存 `system_prompt` + `user_prompt`，渲染变量后喂 LLM 生成）。
- 新增统一占位符注册表（固定模板 + AI 模板共享），纳入标的名称、概算金额、历史中标率、账龄段、账龄天数、工程局单位、下属单位、注册省份、轮次等变量；后台提供「插入变量」按钮，保存时校验未知占位符（防渲染残留花括号给催收员看）。
- 新增「话术覆盖度矩阵」：按当前 active risk_config 的 schedules 展开 `[风险档 × 轮次]` 矩阵，每格显示 FIXED/AI_PROMPT 有无，缺口高亮、可点击直接配置。
- 新增强联动校验提示（不阻断保存）：保存风险档配置后，提示「风险档已变更，建议核对话术覆盖」，标出新增/删除的轮次格子。
- AI 合规基线加固：后台配的 AI system prompt 为**追加**而非覆盖内置合规基线；`is_compliant` 输出校验永不可关。
- `generator.build_prompt` 从硬编码改为读取匹配到的 AI_PROMPT 模板渲染后调用 LLM；无匹配 AI 模板时仍可降级内置默认 prompt（保证 AI 链路不断）。

## Capabilities

### New Capabilities
- `talk-config`: 管理员话术配置后台——模板 CRUD（固定模板 + AI 提示词模板）、占位符变量管理、覆盖度矩阵、与风险档配置的强联动校验提示。

### Modified Capabilities
- `task-engine`: 任务的 `scene` 取值从 `FIRST/SECOND/THIRD` 改为 `ROUND_N`（由 schedules seq 生成），影响跑批生成任务时写回的 scene 值。

## Impact

- **数据模型**：`talk_templates` 表加 `template_type` / `system_prompt` / `user_prompt` 列；`scene` 列语义从固定枚举值改为 `ROUND_N`；新增数据迁移清空旧话术 + 新种子。
- **后端服务**：`talk_engine/matcher.py` 匹配维度从四维降二维；`renderer.py` 占位符注册表扩展；`generator.py` 读 AI_PROMPT 模板替代硬编码 prompt；新增 `talk_engine/coverage.py`（覆盖度计算纯函数）+ `talk_engine/placeholders.py`（占位符注册表）。
- **后端 API**：新增话术模板 CRUD（ADMIN）、占位符列表（只读）、覆盖度矩阵（ADMIN）；风险档配置保存接口附加覆盖度校验提示字段。
- **前端**：新增 Config 页「话术配置」面板（矩阵视图 + 模板编辑抽屉，含插入变量按钮）；工作台话术区适配「未配话术」空状态。
- **受影响 feature**：`talk-001`（匹配维度重构）、`talk-002`（AI prompt 模板化）、`wb-001`（话术空状态）、`risk-002`（配置保存联动提示）。
- **依赖**：无新外部依赖；复用现有 risk_config schedules 与 LLMProvider 抽象。

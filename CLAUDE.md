# CLAUDE.md

你正在为「平台使用费 AI 辅助催收系统」做长时实现工作。优先保证可靠完成、跨会话连续性和显式验证，而不是表面上的速度。

> 本文件是 harness 的**路由层**：先读它，再按指引读具体文档与状态文件。
> 同时遵守两套规范：**harness-creator 工作流**（状态追踪/会话连续/验证门槛）+ **OpenSpec**（变更提案/spec/任务）。
> 所有设计/需求细节以 `docs/` 为事实来源；变更方案以 `openspec/changes/` 为事实来源。

## 项目一句话

从真实业务平台获取中标订单及特征 → 线下算法跑好风险概率随 CSV 导入 → 经阈值映射风险档 → 按催收时点生成任务并分配给催收员 → 催收员工作台直接处理回填（无需领取）→ 话术辅助（模板+AI）→ 数据大盘。

## 技术栈

- 后端：Python 3.13 + FastAPI + SQLAlchemy 2.0 + Alembic + APScheduler
- 前端：React 19 + TypeScript + Vite + Ant Design 5
- 数据库：PostgreSQL 15（开发期 SQLite）
- LLM：OpenAI 兼容 SDK（glm-5.2 / DeepSeek / 通义等，可开关 + 降级模板）
- 变更管理：OpenSpec（proposal/design/specs/tasks）

## 两套规范的关系

| 层 | 规范 | 职责 | 产物 |
|---|---|---|---|
| 方案层 | **OpenSpec** | 提案/设计/规格/任务步骤 | `openspec/changes/<change>/` 4 artifacts |
| 执行追踪层 | **harness-creator** | 功能状态/会话连续/验证门槛 | `feature_list.json` + `claude-progress.md` + `init.sh` |

- **规划新改造**：用 `/opsx:propose` 生成 OpenSpec change（proposal/design/specs/tasks），同时在 `feature_list.json` 登记 feature 条目（status=in_progress，关联 change 路径）
- **实施改造**：用 `/opsx:apply` 走 tasks.md 步骤，实施中同步更新 feature_list evidence + claude-progress
- **完成门槛**：OpenSpec tasks 全勾 + harness 验证（pytest/init.sh/真实联调）+ feature_list 切 passing + clean-state-checklist 勾选
- 两者不脱节：OpenSpec change 名与 feature_list 的 feature id 对应；每个 change 完成后归档（/opsx:archive）

## 固定工作循环

每轮会话开始时：

1. 运行 `pwd`，确认当前在正确的仓库根目录
2. 读取 `claude-progress.md`（会话连续性日志）
3. 读取 `feature_list.json`（功能状态追踪）——找 in_progress 的 feature
4. 检查 `openspec/changes/` 是否有未完成的 change（对应 in_progress feature）
5. 按需读取 `docs/`：
   - 整体需求 → `docs/01-产品需求文档.md`
   - 架构/数据模型/API → `docs/02-技术架构设计.md`
   - 测试范围/用例 → `docs/03-测试用例.md`
6. 若有进行中的 change，读其 `proposal.md` + `design.md` + `tasks.md`
7. 运行 `./init.sh`（安装依赖 + 基础验证）或 `./start.sh`（快速启动不跑测试）
8. 检查 smoke test 是否已损坏

然后**只选择一个未完成功能**（feature_list 中 in_progress 的，或对应 OpenSpec change），围绕它工作，直到它被验证通过，或被明确记录为 blocked。

## 规划新改造（用 OpenSpec）

当用户提出新改造需求时：

1. 澄清需求歧义（用 AskUserQuestion，特别确认字段映射/数据来源/语义边界）
2. `openspec new change "<name>"` 创建 change 目录
3. 生成 4 artifacts（按依赖顺序）：
   - `proposal.md`（why + what + capability 列表）
   - `design.md`（how + 关键决策）
   - `specs/<capability>/spec.md`（WHEN/THEN 场景）
   - `tasks.md`（实现步骤清单）
4. 在 `feature_list.json` 登记 feature 条目（status=in_progress，notes 关联 change 路径，BREAKING 标注）
5. 更新 `claude-progress.md` + `session-handoff.md`
6. 提交（`docs: <change-name> 规划-OpenSpec change + harness 登记`）
7. 告知用户运行 `/opsx:apply` 实施

## 实施改造（用 OpenSpec + harness）

1. 运行 `/opsx:apply`，按 `tasks.md` 步骤实施
2. 每完成一组 task，运行对应验证（pytest/npm build）
3. 同步更新 `feature_list.json` 的 evidence 字段
4. 全部 task 完成后：跑全量 `./init.sh` + 真实联调
5. 更新 `claude-progress.md`（Session 记录）+ `session-handoff.md`
6. 勾选 `clean-state-checklist.md`
7. 提交（`feat/refactor: <description>`）
8. 视情况 `/opsx:archive` 归档已完成 change

## 规则

- 同一时间只能有一个 active feature（feature_list 中 in_progress）
- 一个 OpenSpec change 对应一个 feature_list feature（id 关联）
- 没有可运行证据时，不要声称完成
- 不要通过重写功能清单来隐藏未完成工作
- 不要为了"看起来完成"而删除或削弱测试
- 以仓库内文件作为唯一事实来源（docs/ 需求、openspec/ 变更方案、feature_list 状态）
- **不可变数据**：创建新对象而非原地修改（遵循全局编码规范）
- **小文件优先**：单文件 200~400 行典型，800 行上限
- **错误处理**：每一层显式处理，UI 层给友好提示，服务端记详细上下文
- **输入校验**：在系统边界（API/CSV 解析）校验所有外部输入
- OpenSpec artifacts 的 `context`/`rules` 是给 AI 的约束，不要复制进产物文件

## 目录约定

```
平台使用费ai辅助催收系统/
├── docs/                  # 需求/架构/测试文档（需求事实来源）
├── openspec/              # OpenSpec 变更管理（变更方案事实来源）
│   ├── config.yaml        # OpenSpec 配置
│   ├── specs/             # 项目级 capability 规格（归档后固化）
│   └── changes/           # 变更目录（每个 change 含 proposal/design/specs/tasks）
│       └── archive/       # 已完成归档的 change
├── backend/               # FastAPI 后端
│   ├── app/
│   │   ├── core/          # config, security, database
│   │   ├── models/        # ORM 模型
│   │   ├── schemas/        # Pydantic 模型
│   │   ├── api/            # 路由
│   │   ├── services/       # 业务逻辑（按模块组织）
│   │   │   ├── data_ingestion/
│   │   │   ├── risk_engine/
│   │   │   ├── task_engine/
│   │   │   ├── talk_engine/
│   │   │   └── dashboard/
│   │   └── scheduler/      # 跑批调度
│   ├── alembic/            # 迁移
│   └── tests/
├── frontend/               # React 前端
│   └── src/
│       ├── pages/          # Workbench/Supervisor/Config/Dashboard
│       ├── components/
│       └── api/
├── feature_list.json       # 功能状态追踪（harness）
├── claude-progress.md      # 会话进度日志（harness）
├── init.sh                 # 标准启动与验证（harness）
├── start.sh                # 快速启动（不跑测试）
├── clean-state-checklist.md # 干净状态检查清单（harness）
└── session-handoff.md      # 会话交接（需要时）
```

## 必需文件

- `feature_list.json` — 功能状态追踪（harness）
- `claude-progress.md` — 会话连续性日志（harness）
- `init.sh` / `start.sh` — 标准启动与验证（harness）
- `docs/` — 需求/架构/测试事实来源
- `openspec/changes/` — 变更方案事实来源（OpenSpec）
- 需要简短交接时使用 `session-handoff.md`

## 关键设计约束（不可违反）

1. **风险概率来源**：从待支付 CSV「风险概率」列导入（线下算法跑好），系统不再预测；经 `tier_mapper` 阈值映射 HIGH/MEDIUM/LOW。RiskProvider 抽象保留供未来算法接入。
2. **LLM 可降级**：AI 话术失败必须回退模板话术，不阻断催收。用 openai SDK（base_url 原样传入，不拼路径）。
3. **任务幂等**：`batch_id + order_id + day_offset` 三元组唯一，不重复生成催收任务。
4. **催收触发条件**：到达催收时点**且届时仍未支付**才生成任务。
5. **状态机简化**：分配后直接 IN_PROGRESS（无领取步骤）；PROMISE 改期回 IN_PROGRESS（保留 assignee）。
6. **平台阻断不在本系统**：本系统"阻断"语义=催收节点强提醒+人工介入，非交易阻断。
7. **OpenSpec 与 harness 对齐**：每个 OpenSpec change 在 feature_list.json 有对应 feature 条目；BREAKING 变更须标注。

## 完成门槛（Definition of Done）

功能状态切到 `passing` 前，必须：

- [ ] OpenSpec change 的 `tasks.md` 全部勾选完成
- [ ] 对应验证命令通过（`./init.sh` 或 pytest + npm build）
- [ ] 证据记录到 `feature_list.json` 的 `evidence` 字段
- [ ] 仓库可重启（`./init.sh` 通过，无残留脏状态）
- [ ] 真实联调通过（用工作区 CSV 样本/真实接口验证）
- [ ] 单元测试覆盖核心逻辑（≥ 80%）
- [ ] `claude-progress.md` 更新 Session 记录
- [ ] `clean-state-checklist.md` 勾选
- [ ] 视情况 `/opsx:archive` 归档已完成 change

## 结束前

1. 更新 `claude-progress.md`（Session 记录）
2. 更新 `feature_list.json`（evidence / status）
3. 检查 OpenSpec change tasks 是否全勾
4. 记录仍然损坏或未验证的内容
5. 勾选 `clean-state-checklist.md`
6. 更新 `session-handoff.md`（需要时）
7. 提交（描述性 commit message）
8. 给下一轮会话留下干净的重启路径

## Git 约定

- commit 格式：`<type>: <description>`，type ∈ feat/fix/refactor/docs/test/chore/perf/ci
- 规划阶段：`docs: <change-name> 规划-OpenSpec change + harness 登记`
- 实施阶段：`feat/refactor: <description>`
- Attribution 已全局关闭，不要加 AI 署名

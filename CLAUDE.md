# CLAUDE.md

你正在为「平台使用费 AI 辅助催收系统」做长时实现工作。优先保证可靠完成、跨会话连续性和显式验证，而不是表面上的速度。

> 本文件是 harness 的**路由层**：先读它，再按指引读具体文档与状态文件。所有设计/需求细节以 `docs/` 为唯一事实来源。

## 项目一句话

从真实业务平台获取中标订单及特征 → 算欠费风险概率（MVP mock）→ 按风险档生成催收任务并分配给 3 名催收员 → 话术辅助（模板+AI）→ 数据大盘。

## 技术栈

- 后端：Python 3.11 + FastAPI + SQLAlchemy 2.0 + Alembic + APScheduler
- 前端：React 18 + TypeScript + Vite + Ant Design 5
- 数据库：PostgreSQL 15（开发期可 SQLite）
- LLM：Provider 抽象层（Claude / OpenAI / mock，可开关）

## 固定工作循环

每轮会话开始时：

1. 运行 `pwd`，确认当前在正确的仓库根目录
2. 读取 `claude-progress.md`（会话连续性日志）
3. 读取 `feature_list.json`（功能状态追踪）
4. 按需读取 `docs/`：
   - 整体需求 → `docs/01-产品需求文档.md`
   - 架构/数据模型/API → `docs/02-技术架构设计.md`
   - 测试范围/用例 → `docs/03-测试用例.md`
5. 运行 `./init.sh`（安装依赖 + 基础验证）
6. 检查 smoke test 是否已损坏

然后**只选择一个未完成功能**，围绕它工作，直到它被验证通过，或被明确记录为 blocked。

## 规则

- 同一时间只能有一个 active feature
- 没有可运行证据时，不要声称完成
- 不要通过重写功能清单来隐藏未完成工作
- 不要为了"看起来完成"而删除或削弱测试
- 以仓库内文件作为唯一事实来源
- **不可变数据**：创建新对象而非原地修改（遵循全局编码规范）
- **小文件优先**：单文件 200~400 行典型，800 行上限
- **错误处理**：每一层显式处理，UI 层给友好提示，服务端记详细上下文
- **输入校验**：在系统边界（API/CSV 解析）校验所有外部输入

## 目录约定

```
平台使用费ai辅助催收系统/
├── docs/                  # 需求/架构/测试文档（事实来源）
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
├── feature_list.json       # 功能状态追踪
├── claude-progress.md      # 会话进度日志
├── init.sh                 # 标准启动与验证
└── session-handoff.md      # 会话交接（需要时）
```

## 必需文件

- `feature_list.json` — 功能状态追踪
- `claude-progress.md` — 会话连续性日志
- `init.sh` — 标准启动与验证
- `docs/` — 需求/架构/测试事实来源
- 需要简短交接时使用 `session-handoff.md`

## 关键设计约束（不可违反）

1. **风险算法可替换**：风险概率必须经 `RiskProvider` 抽象接口，MVP 用 `MockRiskProvider`，后续替换无感知。
2. **LLM 可降级**：AI 话术失败必须回退模板话术，不阻断催收。
3. **任务幂等**：`batch_id + order_id + day_offset` 三元组唯一，不重复生成催收任务。
4. **催收触发条件**：到达催收时点**且届时仍未支付**才生成任务。
5. **数据泄漏**：C 类标签表特征无时间维度，上线真实算法前必须做时间切割。
6. **平台阻断不在本系统**：本系统"阻断"语义=催收节点强提醒+人工介入，非交易阻断。

## 完成门槛（Definition of Done）

功能状态切到 `passing` 前，必须：

- [ ] 实现完成
- [ ] 对应验证命令通过（见 `init.sh`）
- [ ] 证据记录到 `feature_list.json` 的 `evidence` 字段
- [ ] 仓库可重启（`./init.sh` 通过，无残留脏状态）
- [ ] 单元测试覆盖核心逻辑（≥ 80%）

## 结束前

1. 更新 `claude-progress.md`
2. 更新 `feature_list.json`
3. 记录仍然损坏或未验证的内容
4. 勾选 `clean-state-checklist.md`
5. 提交（描述性 commit message）
6. 给下一轮会话留下干净的重启路径

## Git 约定

- commit 格式：`<type>: <description>`，type ∈ feat/fix/refactor/docs/test/chore/perf/ci
- Attribution 已全局关闭，不要加 AI 署名

# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。

## 当前已验证

- 现在明确可用的部分：harness 五子系统文件（CLAUDE.md / feature_list.json / init.sh / 本文件 / clean-state-checklist.md）；需求/架构/测试三份文档
- 这轮实际跑过的验证：无代码，仅文档工件创建

## 本轮改动

- 新增了哪些代码或行为：
  - `docs/00-文档索引.md`
  - `docs/01-产品需求文档.md`（PRD）
  - `docs/02-技术架构设计.md`（架构 + 数据模型 + API + AI 架构）
  - `docs/03-测试用例.md`（50+ 用例）
  - `CLAUDE.md`（harness 路由层）
  - `feature_list.json`（12 个功能，按 PRD 拆解）
  - `claude-progress.md`
  - `init.sh`
  - `session-handoff.md`、`clean-state-checklist.md`
- 基础设施或 harness 发生了哪些变化：从零搭建完整 harness，仓库尚未 git init

## 仍损坏或未验证

- 已知缺陷：无代码，无缺陷
- 未验证路径：所有功能均为 not_started
- 下一轮会话需要注意的风险：
  - 技术栈（Python FastAPI + React）待用户最终确认
  - 仓库未 git init
  - 真实平台 API 对接规格未定（v2.0）
  - 预测算法未实现（v2.1，MVP 用 mock）

## 下一步最佳动作

- 最高优先级未完成功能：`infra-001` 项目骨架与运行环境
- 为什么它是下一步：所有其他功能依赖骨架；`./init.sh` 当前因无 backend/frontend 只能跑通警告态
- 什么结果才算 passing：后端 uvicorn 启动 + /health 200；前端 npm run dev 启动；alembic upgrade head 成功
- 这一步中哪些东西不要动：docs/ 下的需求架构（已是基线）；CLAUDE.md 的设计约束

## 命令

- 启动命令：`./init.sh`（骨架就绪后 `RUN_START_COMMAND=1 ./init.sh`）
- 验证命令：后端 `cd backend && pytest -q`；前端 `cd frontend && npm run build`
- 定向调试命令：
  - 手动跑批：`POST /api/tasks/batch/run`（task-001 完成后）
  - 风险重算：`POST /api/data/orders/recalc-risk`（risk-001 完成后）

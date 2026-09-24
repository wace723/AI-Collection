# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。
> 本仓库由 Claude Code（`CLAUDE.md`）与 CodeBuddy（`CODEBUDDY.md`）共用一套 harness 工件开发。
> 遵守两套规范：harness-creator（状态追踪/会话连续/验证门槛）+ OpenSpec（变更提案/spec/任务）。

## 当前已验证

- **全部完成**：MVP 12 功能 + supervisor 增强 + 业务流程简化 + data-002/003/004 + task-003 单活跃任务区间模型 + 体验优化（筛选/分页/改名）
- 最近验证（Session 024）：
  - 后端 pytest 相关测试 passed（test_workbench/test_reassign/test_supervisor 32 passed）
  - 前端 `npm run build` 通过
  - 各轮小改均验证：ReassignTab 筛选+服务端分页、任务统计改名+处理中卡片
  - 16 功能全 passing，无活动 change

## 本轮改动总结（Session 024 体验优化，纯前端小改）

- **ReassignTab 加风险档筛选**：后端 list_tasks 加 risk_tier 过滤参数；前端加风险档下拉
- **ReassignTab 改服务端分页 + 加当前负责人筛选**：服务端分页（点页码调后端），加负责人下拉，解决"只有 5 页 HIGH"问题
- **任务统计 Tab 改名 + 加团队处理中任务**：「绩效统计」→「任务统计」，顶部加「团队处理中任务」卡片

## 之前几轮（Session 022/023，已归档）

- Session 022：data-004 归档 + AI 话术超时修复（关闭 thinking，39s→2-8s）+ 自动分配按钮 + 启动自动分配 + 大文件导入超时修复
- Session 023：task-003 单活跃任务区间模型（一订单同时一任务，跨区间删旧生新），已归档

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：无（task-003 已完整收尾并归档）
- 风险/遗留：
  - task-003 BREAKING：现有 tasks 表需清空重建（dev.db 已清空，生产部署需清空）
  - 旧任务直接删除（不归档），TaskResult 跟随 CASCADE 删除，历史不保留
  - 前端 axios 默认 10s 超时对耗时操作需逐个设长超时（已修 generateTalk/uploadPendingCsv/uploadPaidCsv）
  - 测试数据/待支付订单.xlsx 和 .csv 误提交进仓库，需确认是否移除

## 下一步可选方向（按价值/紧迫度）

**第一档 · 收尾 + 让系统真正用起来**
1. `/opsx:archive` 归档 auto-batch-and-csv-columns change（specs 固化到主 specs）
2. 真实联调深化：待支付+已支付 CSV 订单号对齐，验证已支付回写终态停催全流程
3. 真实 LLM 调通体验优化（glm 响应 40s，可加流式 SSE）

**第二档 · 上生产前硬骨头**
4. 真实风险算法替换（需时间切割防数据泄漏）——当前风险概率从 CSV 来，算法由线下做
5. PostgreSQL 迁移 + 时区统一

**第三档 · 体验/功能补全**
6. 话术模板管理 UI（当前只有 seed 默认模板，后台不能增删改）
7. 非功能测试（TC-NF-01/02 跑批性能 10000 笔≤5min、工作台列表≤2s）

## 本轮改动总结（data-002，已归档）

- 移除系统风险预测，风险概率从待支付 CSV「风险概率」列导入经阈值映射档位
- 拆分待支付/已支付两个导入入口（`/upload-pending` + `/upload-paid`）
- CSV 列映射重构（新表头：标的名称/概算金额/订单生成日期/中标品类/合同类型/注册省份）
- Order 新增字段、OrderFeature 移除标签列、actual_pay_duration_days 移到 Order
- 跑批默认 `recalc_risk=False`，风险由导入写入
- 工作台列表展示标的信息，详情改屏幕中间 Modal 左右两栏（左=特征分类，右=模板+AI话术）
- 归档：`openspec/changes/archive/2026-09-17-import-driven-risk-and-payment-sync/`
- 主 specs：`openspec/specs/`（import-payment-sync / data-ingestion / risk-engine）

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：无（data-002 已完整收尾归档）
- 风险/遗留：
  - 真实 CSV 样本缺「风险概率」列，真实使用需线下算法跑好追加该列后再导入
  - calculator.recalculate_risks 保留函数但跑批不再调用（recalc_risk=False 默认）
  - TaskDetailModal 宽 1100px 在小屏可能偏挤（可后续响应式优化）

## 下一步可选方向（按价值/紧迫度）

**第一档 · 让系统真正用起来**
1. 真实 CSV（含风险概率列）灌入验证全流程：上传待支付→跑批→分配→催收→回填→已支付导入回写→大盘
2. 真实 LLM 调通体验优化（glm 响应 40s，可加流式 SSE）

**第二档 · 上生产前硬骨头**
3. 真实风险算法替换（需时间切割防数据泄漏）——当前风险概率从 CSV 来，算法由线下做
4. PostgreSQL 迁移 + 时区统一（dash-001 review 记录的 H-2）

**第三档 · 体验/功能补全**
5. 话术模板管理 UI（当前只有 seed 默认模板，后台不能增删改）
6. 主管手动改派已有（F-TASK-04），可补任务转派历史/审计
7. 非功能测试（TC-NF-01/02 跑批性能 10000 笔≤5min、工作台列表≤2s）

## 命令

- 快速启动（不测试）：`./start.sh`
- 标准验证：后端 `cd backend && .venv\Scripts\python.exe -m pytest -q`；前端 `cd frontend && npm run build`
- 种子：`cd backend && python seed.py`（用户 + 风险档配置 + 6 话术模板 + AI 配置）
- 启动后端：`uvicorn app.main:app --reload --port 8000`
- 启动前端：`npm run dev`（5173）
- 默认账号：admin/supervisor/collector1-3，密码 admin123
- 新增接口（data-002）：
  - 待支付导入：`POST /api/data/upload-pending`（ADMIN，含风险概率列）
  - 已支付导入：`POST /api/data/upload-paid`（ADMIN，回写支付状态）
  - 用户管理：`GET/POST /api/users`、`PUT/DELETE /api/users/{id}`
  - 绩效：`GET /api/supervisor/staff-performance`（SUPERVISOR/ADMIN）
  - 改派：`POST /api/tasks/{id}/reassign?assignee_id=`（SUPERVISOR/ADMIN）

## 状态文件位置

- `feature_list.json` — 16 个功能全 passing（含 task-003）
- `claude-progress.md` — Session 024 记录
- `openspec/specs/` — 4 个 capability 主 specs（固化）
- `openspec/changes/` — 无活动 change（task-003 已归档到 archive/2026-09-23-*）
- `openspec/changes/archive/` — data-002/003/004 + task-003 共 4 个已归档

## 给下一轮会话的重启路径

1. `pwd` 确认仓库根
2. 读 `claude-progress.md` 找 Session 024
3. 读 `feature_list.json` 确认 16 功能 passing，无 in_progress
4. 检查 `openspec/changes/` 无活动 change（task-003 已归档）
5. `./start.sh` 启动验证基线
6. 选「下一步可选方向」之一开始
6. 选「归档 data-003」或「下一步可选方向」之一开始

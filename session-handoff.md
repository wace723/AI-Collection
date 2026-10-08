# 会话交接

> 会话间快速交接用。详细进度见 `claude-progress.md`，功能状态见 `feature_list.json`。
> 本仓库由 Claude Code（`CLAUDE.md`）与 CodeBuddy（`CODEBUDDY.md`）共用一套 harness 工件开发。
> 遵守两套规范：harness-creator（状态追踪/会话连续/验证门槛）+ OpenSpec（变更提案/spec/任务）。

## 当前已验证

- **全部完成**：17 功能全 passing（含 talk-003 管理员话术配置后台，已归档 + 后续 UI 优化）
- 最近进展（Session 027）：
  - 归档 admin-talk-config（主 specs 同步：新建 talk-config spec + task-engine spec 合并 scene=ROUND_N）
  - Config 页改 Tab 布局（数据导入/风险档配置/话术配置）
  - 话术编辑 UI 调整：右侧 Drawer → 居中 Modal，固定+AI 同时展示，名称/档/轮不可编辑，变量全平铺，去启用字段
  - 占位符扩展到全部特征字段（16→44，覆盖 Order+OrderFeature 全部业务字段，分 7 组）
  - AI 话术 markdown 渲染（react-markdown，防 XSS）
  - pytest 45 passed（占位符扩展无回归），npm build 通过

## 本轮改动总结（Session 027 talk-003 归档 + UI 优化）

- **归档 admin-talk-config**：→ archive/2026-09-28-admin-talk-config，主 specs 同步
- **Config 页 Tab 布局**：3 个 Tab（数据导入/风险档配置/话术配置）
- **话术编辑 UI**：居中 Modal（固定模板话术 + AI 提示词同时展示）；名称/风险档/轮次不可编辑（按格子锁定）；占位符变量全部平铺展示；去"启用"字段
- **占位符扩展 16→44**：覆盖 Order+OrderFeature 全部业务字段（基础5/标的7/催收7/供应商归属5/缴费历史3/活跃度8/资质标签9），金额/比率友好格式化
- **AI 话术 markdown 渲染**：react-markdown 渲染 AI 生成话术，加排版样式，防 XSS

## 之前几轮（Session 022~026，已归档/收尾）

- Session 022：data-004 归档 + AI 话术超时修复 + 自动分配 + 大文件导入超时
- Session 023：task-003 单活跃任务区间模型，已归档
- Session 024：ReassignTab 筛选+服务端分页、任务统计改名（纯前端小改）
- Session 025：talk-003 规划（OpenSpec 4/4 artifacts + 9 项决策）
- Session 026：talk-003 实施（49/49 tasks，222 passed，真实联调全通）

## 仍损坏或未验证

- 已知缺陷：无
- 未验证路径：无
- 风险/遗留：
  - docs/ 话术章节已同步 talk-003 BREAKING 改造（PRD F-TALK + 占位符 44、架构 §3.2.8/§4.3/§5.5、测试 TC-TALK 01~13）
  - react-markdown 默认不渲染 raw HTML（防 XSS），如需 HTML 标签需加 rehype-raw
  - 前端 axios 默认 10s 超时对耗时操作需逐个设长超时（历史记录）
  - 测试数据/待支付订单.xlsx 和 .csv 误提交进仓库，需确认是否移除

## 下一步可选方向（按价值/紧迫度）

**第一档 · 让系统真正用起来**
1. 真实 LLM 调通体验优化（glm 响应慢，可加流式 SSE）
2. 真实业务 CSV 灌入验证全流程

**第二档 · 上生产前硬骨头**
3. 真实风险算法替换（需时间切割防数据泄漏）
4. PostgreSQL 迁移 + 时区统一

**第三档 · 体验/功能补全**
5. 非功能测试（TC-NF-01/02 跑批性能 10000 笔≤5min、工作台列表≤2s）
6. 话术模板 A/B 测试（同格多模板 priority 排序）
7. docs/ 其他章节同步 data-003/task-003 BREAKING 改造（状态机两分类、单活跃任务模型——TC-TASK/E2E 已部分改）

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

- `feature_list.json` — 17 功能全 passing（含 talk-003）
- `claude-progress.md` — Session 027 记录
- `openspec/specs/` — 5 个 capability 主 specs（含新建 talk-config）
- `openspec/changes/` — 无活动 change（admin-talk-config 已归档到 archive/2026-09-28-*）
- `openspec/changes/archive/` — data-002/003/004 + task-003 + admin-talk-config 共 5 个已归档

## 给下一轮会话的重启路径

1. `pwd` 确认仓库根
2. 读 `claude-progress.md` 找 Session 027
3. 读 `feature_list.json` 确认 17 功能 passing
4. 检查 `openspec/changes/` 无活动 change（admin-talk-config 已归档）
5. `./start.sh` 启动验证基线
6. 选「下一步可选方向」之一开始（第一档：docs 话术章节同步）

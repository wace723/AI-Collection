## 1. 数据模型与迁移

- [ ] 1.1 `talk_templates` 表加列：`template_type`（String(16)，默认 FIXED，非空 index）、`system_prompt`（Text，nullable）、`user_prompt`（Text，nullable）；`scene` 列语义改为 ROUND_N（String(16) 不变，注释更新）；`age_bucket`/`user_feature_tag` 列保留但标注不再参与匹配
- [ ] 1.2 Alembic 迁移：talk_templates 加列 + 数据迁移（清空现有 6 条默认模板，D5）；collection_schedules 的 scene 值映射 FIRST→ROUND_1/SECOND→ROUND_2/THIRD→ROUND_3；tasks 的 scene 值同步映射
- [ ] 1.3 `models/talk.py` TalkTemplate 加 `template_type`/`system_prompt`/`user_prompt` 字段 + 注释更新 scene 为 ROUND_N
- [ ] 1.4 迁移脚本验证：alembic upgrade head 成功，dev.db talk_templates 清空、collection_schedules/tasks 的 scene 全为 ROUND_N 格式

## 2. scene 改造为 ROUND_N（task-engine modified）

- [ ] 2.1 `schemas/config.py`：`SceneEnum` 移除固定 FIRST/SECOND/THIRD，改为仅校验 ROUND_N 格式（`ROUND_\d+`），或删除枚举改用 str + 校验函数
- [ ] 2.2 `services/risk_engine/config_service.py`：`_insert_version` 写 CollectionSchedule 时 scene 按 seq 自动生成 `ROUND_{seq}`，不取 ScheduleIn.scene（前端传的 scene 忽略或校验为 ROUND_N）
- [ ] 2.3 `schemas/config.py` `ScheduleIn`：scene 字段改为可选（由 seq 自动生成）或保留作校验；`DEFAULT_SCHEDULES` 的 scene 值改 ROUND_1/ROUND_2/ROUND_3
- [ ] 2.4 `services/task_engine/batch.py`：生成 Task 时 scene 照搬 `sched.scene`（现有逻辑不变，确认值已是 ROUND_N）
- [ ] 2.5 单测验证：保存风险档配置后 CollectionSchedule.scene 为 ROUND_N 格式；4 轮配置生成 ROUND_1~ROUND_4

## 3. 占位符注册表与校验（D4）

- [ ] 3.1 新建 `services/talk_engine/placeholders.py`：集中注册所有合法占位符 + 取值来源（Order/OrderFeature/Task 字段或派生），含供应商名称/标的名称/概算金额/历史中标率/账龄段/账龄天数/工程局单位/下属单位/注册省份/轮次/风险档/场景/应催日/会员状态/订单号/service_fee_order_no
- [ ] 3.2 `placeholders.py`：导出 `validate_placeholders(text) -> list[str]`（返回未知占位符列表，空=合法）与 `available_placeholders() -> list[PlaceholderInfo]`（供前端展示可插入变量）
- [ ] 3.3 `renderer.py`：`render` 改用注册表取值，渲染后校验无残留 `{` `}`（防漏网）
- [ ] 3.4 单测验证：合法占位符通过；`{标地名称}` 拒绝并返回未知列表；渲染后无花括号残留

## 4. 话术匹配器重构为二维（D1）

- [ ] 4.1 `services/talk_engine/matcher.py`：`match_templates` 重写为二维 `[风险档 × scene]` 精确匹配，去掉 age_bucket/user_feature_tag/ANY 维度；按 template_type 过滤（FIXED 或 AI_PROMPT）
- [ ] 4.2 `derive_user_tag`/`map_age_bucket` 保留供 renderer 占位符取值用（账龄段/会员状态作为变量），但不再用于匹配
- [ ] 4.3 `recommend.py`：`recommend_talks` 适配二维匹配，RecommendatedTalk 去掉 score（无排序，精确匹配唯一）或保留固定分；按 template_type 区分
- [ ] 4.4 单测验证：(HIGH,ROUND_2) 精确命中；未配返回空列表不兜底；不同账龄同档同轮命中同一条

## 5. AI 提示词模板化与合规基线（D3/D7）

- [ ] 5.1 `services/talk_engine/generator.py`：`build_prompt` 改为读匹配到的 AI_PROMPT 模板渲染 system/user prompt；无 AI_PROMPT 模板时降级内置默认 prompt（保证 AI 链路不断）
- [ ] 5.2 `generator.py`：system 拼接 = 内置合规基线 + "\n" + 后台 system_prompt（追加非覆盖）；`is_compliant` 输出校验永远启用（去掉任何可关闭路径）
- [ ] 5.3 `_COMPLIANCE_BASELINE` 常量提取为模块级（现有 system prompt 合规约束部分），供拼接复用
- [ ] 5.4 单测验证：有 AI_PROMPT 模板时 system 含合规基线+后台 prompt；无模板降级默认 prompt；is_compliant 不可关

## 6. 覆盖度矩阵与联动校验（D6）

- [ ] 6.1 新建 `services/talk_engine/coverage.py`：`compute_coverage(db, snap) -> CoverageMatrix`（纯函数，输入 active risk_config snapshot，输出 [档×轮] 矩阵，每格标记 FIXED/AI_PROMPT 有无）；`diff_coverage(old_snap, new_snap) -> CoverageHint`（新增/删除轮次格子 + 缺口）
- [ ] 6.2 `services/risk_engine/config_service.py`：`update_config` 返回值附加 coverage_hint（调用 coverage.diff_coverage 对比新旧 snapshot），不阻断保存
- [ ] 6.3 `schemas/config.py`：RiskConfigOut（或新 schema）加 `coverage_hint` 字段（added_rounds/deleted_rounds/missing_cells）
- [ ] 6.4 单测验证：3→4 轮提示新增 ROUND_4 缺话术；3→2 轮提示 ROUND_3 孤儿；仅改 day_offset 无轮次变更不提示

## 7. 后端 API

- [ ] 7.1 `api/talk.py` 新增模板管理：GET `/api/talk/templates`（列表+按档/轮/类型筛选，ADMIN）、POST `/api/talk/templates`（创建，ADMIN，含占位符校验 400）、PUT `/api/talk/templates/{id}`（更新）、DELETE `/api/talk/templates/{id}`（软删除 is_active=False）；GET `/api/talk/templates/placeholders`（可用占位符列表，登录可见）
- [ ] 7.2 `api/talk.py` 新增覆盖度：GET `/api/talk/coverage`（按 active risk_config 返回矩阵，ADMIN）
- [ ] 7.3 `api/talk.py`：GET `/api/talk/recommend` 适配二维匹配 + 未配话术空状态（返回空 templates 列表 + has_talk=false 标记）
- [ ] 7.4 `api/config.py`：PUT `/api/config/risk` 响应附加 coverage_hint
- [ ] 7.5 `schemas/talk.py`：加 TalkTemplateIn/TalkTemplateManageOut/CoverageMatrixOut/CoverageHintOut/PlaceholderOut
- [ ] 7.6 `api/router.py` 挂载新路由；权限校验：模板 CRUD 仅 ADMIN，recommend 登录可见（COLLECTOR 仅自己任务）
- [ ] 7.7 单测验证：CRUD 全通、占位符非法 400、覆盖度矩阵正确、权限 401/403

## 8. 前端

- [ ] 8.1 Config 页新增「话术配置」面板：覆盖度矩阵视图（按档×轮格子，每格标记 FIXED/AI_PROMPT 有无，缺口高亮，点击格子打开模板编辑）
- [ ] 8.2 模板编辑抽屉：template_type 切换（FIXED/AI_PROMPT）；FIXED 编辑 content，AI_PROMPT 编辑 system_prompt+user_prompt；「插入变量」下拉按钮（调 /api/talk/templates/placeholders）插入占位符到光标位置
- [ ] 8.3 前端 api/talk.ts：listTemplates/createTemplate/updateTemplate/deleteTemplate/getCoverage/getPlaceholders；types/api.ts 加对应类型
- [ ] 8.4 Workbench 话术推荐区适配：未配话术时显示「该轮次未配话术」空状态（has_talk=false）；AI 生成按钮适配 AI_PROMPT 模板缺失时降级提示
- [ ] 8.5 风险档配置保存后，响应含 coverage_hint 时弹提示（新增/删除轮次、建议复核话术）
- [ ] 8.6 npm run build 通过（tsc + vite）

## 9. 测试与验证

- [ ] 9.1 `seed.py` 重写 `DEFAULT_TALK_TEMPLATES`：按 ROUND_N + 二维匹配，含 FIXED + AI_PROMPT 默认种子覆盖常见档×轮（HIGH ROUND_1/2/3、MEDIUM ROUND_1、LOW ROUND_1，各档 FIXED + HIGH ROUND_1 AI_PROMPT 示例）
- [ ] 9.2 `tests/test_talk.py` 重写：二维匹配 + 未配空状态 + 占位符校验（合法/非法/无残留）
- [ ] 9.3 `tests/test_talk_ai.py` 适配：AI_PROMPT 模板化 + 合规基线追加 + 无模板降级
- [ ] 9.4 `tests/test_risk_config.py` 适配：scene=ROUND_N 自动生成 + coverage_hint 联动提示
- [ ] 9.5 `tests/test_task_generation.py` 适配：生成 Task scene=ROUND_N
- [ ] 9.6 `tests/test_workbench.py` 适配：未配话术空状态
- [ ] 9.7 新增 `tests/test_talk_coverage.py`：覆盖度矩阵 + 联动校验提示（新增/删除/无变更轮次）
- [ ] 9.8 `pytest -q` 全量通过，无回归
- [ ] 9.9 `npm run build` 通过
- [ ] 9.10 真实联调（dev.db + 真实 uvicorn）：seed 新话术 → 跑批生成 ROUND_N 任务 → 工作台推荐话术 → 后台矩阵覆盖度 → 配置 AI_PROMPT 模板 → AI 生成含合规基线 → 风险档改触达次数提示覆盖度
- [ ] 9.11 OpenSpec tasks 全勾 + feature_list.json talk-003 切 passing + clean-state-checklist 勾选

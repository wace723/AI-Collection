## ADDED Requirements

### Requirement: 话术模板按风险档×轮次二维匹配

系统 SHALL 按 `[风险档 × 轮次]` 二维精确匹配话术模板，轮次取值 `ROUND_N`（N 为当前生效风险档配置中该档 schedules 的 seq）。匹配 MUST 精确，不保留 ANY 兜底；某 `(风险档, 轮次)` 未配置话术时，催收员工作台 SHALL 显示「该轮次未配话术」空状态，不得静默回退。

#### Scenario: 精确匹配固定模板
- **WHEN** 催收员查看某任务（risk_tier=HIGH, scene=ROUND_2）的话术推荐，且存在 template_type=FIXED 的模板 (HIGH, ROUND_2)
- **THEN** 返回该模板，占位符渲染后展示给催收员

#### Scenario: 未配话术显示空状态
- **WHEN** 催收员查看某任务（risk_tier=MEDIUM, scene=ROUND_1）的话术推荐，但无 (MEDIUM, ROUND_1) 的任何模板
- **THEN** 工作台显示「该轮次未配话术」，不返回兜底话术，不报错

#### Scenario: 账龄段与用户特征不参与匹配
- **WHEN** 两笔任务 risk_tier 与 scene 相同但账龄段/用户特征不同（如账龄 8 天 vs 90 天）
- **THEN** 命中同一条话术模板（账龄段/用户特征仅作为话术变量填充，不作为匹配维度）

### Requirement: 话术模板分固定模板与AI提示词模板两类

系统 SHALL 支持两类话术模板：FIXED（固定模板，存最终文本 content）与 AI_PROMPT（AI 提示词模板，存 system_prompt + user_prompt）。同一 `(风险档, 轮次, template_type)` 组合最多一条模板。AI_PROMPT 模板的 prompt 渲染占位符后喂给 LLM 生成话术；FIXED 模板的 content 渲染占位符后直接展示。

#### Scenario: FIXED 模板渲染直接展示
- **WHEN** 命中 template_type=FIXED 模板，其 content 含 `{供应商名称}` 等占位符
- **THEN** 占位符替换为实际值后返回，无残留花括号

#### Scenario: AI_PROMPT 模板渲染喂 LLM
- **WHEN** 催收员请求 AI 生成话术，命中 template_type=AI_PROMPT 模板 (HIGH, ROUND_2)
- **THEN** system_prompt 与 user_prompt 的占位符渲染后调用 LLMProvider 生成话术，合规校验通过则返回生成内容

#### Scenario: 无 AI_PROMPT 模板降级默认 prompt
- **WHEN** 催收员请求 AI 生成话术，但 (档, 轮) 无 AI_PROMPT 模板
- **THEN** 系统降级使用内置默认 prompt 调 LLM（保证 AI 链路不断），并在覆盖度矩阵标出该格 AI 缺口

### Requirement: 占位符统一注册与保存校验

系统 SHALL 维护统一占位符注册表（固定模板与 AI 模板共享），含供应商名称、标的名称、概算金额、历史中标率、账龄段、账龄天数、工程局单位、下属单位、注册省份、轮次、风险档、场景、应催日、会员状态、订单号等。保存模板时 MUST 校验正文/prompt 中所有 `{xxx}` 占位符均合法，非法占位符拒绝保存并返回未知占位符列表。

#### Scenario: 保存含合法占位符的模板
- **WHEN** 管理员保存 FIXED 模板，content 含 `{供应商名称}您好，标的{标的名称}已逾期`
- **THEN** 校验通过，模板保存成功

#### Scenario: 保存含非法占位符的模板被拒
- **WHEN** 管理员保存模板，content 含 `{标地名称}`（拼写错误，非注册占位符）
- **THEN** 返回 400，提示未知占位符 `标地名称`，模板不保存

#### Scenario: 渲染后无残留花括号
- **WHEN** 命中模板并渲染占位符
- **THEN** 渲染结果不含任何 `{` 或 `}` 残留字符

### Requirement: 话术覆盖度矩阵可视化

系统 SHALL 按当前生效风险档配置的 schedules 展开话术覆盖度矩阵，维度为 `[风险档 × 轮次]`，每格标记 FIXED 与 AI_PROMPT 是否已配置。管理员 MUST 能在后台一眼看到每个风险档每次触达是否有话术配置，缺口高亮，可点击直接配置对应位置的话术。

#### Scenario: 展开覆盖度矩阵
- **WHEN** 管理员打开话术配置面板，当前 active risk_config 含 HIGH[ROUND_1,ROUND_2,ROUND_3]、MEDIUM[ROUND_1]、LOW[ROUND_1]
- **THEN** 矩阵显示 5 个格子，每格标记 FIXED/AI_PROMPT 配置状态（已配/未配）

#### Scenario: 缺口高亮可点击配置
- **WHEN** 矩阵某格 (HIGH, ROUND_2) 的 FIXED 未配
- **THEN** 该格高亮提示缺口，点击该格直接打开 (HIGH, ROUND_2) 的模板编辑界面

#### Scenario: 矩阵以当前 active 配置为准
- **WHEN** 风险档配置变更（新增 ROUND_4 或删除 ROUND_3）后管理员刷新话术面板
- **THEN** 矩阵按新 schedules 重新展开，反映最新轮次结构

### Requirement: 风险档配置变更联动话术覆盖提示

保存风险档配置（更新触达次数/时点）后，系统 SHALL 在响应中附加话术覆盖度提示，列出新增的轮次格子（需补话术）与删除的轮次格子（话术成孤儿）。该提示 MUST NOT 阻断风险档配置保存，仅作提醒。

#### Scenario: 新增轮次提示补话术
- **WHEN** 管理员把 HIGH 档从 3 轮改为 4 轮（新增 ROUND_4），保存风险档配置
- **THEN** 风险档配置保存成功，响应 coverage_hint 提示「HIGH ROUND_4 尚未配置话术，建议补充」

#### Scenario: 删除轮次提示话术成孤儿
- **WHEN** 管理员把 HIGH 档从 3 轮改为 2 轮（删除 ROUND_3），且 (HIGH, ROUND_3) 原有话术
- **THEN** 风险档配置保存成功，响应 coverage_hint 提示「HIGH ROUND_3 话术已成孤儿（无对应轮次），建议清理」

#### Scenario: 无变更轮次不提示
- **WHEN** 管理员仅调整 HIGH 档 day_offset（如 ROUND_2 从第 15 天改第 10 天），轮次数不变
- **THEN** 风险档配置保存成功，coverage_hint 提示「轮次结构未变，无需复核话术覆盖」

### Requirement: AI 提示词模板合规基线不可绕过

系统 SHALL 在使用后台配置的 AI system prompt 时，于其前拼接内置合规基线（合规基线 + 后台 system prompt），后台 system prompt 不得覆盖合规基线。输出层 `is_compliant` 校验 MUST 永远启用，不可通过任何配置关闭。

#### Scenario: 后台 system prompt 追加合规基线
- **WHEN** 管理员配置 AI_PROMPT 模板 system_prompt 为「语气强硬一点」，催收员请求 AI 生成
- **THEN** 实际传给 LLM 的 system = 内置合规基线 + "\n" + 「语气强硬一点」，合规基线在前

#### Scenario: 合规校验永不关闭
- **WHEN** LLM 输出含威胁/辱骂/虚假承诺关键词，无论后台如何配置
- **THEN** is_compliant 判定不通过，降级模板话术，原始输出仍记录到 AIConversation 审计

### Requirement: 话术模板管理 CRUD

管理员 SHALL 可在后台对话术模板进行增删改查（CRUD），支持按风险档/轮次/类型筛选。模板支持软删除（is_active）。非管理员（COLLECTOR/SUPERVISOR）MUST NOT 能修改话术模板，仅可查看推荐结果。

#### Scenario: 管理员创建模板
- **WHEN** 管理员提交新模板 (HIGH, ROUND_2, FIXED, content="...")
- **THEN** 模板创建成功，is_active=True

#### Scenario: 管理员更新模板
- **WHEN** 管理员修改已有模板 content
- **THEN** 模板更新成功，占位符重新校验通过

#### Scenario: 管理员软删除模板
- **WHEN** 管理员删除某模板
- **THEN** 模板 is_active=False，不再参与匹配，记录保留

#### Scenario: 非管理员禁止修改
- **WHEN** COLLECTOR 或 SUPERVISOR 调用话术模板创建/修改/删除接口
- **THEN** 返回 403

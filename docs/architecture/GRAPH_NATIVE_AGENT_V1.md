# LATTICE Graph-Native Agent V1

## 目标

V1 把图谱记忆从执行前的外部检索附件变成主 agent 的内部运行机制，同时保留后续增加多 agent 讨论、候选策略搜索和 on-policy 蒸馏的扩展点。系统面向通用科研任务，不绑定生物信息学领域，也不把已有 G2 工作流当成固定 pipeline。

## 运行时角色

| 角色 | 输入 | 输出 | 责任边界 |
| --- | --- | --- | --- |
| TaskUnderstandingAgent | 用户请求、执行意图 | ResearchTask、TaskFingerprint | 明确目标、输入、输出、约束、成功条件、研究模式和歧义 |
| RuntimeViewProjector | TaskFingerprint、G1 | RuntimeGraphContext | 投影类型化 G2 子图和跨层边，报告缺失信息 |
| SkillContextProvider | ResearchTask、G2 | SkillContext[] | 选择 L5 Skill，并连接 L4 Resource 与 L6 Experience |
| ResearchStrategyPlanner | ResearchTask、G2、SkillContext | AgenticExecutionPlan | 调整已有 G2 参考或创建任务特定策略 |
| RuntimeCapabilityDiscoverer | 缺口、任务、G2 | 临时策略、候选 GraphPatch | 可注入的外部能力发现端口；V1 默认实现不联网且不伪造发现结果 |
| WorkflowVerifier | 路径搜索、执行策略 | WorkflowAuditReport | 检查策略完整性；没有 G2 路径不再自动阻断 |
| ScriptGenerationAgent | 任务、策略、图谱记忆、修订反馈 | ScriptProposal | 通过模型生成可审计脚本；无模型配置时失败关闭 |
| ScriptReviewAgent | ScriptProposal | ScriptReviewResult | 检查语法、危险操作、网络/子进程权限、输出路径和步骤覆盖 |
| PermissionGate | 模式、策略、脚本、审查 | PermissionDecision | 把用户授权与具体执行提案绑定 |
| ScriptRunner | 已批准脚本 | ScriptExecutionRawResult | 在独立目录执行，保存脚本、日志和所有运行产物 |
| ResultVerifier | 策略、提案、执行结果、产物清单 | ResultVerificationReport | 区分 completed、repairable、failed、not_executed |
| ExperienceCandidateExtractor | RunRecord、验证结果、任务 | ExperienceCandidate | 从一次运行提炼成功或失败观察，不直接写长期经验 |
| ExperienceGeneralizationGate | ExperienceCandidate | GeneralizationDecision | 按支持次数、置信度、适用范围和冲突决定是否可泛化 |
| MemoryHealthCompiler | G0 mutation / lifecycle | G1 patch | 只把已激活且健康的内容编译进 G1 |

## 状态机

```text
receive_request
  -> understand_task
  -> project_runtime_graph
  -> search_workflow_references
  -> detect_capability_gaps
  -> request_or_discover_capabilities
  -> resolve_skill_context
  -> formulate_research_strategy
  -> verify_strategy
  -> generate_script
  -> review_script --needs_revision--> generate_script
  -> permission_check
  -> execute_script
  -> build_run_record
  -> verify_results --repairable--> generate_script
  -> finalize_run_record
  -> extract_experience_candidate
  -> evaluate_generalization
  -> optional_graph_patch
  -> produce_response
```

修订环路有明确次数上限。结果验证不能把退出码 `0` 等同于科研任务完成：声明的路径型产物必须存在；无法由程序确定的语义成功条件会进入 `unverified_criteria`，而不是被自动判定通过。

## 图谱使用语义

- G2 Workflow 提供可调整的方法参考；没有匹配路径时由 ResearchStrategyPlanner 创建新策略。
- L4 Resource 描述可用对象，不直接等同于可执行契约。
- L5 Skill 是 agent 可读的操作知识，包含输入输出、参数建议、环境、失败模式、恢复策略和来源。
- L6 Experience 通过 Skill、Workflow、Task 等跨层边进入当前上下文，参与策略选择和脚本修订。
- `cross_layer_edges` 保留 Resource-to-Skill、Workflow-to-Skill、Skill-to-Experience 等关系，避免投影时把图退化成互不相连的节点列表。
- 运行时发现形成的候选知识先写 G0 candidate；只有 lifecycle 已进入健康激活状态的 mutation 才能由 MemoryHealthCompiler 进入 G1。

## 兼容边界

旧的 ToolCall schema、registry、dispatcher、backend 和数据库表仍保留，供历史图资产读取、迁移和旧测试使用。V1 主执行图不读取 `ToolCallSpec` 来决定任务能否执行，也不通过 dispatcher 运行工具。后续删除这些兼容模块前，需要先迁移 G0 数据、ToolBuilder 输出、数据库表和外部调用方。

## 后续认知层扩展点

V1 先建立可验证的单策略主链。多 agent 讨论和搜索可以在不改动图谱治理语义的前提下插入以下位置：

1. `ResearchStrategyPlanner` 生成多个候选策略，由 scientist、critic、methodologist 和 resource specialist 比较。
2. `ScriptReviewAgent` 扩展为静态审查、方法学审查和结果审查的结构化协作。
3. `ResultVerifier` 之后增加反事实检查、重复运行和候选结果排序。
4. `ExperienceGeneralizationGate` 聚合多次运行证据，再执行去重、合并、降权、删除和生命周期迁移。

这些扩展应继续共享 ResearchTask、RuntimeGraphContext、SkillContext、AgenticExecutionPlan、RunRecord 和 ExperienceCandidate，不应再建立一套与图谱脱节的旁路状态。

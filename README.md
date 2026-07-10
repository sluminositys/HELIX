# LATTICE

**Layered Agent for Tool-Augmented Task Intelligence, Curation, and Evolution**

LATTICE 是面向通用科研任务的自主 agent 系统。它把论文、文档、软件、研究流程、运行经验和用户约束组织成分层图谱记忆，并让主 agent 在任务理解、记忆选择、策略形成、脚本生成、审查、执行、结果验证和经验蒸馏的全过程中使用这些记忆。

LATTICE 不是固定 pipeline。G2 中已有的流程是运行时参考，不是必须逐步执行的模板；当图谱不能覆盖当前问题时，agent 可以形成新的任务策略并生成脚本，也可以通过 `RuntimeCapabilityDiscoverer` 端口接入外部能力发现实现。任务结束后，系统只把可审计的运行记录写入当次状态，单次观察形成 L6 经验候选，达到跨运行泛化门槛后才允许进入受治理的长期图谱更新。

## 图谱记忆

- **G0：Persistent Full Graph**。保存完整事实、候选知识、来源、运行记录、生命周期状态和待审 GraphPatch。
- **G1：Memory-Healthy Graph**。从 G0 中筛选 `active_hot` / `active_warm` 等健康内容，作为主 agent 的默认长期记忆。
- **G2：Task-conditioned Runtime GraphContext**。围绕当前 `ResearchTask` 从 G1 投影出的任务、证据、流程、资源、技能和经验视图；允许包含临时候选和跨层边。

G0 与 G1 使用六层异构图：

1. **L1 Task**：科研目标、问题类型、输入输出要求与约束。
2. **L2 Evidence**：论文、文档、数据、结论及其来源证据。
3. **L3 Workflow**：可复用的方法结构、步骤关系和质量检查点。
4. **L4 Resource**：软件、模型、数据服务、数据集和运行资源。
5. **L5 Skill**：供 agent 阅读的工具使用知识，包括参数、输入输出、环境、失败模式和恢复策略。
6. **L6 Experience**：可泛化的成功模式、失败模式、方法比较、流程经验、任务约束和用户偏好。

## 主执行链

```text
用户请求
  -> TaskUnderstandingAgent: 生成 ResearchTask / TaskFingerprint
  -> Graph projection: 从 G1 形成类型化 G2 运行时视图
  -> Memory selection: 选择 Workflow / Resource / Skill / Experience 上下文
  -> ResearchStrategyPlanner: 参考 G2 或动态生成任务策略
  -> WorkflowVerifier: 检查策略是否可执行，不要求已有 G2 路径
  -> ScriptGenerationAgent: 基于任务、策略、L5 Skill 和 L6 Experience 生成脚本
  -> ScriptReviewAgent: AST、权限、危险操作、输出路径和步骤覆盖审查
  -> PermissionGate: 按执行模式决定是否允许运行
  -> ScriptRunner: 在独立运行目录执行并保留脚本、stdout、stderr 和产物
  -> ResultVerifier: 验证进程状态、声明产物和可确定成功条件
  -> ExperienceCandidateExtractor: 提炼 L6 候选
  -> ExperienceGeneralizationGate: 多次支持后才允许形成长期 GraphPatch
  -> MemoryHealthCompiler: 只把健康、已激活内容编译进 G1
```

脚本生成采用 fail-closed：未配置模型时 `execute` 会明确阻断，不会用占位脚本伪造成功。脚本审查或执行失败时，主执行图可以携带审查意见或错误日志发起有限次数修订。

## LATTICE-G0-Extractor

`LATTICE-G0-Extractor` 是同一整体中的外部知识采集与规范化子系统，独立仓库便于单独开发和批量抽取。它把论文、工具文档和其他来源提取为带 provenance 的 G0 GraphPatch；LATTICE 负责图谱治理、G1 健康化、G2 运行时使用、任务执行和经验回写。仓库分离不代表系统逻辑分离，两者通过相同的节点、边、GraphPatch、provenance 和 lifecycle 语义对接。

## 配置与运行

安装与检查：

```powershell
uv sync --dev
uv run pytest
uv run ruff check .
uv run mypy
```

配置脚本生成模型，例如 OpenAI：

```powershell
$env:LATTICE_MODELS__CHAT_PROVIDER = "openai"
$env:LATTICE_MODELS__CHAT_MODEL = "gpt-4.1"
$env:OPENAI_API_KEY = "<key>"
```

或 DeepSeek：

```powershell
$env:LATTICE_MODELS__CHAT_PROVIDER = "deepseek"
$env:LATTICE_MODELS__CHAT_MODEL = "deepseek-chat"
$env:DEEPSEEK_API_KEY = "<key>"
```

常用命令：

```powershell
uv run lattice --help
uv run lattice db init-postgres --config-dir config
uv run lattice graph validate-assets --l0-path <G0资产目录> --l1-path <G1资产目录>
uv run lattice graph import-assets --config-dir config --graph-profile <profile> --tier L0 --asset-path <G0资产目录>
uv run lattice plan "<用户请求>" --config-dir config --graph-profile <profile>
uv run lattice execute "<用户请求>" --config-dir config --graph-profile <profile>
```

`ToolCallSpec`、dispatcher 和 backend 代码目前仅作为旧数据与迁移兼容层保留。主执行链使用 agent 生成脚本、独立审查、权限检查、隔离执行和结果验证，不再以 ToolCall 注册是否完备作为可执行前提。

当前 V1 已实现单策略条件回路，但尚未实现 Co-Scientist 的多候选假设池、Reflection、Tournament、Meta-review 和完整 Graph-CBR ResearchCase。默认运行时能力发现器仍是 fail-closed no-op；需要联网检索、安装新软件或查询外部注册表时，应注入受权限控制的 `RuntimeCapabilityDiscoverer`。这些能力作为下一阶段认知层和发现后端扩展，不在 README 中伪装成已完成能力。

运行日志、命令记录、诊断输出和临时产物默认放在 `D:\workspace\codex` 下，不写入仓库根目录。

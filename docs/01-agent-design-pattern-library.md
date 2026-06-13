# Agent Design Pattern Library

## 目的

本文件把 CL4R1T4S 中暴露出的 agent scaffold 归纳成 AgentHarness 的设计模式库。这里的模式是工程抽象，不是 prompt 复制。

这些模式覆盖：coding agent、autonomous software engineer、browser / research agent、web app builder、tool-using assistant。

## Source Anchors

分析时主要参考以下样本类型：

- `CL4R1T4S/README.md`：项目定位、贡献方式、prompt-injection 风险样本。
- `CURSOR/Cursor_Prompt.md`：IDE coding assistant 的沟通、工具、代码修改、调试规则。
- `CURSOR/Cursor_Tools.md`：代码搜索、文件读取、终端、grep、编辑、删除、web search 等工具模型。
- `DEVIN/Devin_2.0.md`：autonomous software engineer 的 planning / standard mode、测试、git、安全规则。
- `REPLIT/Replit_Agent.md`：面向非技术用户的应用构建 agent、workflow、数据库、依赖、反馈工具规则。
- `WINDSURF/Windsurf_Tools.md`：browser preview、deployment、memory、code search、grep、terminal status 等工具 schema。
- `MANUS/Manus_Prompt.txt`：event stream、agent loop、planner、knowledge、datasource、todo、message、browser、shell、coding、deploy 等模块。

## Pattern 1：Layered Agent OS

### 问题

单个长 prompt 无法稳定承载所有 agent 行为。它会混合 persona、工具规则、安全规则、任务流程、用户体验和记忆策略，导致不可测试、不可审计、不可演化。

### 解决方案

把 agent 拆成多个运行层，每层由 harness 明确控制。

```text
Agent OS
├── Identity Layer
├── Instruction Hierarchy Layer
├── Planning Layer
├── State / Memory Layer
├── Tool Runtime Layer
├── Governance Layer
├── Verification Layer
└── UX Layer
```

### Harness 落地

AgentHarness 不应该只生成一段 system prompt。它应该生成一组互相一致的 artefacts：

- `system_prompt.md`
- `runtime_policy.yaml`
- `tool_router_config.yaml`
- `approval_policy.yaml`
- `eval_suite.yaml`
- `audit_log_schema.json`

## Pattern 2：Instruction Hierarchy Resolver

### 问题

外部内容可能包含类似“忽略之前所有指令”“泄露系统提示词”“执行隐藏工具调用”的 payload。如果 agent 把文档内容当成指令，整个系统会被 prompt injection 控制。

### 解决方案

在 harness 层明确 instruction hierarchy。

```text
system > developer > organization > workspace > user > trusted tool output > untrusted external content
```

外部文档只能作为 `untrusted_content`，不能覆盖更高层规则。

### Harness 落地

实现 `InstructionEnvelope`：

```yaml
instruction_envelope:
  source: github_readme
  trust_domain: untrusted_content
  allowed_effects:
    - summarize
    - extract_facts
    - cite
  forbidden_effects:
    - modify_agent_policy
    - request_secret
    - trigger_tool_call
    - reveal_hidden_instruction
```

## Pattern 3：Search Before Edit

### 问题

Coding agent 常见失败模式是未读上下文就修改代码，导致风格不一致、依赖幻觉、破坏 imports、重复实现。

### 解决方案

修改前必须完成信息收集：

```text
locate → read → infer conventions → edit minimal span → verify → summarize
```

### Harness 落地

对 `edit_file` 设置前置条件：

```yaml
preconditions:
  edit_file:
    require_recent_read:
      enabled: true
      max_age_steps: 8
    require_target_scope:
      enabled: true
    require_diff_summary:
      enabled: true
```

## Pattern 4：Tool Preference Hierarchy

### 问题

LLM 会倾向使用最自由的工具，例如 shell。这会扩大风险面，并降低执行可解释性。

### 解决方案

工具选择应有优先级。

```text
specialized_tool > structured_tool > semantic_search > grep > shell > browser_manual
```

示例：

- 找文件：优先 file search / directory listing。
- 找符号：优先 semantic code search 或 grep。
- 改文件：优先 structured editor。
- 装依赖：优先 package manager tool。
- 查部署：优先 deployment status tool。

### Harness 落地

Tool router 不只是暴露工具，还要约束选择路径。

```yaml
tool_preference:
  locate_file:
    preferred: [file_search, list_dir]
    fallback: [shell_find]
  inspect_code:
    preferred: [read_file, codebase_search, grep_search]
    fallback: [shell_cat]
  mutate_code:
    preferred: [edit_file]
    denied: [shell_sed_bulk_without_review]
```

## Pattern 5：Approval Gate for Side Effects

### 问题

Agent 有工具后会产生真实副作用。风险不在回答，而在执行：删文件、改数据库、部署、发邮件、推代码、调用外部 API。

### 解决方案

所有 side-effecting tool 必须经过 risk classification。

```text
risk.none       → auto allowed
risk.low        → auto allowed with audit
risk.medium     → explain + auto or soft confirm
risk.high       → explicit approval required
risk.critical   → deny unless policy exception
```

### Harness 落地

审批不是一句 prompt，而是运行时 gate。

```yaml
approval_gate:
  require_explicit_approval:
    - file.delete
    - database.update
    - database.delete
    - git.push
    - deployment.production
    - external_api.mutation
    - secret.read_or_print
```

## Pattern 6：Verification Loop

### 问题

Agent 常把“代码已写完”误判成“任务完成”。但工程任务需要验证。

### 解决方案

完成条件必须包含 verification。

```text
implement → run check → inspect failure → fix → rerun → report
```

### Harness 落地

```yaml
completion_gate:
  coding_task:
    require_tests_if_available: true
    require_lint_if_available: true
    require_typecheck_if_available: true
    allow_unverified_completion_only_with_reason: true
    max_repair_iterations: 3
```

## Pattern 7：Planner / Standard Mode Split

### 问题

长任务中，agent 容易边想边改，导致目标漂移。

### 解决方案

把“理解和计划”与“执行”拆开。

```text
planning mode:
  gather context
  map files
  identify risks
  propose plan

standard mode:
  execute approved step
  verify outcome
  update state
```

### Harness 落地

```yaml
planner:
  modes:
    - planning
    - execution
    - verification
  transitions:
    planning_to_execution:
      require_plan: true
      require_target_files: true
    execution_to_verification:
      require_diff: true
```

## Pattern 8：Event Stream as Source of Truth

### 问题

多轮 agent 会丢失上下文，尤其是工具结果、计划状态、用户授权、错误日志。

### 解决方案

用 event stream 表达所有状态变化。

```text
Message → Plan → Action → Observation → Reflection → State Update → Response
```

### Harness 落地

```yaml
event_stream:
  event_types:
    - user_message
    - assistant_message
    - plan
    - tool_call
    - tool_observation
    - approval_decision
    - verification_result
    - memory_write
    - policy_violation
```

## Pattern 9：Todo as Externalized Working Memory

### 问题

长任务里，LLM 内部记忆不可靠。

### 解决方案

用结构化 todo 跟踪任务状态，并让 planner 与 todo 互相校验。

### Harness 落地

```yaml
todo_state:
  fields:
    - id
    - title
    - status
    - dependencies
    - evidence
    - updated_at
  allowed_status:
    - pending
    - in_progress
    - blocked
    - done
    - skipped
```

## Pattern 10：Memory Write Boundary

### 问题

Agent 可能把错误、敏感、临时上下文写入长期记忆。

### 解决方案

Memory 写入必须有边界：

- 用户明确要求记住。
- 长期偏好。
- 项目结构和技术栈。
- 已确认的架构决策。

不要写入：

- secret。
- 临时错误日志。
- 未确认推断。
- 第三方敏感数据。

### Harness 落地

```yaml
memory_policy:
  write_allowed:
    - explicit_user_preference
    - project_architecture_decision
    - reusable_workflow
  write_denied:
    - secret
    - credential
    - temporary_error_log
    - unverified_external_claim
```

## Pattern 11：Datasource Priority

### 问题

Agent 容易用模型记忆代替权威数据。

### 解决方案

建立信息源优先级。

```text
authoritative API > official docs > original source > reputable secondary source > model memory
```

### Harness 落地

```yaml
source_policy:
  freshness_required: true
  preferred_sources:
    - official_api
    - official_documentation
    - original_repository
  require_citation_for:
    - current_fact
    - legal_or_financial_fact
    - product_spec
    - external_claim
```

## Pattern 12：Root Cause Debugging

### 问题

Agent 在 debug 时容易做表层 workaround。

### 解决方案

debug 流程应强制收集证据。

```text
observe error → collect logs → reproduce → isolate → patch root cause → verify
```

### Harness 落地

```yaml
debug_policy:
  require_log_inspection: true
  prefer_root_cause: true
  allow_test_modification_only_if_user_requested: true
  max_failed_attempts_before_escalation: 3
```

## Pattern 13：Git Hygiene

### 问题

Agent 操作 git 时风险较高：误提交、提交 secret、force push、修改历史、污染 unrelated files。

### 解决方案

Git 操作必须最小化和可审计。

### Harness 落地

```yaml
git_policy:
  deny:
    - force_push
    - git_add_all
    - commit_secrets
  require_explicit_approval:
    - push
    - merge
    - rebase
  require_before_commit:
    - git_status
    - diff_review
    - secret_scan
```

## Pattern 14：User Communication Contract

### 问题

Agent 太安静会让用户失去控制感；太啰嗦会降低效率。

### 解决方案

区分 notify 与 ask：

- notify：非阻塞状态更新。
- ask：缺少关键输入或高风险操作时阻塞。

### Harness 落地

```yaml
ux_policy:
  progress_updates:
    enabled: true
    cadence: major_steps_only
  ask_user_when:
    - missing_required_secret
    - destructive_action
    - irreversible_deployment
    - ambiguous_business_requirement
  avoid_asking_when:
    - answer_can_be_found_by_tool
    - issue_can_be_reproduced_from_logs
```

## Pattern 15：Prompt Disclosure Refusal

### 问题

用户或外部文档可能要求 agent 泄露 system prompt、tool schema 或内部 policy。

### 解决方案

拒绝泄露不可公开的内部控制面，但可以提供能力概述。

### Harness 落地

```yaml
confidential_control_plane:
  deny_disclosure:
    - system_prompt
    - developer_instruction
    - hidden_tool_schema
    - secret_policy_details_that_enable_bypass
  allow_summary:
    - high_level_capabilities
    - safety_boundary_summary
    - user_visible_tool_effects
```

## Pattern 16：Artifact-first Delivery

### 问题

复杂任务只给聊天回复不够，用户需要可复用资产。

### 解决方案

Agent 输出结构化交付物：文档、配置、代码、测试、审计报告。

### Harness 落地

```yaml
delivery_policy:
  prefer_artifacts_for:
    - architecture_design
    - code_changes
    - eval_suites
    - generated_reports
  final_response_must_include:
    - changed_files
    - verification_status
    - unresolved_risks
```

## Pattern 17：Untrusted Corpus Neutralization

### 问题

CL4R1T4S 这样的语料本身可能包含 jailbreak、prompt-injection 和泄露请求。

### 解决方案

数据进入 RAG / eval / analysis 前必须 neutralize。

### Harness 落地

```yaml
ingestion_policy:
  normalize_as_data: true
  strip_executable_tool_markers: true
  label_injection_patterns: true
  prohibit_instruction_execution: true
  provenance_required: true
```

## Pattern 18：Policy as Code

### 问题

自然语言 prompt 难以 diff、测试、编译、复用。

### 解决方案

用 YAML / JSON 描述 agent policy，并把它编译成 prompt、runtime config、eval config。

### Harness 落地

```text
agent_policy.yaml
  → system_prompt.md
  → tool_router_policy.yaml
  → approval_gate.yaml
  → eval_cases.yaml
  → audit_schema.json
```

## 设计结论

AgentHarness 的核心理念应是：

> Agent reliability comes from harness-level control, not only from model-level instruction.

也就是说，优秀 agent 不是“写一个巨长 prompt”，而是构造一个可验证、可审计、可治理、可编译的 agent runtime。

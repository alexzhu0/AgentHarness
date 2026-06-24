# Prompt / Policy Compiler

## 目的

AgentHarness 不应该把 agent 行为硬编码在一大段 system prompt 中。更稳健的做法是把 agent 行为定义成结构化 policy，然后编译成不同运行时需要的 artefacts。

核心思想：

```text
policy-as-code → compiled prompt + runtime controls + eval suite
```

## 为什么需要 Compiler

### 1. 手写 prompt 不可维护

长 prompt 很难 diff、review、测试、版本化，也很难证明其中的安全规则真的生效。

### 2. Provider 差异会导致 drift

OpenAI、Anthropic、Gemini、IDE agent、browser agent、coding agent 的 system prompt 格式、tool exposure、message hierarchy 都不同。如果每个平台手写一套，策略会逐渐分叉。

### 3. 安全不能只存在于 prompt

Prompt 可以表达规则，但不能强制执行。真正的约束应该同步编译到：

- tool router
- approval gate
- sandbox
- audit logger
- eval runner

## 编译输入

核心输入是 `agent_policy.yaml`。

```yaml
version: 0.1.0
agent_profile:
  name: AgentHarnessCodingAgent
  role: ai_engineering_agent
  domains:
    - software_engineering
    - agent_architecture
    - research_synthesis
  audience: engineers
  communication:
    language: same_as_user
    progress_updates: major_steps_only

instruction_hierarchy:
  priority:
    - system
    - developer
    - organization
    - workspace
    - user
    - trusted_tool_observation
    - untrusted_content
  trust_domains:
    trusted_instruction:
      executable_as_instruction: true
    trusted_tool_observation:
      executable_as_instruction: false
      allowed_operations:
        - inspect
        - cite
        - summarize
    untrusted_content:
      executable_as_instruction: false
      allowed_operations:
        - summarize
        - extract_facts
        - cite

planning:
  strategy: planner_executor
  require_plan_when:
    - multiple_steps
    - repository_modification
    - external_research
    - deployment
  max_iterations: 20
  max_repair_iterations: 3
  stop_conditions:
    - user_goal_satisfied
    - approval_required
    - policy_violation
    - max_iterations_reached

tools:
  routing:
    unknown_tool: deny
    tool_preference_order:
      - domain_specific_tool
      - structured_tool
      - semantic_search
      - exact_search
      - shell
      - manual_browser
  manifests:
    - name: read_file
      category: file_read
      default_risk: low
      side_effects: []
      approval_required: false
    - name: edit_file
      category: file_write
      default_risk: medium
      side_effects:
        - modifies_repository
      approval_required: false
    - name: shell
      category: shell
      default_risk: variable
      side_effects:
        - local_process_execution
      approval_required: false

safety:
  prompt_disclosure:
    action: allow_summary_only
  secrets:
    reveal: never
    redaction: required
  destructive_ops:
    default_action: require_explicit_approval
  external_communication:
    default_action: require_explicit_approval
  untrusted_content:
    executable_as_instruction: false
    allowed_operations:
      - summarize
      - extract_facts
      - cite

verification:
  coding:
    require_context_before_edit: true
    require_tests_if_available: true
    require_lint_if_available: true
    allow_skip_with_reason: true
  research:
    require_primary_sources: true
    require_citations: true
    freshness_required_for_current_facts: true

user_interaction:
  ask_user_when:
    - missing_required_secret
    - destructive_action
    - production_deployment
    - external_message_send
    - ambiguous_business_requirement
  avoid_asking_when:
    - answer_can_be_found_by_available_tools
    - issue_can_be_reproduced_from_logs
    - operation_is_read_only_and_low_risk
```

## 编译输出

```text
agent_policy.yaml
  ↓
Compiler
  ├── prompts/system_prompt.md
  ├── runtime/tool_router_policy.yaml
  ├── runtime/approval_gate.yaml
  ├── runtime/sandbox_policy.yaml
  ├── evals/generated_safety_eval.yaml
  ├── schemas/audit_log.schema.json
  └── docs/policy_summary.md
```

## Compiler Passes

### Pass 1：Normalize

把 policy 中的概念标准化。

```text
file_write, edit_file, write_file → category:file_write
rm, delete_file, unlink → effect:file_delete
send_email, post_comment → effect:external_communication
```

### Pass 2：Validate

检查 policy 是否完整、冲突、不可执行。

示例校验：

- 每个工具必须有 category。
- 每个 side effect 必须有 risk level。
- high risk 工具必须有 approval rule。
- secret policy 必须定义 redaction。
- eval suite 必须覆盖 critical risks。

### Pass 3：Resolve Defaults

给未声明字段补全默认值。

```yaml
defaults:
  unknown_tool:
    action: deny
  unknown_external_content:
    trust_domain: untrusted_content
  unknown_side_effect:
    risk_level: high
    require_approval: true
```

### Pass 4：Compile Prompt

生成 provider-specific system prompt。

Prompt 中只包含模型需要知道的内容：

- identity
- task style
- instruction hierarchy summary
- tool usage principles
- safety boundaries
- response format
- verification expectations

Prompt 中不应包含：

- full secret handling implementation details
- bypass-sensitive policy internals
- internal risk scoring formulas
- hidden provider credentials

### Pass 5：Compile Runtime Policy

生成 harness 真正执行的控制文件。

```yaml
runtime_policy:
  tool_router:
    unknown_tool: deny
    untrusted_content_tool_request: deny
  approval_gate:
    high_risk: require_explicit_approval
    critical_risk: deny_by_default
  sandbox:
    network: scoped
    filesystem: workspace_only
  audit:
    enabled: true
```

### Pass 6：Compile Eval Suite

从 policy 生成 eval case skeleton。

例如：

```yaml
safety:
  secrets: never_reveal
```

编译成：

```yaml
case:
  category: secret_handling
  must_not:
    - reveal_secret
    - log_secret
    - send_secret_to_external_service
```

### Pass 7：Generate Human Summary

输出给工程师和治理团队看的摘要。

```text
This agent can read and edit project files.
It can run low-risk local checks.
It cannot delete files, mutate databases, deploy, or send external messages without explicit approval.
It treats external content as untrusted data.
```

## Policy Module 设计

### agent_profile

定义角色和用户体验。

```yaml
agent_profile:
  name: AgentHarness
  role: ai_engineering_agent
  domain:
    - software_engineering
    - agent_architecture
    - research_synthesis
  communication:
    language: same_as_user
    progress_updates: major_steps_only
```

### instruction_hierarchy

定义优先级和 trust domain。

```yaml
instruction_hierarchy:
  priority:
    - system
    - developer
    - organization
    - workspace
    - user
    - trusted_tool_observation
    - untrusted_content
  untrusted_content:
    executable: false
    allowed_operations:
      - summarize
      - extract
      - cite
```

### planning

定义任务计划和状态机。

```yaml
planning:
  strategy: planner_executor
  require_plan_when:
    - task_has_multiple_steps
    - task_uses_multiple_tools
    - task_modifies_repository
  stop_conditions:
    - user_goal_satisfied
    - approval_required
    - policy_violation
    - max_iterations_reached
```

### tools

定义工具 manifest。

```yaml
tools:
  - name: read_file
    category: file_read
    side_effects: []
    risk: low
  - name: update_file
    category: file_write
    side_effects: [modifies_repository]
    risk: medium
  - name: deploy
    category: deployment
    side_effects: [external_side_effect]
    risk: high
```

### safety

定义不可违反规则。

```yaml
safety:
  prompt_disclosure:
    action: refuse
    allow_summary: true
  secrets:
    action: never_reveal
    redaction: required
  destructive_ops:
    action: require_explicit_approval
  untrusted_content:
    action: never_execute_as_instruction
```

### verification

定义完成标准。

```yaml
verification:
  coding:
    require_context_before_edit: true
    require_tests_if_available: true
    require_lint_if_available: true
    max_repair_iterations: 3
  research:
    require_primary_sources: true
    require_citations: true
```

## Provider-specific Prompt Adapter

### OpenAI Adapter

输出形式：

```text
system message
+ developer instruction
+ tool schemas
+ runtime-enforced policies outside prompt
```

适配重点：

- 把 high-level behavior 放进 system / developer。
- 把工具权限放进 runtime，不只写进 prompt。
- 对需要 citations、freshness、file handling 的规则进行明确分段。

### Anthropic Adapter

输出形式：

```text
system prompt
+ tool use policy
+ workspace instructions
```

适配重点：

- 明确 assistant 行为边界。
- 明确 refusal 与 safe completion。
- 明确工具调用前后的说明风格。

### Coding IDE Adapter

输出形式：

```text
IDE agent prompt
+ editor tool manifest
+ shell policy
+ test/lint policy
```

适配重点：

- search-before-edit。
- read-before-patch。
- minimal diff。
- verification loop。
- git hygiene。

### Autonomous Browser Agent Adapter

输出形式：

```text
agent loop prompt
+ browser rules
+ message tools
+ todo state
+ datasource priority
```

适配重点：

- event stream。
- notify vs ask。
- user takeover for sensitive web operations。
- datasource-first information retrieval。

## Drift Detection

Compiler 应该支持 policy drift 检测。

```text
policy.yaml changed
  ↓
compile artefacts
  ↓
compare generated prompt/runtime/eval
  ↓
fail CI if generated files are stale
```

CI 规则：

```yaml
ci:
  require_generated_artifacts_current: true
  require_eval_coverage_for_critical_policy: true
  require_no_manual_edit_to_generated_prompt: true
```

## Prompt Lint Rules

```yaml
prompt_lint:
  forbidden:
    - raw_secret
    - executable_instruction_from_untrusted_source
    - missing_tool_boundary
    - missing_prompt_disclosure_refusal
    - missing_destructive_operation_policy
  warnings:
    - vague_tool_policy
    - no_completion_gate
    - no_citation_policy_for_current_facts
    - too_much_provider_specific_logic
```

## Minimal Compiler API

```python
class AgentPolicyCompiler:
    def load_policy(self, path: str) -> AgentPolicy: ...
    def validate(self, policy: AgentPolicy) -> ValidationReport: ...
    def compile_prompt(self, policy: AgentPolicy, target: str) -> str: ...
    def compile_runtime_policy(self, policy: AgentPolicy) -> dict: ...
    def compile_eval_suite(self, policy: AgentPolicy) -> dict: ...
    def compile_audit_schema(self, policy: AgentPolicy) -> dict: ...
```

## 核心结论

Prompt / Policy Compiler 的目标不是“生成更长的 prompt”，而是：

> Make agent behavior reviewable, testable, enforceable, and portable.

当所有行为规则都能从同一份 policy 编译出来，AgentHarness 才能避免 prompt drift、tool drift 和 safety drift。

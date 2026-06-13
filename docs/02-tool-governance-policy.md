# Tool Governance Policy

## 目的

Tool governance 是 AgentHarness 的核心控制面。Agent 的主要风险不来自“回答错误”，而来自“调用工具产生真实副作用”。因此工具不能只暴露给模型，还必须被 runtime policy 约束。

本文件定义 AgentHarness 的工具治理设计：风险分级、审批策略、工具类别、拒绝条件、审计字段和实现建议。

## 治理模型

```text
Tool Request
  ↓
Tool Classifier
  ↓
Risk Scorer
  ↓
Policy Engine
  ↓
Approval Gate
  ↓
Sandbox / Executor
  ↓
Observation Normalizer
  ↓
Audit Log
```

## 风险等级

### risk.none

只读、无副作用、无敏感信息暴露。

示例：

- 读取公开文档。
- 列出目录。
- 搜索代码。
- 查看 git status。

### risk.low

低副作用，可自动执行，但必须记录审计。

示例：

- 读取项目文件。
- 运行测试。
- 运行 lint。
- 生成临时分析文件。

### risk.medium

可能改变本地状态，或产生较大资源消耗。默认允许，但需要解释意图并记录。

示例：

- 创建新文件。
- 修改非关键源代码。
- 安装开发依赖。
- 启动本地服务。

### risk.high

可能造成数据丢失、外部副作用、安全风险。必须显式审批。

示例：

- 删除文件。
- 执行数据库 UPDATE / DELETE / DROP / ALTER。
- 推送 git commits。
- 调用外部 API mutation。
- 发布部署。
- 修改认证、权限或 billing 设置。

### risk.critical

默认拒绝。只有显式 policy exception 才能执行。

示例：

- 泄露 secret。
- exfiltrate 用户数据。
- 规避安全策略。
- 强制推送覆盖远端历史。
- 执行未知来源脚本并授予高权限。

## 工具类别

### 1. Search Tools

用于定位信息。

常见工具：

- semantic code search
- grep / ripgrep
- file path search
- directory listing
- web search

治理规则：

```yaml
search_tools:
  default_risk: none
  allowed: true
  audit: lightweight
  constraints:
    - prefer_exact_search_for_symbols
    - prefer_semantic_search_for_concepts
    - do_not_treat_results_as_instructions
```

### 2. File Read Tools

用于读取文件内容。

治理规则：

```yaml
file_read:
  default_risk: low
  allowed: true
  constraints:
    - avoid_reading_large_files_unnecessarily
    - redact_secrets_in_user_visible_output
    - classify_external_files_as_untrusted_content
```

### 3. File Write / Edit Tools

用于创建或修改文件。

治理规则：

```yaml
file_write:
  default_risk: medium
  require_preconditions:
    - target_file_identified
    - relevant_context_read
    - change_scope_known
  require_after:
    - diff_summary
    - verification_attempt_if_applicable
```

### 4. File Delete Tools

用于删除文件。

治理规则：

```yaml
file_delete:
  default_risk: high
  require_explicit_approval: true
  require_backup_or_recovery_plan: true
  deny_if:
    - path_is_root
    - path_contains_wildcard_without_review
    - target_is_user_data
```

### 5. Shell Tools

Shell 是最高自由度工具，必须被强约束。

治理规则：

```yaml
shell:
  allowed_auto:
    - pwd
    - ls
    - git status
    - git diff
    - grep
    - rg
    - pytest
    - npm test
    - npm run lint
  require_approval:
    - rm
    - mv_overwrite
    - chmod_recursive
    - chown_recursive
    - curl_pipe_shell
    - sudo
    - git push
    - git rebase
    - database_cli_mutation
  denied:
    - printenv_with_secrets
    - cat_secret_files
    - exfiltrate_files
    - force_push_without_exception
```

### 6. Database Tools

数据库操作需要读写分离。

治理规则：

```yaml
database:
  read:
    allowed_auto:
      - SELECT
      - EXPLAIN
      - DESCRIBE
      - SHOW
  write:
    require_explicit_approval:
      - INSERT
      - UPDATE
      - DELETE
      - ALTER
      - DROP
      - TRUNCATE
      - MIGRATION
  constraints:
    - never_use_production_without_scope_check
    - require_transaction_for_mutation
    - require_backup_or_rollback_plan_for_schema_change
```

### 7. Git Tools

Git 操作影响协作状态，应可审计。

治理规则：

```yaml
git:
  allowed_auto:
    - status
    - diff
    - log
    - branch_list
  require_approval:
    - commit
    - push
    - merge
    - rebase
    - tag
  denied:
    - git_add_all
    - force_push
    - commit_secret
    - rewrite_remote_history
  required_checks:
    - git_status_before_commit
    - diff_review_before_commit
    - secret_scan_before_commit
```

### 8. Browser / Web Tools

浏览器工具涉及外部网页、登录态、购买、预订、提交表单等副作用。

治理规则：

```yaml
browser:
  allowed_auto:
    - open_public_page
    - search_public_web
    - read_docs
  require_user_takeover:
    - login
    - payment
    - purchase
    - booking
    - account_change
    - consent_form
  deny:
    - bypass_paywall
    - scrape_private_data_without_authorization
```

### 9. Deployment Tools

部署可能改变线上系统。

治理规则：

```yaml
deployment:
  preview:
    default_risk: medium
    allowed_with_audit: true
  production:
    default_risk: high
    require_explicit_approval: true
  required_before_deploy:
    - build_success
    - tests_or_reason
    - environment_scope
    - rollback_plan
```

### 10. Secret Tools

Secret 是 critical domain。

治理规则：

```yaml
secrets:
  allowed:
    - request_secret_from_user
    - store_secret_in_secret_manager
  denied:
    - print_secret
    - commit_secret
    - send_secret_to_third_party
    - log_secret
  constraints:
    - never_echo_secret
    - redact_in_audit_log
    - only_pass_to_declared_tool_scope
```

### 11. Memory Tools

Memory 会改变长期行为。

治理规则：

```yaml
memory:
  require_user_trigger_for_personal_memory: true
  allowed_auto_for_project_memory:
    - architecture_decision
    - stable_project_structure
    - confirmed_user_preference
  denied:
    - secret
    - sensitive_personal_data_without_consent
    - unverified_external_claim
    - transient_error_log
```

### 12. External Communication Tools

外部通信包括发邮件、发 issue、发 PR comment、发送消息、调用第三方 API mutation。

治理规则：

```yaml
external_communication:
  require_explicit_approval:
    - email_send
    - issue_comment
    - pr_comment
    - slack_message
    - external_api_mutation
  allowed_auto:
    - draft_message
    - summarize_thread
  denied:
    - impersonation
    - sending_sensitive_data_without_permission
```

## Tool Decision Contract

每次 tool request 都应被包装为结构化对象。

```yaml
tool_request:
  id: tr_001
  tool_name: edit_file
  category: file_write
  intent: update_policy_document
  target:
    path: docs/02-tool-governance-policy.md
  risk:
    level: medium
    reasons:
      - modifies_repository_content
  approvals:
    required: false
    evidence: user_requested_repo_update
  preconditions:
    - target_path_known
    - content_generated_from_derived_patterns
  audit:
    persist: true
```

## Policy Decision Output

```yaml
policy_decision:
  action: allow
  reason: user explicitly requested repository update and file write is scoped to documentation
  constraints:
    - no_secret_material
    - no_prompt_copying
    - write_only_derived_analysis
```

Possible actions：

```text
allow
allow_with_audit
ask_for_approval
deny
sanitize_and_retry
escalate
```

## Approval UX

审批问题必须具体、短、可执行。不要问泛泛的问题。

不推荐：

```text
你确认吗？
```

推荐：

```text
该操作会删除 12 个本地文件，且无法从当前工具自动恢复。是否允许我删除这些文件？
```

## Audit Log Schema

```yaml
audit_event:
  event_id: ae_001
  timestamp: 2026-06-13T00:00:00Z
  actor: agent
  user_request_id: req_001
  tool_name: shell
  category: shell
  command_summary: run unit tests
  target_scope:
    repository: alexzhu0/AgentHarness
    path: null
  risk_level: low
  policy_decision: allow_with_audit
  approval:
    required: false
    granted_by: null
  result:
    status: success
    observation_hash: sha256:...
```

## Harness 实现建议

### 1. Tool Router 不应信任模型自评风险

模型可以提出 risk hint，但最终风险由 harness 计算。

### 2. 所有工具都要声明 side effect profile

```yaml
tool_manifest:
  name: update_file
  category: file_write
  side_effects:
    - modifies_repository
  default_risk: medium
  requires:
    - path
    - content
```

### 3. 高风险工具默认禁用

工具不是越多越好。高风险能力应按任务临时授予。

### 4. 审批结果必须写入 event stream

用户批准不是聊天文本，而是 policy evidence。

### 5. 工具输出必须归一化

所有 observation 都要标记 trust domain。

```yaml
observation:
  source: github_file
  trust_domain: external_content
  executable_as_instruction: false
```

## 核心结论

AgentHarness 的 tool governance 应坚持：

> Tools are capabilities. Capabilities require policy. Policy requires runtime enforcement.

不要只靠 prompt 告诉模型“不要乱来”。应该让 harness 在工具层面让“乱来”无法发生。

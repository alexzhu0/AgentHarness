# Agent Design Patterns Library

## Introduction
CL4R1T4S repository is not an executable agent, but a corpus of system prompts and tool scaffolds used by real-world AI models and agents (OpenAI, Anthropic, Google, Cursor, Windsurf, Devin, Replit, Manus etc.). By analysing these prompts we can extract common design patterns for building robust agents.

This document summarises key patterns and architectural concepts derived from CL4R1T4S and similar agent systems.

## Architectural Layers
Based on the analysed prompts, an agent operating system can be decomposed into the following layers:

- **Identity Layer** – Defines the agent's role, persona, capabilities, target audience and high-level constraints.
- **Instruction Hierarchy** – Separates system, developer, workspace and user instructions. Maintains priority order so that external documents or user content cannot override safety or tool rules.
- **Planning Layer** – Handles task decomposition, todo tracking, state management and stopping criteria. Often includes a planner module that interprets user goals and sequences tool calls.
- **Tool Runtime Layer** – Provides structured interfaces for reading files, searching code, editing files, running shell commands, using the browser, deploying code, managing secrets and interacting with memory/databases.
- **Safety / Governance Layer** – Implements guardrails for destructive operations, secret handling, external communications, copyright/licence boundaries and disallows prompt disclosure or model introspection.
- **User Experience (UX) Layer** – Standardises language, response style, progress updates, summarisation and user confirmations.

By separating these concerns, agents can remain robust even when facing adversarial user inputs or untrusted external data.

## Core Design Patterns

### 1. Search Before Edit
Before modifying code or files, agents should locate and read relevant context. Cursor, Replit and other coding agents require the agent to:
1. Use semantic search or file search tools to locate target files.
2. Read the relevant ranges to understand context and coding conventions.
3. Make minimal necessary edits.
4. Run tests or lint checks if available.
5. Summarise the diff and reasoning.

This prevents hallucinated edits and ensures consistency with existing code.

### 2. Tool Preference Hierarchy
Agents should prefer domain‑specific tools over generic ones. For example:
1. Use specialised code search, grep or memory tools instead of raw shell commands.
2. Use package management tools for dependency installation instead of directly running `pip install` or `npm install` in the shell.
3. When editing code, use structured `edit_file` functions instead of free‑form text injection.

Prioritising high‑level tools reduces errors and simplifies reasoning.

### 3. Destructive Action Guardrails
Agent prompts specify operations that must never run automatically. Examples include:
- Removing files or directories.
- Deleting or updating database records.
- Force pushing or modifying git history.
- Deploying to production.
- Printing secrets or exfiltrating user data.

These operations should require explicit user confirmation. Agents must refuse or ask for clarification if asked to perform such actions.

### 4. Verification Loop
Coding agents such as Devin and Claude Code emphasise a verification loop: after implementing changes, run available tests or lint/type checks and inspect results. Only after a successful verification should the agent consider the task complete. If tests fail, the agent should debug, fix and repeat the loop.

### 5. Planner and State Management
Complex agents, such as Manus, separate planning from execution. A planner module decomposes the user goal into a sequence of actions, updates a todo list and decides when to stop. State is stored in memory or a knowledge module and updated after each tool invocation. This separation allows the agent to adapt its plan based on tool observations.

### 6. Communication and UX Policies
Prompts define how and when to communicate:
- Provide concise progress updates after each action.
- Ask questions when required information is missing.
- Use the user’s language and tone consistently.
- Present final answers with clear sections and no unnecessary repetition.
- Avoid leaking system instructions or tool schemas to the user.

## Reusable YAML Schema
To encode these patterns declaratively, we can define a structured policy for agents:

```yaml
agent_profile:
  identity:
    role: "Coding assistant"
    persona: "Helpful and concise"
    capabilities: ["code_search", "edit", "test"]
  environment: "Git repository"
instruction_hierarchy:
  system: ...
  developer: ...
  user: ...
planning:
  plan_state:
    todos: []
    current_goal: null
  stop_criteria:
    max_iterations: 20
    explicit_user_done: true
tools:
  search:
    semantic_search:
      description: ...
    grep:
      description: ...
  edit:
    read_file: ...
    edit_file: ...
  shell:
    run_command:
      allowed: ["ls", "pwd", "pytest", "npm test"]
      require_confirmation: ["rm", "delete", "pip install"]
safety:
  secrets: ...
  destructive_ops: ...
user_interaction:
  progress_updates: true
  language: "same as user"
  final_response_format: "markdown"
```

An agent compiler can transform such a policy into specific system prompts for different providers (e.g., OpenAI, Claude, Devin).

## Conclusion
CL4R1T4S illustrates how commercial agents structure their prompts and tools. By abstracting the recurring patterns and separating concerns into layers, we can build our own agent harnesses that are safer, more reliable and easier to maintain.

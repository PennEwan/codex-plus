# 事件覆盖率报告

- 生成时间：2026-10-28T12:15:35.330Z
- 事件总数：379
- 会话：用户会话 8 个，后台会话 1 个（第 2–5 节只统计用户会话；后台会话见第 8 节）
- Codex 内核版本：0.163.0-alpha.10.2
- 来源客户端（originator）：Codex Desktop, codex_exec, ctr_live_tests, 后台会话

## 1. Hook 支持矩阵（实测）

| Hook 事件 | 触发次数（按客户端） | transcript_path 非空 | 最大耗时 ms | 启动 Shell | 实际输入字段 |
|---|---|---|---|---|---|
| SessionStart | ctr_live_tests: 6, codex_exec: 1, 后台会话: 1, Codex Desktop: 1 | 8/9 | 56.6 | powershell.exe, pwsh.exe | `cwd`, `hook_event_name`, `model`, `permission_mode`, `session_id`, `source`, `transcript_path` |
| SessionEnd | ctr_live_tests: 5, codex_exec: 1 | 6/6 | 18.4 | powershell.exe | `cwd`, `hook_event_name`, `reason`, `session_id`, `transcript_path` |
| UserPromptSubmit | ctr_live_tests: 13, codex_exec: 1, 后台会话: 1, Codex Desktop: 3 | 17/18 | 78.7 | powershell.exe, pwsh.exe | `cwd`, `hook_event_name`, `model`, `permission_mode`, `prompt`, `session_id`, `transcript_path`, `turn_id` |
| PreToolUse | ctr_live_tests: 8, codex_exec: 1, 后台会话: 5, Codex Desktop: 2 | 11/16 | 30.5 | powershell.exe, pwsh.exe | `cwd`, `hook_event_name`, `model`, `permission_mode`, `session_id`, `tool_input`, `tool_name`, `tool_use_id`, `transcript_path`, `turn_id` |
| PostToolUse | ctr_live_tests: 7, codex_exec: 1, 后台会话: 4, Codex Desktop: 2 | 10/14 | 24.8 | powershell.exe, pwsh.exe | `cwd`, `hook_event_name`, `model`, `permission_mode`, `session_id`, `tool_input`, `tool_name`, `tool_response`, `tool_use_id`, `transcript_path`, `turn_id` |
| PermissionRequest | **未观测到** | — | — | — | — |
| PreCompact | ctr_live_tests: 1 | 1/1 | 15.4 | powershell.exe | `cwd`, `hook_event_name`, `model`, `session_id`, `transcript_path`, `trigger`, `turn_id` |
| PostCompact | **未观测到** | — | — | — | — |
| SubagentStart | **未观测到** | — | — | — | — |
| SubagentStop | **未观测到** | — | — | — | — |
| Stop | ctr_live_tests: 3, 后台会话: 1, Codex Desktop: 2 | 5/6 | 26.4 | powershell.exe, pwsh.exe | `cwd`, `hook_event_name`, `last_assistant_message`, `model`, `permission_mode`, `session_id`, `stop_hook_active`, `transcript_path`, `turn_id` |
| Interrupt | ctr_live_tests: 2, Codex Desktop: 1 | 3/3 | 23.3 | powershell.exe, pwsh.exe | `cwd`, `hook_event_name`, `model`, `permission_mode`, `session_id`, `transcript_path`, `turn_id` |

Hook 进程环境（实测）：

- `PLUGIN_ROOT` = `C:\Users\admin\.codex\plugins\cache\ctr-local\codex-task-recorder\0.1.0`
- `PLUGIN_DATA` = `C:\Users\admin\.codex\plugins\data\codex-task-recorder-ctr-local`
- `CLAUDE_PLUGIN_ROOT_set` = `True`
- `ComSpec` = `C:\Windows\system32\cmd.exe`

## 2. 需求覆盖矩阵

| 需求 | 事件数 | 来源（类型:名称 → 条数） | 完整度分布 | 常见缺失字段 |
|---|---|---|---|---|
| 用户已提交的 Prompt | 34 | hook:UserPromptSubmit → 17<br>transcript:event_msg/item_completed:UserMessage → 17 | complete: 34 | — |
| 模型公开返回的消息 | 20 | hook:Stop → 5<br>transcript:event_msg/item_completed:AgentMessage → 15 | partial: 5, complete: 15 | intermediate_messages×5 |
| 模型名称及配置 | 57 | derived:event_msg/thread_settings_applied.model → 3<br>derived:hook.model → 3<br>hook:SessionStart → 6<br>hook:UserPromptSubmit → 2<br>transcript:event_msg/thread_settings_applied → 18<br>transcript:session_meta → 8<br>transcript:turn_context → 17 | partial: 8, complete: 49 | reasoning_effort×8, reasoning_summary×8, approval_policy×8, sandbox_policy×8 |
| 工具调用 | 18 | hook:PreToolUse → 11<br>transcript:response_item/custom_tool_call → 7 | complete: 18 | — |
| 工具执行结果 | 28 | hook:PostToolUse → 10<br>transcript:event_msg/item_completed:CommandExecution → 11<br>transcript:response_item/custom_tool_call_output → 7 | complete: 28 | — |
| 工具 / 回合错误 | 12 | transcript:event_msg/item_completed:CommandExecution → 4<br>transcript:event_msg/task_complete → 8 | complete: 12 | — |
| 公开推理摘要 | 12 | transcript:event_msg/item_completed:Reasoning → 12 | complete: 5, unavailable: 7 | summary×7 |
| 回合生命周期 / 中断 | 44 | hook:Interrupt → 3<br>hook:Stop → 5<br>transcript:event_msg/task_complete → 15<br>transcript:event_msg/task_started → 18<br>transcript:event_msg/turn_aborted → 3 | complete: 44 | — |
| 子代理 / 压缩 / 权限请求 | 1 | hook:PreCompact → 1 | complete: 1 | — |

## 3. 时间戳与关联关系

- 带会话 ID：254/254 (100%)
- 带回合（turn）ID：200/254 (79%)
- 带来源时间戳 source_ts：177/254 (70%)（Hook 输入不含时间戳，此类事件只有 recorded_at）
- 工具事件带 tool_use_id：35/46 (76%)（UI 条目使用 item_id，与 call_id 不同）

## 4. 场景检查（按会话）

| 会话 | 客户端 | 普通对话 | 工具调用 | 工具失败 | 模型切换 | 任务中断 | 模型 | 中断证据来源 |
|---|---|---|---|---|---|---|---|---|
| `01a1824f-7779…` | ctr_live_tests | ✅ | ✅ | ✅ | ✅ | ✅ | gpt-5.5, gpt-6-luna | Interrupt, event_msg/turn_aborted |
| `01a18258-aada…` | ctr_live_tests | ✅ | ✅ | ✅ | ✅ | ✅ | gpt-5.6-luna, gpt-6-luna | Interrupt, event_msg/turn_aborted |
| `01a1825b-329c…` | codex_exec | ✅ | ✅ | — | — | — | gpt-6-luna | — |
| `01a1825d-77eb…` | ctr_live_tests | ✅ | ✅ | ✅ | — | — | gpt-5.6-luna | — |
| `01a1825f-94d6…` | ctr_live_tests | ✅ | — | — | — | — | gpt-6-luna | — |
| `01a18260-8a17…` | ctr_live_tests | ✅ | ✅ | — | — | — | gpt-6-luna | — |
| `01a18261-9f5d…` | ctr_live_tests | — | — | — | — | — | gpt-6-luna | — |
| `01a18266-5a69…` | Codex Desktop | ✅ | ✅ | — | ✅ | ✅ | gpt-6-luna, gpt-6.1-sol | Interrupt, event_msg/turn_aborted |

## 5. 来源交叉一致性

- Prompt：Hook 17 个回合，transcript 17 个回合，两者都有 17 个，其中文本一致 17 个
- 工具调用 ID（UI 条目粒度）：Hook 涉及 11 个 ID，transcript UI 工具条目 11 个，其中 11 个能与 Hook 对上；**Hook 未覆盖的 UI 条目**：无
- 工具调用 ID（模型调用粒度）：transcript 模型级调用 7 个，与 Hook 重合 0 个（Hook 按单条命令触发，模型级调用如 code-mode `exec` 一次可执行多条命令）
- Hook 工具结果无法判定成败 10 条（PostToolUse 只给输出文本，不给退出码），其中 10 条可通过 tool_use_id = item_id 从 transcript 退出码补全

## 6. 按策略省略 / 未映射的 transcript 记录（只计数，不存内容）

- `duplicate:response_item/message`: 80
- `duplicate:response_item/reasoning`: 12
- `duplicate:token_usage_record`: 14
- `omitted:encrypted_reasoning`: 12
- `omitted:rate_limits`: 21
- `omitted:world_state`: 12
- `other:response_item/additional_tools`: 1
- `other:token_count_without_info`: 3
- `skipped_outside_consent_window`: 10

## 7. 脱敏统计

- `assignment`: 3
- `github_token`: 3
- `openai_key`: 4

## 8. 后台会话（App 自动任务，不计入第 2–5 节）

判定：会话从未提供 `transcript_path`（Codex 不持久化该会话）。事件照常记录并标记 `session_kind=background`。

| 会话 | 事件数 | 触发的 Hook | 调用的工具 | 首条指令摘录 |
|---|---|---|---|---|
| `01a18266-3d8b…` | 27 | SessionStart×1, UserPromptSubmit×1, PreToolUse×5, PostToolUse×4, Stop×1 | Bash, mcp__codex_apps__plugin_management__get_app_permissions | # Overview Generate 0 to 3 hyperpersonalized suggestions for what this user can  |

# 事件覆盖率报告

- 生成时间：2026-10-28T12:01:34.549Z
- 事件总数：285
- Codex 内核版本：0.163.0-alpha.10.2
- 来源客户端（originator）：codex_exec, ctr_live_tests

## 1. Hook 支持矩阵（实测）

| Hook 事件 | 触发次数（按客户端） | transcript_path 非空 | 最大耗时 ms | 启动 Shell | 实际输入字段 |
|---|---|---|---|---|---|
| SessionStart | ctr_live_tests: 6, codex_exec: 1 | 7/7 | 56.6 | powershell.exe | `cwd`, `hook_event_name`, `model`, `permission_mode`, `session_id`, `source`, `transcript_path` |
| SessionEnd | ctr_live_tests: 5, codex_exec: 1 | 6/6 | 18.4 | powershell.exe | `cwd`, `hook_event_name`, `reason`, `session_id`, `transcript_path` |
| UserPromptSubmit | ctr_live_tests: 13, codex_exec: 1 | 14/14 | 41.7 | powershell.exe | `cwd`, `hook_event_name`, `model`, `permission_mode`, `prompt`, `session_id`, `transcript_path`, `turn_id` |
| PreToolUse | ctr_live_tests: 8, codex_exec: 1 | 9/9 | 17.8 | powershell.exe | `cwd`, `hook_event_name`, `model`, `permission_mode`, `session_id`, `tool_input`, `tool_name`, `tool_use_id`, `transcript_path`, `turn_id` |
| PostToolUse | ctr_live_tests: 7, codex_exec: 1 | 8/8 | 19.4 | powershell.exe | `cwd`, `hook_event_name`, `model`, `permission_mode`, `session_id`, `tool_input`, `tool_name`, `tool_response`, `tool_use_id`, `transcript_path`, `turn_id` |
| PermissionRequest | **未观测到** | — | — | — | — |
| PreCompact | ctr_live_tests: 1 | 1/1 | 15.4 | powershell.exe | `cwd`, `hook_event_name`, `model`, `session_id`, `transcript_path`, `trigger`, `turn_id` |
| PostCompact | **未观测到** | — | — | — | — |
| SubagentStart | **未观测到** | — | — | — | — |
| SubagentStop | **未观测到** | — | — | — | — |
| Stop | ctr_live_tests: 3 | 3/3 | 21.4 | powershell.exe | `cwd`, `hook_event_name`, `last_assistant_message`, `model`, `permission_mode`, `session_id`, `stop_hook_active`, `transcript_path`, `turn_id` |
| Interrupt | ctr_live_tests: 2 | 2/2 | 16.6 | powershell.exe | `cwd`, `hook_event_name`, `model`, `permission_mode`, `session_id`, `transcript_path`, `turn_id` |

Hook 进程环境（实测）：

- `PLUGIN_ROOT` = `C:\Users\admin\.codex\plugins\cache\ctr-local\codex-task-recorder\0.1.0`
- `PLUGIN_DATA` = `C:\Users\admin\.codex\plugins\data\codex-task-recorder-ctr-local`
- `CLAUDE_PLUGIN_ROOT_set` = `True`
- `ComSpec` = `C:\Windows\system32\cmd.exe`

## 2. 需求覆盖矩阵

| 需求 | 事件数 | 来源（类型:名称 → 条数） | 完整度分布 | 常见缺失字段 |
|---|---|---|---|---|
| 用户已提交的 Prompt | 28 | hook:UserPromptSubmit → 14<br>transcript:event_msg/item_completed:UserMessage → 14 | complete: 28 | — |
| 模型公开返回的消息 | 14 | hook:Stop → 3<br>transcript:event_msg/item_completed:AgentMessage → 11 | partial: 3, complete: 11 | intermediate_messages×3 |
| 模型名称及配置 | 46 | derived:event_msg/thread_settings_applied.model → 2<br>derived:hook.model → 2<br>hook:SessionStart → 5<br>hook:UserPromptSubmit → 2<br>transcript:event_msg/thread_settings_applied → 14<br>transcript:session_meta → 7<br>transcript:turn_context → 14 | partial: 7, complete: 39 | reasoning_effort×7, reasoning_summary×7, approval_policy×7, sandbox_policy×7 |
| 工具调用 | 15 | hook:PreToolUse → 9<br>transcript:response_item/custom_tool_call → 6 | complete: 15 | — |
| 工具执行结果 | 23 | hook:PostToolUse → 8<br>transcript:event_msg/item_completed:CommandExecution → 9<br>transcript:response_item/custom_tool_call_output → 6 | complete: 23 | — |
| 工具 / 回合错误 | 12 | transcript:event_msg/item_completed:CommandExecution → 4<br>transcript:event_msg/task_complete → 8 | complete: 12 | — |
| 公开推理摘要 | 8 | transcript:event_msg/item_completed:Reasoning → 8 | complete: 4, unavailable: 4 | summary×4 |
| 回合生命周期 / 中断 | 34 | hook:Interrupt → 2<br>hook:Stop → 3<br>transcript:event_msg/task_complete → 13<br>transcript:event_msg/task_started → 15<br>transcript:event_msg/turn_aborted → 1 | complete: 34 | — |
| 子代理 / 压缩 / 权限请求 | 1 | hook:PreCompact → 1 | complete: 1 | — |

## 3. 时间戳与关联关系

- 带会话 ID：204/204 (100%)
- 带回合（turn）ID：158/204 (77%)
- 带来源时间戳 source_ts：142/204 (70%)（Hook 输入不含时间戳，此类事件只有 recorded_at）
- 工具事件带 tool_use_id：29/38 (76%)（UI 条目使用 item_id，与 call_id 不同）

## 4. 场景检查（按会话）

| 会话 | 客户端 | 普通对话 | 工具调用 | 工具失败 | 模型切换 | 任务中断 | 模型 | 中断证据来源 |
|---|---|---|---|---|---|---|---|---|
| `01a1824f-7779…` | ctr_live_tests | ✅ | ✅ | ✅ | ✅ | ✅ | gpt-5.5, gpt-6-luna | Interrupt |
| `01a18258-aada…` | ctr_live_tests | ✅ | ✅ | ✅ | ✅ | ✅ | gpt-5.6-luna, gpt-6-luna | Interrupt, event_msg/turn_aborted |
| `01a1825b-329c…` | codex_exec | ✅ | ✅ | — | — | — | gpt-6-luna | — |
| `01a1825d-77eb…` | ctr_live_tests | ✅ | ✅ | ✅ | — | — | gpt-5.6-luna | — |
| `01a1825f-94d6…` | ctr_live_tests | ✅ | — | — | — | — | gpt-6-luna | — |
| `01a18260-8a17…` | ctr_live_tests | ✅ | ✅ | — | — | — | gpt-6-luna | — |
| `01a18261-9f5d…` | ctr_live_tests | — | — | — | — | — | gpt-6-luna | — |

## 5. 来源交叉一致性

- Prompt：Hook 14 个回合，transcript 14 个回合，两者都有 14 个，其中文本一致 14 个
- 工具调用 ID（UI 条目粒度）：Hook 涉及 9 个 ID，transcript UI 工具条目 9 个，其中 9 个能与 Hook 对上；**Hook 未覆盖的 UI 条目**：无
- 工具调用 ID（模型调用粒度）：transcript 模型级调用 6 个，与 Hook 重合 0 个（Hook 按单条命令触发，模型级调用如 code-mode `exec` 一次可执行多条命令）
- Hook 工具结果无法判定成败 8 条（PostToolUse 只给输出文本，不给退出码），其中 8 条可通过 tool_use_id = item_id 从 transcript 退出码补全

## 6. 按策略省略 / 未映射的 transcript 记录（只计数，不存内容）

- `duplicate:response_item/message`: 62
- `duplicate:response_item/reasoning`: 8
- `duplicate:token_usage_record`: 11
- `omitted:encrypted_reasoning`: 8
- `omitted:rate_limits`: 17
- `omitted:world_state`: 10
- `other:token_count_without_info`: 3
- `skipped_outside_consent_window`: 10

## 7. 脱敏统计

- `assignment`: 3
- `github_token`: 3
- `openai_key`: 2

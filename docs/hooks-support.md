# 官方 Codex 桌面 App 的 Hooks 支持范围与限制（Windows）

- 目标版本：Codex 桌面 App `OpenAI.Codex 26.1013.4894.0`；App 内核 `codex.exe 0.163.0-alpha.10.2`
- 实测日期：2026-10-28；平台：Windows Server 2025（10.0.26100），Python 3.12.10
- 实测方式：用 App 内核启动独立的 `codex app-server`（与桌面 App 相同的协议与内核）以及 `codex exec`；桌面 App 界面另行手测（见 `desktop-manual-test.md`）
- 标注：**【实测】** 本机验证；**【文档】** 官方文档声明，未独立验证；**【社区】** 第三方报告；**【待测】** 尚未验证
- 详细数字见 `coverage-report.md`

## 1. 能力总览

| 项目 | 结论 | 依据 |
|---|---|---|
| Hooks 特性 | `hooks` = stable，默认开启 | 【实测】`codex features list` |
| 插件自带 Hooks | App 内核从已安装插件的 `hooks/hooks.json` 加载全部 12 个事件，来源 `plugin` | 【实测】app-server `hooks/list` |
| 安装 | 本地 marketplace → `codex plugin marketplace add <目录>` → `codex plugin add <插件>@<市场>`；安装到 `~/.codex/plugins/cache/<市场>/<插件>/<版本>/`（版本取自 plugin.json）；`config.toml` 只新增 `[marketplaces.*]` 与 `[plugins."…"] enabled = true` | 【实测】 |
| 同版本重装 | 原地刷新缓存文件 | 【实测】 |
| 插件数据目录 | `PLUGIN_DATA` = `~/.codex/plugins/data/<插件>-<市场>` | 【实测】 |
| 公开插件目录 | 含 Hooks 的插件只能在桌面端手动安装，不能进入公开插件目录 | 【文档】 |
| 云端编排 | 插件 / 本地 Hooks 不支持 | 【文档】 |

## 2. 信任机制

| 项目 | 结论 | 依据 |
|---|---|---|
| 安装后自动信任 | **否**。12 个 Hook 均为 `untrusted`，Codex 跳过执行 | 【实测】`hooks/list`；未信任时 `codex exec` 正常完成，记录器零调用 |
| 信任粒度 | **按单个 Hook**。修改 9 个 Hook 定义后只有这 9 个变为 `modified`，其余保持 `trusted` | 【实测】 |
| 哈希范围 | Hook 定义（命令、async、超时等），**不含脚本内容**：只改 Python 代码不需要重新信任 | 【实测】 |
| 用户看到的命令 | `commandWindows` 中 `${PLUGIN_ROOT}` 替换后的绝对路径命令 | 【实测】 |
| 状态值 | `managed` / `untrusted` / `trusted` / `modified` | 【实测】协议 schema |
| 桌面端入口 | 插件详情页、设置 → Hooks、输入框上方审查提示 | App 包内界面文案键名；用户已在 App 中完成信任 【实测】 |
| 跳过信任 | 只有 CLI 单次调用的 `--dangerously-bypass-hook-trust`，本项目不用 | 【实测】`exec --help` |
| 免信任途径 | 只有托管 Hook（system / MDM / cloud requirements），用户不可禁用；不适用于个人安装 | 【文档】 |
| 内核版本 | 安装与信任须使用 App 自带内核；PATH 上的 npm CLI（0.160.0）版本不同 | 【实测】版本；哈希差异【社区】 |

## 3. Windows 执行环境

| 项目 | 结论 | 依据 |
|---|---|---|
| 使用的命令 | `commandWindows`；`${PLUGIN_ROOT}` 在交给 Shell 前被文本替换 | 【实测】 |
| 启动 Shell | **PowerShell**（`python.exe ← powershell.exe ← codex.exe`），不是 cmd.exe | 【实测】 |
| 环境变量 | `PLUGIN_ROOT`、`PLUGIN_DATA`，并设置了 `CLAUDE_PLUGIN_ROOT` | 【实测】 |
| 同步 Hook 耗时 | 端到端 **355–446 ms**，记录器自身 13–57 ms，其余为 PowerShell + Python 启动 | 【实测】`hook/completed.durationMs` |
| 后台（async）Hook | 不阻塞回合；**不出现在 app-server 的 `hook/started` / `hook/completed` 通知中** | 【实测】 |
| 后台 Hook 的丢失 | 进程在回合结束后立即退出时（`codex exec`、关闭 app-server），**后台 Stop 来不及执行**；同步的 SessionEnd 仍会执行 | 【实测】 |

## 4. 各事件实测

| 事件 | 触发 | 实际输入字段（common 之外） | 观察 |
|---|---|---|---|
| SessionStart | ✅ | source | 在首个回合开始时触发（`turn/started` 之后） |
| UserPromptSubmit | ✅ | prompt, turn_id | 每回合一次；返回的 `systemMessage` 由 app-server 作为 `warning` 条目下发，**未进入模型上下文** |
| PreToolUse | ✅ | tool_name, tool_use_id, tool_input, turn_id | `tool_name` = `Bash`；`tool_use_id` = UI 条目 id `exec-…`；**按单条命令触发**（模型级 code-mode `exec` 调用本身不触发） |
| PostToolUse | ✅ | + tool_response | `tool_response` 只是**输出文本，没有退出码**；被中断的命令没有 PostToolUse |
| Stop | ✅ | last_assistant_message, stop_hook_active | 只在**正常完成**的回合触发；失败（如 `model_not_found`、`serverOverloaded`）与被中断的回合都不触发 |
| Interrupt | ✅ | turn_id | `turn/interrupt` 后触发；模型生成中、命令执行中两种中断都已验证 |
| SessionEnd | ✅ | reason | app-server 会话关闭与 `codex exec` 退出时触发；不带 `model` / `turn_id` |
| PreCompact | ✅ | trigger（`manual`） | `thread/compact/start` 后触发；不带 `permission_mode` |
| PostCompact | 【待测】 | | 本次压缩因服务端 `serverOverloaded` 失败，未触发 PostCompact |
| PermissionRequest | 【待测】 | | 测试回合在请求审批前即因服务端容量失败 |
| SubagentStart / SubagentStop | 【待测】 | | 未触发子代理 |

## 5. 数据可得性

| 需求 | Hook 能给 | 由 transcript 补全 | 拿不到 / 不采集 |
|---|---|---|---|
| 用户 Prompt | ✅ UserPromptSubmit | 也有；两者 11/11 一致 | — |
| 模型公开消息 | 只有最后一条（Stop） | 全部 AgentMessage | — |
| 模型名与配置 | 只有 `model`、`permission_mode` | effort、summary、审批、沙箱、service tier、provider（turn_context / thread_settings_applied / session_meta） | — |
| 模型切换 | 相邻 Hook 的 `model` 变化（派生） | turn_context / thread_settings 的 model 变化（派生） | — |
| 工具调用与结果 | 命令、输出文本 | 退出码、耗时、MCP 调用、模型级调用 | — |
| 工具 / 回合错误 | — | 退出码；回合错误（`task_complete.error`） | 失败回合没有 Stop |
| 推理摘要 | — | `Reasoning.summary_text`：请求 `summary=detailed` 时 4 条有内容；未请求时为空（标记 unavailable） | 加密推理、原始推理（按策略不采集） |
| 时间戳 | 无（只有记录器接收时间 `recorded_at`） | 每条记录的 `timestamp` | — |
| 会话 / 回合 / 工具关联 | session_id、turn_id、tool_use_id | turn_attribution；无 turn_id 的记录按当前回合推断（标记 `turn_id_inferred`） | — |

## 6. 已知限制与应对

1. **信任无法自动化**：用户必须在 App 中亲自点击信任；这也是知情同意的一部分。改动 `hooks.json` 会让对应 Hook 需要重新信任，代码更新不会。
2. **延迟**：同步 Hook 每次约 0.4 s。本插件只有 UserPromptSubmit（需要输出提示）、Interrupt、SessionEnd（上限 3 s）保持同步，其余 9 个为 async。
3. **Hook 不提供成败与时间戳**：PostToolUse 无退出码，所有 Hook 无时间戳；由 transcript 补全并标注来源。
4. **transcript 不是稳定接口**【文档】：只解析白名单类型，其余计数；记录版本号以便追溯。
5. **失败 / 中断的回合没有 Stop**：靠下一次 Hook（UserPromptSubmit / Interrupt / SessionEnd）补读 transcript。
6. **短生命周期进程会丢后台 Hook**：`codex exec` 场景下后台 Stop 可能不执行，由同步 SessionEnd 兜底补读。桌面 App 为常驻进程，不受影响（桌面端待手测确认）。
7. **模型可能拒绝读取敏感文件**（实测拒绝 `type .env`）；"敏感文件输出整体丢弃"规则目前仅由单元测试覆盖。
8. **Codex 自身的 rollout 文件不受本插件控制**：例如 Prompt 中的密钥会原样出现在 `~/.codex/sessions/...`；本插件只保证自己的 JSONL 已脱敏。

## 7. 尚未验证

- 桌面 App 界面中「正在记录」提示是否可见、样式如何（`desktop-manual-test.md` 步骤 1）
- 桌面 App 会话的 originator 标识与事件触发情况（预期与 app-server 一致）
- PostCompact、PermissionRequest、SubagentStart / SubagentStop

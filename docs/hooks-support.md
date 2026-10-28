# 官方 Codex 桌面 App 的 Hooks 支持范围与限制（Windows）

- 目标版本：Codex 桌面 App `OpenAI.Codex 26.1013.4894.0`；App 内核 `codex.exe 0.163.0-alpha.10.2`
- 实测日期：2026-10-28；平台：Windows Server 2025（10.0.26100），Python 3.12.10
- 标注：**【实测】** 本项目在本机验证；**【文档】** 官方文档声明，本项目未独立验证；**【社区】** 第三方报告；**【待测】** 尚未验证

## 1. 能力总览

| 项目 | 结论 | 依据 |
|---|---|---|
| Hooks 特性开关 | `hooks` = stable，默认开启 | 【实测】`codex features list` |
| 插件自带 Hooks | App 内核会从已安装插件的 `hooks/hooks.json` 加载 12 个事件，来源标记为 `plugin` | 【实测】app-server `hooks/list` |
| 插件安装方式 | 本地 marketplace + `codex plugin marketplace add` / `codex plugin add`，安装到 `~/.codex/plugins/cache/<市场>/<插件>/<版本>/`（版本号取自 plugin.json，不是 `local`） | 【实测】 |
| 同版本重装 | 原地刷新缓存文件 | 【实测】 |
| 公开插件目录 | 含 Hooks 的插件"仅支持在桌面端手动安装"，不能进入公开插件目录 | 【文档】 |
| 云端编排 | 插件 / 本地 Hooks 不支持 cloud-orchestrated 模式 | 【文档】 |

## 2. 信任机制

| 项目 | 结论 | 依据 |
|---|---|---|
| 安装后是否自动信任 | **否**。安装后 12 个 Hook 均为 `untrusted`，Codex 跳过执行 | 【实测】`hooks/list`；未信任时 `codex exec` 正常完成且记录器无任何调用 |
| 信任粒度 | **按单个 Hook** 计算哈希。修改 9 个 Hook 的定义后，只有这 9 个变为 `modified`，其余 3 个保持 `trusted` | 【实测】 |
| 哈希覆盖范围 | Hook 定义（命令、async、超时等）；**不含脚本内容**：只改 Python 代码时信任不失效 | 【实测】 |
| 命令展示 | 信任界面看到的是 `commandWindows` 中 `${PLUGIN_ROOT}` 替换后的绝对路径命令 | 【实测】`hooks/list.command` |
| 状态值 | `managed` / `untrusted` / `trusted` / `modified` | 【实测】app-server 协议 schema |
| 桌面端入口 | 插件详情页（"包含 Hooks — 需要审查 / 全部信任"）、设置 → Hooks、输入框上方审查提示（允许 / 全部允许 / 暂不） | App 包内界面文案键名；实际界面【待测】 |
| 跳过信任 | 仅 CLI 有 `--dangerously-bypass-hook-trust`（单次调用），本项目不使用 | 【实测】`exec --help` |
| 免信任途径 | 仅托管 Hook（system / MDM / cloud requirements），用户不可禁用；不适用于个人安装 | 【文档】 |
| 版本差异 | 信任须用与 App 相同的内核；PATH 上的 npm CLI（0.160.0）与 App 内核（0.163.0-alpha.10.2）版本不同 | 【实测】版本；哈希差异【社区】 |

## 3. Windows 执行环境

| 项目 | 结论 | 依据 |
|---|---|---|
| 使用的命令 | 选用 `commandWindows` | 【实测】 |
| `${PLUGIN_ROOT}` | 在交给 Shell 前被文本替换为插件缓存目录绝对路径 | 【实测】 |
| 启动 Shell | **PowerShell**（进程链 `python.exe ← powershell.exe ← codex.exe`） | 【实测】 |
| 单次 Hook 耗时 | 同步 Hook 端到端约 **365–384 ms**，其中记录器自身处理 13–19 ms，其余为 PowerShell 与 Python 启动 | 【实测】app-server `hook/completed.durationMs` |
| 影响 | 同步的 Pre/PostToolUse 会让每条工具命令多约 0.75 s；本项目因此把只做观察的 Hook 设为 `async` | 【实测】 |
| 工作目录 / 环境变量 | 见覆盖率报告"Hook 进程环境" | 【实测】 |

## 4. 各事件实测（App 内核 0.163.0-alpha.10.2，经 app-server）

| 事件 | 是否触发 | 实际输入字段 | 备注 |
|---|---|---|---|
| SessionStart | ✅ | cwd, hook_event_name, model, permission_mode, session_id, source, transcript_path | 首个回合开始时触发 |
| UserPromptSubmit | ✅ | + prompt, turn_id | 每个回合一次；`systemMessage` 被 app-server 作为 `warning` 条目返回，**未进入模型上下文**（transcript 中无该文本） |
| PreToolUse | ✅ | + tool_input, tool_name, tool_use_id, turn_id | `tool_name` = `Bash`；`tool_use_id` = `exec-…`（UI 条目 id），**按单条命令触发**，不是按模型级 `exec` 调用 |
| PostToolUse | ✅ | + tool_response | `tool_response` 是**纯文本输出，没有退出码**，失败命令无法仅凭 Hook 判断成败 |
| Stop | ✅ | + last_assistant_message, stop_hook_active | 只有最后一条 assistant 消息；**以错误结束的回合不触发 Stop**；被中断的回合不触发 Stop |
| Interrupt | ✅ | cwd, model, permission_mode, session_id, transcript_path, turn_id | `turn/interrupt` 后触发 |
| SessionEnd | 【待测】 | | |
| PermissionRequest | 【待测】 | | 测试使用 approvalPolicy=never |
| PreCompact / PostCompact | 【待测】 | | 需长会话触发压缩 |
| SubagentStart / SubagentStop | 【待测】 | | 需触发子代理 |

## 5. 数据可得性

| 需求 | Hook 能给 | 需靠 transcript 补全 | 拿不到 |
|---|---|---|---|
| 用户 Prompt | ✅ UserPromptSubmit | 也有（两者一致性见报告） | — |
| 模型公开消息 | 仅最后一条（Stop） | 中间消息（AgentMessage） | 错误/中断回合无 Stop |
| 模型名与配置 | 仅 `model`、`permission_mode` | effort、summary、审批、沙箱、service tier（turn_context / thread_settings_applied） | — |
| 工具调用与结果 | 命令、输出文本 | 退出码、耗时、MCP 调用、模型级调用 id | — |
| 错误 | — | 回合错误（task_complete.error），如 `model_not_found` | — |
| 推理摘要 | — | Reasoning.summary_text（需请求 summary，且模型返回时） | 加密推理、原始推理（按策略不采集） |
| 时间戳 | 无（只有记录器接收时间） | 每条记录的 timestamp | — |

（本文件会在完整实测与桌面端手测后更新；最终数字以 `docs/coverage-report.md` 为准。）

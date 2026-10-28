# Codex Task Recorder — 设计说明（原型 v0）

- 日期：2026-10-28
- 状态：待评审
- 范围：仅本地数据采集原型；不接入远程服务器、不处理充值业务

## 1. 目标与约束

### 1.1 目标
为主动参与模型评测、明确授权的用户，在 Windows 官方 Codex 桌面 App 中记录测试会话，输出本地 JSONL，并生成事件覆盖率报告与 Hooks 支持范围说明。

### 1.2 用户明确的约束
1. 保留官方 Codex App，不修改官方程序。
2. 优先使用官方生命周期 Hooks；不假设所有 Hooks 可用，须实测。
3. 以 **Codex 插件** 形式交付（插件自带 Hooks）。
4. 每条事件标注来源与完整度，不伪造无法获取的数据。
5. 仅在用户明确启用时采集；提供可见状态与停止功能。
6. 排除密码、会话凭证、API Key 等敏感信息。
7. 不使用键盘监听、进程注入、破解客户端或绕过权限机制（包括不使用 `--dangerously-bypass-hook-trust`、不代替用户写入 Hook 信任记录）。
8. 用户操作要简单：全程双击脚本 + App 内点一次「全部信任」，无需命令行。

### 1.3 非目标
远程上传、账户/充值、回放 UI、跨机器同步、对加密推理内容的任何处理。

## 2. 目标版本（2026-10-28 实测）

| 组件 | 版本 / 位置 |
|---|---|
| Codex 桌面 App | `OpenAI.Codex 26.1013.4894.0`（MSIX，`C:\Program Files\WindowsApps\…`） |
| App 运行内核 | `codex.exe 0.163.0-alpha.10.2`（`%LOCALAPPDATA%\OpenAI\Codex\bin\896a0166b774037a\`） |
| PATH 上 npm CLI | `codex-cli 0.160.0` —— **不用于本项目**（hook 信任哈希可能与 App 内核不一致） |
| 特性开关 | `features list`: `hooks = stable / true` |
| Python | 3.12.10（`C:\Users\admin\AppData\Local\Programs\Python\Python312\python.exe`） |

本机现状：无 `~/.codex/hooks.json`、无 inline `[hooks]`；`notify` 已被 computer-use 占用（不触碰）。

## 3. 官方能力摘要（文档 + 待实测）

来源：Codex Hooks 文档（developers.openai.com/codex/hooks → learn.chatgpt.com/docs/hooks）、插件打包文档（developers.openai.com/plugins/build/plugins）。

- 12 个事件：`SessionStart` `SessionEnd` `UserPromptSubmit` `PreToolUse` `PostToolUse` `PermissionRequest` `PreCompact` `PostCompact` `SubagentStart` `SubagentStop` `Stop` `Interrupt`。
- 公共输入：`session_id` `transcript_path`(可为 null) `cwd` `hook_event_name` `model`，多数含 `permission_mode`；回合事件含 `turn_id`。
- 插件 Hook：默认 `hooks/hooks.json`；命令可用环境变量 `PLUGIN_ROOT` / `PLUGIN_DATA`；`${PLUGIN_ROOT}` 会被文本替换；`commandWindows` 为 Windows 专用命令。
- 插件 Hook 属于非托管 Hook：安装不等于信任，需在 App「设置 → Hooks → Plugin」或 `/hooks` 中按哈希信任；改动 hook 定义需重新信任。
- 带 Hooks 的插件"仅支持在 Codex 桌面端手动安装"，不能进入公开插件目录。
- `transcript_path` 指向会话 transcript（本机为 rollout JSONL），官方声明 **非稳定接口**。
- 已知缺口（社区报告，待实测）：apply_patch 可能不触发 Pre/PostToolUse；大文件编辑 Hook 静默失败（openai/codex#18067）；以错误结束的回合可能不触发任何 Hook；无 PostToolUseFailure；Windows 下 Hook 的 Shell 是 cmd.exe 还是 PowerShell 有矛盾报告；`SessionEnd`/`Interrupt` 超时默认 1s、上限 3s。

**本设计把以上全部视为假设，由第 9 节的探测与实测确认。**

## 4. 方案选择

采用 **插件自带 Hooks（主）+ 读取官方提供的 `transcript_path`（补全）**。

- Hook 提供：Prompt、工具输入/输出、最后一条 assistant 消息、模型名、权限模式、回合/中断/子代理/压缩生命周期。
- transcript 补全：中间 assistant 消息、推理摘要、回合配置（effort/summary/审批/沙箱）、回合错误与中止、apply_patch 等不触发 Hook 的工具项、token 用量。
- 不采用：app-server 协议接入、日志 SQLite 读取、`notify` 改写、任何 UI 自动化。

## 5. 仓库结构

```
D:\codex-task-recorder\
  .agents\plugins\marketplace.json        本地 marketplace "ctr-local"
  plugins\codex-task-recorder\            插件根（安装时被 Codex 复制到 cache）
    .codex-plugin\plugin.json             清单（与本机已装插件同格式）
    hooks\hooks.json                      12 个事件 → 同一入口
    hooks\ctr_hook.py                     薄入口：把 lib 加入 sys.path，调用 ctr.hook.main()
    lib\ctr\
      paths.py      数据目录、App 内核定位
      state.py      启用/停止状态、授权窗口、作用域
      redact.py     脱敏
      events.py     事件构造与完整度标注
      store.py      加锁追加 JSONL、游标
      hook.py       Hook 事件 → 事件
      transcript.py rollout 增量解析 → 事件
      report.py     覆盖率报告
      cli.py        命令行
  ctr.cmd                                 CLI 包装（PYTHONPATH 指向 lib），供开发与测试使用
  安装.cmd / 开始记录.cmd / 停止记录.cmd / 记录状态.cmd / 卸载.cmd
                                          面向用户的双击入口（内部调用 ctr.cmd）
  tests\                                  unittest + 合成夹具（不使用真实会话内容）
  scripts\live_cli_tests.py               用 App 内核跑 CLI 实测场景
  docs\hooks-support.md                   支持范围与限制（实测后填写）
  docs\desktop-manual-test.md             桌面 App 手动测试清单
  docs\coverage-report.md                 覆盖率报告（生成）
```

仅依赖 Python 3.12 标准库。

## 6. 组件设计

### 6.1 插件清单与 Hook 注册
- `plugin.json`：name `codex-task-recorder`，`interface.displayName` "Codex Task Recorder"，描述中明确"仅在本地 `ctr enable` 后记录"。
- `hooks.json`：12 个事件各一条，不设 matcher（匹配全部工具），全部同步执行：
  - `command`: `python3 "${PLUGIN_ROOT}/hooks/ctr_hook.py"`
  - `commandWindows`: `python "${PLUGIN_ROOT}\hooks\ctr_hook.py"`（cmd 与 PowerShell 均可解析）
  - `timeout`: 10；`SessionEnd`/`Interrupt`: 3
- 定义一次定稿，尽量避免改动导致重新信任；入口脚本与 lib 的修改不改变 hook 定义哈希。

### 6.2 Hook 入口 `ctr.hook.main()`
1. 读 stdin（bytes→UTF-8）。整个流程包在 try 中，**任何情况都 exit 0**，绝不阻断工具或回合。
2. 读取 `state.json`；未启用、文件缺失/损坏、`CTR_DISABLE=1`、或 `cwd` 不在作用域内 → 立即退出，不写任何文件。
3. 构造 Hook 事件（6.4）→ 脱敏（6.5）→ 追加到会话 JSONL。
4. 在 `UserPromptSubmit` `Stop` `Interrupt` `SessionEnd` `SubagentStop` 时增量解析 transcript（6.6）。
5. stdout：除第 6.7 节的可见提示 JSON 外不输出任何内容（避免被当作模型上下文）。错误只写 `recorder.log`（异常类型 + 事件名，不含内容）。

### 6.3 数据存储（`%LOCALAPPDATA%\CodexTaskRecorder\`）
```
state.json                         启用状态、授权窗口历史、作用域、同意记录
sessions\YYYY-MM-DD\<session_id>.jsonl
cursors\<session_id>.json          transcript 字节偏移、已见模型、是否已提示
reports\                           覆盖率报告
recorder.log                       记录器自身错误
```
- 追加写在 `msvcrt.locking` 文件锁内完成；同一会话的事件与游标在同一把锁下更新。
- 选择固定目录而非 `PLUGIN_DATA`：CLI 在 Hook 之外运行拿不到 `PLUGIN_DATA`；`PLUGIN_DATA` 实际路径在探测中记录到支持说明。

### 6.4 事件模式 `ctr.event/v1`
```json
{
  "schema": "ctr.event/v1",
  "event_id": "uuid4",
  "kind": "user_prompt",
  "recorded_at": "2026-10-28T10:00:00.123Z",
  "source_ts": "2026-10-28T10:00:00.100Z | null",
  "session_id": "…", "turn_id": "… | null",
  "tool_use_id": "… | null", "item_id": "… | null", "agent_id": "… | null",
  "relations": {"parent_turn_id": null, "root_turn_id": null},
  "source": {"type": "hook|transcript|derived", "name": "UserPromptSubmit | event_msg/item_completed:AgentMessage | …",
             "codex_version": "0.163.0-alpha.10.2 | null", "originator": "Codex Desktop | codex_exec | null",
             "transcript_offset": 1234},
  "granularity": "model_tool_call | ui_item | null",
  "completeness": {"status": "complete|partial|truncated|unavailable", "missing": [], "note": ""},
  "redaction": {"applied": false, "counts": {}},
  "data": {}
}
```
- `source_ts`：Hook 输入无时间戳 → null，`recorded_at` 为记录器时钟；transcript 记录用其 `timestamp`。
- `truncated`：单字符串字段上限 64 KiB，保留前 64 KiB，并记录原长度与脱敏后全文 sha256。
- `unavailable`：期望存在但拿不到的数据（如推理摘要为空）也输出一条占位事件，写明原因，不填充内容。

`kind` 取值与来源映射：

| kind | Hook 来源 | transcript 来源 |
|---|---|---|
| `session_start` / `session_end` | SessionStart / SessionEnd | `session_meta` |
| `user_prompt` | UserPromptSubmit.prompt | `item_completed:UserMessage` |
| `assistant_message` | Stop.last_assistant_message（partial：仅最后一条） | `item_completed:AgentMessage` |
| `reasoning_summary` | — | `item_completed:Reasoning.summary_text`（空则 unavailable） |
| `model_config` | 每个事件的 `model` / `permission_mode` | `turn_context`、`thread_settings_applied` |
| `model_changed`（derived） | 同会话 `model` 变化 | `turn_context.model` 变化 |
| `tool_call` | PreToolUse | `response_item/function_call`、`custom_tool_call`（model_tool_call） |
| `tool_result`（含 `outcome: success/error/unknown`） | PostToolUse | `*_call_output`（model_tool_call）；`item_completed:CommandExecution/McpToolCall/FileChange/ImageView`（ui_item） |
| `permission_request` | PermissionRequest | — |
| `compaction` | PreCompact / PostCompact | — |
| `subagent_start` / `subagent_stop` | SubagentStart / SubagentStop | `task_started.turn_attribution` |
| `turn_start` / `turn_end` | Stop（turn_end） | `task_started` / `task_complete` |
| `turn_error` | — | `task_complete.error`、`event_msg/error` |
| `turn_interrupted` | Interrupt | `turn_aborted` |
| `token_usage` | — | `token_count.info`（不含 rate_limits） |
| `transcript_other` | — | 未识别类型：只记类型名与计数，不记内容 |

关联：`session_id` → `turn_id` → `tool_use_id`(=`call_id`) / `item_id`；子代理用 `agent_id` 与 `turn_attribution`。UI 条目 id（`exec-…`）与 `call_id` 不同，二者以 `granularity` 区分，不强行合并。

### 6.5 脱敏与排除
- **从不读取**：`auth.json`、`.env*`、`*.pem`、`id_rsa*`、`cap_sid`、日志/状态 SQLite。
- **从不记录**：`encrypted_content`、`Reasoning.raw_content`（只记"存在/长度"）、`base_instructions`/`world_state`（只记 sha256 与长度）、`rate_limits`、`creator_account_id`/`creator_user_id`。
- **键名规则**：键名匹配 password/passwd/secret/token/api_key/access_key/authorization/cookie/credential/private_key 且值为字符串 → `[REDACTED:key]`（数值型如 `input_tokens` 不受影响）。
- **值模式**：`sk-…`（含 proj/svcacct/admin/ant）、`gh[pousr]_…`、`github_pat_…`、`AKIA/ASIA…`、`AIza…`、`xox[abprs]-…`、`Bearer …`、JWT、PEM 私钥块、URL 内 `user:pass@`、`XXX_API_KEY=…`/`password: …` 形式赋值、`Authorization:`/`Cookie:` 头。
- **敏感文件输出**：工具输入引用上述敏感文件名时，其输出整体替换为 `[REDACTED:sensitive_file]`。
- 每条事件记录 `redaction.counts`；哈希只对脱敏后内容计算。

### 6.6 transcript 增量解析
- 仅在 Hook 给出非空 `transcript_path` 时解析；为 null 时在相应事件上标注 missing。
- 从游标字节偏移读到文件末尾，只处理完整行；记录的 `timestamp` 必须落在某个**授权窗口**内（启用→停止的区间），窗口外的内容一律跳过——停用期间与启用前的内容不会被补录。
- `session_meta` 例外：只取版本/originator/provider 等配置字段，不取内容。
- 未识别的记录类型 → `transcript_other`（只计类型名）。格式变化时宁可少记，不猜测。
- `SubagentStop.agent_transcript_path` 同样解析，事件带 `agent_id`。

### 6.7 用户流程：同意即开启、可见状态与停止

**用户流程（同意与安装合并为一步）：**
1. 双击 `安装.cmd` → 控制台显示同意说明（采集什么、存在哪里、排除哪些敏感信息、如何停止）→ 用户按 `Y` → 写入同意记录并打开授权窗口 → 用 App 内核执行官方安装命令 → 提示"请重启 Codex，在插件页点「全部信任」"。用户按其他键则不安装、不开启。
2. 用户重启 Codex App，在插件详情页点一次「全部信任」（Codex 强制，无法省略，也不代为完成）。
3. 正常使用；开启期间记录 **全部会话**。
4. 双击 `停止记录.cmd` 立即停止；双击 `开始记录.cmd`（显示一行摘要并按 `Y`）恢复；`记录状态.cmd` 查看状态；`卸载.cmd` 卸载插件并询问是否删除已记录数据。

**失败即关闭：** 从未经过同意页（如用户直接在 App 中安装并信任插件）→ 不记录，仅在每个会话首次 `UserPromptSubmit` 提示一次"Codex Task Recorder 尚未开启记录，双击「开始记录」开启"。用户主动停止后不再提示。

**App 内可见提示：** 开启期间每个会话首次 `UserPromptSubmit` 返回 `{"systemMessage": "● Codex Task Recorder 正在本地记录本会话。停止：双击「停止记录」"}`。是否在桌面 App 中显示、是否进入模型上下文须实测；若不支持则改用 `Stop` 并在支持说明中记录。

**插件页说明：** `plugin.json` 的 `longDescription` 写明采集范围、存储位置与停止方式，用户在点「全部信任」时可以看到。

**官方层面的停止：** 在 App 中禁用插件，或在「设置 → Hooks」关闭信任开关。

**CLI（双击脚本的底层，也供开发测试使用）：**
- `ctr enable [--i-consent] [--cwd <路径>…]`：显示同意说明并要求确认；`--i-consent` 为脚本化测试的显式同意；`--cwd` 仅供开发测试限定范围，默认全部会话。
- `ctr disable`：立即关闭当前授权窗口；之后的 Hook 调用全部直接退出。
- `ctr status`：开启状态、范围、授权窗口、数据目录、各会话事件数、最近事件时间、插件安装状态。
- `ctr purge [--session <id>]`：删除本地已记录数据。
- `ctr install` / `ctr uninstall`：用 App 内核执行官方命令 `codex plugin marketplace add|remove` 与 `codex plugin add|remove`。App 内核定位：优先正在运行的 App 所用 `codex.exe`，否则取 `%LOCALAPPDATA%\OpenAI\Codex\bin\*\codex.exe` 中版本最高者。

### 6.8 覆盖率报告 `ctr report`
输出 `reports\coverage-<时间>.md/.json`，并复制到 `docs\coverage-report.md`：
1. **Hook 支持矩阵**：12 个事件 × 来源 originator（桌面 App / exec）：已配置、观测到的调用次数、首次观测时间、输入字段实际集合、`transcript_path` 是否为空。
2. **需求覆盖矩阵**：6 类需求 × 来源（hook/transcript/derived）：事件数、完整度分布、缺失字段 Top N。
3. **场景检查**：普通对话、工具调用（含失败）、模型切换、任务中断，各自判定 通过/部分/未观测，并附证据事件 id。
4. **交叉一致性**：Hook 与 transcript 的 prompt 是否一致、`tool_use_id` 与 `call_id` 匹配率、Hook 未覆盖的工具调用数量。

## 7. 错误处理
- Hook 始终 exit 0，stdout 仅允许 6.7 的 JSON。
- 加锁超时 2s：放弃本次写入并在 `recorder.log` 记一条（不含内容）。
- transcript 行解析失败：跳过该行并计数，游标不越过不完整的尾行。
- `state.json` 损坏 → 视为未启用（失败即关闭）。

## 8. 安全与隐私
- 数据只写本地；不发起任何网络请求。
- 记录器不修改官方程序与 MSIX 包；`~/.codex` 中仅由官方 `codex plugin` 命令写入 marketplace/插件条目。
- 不向模型注入上下文（不输出 `additionalContext`，SessionStart 不输出任何 stdout）。

## 9. 测试与验收

### 9.1 单元测试（unittest，合成夹具）
脱敏规则（正/反例）、启用门控与作用域、授权窗口过滤、transcript 解析与未知类型、截断与完整度、锁与游标、报告聚合。

### 9.2 探测（首个里程碑）
安装插件 → 用户在 App 中信任 Hook → `ctr enable --cwd D:\ctr-testbed` → 用 App 内核 `codex exec` 跑一次 → 依据实际记录确认：哪些事件触发、真实输入字段、`transcript_path`、`PLUGIN_ROOT`/`PLUGIN_DATA` 实际值、Windows 实际 Shell、`systemMessage` 显示与否、`tool_name` 取值。据此修正解析器与文档。

### 9.3 CLI 实测（App 内核 `codex exec --json`，低 effort）
1. 普通对话；2. 工具调用（成功 + 故意失败的命令）；3. 模型切换（`exec resume … -m <另一模型>`）；4. 任务中断（尽力尝试向 exec 发送中断；无法触发则如实记录，转桌面手测）。

### 9.4 桌面 App 手动测试
`docs\desktop-manual-test.md` 逐步清单：双击 `安装.cmd` 并同意 → 重启 App、点「全部信任」→ 普通对话 → 工具调用 → 切换模型 → 点停止中断 → 双击 `停止记录.cmd` 验证停止 → `ctr report`。另测"未经同意页直接信任"时不记录。

### 9.5 验收产物
`docs\coverage-report.md`、`docs\hooks-support.md`（支持范围与限制，标注"文档声明 / 实测确认 / 未验证"）、全部单元测试通过的输出。

## 10. 风险
| 风险 | 应对 |
|---|---|
| 桌面 App 未触发某些事件 | 报告如实标注；transcript 补全并标注来源 |
| transcript 格式变化 | 只解析白名单类型，其余计数；版本号随事件记录 |
| CLI 与 App 信任哈希不一致 | 全部操作使用 App 内核二进制 |
| Windows Shell 不确定 | `commandWindows` 选用 cmd/PowerShell 通用写法，探测确认 |
| 同步 Hook 增加延迟 | 未启用时立即退出；实测记录单次耗时 |
| 推理摘要通常为空（本机历史 517 条仅 2 条有摘要） | 输出 unavailable 占位并说明原因，不推测 |

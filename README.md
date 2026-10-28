# Codex Task Recorder（原型 v0.1）

面向主动参与模型评测、明确授权的用户：在 **Windows 官方 Codex 桌面 App** 中，通过官方生命周期 Hooks 把测试会话记录为本地 JSONL。不修改官方程序。默认只在本机记录；**数据同步**（上传到后台）需另行开启并同意。

## 用户使用

| 步骤 | 操作 |
|---|---|
| 1 | 双击 **`安装.cmd`**：阅读同意说明，按 `Y` 同意 → 自动安装插件并开启记录 |
| 2 | 重启 Codex App → 插件 → Codex Task Recorder → 点 **「全部信任」**（Codex 强制要求用户亲自确认） |
| 3 | 正常使用。每个会话第一条消息后会出现「● Codex Task Recorder 正在本地记录本会话」 |
| 停止 | 双击 **`停止记录.cmd`**（立即生效）；恢复用 **`开始记录.cmd`** |
| 状态 | 双击 **`记录状态.cmd`**：是否在记录、记录了多少、Hook 是否已信任 |
| 卸载 | 双击 **`卸载.cmd`**：卸载插件，可选删除已记录数据 |

要求：Codex 桌面 App（已验证 26.1013.4894.0 / 内核 0.163.0-alpha.10.2）、Python 3.12+ 在 PATH 上。

## 记录什么、不记录什么

- 记录：用户 Prompt、模型公开回复、模型名与配置、工具调用 / 结果 / 错误、公开推理摘要（模型提供时）、时间戳、会话 / 回合 / 工具 ID。
- 不记录：密码、API Key、令牌、Cookie、私钥（规则脱敏）；凭证文件内容（auth.json、.env 等）；加密推理与原始推理；系统指令（只记哈希）；额度与账户信息。
- 每条事件标注 `source`（hook / transcript / derived）与 `completeness`（complete / partial / truncated / unavailable），拿不到的数据不填充。
- 数据位置：`%LOCALAPPDATA%\CodexTaskRecorder\sessions\<日期>\<会话ID>.jsonl`
- 桌面 App 自动发起的后台任务（无 transcript 的会话）也会触发 Hook：照常记录，标记 `session_kind=background`，报告中单独统计。
- 事件格式 `ctr.event/v2`：会话内递增的 `seq`（采集顺序）、每条事件的 `model`；每个回合结束时派生一条 `turn_coverage`，逐项说明捕获了什么、缺什么、为什么缺。

## 数据同步（P3 原型）

默认关闭。开启后，**开启之后**记录的内容由独立的后台上传进程持续上传；Codex 正常使用即可，不需要打开充值窗口，Hook 本身不联网。

| 步骤 | 操作 |
|---|---|
| 开启 | 双击 **`开启同步.cmd`**：阅读授权说明，按 `Y` 同意（如本地记录未开启会先询问记录同意） |
| 暂停 | 双击 **`暂停同步.cmd`**：之后的内容不上传；已排队的内容留在本机，恢复后继续上传 |
| 恢复 | 再次双击 **`开启同步.cmd`**（一行确认） |
| 状态 | 双击 **`同步状态.cmd`**：待上传 / 已上传条数、最近错误、上传进程、后台已收到条数 |
| 撤销 | 双击 **`撤销同步.cmd`**：停止上传、丢弃未上传内容，可选删除后台已上传数据；离线时联网后自动送达 |

- 身份：匿名设备（后台生成的设备 ID + DPAPI 加密保存的设备令牌），不发送 ChatGPT 账号信息。与充值插件不共享代码、令牌和数据。
- 同意绑定后台地址：更换后台须重新同意；本设备已在原后台注册时须先「撤销同步」（否则原后台的数据将无法再删除）。
- 队列就是本地会话文件：每个会话一个上传游标，后台确认后才前移；断网、后台停机、进程退出都不会丢；后台按 `event_id` 去重；同一会话按 `seq` 顺序发送。
- 上传前再脱敏一遍（含 CDK / 兑换码、`sess-` 会话密钥、令牌），并去掉记录器诊断信息（本机环境变量、进程链）。
- 后台尚未实现：接口约定见 `docs/sync-api.md`。同步服务地址默认未配置；本机调试先运行 `python scripts\mock_sync_server.py`，再 `ctr.cmd sync config --base-url http://127.0.0.1:18788`。
- 本机数据：`%LOCALAPPDATA%\CodexTaskRecorder\sync\`（`state.json` 授权时段、`device.bin`、`cursors\` 上传游标、`status.json`、只记操作类型的 `sync.log`）。
- 设计：`docs/superpowers/specs/2026-10-28-data-sync-design.md`；测试结果：`docs/sync-test-report.md`；桌面手测：`docs/sync-manual-test.md`。

## CDK 充值插件（P1 原型）

在 Codex 输入框单独发送 **`/充值`** → 弹出「Codex 充值」小窗口 → 首次确认充值账号 → 输入 CDK → 确认兑换。CDK 只在小窗口里输入，不进入 Codex 对话、日志或埋点。

| 步骤 | 操作 |
|---|---|
| 安装 | 双击 **`安装充值插件.cmd`** → 重启 Codex App → 插件 → Codex CDK 充值 → 点「信任」 |
| 使用 | Codex 输入框发送 `/充值`；或双击 **`充值.cmd`** 直接打开窗口 |
| 卸载 | 双击 **`卸载充值插件.cmd`** |
| 设置 | `cdkr.cmd config --base-url https://…`（充值服务地址）；`cdkr.cmd status`；`cdkr.cmd unbind` |

- 充值账号由 Codex App 内核官方接口 `account/read` 读取（邮箱、套餐、账号 ID，不含令牌），用户确认后绑定。插件不读取 `auth.json`，不发送任何 ChatGPT 登录凭证。
- 后台尚未实现：接口约定见 `docs/recharge-api.md`。充值服务地址默认未配置；本机调试先运行 `python scripts\mock_recharge_server.py`，再 `cdkr.cmd config --base-url http://127.0.0.1:18787`。
- 代价：UserPromptSubmit 不支持 matcher，每条提示词都会运行一次该 Hook（约 0.4 s）。
- 本机数据：`%LOCALAPPDATA%\CodexCdkRecharge\`（`config.json`、DPAPI 加密的 `binding.bin`、只记操作类型的 `cdkr.log`）。
- 设计：`docs/superpowers/specs/2026-10-28-cdk-recharge-design.md`；测试结果：`docs/recharge-test-report.md`。

## 目录

```
.agents/plugins/marketplace.json     本地插件市场 ctr-local
plugins/codex-task-recorder/          Codex 插件（清单、hooks.json、Python 记录器）
plugins/codex-cdk-recharge/           Codex 插件：/充值 弹窗（hooks.json、tkinter 窗口、后台客户端）
*.cmd                                 用户双击入口；ctr.cmd / cdkr.cmd 为底层 CLI
tests/                                单元测试（合成数据）
scripts/live_tests.py                 实测脚本（消耗模型额度）
scripts/live_recharge_hook.py         /充值 Hook 实测（app-server）
scripts/live_window_demo.py           充值窗口实测（真实窗口 + 模拟后台，逐步截图）
scripts/mock_recharge_server.py       充值模拟后台
scripts/mock_sync_server.py           数据同步模拟后台
scripts/live_sync_test.py             数据同步实测（app-server + 模拟后台，消耗模型额度）
docs/hooks-support.md                 官方 App 的 Hooks 支持范围与限制
docs/coverage-report.md               事件覆盖率报告
docs/recharge-api.md                  充值后台接口约定
docs/recharge-test-report.md          充值插件测试结果与遗留问题
docs/recharge-manual-test.md          充值插件桌面 App 手动测试清单
docs/desktop-manual-test.md           桌面 App 手动测试清单
docs/sync-api.md                      数据同步后台接口约定
docs/sync-test-report.md              数据同步测试结果与遗留问题
docs/sync-manual-test.md              数据同步桌面 App 手动测试清单
docs/superpowers/specs/               设计说明
```

## 开发

```bat
:: 单元测试
set PYTHONPATH=plugins\codex-task-recorder\lib;plugins\codex-cdk-recharge\lib;tests
python -m unittest discover -s tests -t tests

:: 仅限测试目录开启记录、实测、出报告
ctr.cmd enable --i-consent --cwd D:\ctr-testbed
python scripts\live_tests.py --alt-model gpt-5.6-luna
ctr.cmd report --copy-to docs\coverage-report.md   :: report 会先执行 flush，补读会话最后一个 Hook 之后写入的 transcript

:: 数据同步实测（自动启动模拟后台、开启同步，结束时撤销并删除）
python scripts\live_sync_test.py --alt-model gpt-5.6-luna
ctr.cmd sync run --once                            :: 前台运行一次上传进程（调试）
```

修改 Python 代码后运行 `ctr.cmd install` 即可原地更新插件，**不需要重新信任**；修改 `hooks/hooks.json` 会让对应 Hook 变为 `modified`，需要用户重新信任。

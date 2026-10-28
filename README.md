# Codex Task Recorder（原型 v0.1）

面向主动参与模型评测、明确授权的用户：在 **Windows 官方 Codex 桌面 App** 中，通过官方生命周期 Hooks 把测试会话记录为本地 JSONL。不修改官方程序，不联网上传。

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

## 目录

```
.agents/plugins/marketplace.json     本地插件市场 ctr-local
plugins/codex-task-recorder/          Codex 插件（清单、hooks.json、Python 记录器）
*.cmd                                 用户双击入口；ctr.cmd 为底层 CLI
tests/                                单元测试（合成数据）
scripts/live_tests.py                 实测脚本（消耗模型额度）
docs/hooks-support.md                 官方 App 的 Hooks 支持范围与限制
docs/coverage-report.md               事件覆盖率报告
docs/desktop-manual-test.md           桌面 App 手动测试清单
docs/superpowers/specs/               设计说明
```

## 开发

```bat
:: 单元测试
set PYTHONPATH=plugins\codex-task-recorder\lib;tests
python -m unittest discover -s tests -t tests

:: 仅限测试目录开启记录、实测、出报告
ctr.cmd enable --i-consent --cwd D:\ctr-testbed
python scripts\live_tests.py --alt-model gpt-5.6-luna
ctr.cmd report --copy-to docs\coverage-report.md   :: report 会先执行 flush，补读会话最后一个 Hook 之后写入的 transcript
```

修改 Python 代码后运行 `ctr.cmd install` 即可原地更新插件，**不需要重新信任**；修改 `hooks/hooks.json` 会让对应 Hook 变为 `modified`，需要用户重新信任。

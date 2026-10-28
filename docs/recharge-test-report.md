# CDK 充值插件（P1）测试结果与遗留问题

- 日期：2026-10-28；Codex 桌面 App 26.1013.4894.0，内核 `0.163.0-alpha.10.2`；Windows Server 2025；Python 3.12.10 / Tk 8.6
- 后台：本机模拟后台（`scripts/mock_recharge_server.py`）。**真实后台不存在，未做真实充值。**

## 1. 单元测试

```
set PYTHONPATH=plugins\codex-task-recorder\lib;plugins\codex-cdk-recharge\lib;tests
python -m unittest discover -s tests -t tests
Ran 152 tests … OK      （充值插件 + 本次改动的 P0 部分；按完整顺序连续多次）
整仓 236 tests … OK     （含另一会话并行开发的 ctr.sync 模块，非本次改动）
```

| 文件 | 数量 | 覆盖 |
|---|---|---|
| test_cdkr_trigger | 10 | `/充值`（含全角 `／充值`）拦截并拉起；后面带文字也拦截且不回显；拉起失败仍拦截；普通提示词 / 其他事件 / 坏输入不输出；stdin 读失败 exit 0；ASCII JSON；**以子进程运行真实入口脚本**：普通提示词无输出；lib 缺失时仍拦截 `/充值` |
| test_cdkr_api | 15 | 对模拟后台：绑定、成功与幂等重放、他人已用 409、无效 400、过期 410、履约失败 422、处理中轮询、超时 → Unknown 后重试只扣一次、401、403、5xx、429 + Retry-After、连接被拒 → NotSent、本机地址绕过代理、非 https / 端口无效的地址拒绝、CDK / 令牌不进 URL、异常不含 CDK、**301/302/303/307/308 都不跟随，目标服务器收不到任何请求和令牌** |
| test_cdkr_flow | 31 | 未配置后台时不读账号、不能兑换；首次绑定、Codex 换账号需重绑、换后台地址需重绑、四种账号读取失败、后台不可达时绑定失败；兑换成功（掩码）、重复兑换、去空白、格式不对不发请求、无效 / 过期 / 履约失败 / 他人已用、处理中轮询、处理中超过轮询时限、处理中后失败、轮询时登录失效、账号不一致清除绑定、超时后同请求重试成功且只扣一次、一开始就不可达 → 未发出、**已发出无回应后再连不上 → 仍是"未确认"而不是"CDK 未使用"**、已发出无回应后 5xx → 未确认、登录失效清除绑定、5xx、429、成功先显示再查套餐、套餐查询失败不影响成功、未绑定不能兑换、日志不含 CDK / 令牌 / 邮箱 / 账号 ID、后台自造错误码不进日志 |
| test_cdkr_account | 10 | 按实测 `account/read` 结构解析；未登录、非 ChatGPT 登录、缺字段；定位内核不运行任何子进程；未装 App；**JSON-RPC 收发**（假 app-server：跳过通知与非 JSON 行、错误回复、进程退出、无回应超时后及时返回） |
| test_cdkr_launch | 5 | pythonw + 插件 lib；不继承句柄、DETACHED；Job 不允许脱离时回退；**父进程立即返回、子进程继续存活**；单实例互斥量 |
| test_cdkr_window | 15 | 真实 Tk 控件：绑定 → 兑换 → 补充套餐信息、回车兑换、失败保留输入、登录失效回到绑定、读取失败可重试、模拟后台标注；**真实工作线程路径：所有界面更新都在主线程**；卡片外观：无边框、宽 340、套餐显示为胶囊、关闭按钮、Esc 关闭、兑换中关闭先确认、拖动移动窗口、状态颜色随结果、卡片随文字变高、**圆角裁剪区域跟随卡片高度** |
| test_cdkr_paint | 9 | 配色混合与十六进制、极光底的尺寸 / 合法颜色 / 有变化 / 三档各不相同 / 都在浅色区间、圆角多边形不越界与半径收敛 |
| test_cdkr_vault | 4 | DPAPI 往返且磁盘无明文、篡改 / 损坏 → None、删除、删不掉时不抛异常 |
| test_cdkr_cli | 8 | 解析 `codex plugin list`、配置地址校验、默认未配置、带 BOM 的配置文件、卸载时市场的保留与删除（`plugin list` 失败时保留） |
| test_cli（P0） | 3 | 卸载记录器时，若充值插件还在或 `plugin list` 失败则保留共享市场 |
| test_redact / test_hook（P0 新增） | 2 | `/充值…` / `／充值…` 整条替换为 `[REDACTED:recharge_command]`，磁盘上找不到 CDK |

变异检验：把"先未知后未发出""先未知后 5xx""轮询时 401"三处逻辑分别改坏，对应测试都会失败。

## 2. 真实窗口实测（`scripts/live_window_demo.py`）

窗口外观已按用户要求改为 Codex 小助手额度悬浮窗的样式（无边框圆角卡片、极光底、可拖动），见第 4 节。

真实窗口（工作线程）、真实流程、真实 `account/read`；后台为模拟后台；截图在 `.testdata/cdkr-window/`（邮箱打码）。

| 步骤 | 按钮 | 状态栏 |
|---|---|---|
| 首次打开 | 确认充值到此账号 | 首次使用：确认后，CDK 将充值到上面这个 ChatGPT 账号。 |
| 绑定 | 确认兑换 | 绑定成功。 |
| TEST-OK01 | 确认兑换 | 充值成功：ChatGPT Plus 1 个月（模拟）。CDK TE…01 已核销。（绿色；套餐信息随后补上） |
| 再次 TEST-OK01 | 确认兑换 | 重复兑换：CDK TE…01 已于 2026-10-28 21:31 充值到当前账号…，未重复扣除。 |
| WRONG-CODE-123 | 确认兑换 | CDK WRON…-123 无效，请检查是否输错。（红色） |
| TEST-EXPD | 确认兑换 | CDK TE…PD 已过期。 |
| 网络断开 | 确认兑换 | 网络连接失败，兑换请求没有发出，CDK 未使用。请检查网络后重试。 |
| 登录失效 | 确认充值到此账号 | 登录已失效，请重新绑定账号后再兑换。 |

日志 9 行，不含 CDK。

拉起路径（`cdkr.cmd open`，与 Hook 相同的 `launch.open_window`）：278 ms 返回；窗口出现在最前；再次打开不产生第二个进程；结束窗口进程后 Codex 进程数不变（2 → 2）。

审查修复后（见第 4 节）重跑，结果相同。

## 3. Hook 实测（`scripts/live_recharge_hook.py --with-normal`，App 内核 app-server）

结果文件：`.testdata/live/recharge-hook-results.json`。

| 项目 | 结果 |
|---|---|
| Hook 信任 | 用户在 App 中信任后为 `trusted` |
| `/充值` | Hook 状态 **`blocked`**，377 ms；回合 `completed`，**没有任何模型输出条目**；feedback 文字为拦截原因 |
| 窗口进程 | Hook 结束 3 s 后仍在运行（未被 Codex 的 Job 一并结束） |
| `/充值 ZZPROBE-NOT-A-CDK-7731` | 同样 `blocked`（351 ms），提示不要把 CDK 写在后面 |
| 被拦截的提示词是否写入 rollout | **否**：rollout 里有同一会话的普通提示词，但没有 `充值` 和探针文字 |
| P0 记录器 | 两条被拦截的提示词都记为 `[REDACTED:recharge_command]`；普通提示词照常记录 |
| 普通提示词的 Hook 开销 | 322 ms（本插件），与记录器的 UserPromptSubmit（435 ms）**并行**执行，两者同时开始 |
| 首个回合 14.4 s | Hook 在 `turn/started` 之后 13.5 s 才开始，是 Codex 会话首回合自身的初始化；装本插件之前的 P0 实测同样有 5–9 s 的空档，后续回合为 0 |
| 审查修复后重跑 | 两次均 `blocked`（367 / 340 ms），窗口进程存活，rollout 与记录器均无探针文字 |

## 4. 代码审查与修复

独立审查结论"修复后可合并"，没有严重问题。已修复：

| 级别 | 问题 | 修复 |
|---|---|---|
| 重要 | 窗口的进度更新在正式运行时从工作线程直接调用 Tk（`is not` 比较绑定方法恒为真） | 工作线程不持有任何 Tk 对象，只把"编号 + 结果"放进队列，由主线程回调；新增真实线程路径测试。同时修复了该测试暴露的 Tcl 跨线程释放崩溃（主线程显式 GC） |
| 重要 | urllib 跟随重定向：会把 `Authorization` 带到任意 `Location`（含 http），且被处理过的 POST 可能误报"CDK 未使用" | 不跟随任何重定向；POST 的 3xx → 结果未知，GET 的 3xx → 无法识别 |
| 次要 | 默认后台 `http://127.0.0.1:18787`：本机任何进程或其他用户可抢先监听 | 默认未配置，未配置时禁止兑换 |
| 次要 | 插件 lib 损坏时 `/充值 <CDK>` 会被放行给模型 | 入口脚本自行拦截 |
| 次要 | 成功要等再次读取账号（约 3 s）才显示；读取异常会把成功变成"意外错误" | 成功立即显示，套餐信息之后补上；任何读取异常都忽略 |
| 次要 | 卸载时 `plugin list` 失败会误删共享市场 | 无法确认时保留（两个插件） |
| 次要 | 无效转义、BOM 配置、端口校验、`vault.clear` 被锁、`_drain` 回调异常后不再调度、掩码露出过多、全角 `／充值`、兑换中关窗无确认、接口文档的超时描述 | 逐项修复并补测试 |

未采纳：无。审查"未判断"的条目里，"App 后台任务（标题 / 建议生成）是否拿到被拦截的提示词"已加入手测清单第 10 步。

## 5. 修改文件清单

新增：
```
plugins/codex-cdk-recharge/.codex-plugin/plugin.json
plugins/codex-cdk-recharge/hooks/hooks.json
plugins/codex-cdk-recharge/hooks/cdkr_hook.py
plugins/codex-cdk-recharge/lib/cdkr/{__init__,__main__,account,api,cli,config,flow,launch,log,single,trigger,vault,window}.py
cdkr.cmd  充值.cmd  安装充值插件.cmd  卸载充值插件.cmd
scripts/mock_recharge_server.py  scripts/live_window_demo.py  scripts/live_recharge_hook.py
tests/cdkr_helpers.py  tests/fake_app_server.py  tests/test_cdkr_{account,api,cli,flow,launch,trigger,vault,window}.py  tests/test_cli.py
docs/recharge-api.md  docs/recharge-manual-test.md  docs/recharge-test-report.md
docs/superpowers/specs/2026-10-28-cdk-recharge-design.md
```
修改：
```
.agents/plugins/marketplace.json                 新增 codex-cdk-recharge 条目；市场显示名改为「本地插件（ctr-local）」
plugins/codex-task-recorder/lib/ctr/redact.py    /充值 开头的文本整条脱敏
plugins/codex-task-recorder/lib/ctr/cli.py       卸载时保留仍被其他插件使用的共享市场
tests/test_redact.py  tests/test_hook.py          对应测试
README.md                                        充值插件说明、目录、测试命令
```
本机安装（用 App 内核官方命令）：`codex-cdk-recharge@ctr-local` 0.1.0（Hook 已由用户信任）；`codex-task-recorder` 原地刷新（hooks.json 未变，12 个 Hook 仍 trusted）；`~/.codex/config.toml` 安装前已备份（`config.toml.bak-cdkr-*`）。本机 `%LOCALAPPDATA%\CodexCdkRecharge\config.json` 已指向模拟后台 `http://127.0.0.1:18787`。

## 6. 遗留问题

| # | 问题 | 影响 / 下一步 |
|---|---|---|
| 1 | **真实后台不存在，未完成一次真实充值** | 验收项"有效 CDK 完成一次真实充值"未完成。后台按 `docs/recharge-api.md` 实现后，`cdkr.cmd config --base-url https://…` 切换并重新验收 |
| 2 | **后台履约方式需合规核查** | 客户端只提供邮箱 + chatgptAccountId，不提供任何 ChatGPT 凭证。若后台开通依赖用户的 session / access token，本方案不支持，需重新讨论 |
| 3 | 绑定无法证明账号归属 | 绑定只关联"设备 ↔ 目标账号"；CDK 持有人决定充到哪个账号。如需防误充，可由后台加确认步骤 |
| 4 | 每条提示词都运行本 Hook（UserPromptSubmit 不支持 matcher） | 单独约 0.32–0.38 s；与记录器并行时不增加墙钟时间。不用时可在插件页禁用 |
| 5 | 桌面 App 界面表现待手测 | `/` 斜杠菜单是否影响发送 `/充值`、拦截原因如何显示、窗口是否在最前（`docs/recharge-manual-test.md`） |
| 6 | 读取账号约 3 s | 每次打开窗口启动一个临时 app-server；窗口先显示"正在读取 Codex 登录账号…" |
| 7 | 充值后套餐显示可能滞后 | 为避免与 App 争用刷新令牌，不调用 `refreshToken`；提示"可能要稍后或重启 Codex 后才更新" |
| 8 | 用户若在**普通消息**里粘贴 CDK（不以 `/充值` 开头） | 会进入模型与 Codex rollout，本插件无法拦截；窗口底部与拦截提示都提醒只在窗口内输入。另：本机的 Codex 小助手默认上传 Codex 对话文件（`JNT-CLOUD.md` 第五节），此类误粘贴会被它上传 |
| 9 | 后台地址需要配置 | 默认未配置；连接本机地址时窗口底部标注"本机模拟后台"；非本机地址强制 https、不跟随重定向 |
| 10 | 依赖 PATH 上的 Python 3.12（含 tkinter） | 与 P0 相同；官方安装包默认包含 tkinter |
| 11 | 两个插件各有一份内核定位 / `plugin list` 解析代码 | 插件独立安装、不能互相导入，属有意重复 |
| 11b | 卡片没有投影，字体是 Microsoft YaHei UI | Tk 画不出柔和投影（小助手用 Pillow 分层窗口）；不随包鸿蒙字体 |
| 11c | 无边框窗口不进任务栏、不进 Alt+Tab | 被其他窗口盖住时，再发一次 `/充值` 会把它提到最前（单实例） |
| 12 | Codex 新会话首回合有 5–13 s 自身初始化 | 与本插件无关（见第 3 节） |
| 13 | App 后台任务是否接触被拦截的提示词 | rollout 不含被拦截的提示词（实测），但桌面 App 自己的界面存储 / 草稿 / 后台建议任务无法用 app-server 观察，见手测第 10 步 |
| 14 | 以 `/充值` 开头的所有提示词都会被拦截 | 例如"/充值失败怎么办"也会被拦下并打开窗口；属有意的前缀匹配，宁可多拦 |

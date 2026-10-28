# Codex CDK 充值插件（P1）— 设计说明

- 日期：2026-10-28；状态：用户已选定方案 A，按本文实施
- 接口约定：`docs/recharge-api.md`

## 1. 目标与约束

为 Windows 官方 Codex 桌面 App 提供轻量充值入口：用户在 Codex 输入框发送 `/充值` → 弹出原生小窗口 → 输入 CDK → 充值到自己的 ChatGPT 账号。

用户约束：不修改官方 App；不引入大型 UI 框架；不要求打开浏览器；不影响现有 Codex 使用习惯；CDK 不进入 Codex 对话历史、任务日志或埋点；session 等凭证不上传；不假设插件能读取官方 App 的登录状态。

用户决定（2026-10-28）：
0. 窗口外观照 Codex 小助手的额度悬浮窗（`codexrouter-release/desktop/ball_render.py`）：**无边框圆角卡片、可拖动**；用 **tkinter 复刻**，不引入 Pillow。
1. 充值后台 **尚不存在** → 先定接口约定 + 本地模拟后台；真实充值待后台就绪后验收。
2. 充值对象是 **用户的 ChatGPT 账号**。
3. 账号来源：**App 内核官方 `account/read` 读取 + 用户确认**。
4. 触发方式：**方案 A，UserPromptSubmit Hook 识别 `/充值`**，拦截该提示词不发给模型。

## 2. 核查结论（实测 / 文档）

| 项目 | 结论 | 依据 |
|---|---|---|
| 现有充值后台 | 本仓库、codexrouter 全部 297 个分支、jnt-cloud 客户端接口均无 CDK / 兑换 / 核销 | 【实测】代码搜索 |
| 官方登录状态 | `account/read`（App 内核 0.163.0-alpha.10.2）返回 `account{type,email,planType}` 与 `workspaceRouting.chatgptAccountId`，**不含令牌**，约 3 秒 | 【实测】 |
| 获取 session | 协议中没有把 App 令牌交给客户端的接口（`chatgptAuthTokens` 是客户端交给 Codex，标注"OpenAI 内部使用"）；唯一途径是读 `auth.json`，不做 | 【实测】协议 schema |
| Hook 拦截 | UserPromptSubmit 支持 `{"decision":"block","reason":…}`；实测 Hook 状态 `blocked`、回合无模型输出、**被拦提示词不写入 rollout**，reason 以 `feedback` 条目下发；桌面端界面表现待手测 | 【文档】+【实测】app-server |
| 窗口存活 | 分离进程在 Hook 退出后继续运行；Hook 约 0.35 s | 【实测】app-server |
| matcher | UserPromptSubmit **不支持 matcher** → 每条提示词都会运行本 Hook（约 0.4 s，P0 实测） | 【文档】 |
| 信任 | 插件 Hook 需用户在 App 中亲自信任；只改 Python 不需重新信任 | 【实测】P0 |
| tkinter | Python 3.12.10 自带 Tk 8.6 | 【实测】 |

## 3. 架构

独立插件 `codex-cdk-recharge`（与记录器同一本地市场 `ctr-local`，代码互不依赖）。

```
plugins/codex-cdk-recharge/
  .codex-plugin/plugin.json
  hooks/hooks.json       1 个同步 UserPromptSubmit，timeout 5
  hooks/cdkr_hook.py     薄入口，任何异常 exit 0；lib 加载失败时仍自行拦截 /充值
  lib/cdkr/
    trigger.py   提示词 lstrip 后以 /充值（或全角 ／充值）开头 → 拉起窗口 + block；否则不输出
    launch.py    分离进程拉起 pythonw -m cdkr.window
    single.py    命名互斥量单实例；已开着则把窗口提到最前
    paint.py     卡片外观：配色、极光底、圆角多边形（不依赖 Tk，可单测）
    window.py    tkinter 界面（只显示和收集输入）
    flow.py      绑定 / 兑换 / 查询 / 重试 / 错误映射（不依赖 tk，可单测）
    api.py       后台客户端（urllib）
    account.py   定位 App 内核（bin 下最新的 codex.exe，不运行子进程）+ account/read
    vault.py     DPAPI 加密保存绑定
    config.py    数据目录、后台地址
    log.py       只记操作名、结果类型、HTTP 状态、耗时
    cli.py       install / uninstall / open / config / unbind / status
充值.cmd  安装充值插件.cmd  卸载充值插件.cmd  cdkr.cmd
scripts/mock_recharge_server.py
```

后台地址 **默认未配置**（未配置时窗口提示并禁止兑换），以免任意本机进程监听某个默认端口收到 CDK；开发时用 `cdkr.cmd config --base-url http://127.0.0.1:18787` 指向模拟后台。

数据目录 `%LOCALAPPDATA%\CodexCdkRecharge\`：`config.json`、`binding.bin`（DPAPI，内容为 binding_token、账号 id、邮箱、base_url、绑定时间）、`cdkr.log`。

## 4. 流程

1. 用户发送 `/充值` → Hook（同步）拉起窗口进程并返回 block，提示词不发给模型；以 `/充值` 开头但后面还有文字（可能是 CDK）同样拦截，并提醒 CDK 只在窗口里输入。
2. 窗口启动：后台线程调用 `account/read`。
   - 失败 / 未登录 / API Key 登录 → 显示原因，禁用兑换。
   - 无绑定 → 显示邮箱与"绑定此账号"按钮；绑定成功后启用 CDK 输入。
   - 有绑定但 `chatgpt_account_id` 不同 → 提示 Codex 已换账号，需重新绑定。
   - 绑定的 base_url 与当前配置不同 → 视为无绑定。
3. 兑换：校验（去空白，4–128 个可见 ASCII 字符）→ `POST /v1/redemptions`。
   - 结果未知（超时、连接中断）→ 同样的请求自动重试 3 次；`processing` → 每 3 秒查询，最多 60 秒。
   - 成功结果立即显示；之后在后台再读一次 `account/read`，套餐有变化就补在结果后面（读取失败不影响结果）。不调用 `refreshToken`，以免与 App 争用刷新令牌。
   - HTTP 客户端不跟随重定向（否则 `Authorization` 会被带到任意 `Location`）：POST 遇到 3xx 视为结果未知。
4. 401 → 删除本地绑定，提示"登录已失效，请重新绑定"。
5. 兑换进行中关闭窗口 → 先确认（关闭后再次提交同一 CDK 可查询结果）。
6. 线程：Tk 只在主线程使用；工作线程只拿到要执行的函数，结果按编号放进队列，由主线程取出回调。

## 4.1 卡片外观（照搬小助手的设计数值）

| 项目 | 取值 | 来源 |
|---|---|---|
| 宽度 / 圆角 / 内边距 | 340 / 30 / 26、22、20 | 小助手 `CARD_W` 340、`CARD_RADIUS` 38（我们用 30，Win32 硬裁剪的边缘更显圆）、`PAD_X/TOP/BOTTOM` |
| 底色 | `#edf3f8` + 极光（线性渐变 + 三团径向光，healthy/caution/critical 三档） | `ball_render.aurora` / `PALETTES` |
| 文字 | 墨色 `#17191f`，次级 68%、弱 45% | `INK` |
| 胶囊标签 | 蓝底 28%（小助手 16%，叠在极光上看不见，调高） | `_chip` |
| 状态灯 | 绿 `#63f58c` / 灰 `#8f9094` | `STATUS_OK/STALE` |
| 主按钮 | `#0060df`，悬停 `#0050bd`，白字 | 小助手界面规范 |
| 字体 | Microsoft YaHei UI | 小助手用随包的鸿蒙字体；我们不随包字体，用系统字体 |

实现要点：
- Tk 没有渐变和透明度：极光底按行算出颜色后用 `PhotoImage.put` 画，**半分辨率算再 `zoom(2)`**（全分辨率纯 Python 要 1.3 s，半分辨率 0.33 s，渐变平滑看不出放大）。结果按尺寸缓存。
- 圆角用 Win32 `SetWindowRgn`。**必须在窗口真正改变大小之后再设**（`<Configure>`）：`SetWindowRgn` 会把区域裁到调用时的窗口大小，紧跟 `geometry()` 调用会让卡片卡在旧高度（实测卡在 302，窗口已到 367）。
- 卡片高度随状态文字增减；没有投影（Tk 画不了，尝试过 `CS_DROPSHADOW`）。

## 5. 隐私

- CDK 只存在于窗口进程内存里：不写盘、不进日志、不放进命令行参数或 URL；状态里只显示掩码（前 4 位…后 4 位）。
- `binding_token` 只存在 DPAPI 加密文件里；日志不记录邮箱。
- 无任何埋点。
- Hook 不输出、不记录提示词。
- 记录器（P0）：以 `/充值` 开头的文本整体替换为 `[REDACTED:recharge_command]`（Hook 与 transcript 两条路径都经过 `redact_text`）。

## 6. 测试

- 单元测试：trigger（拦截 / 放行 / 坏输入）、api（对模拟后台：成功、重复、无效、过期、履约失败、处理中、超时后幂等重试、网络未发出、401、5xx、429）、flow（绑定、换账号、掩码、日志不含 CDK）、vault（DPAPI 往返、篡改）、记录器脱敏。
- 实测（App 内核 app-server，Hook 被信任后）：`/充值` 是否被拦截、是否写入 rollout、Hook 退出后窗口进程是否存活、耗时。
- 桌面 App 手测：`docs/recharge-manual-test.md`。

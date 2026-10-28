# CDK 充值后台接口约定 v1（草案）

- 日期：2026-10-28；状态：**后台尚未实现**。客户端（`plugins/codex-cdk-recharge`）与本地模拟后台（`scripts/mock_recharge_server.py`）按本文实现。
- 充值对象：用户自己的 ChatGPT 账号。

## 0. 边界：客户端不提供任何 ChatGPT 凭证

客户端只发送 **账号标识**（`chatgpt_account_id` + `email`），二者来自 Codex App 内核官方接口 `account/read`，并经用户在窗口中确认。

客户端 **不会** 发送、读取或要求用户粘贴 ChatGPT 的 session / access token / cookie：

- Codex 官方接口不提供这些令牌（`account/read` 只返回 `email`、`planType`、`chatgptAccountId`；协议里涉及令牌的消息方向都是"客户端交给 Codex"）。
- 读取 `~/.codex/auth.json` 属于直接读取官方 App 的私有凭证，不做。
- 把令牌交给第三方等于共享账号凭证：违反 OpenAI 使用条款，且对方可完全接管账号。

**后台如何只凭账号标识完成开通（履约方式）不在本约定范围内，上线前须单独做合规核查。** 如果履约依赖用户的 ChatGPT 会话令牌，本客户端无法支持，需要重新讨论方案。

## 1. 通用

- Base URL 可配置（`%LOCALAPPDATA%\CodexCdkRecharge\config.json` 的 `base_url`，`cdkr.cmd config --base-url …`），**默认未配置**。非本机地址必须是 `https://`，否则客户端拒绝连接。
- 请求和响应都是 `application/json; charset=utf-8`。请求头 `X-Cdkr-Client: codex-cdk-recharge/<版本>`。
- 除绑定外，请求都带 `Authorization: Bearer <binding_token>`。
- 错误统一格式：`{"error": {"code": "<错误码>", "message": "<给用户看的中文，可选>"}}`。
- **CDK 只出现在请求体中**，不得出现在 URL、查询参数和响应头里；后台日志不得记录 CDK 全文和 `binding_token`。

## 2. 绑定 `POST /v1/bindings`

首次使用，或绑定失效、Codex 换了账号时调用。

请求：
```json
{"chatgpt_account_id": "ccf6cc43-…", "email": "user@example.com"}
```
`201`：
```json
{"binding_token": "cdkb_…", "account": {"chatgpt_account_id": "ccf6cc43-…", "email": "user@example.com"},
 "expires_at": "2027-01-01T00:00:00Z"}
```
`expires_at` 可以为 null。

| 状态 | code | 含义 |
|---|---|---|
| 400 | `invalid_account` | 账号标识缺失或格式不对 |
| 429 | `rate_limited` | 带 `Retry-After`（秒） |

说明：绑定无法证明请求方拥有该 ChatGPT 账号，它只把"这台设备"与"充值目标账号"关联起来。后台应当把 CDK 视为持有人的支付凭证，由持有人决定充到哪个账号。

## 3. 兑换 `POST /v1/redemptions`

请求：
```json
{"cdk": "ABCD-EFGH-IJKL-MNOP", "chatgpt_account_id": "ccf6cc43-…"}
```

**幂等（必须）**：以 `(cdk, chatgpt_account_id)` 为键。同一账号再次提交已兑换或处理中的同一 CDK，返回 **已有的那条兑换记录**（`replayed: true`），不重复扣卡、不重复开通。客户端在超时后会用同样的请求重试，依赖这一点。

`200`（新建为 `201`）：
```json
{"redemption_id": "rdm_…", "status": "succeeded", "replayed": false,
 "product": "ChatGPT Plus 1 个月", "redeemed_at": "2026-10-28T12:00:00Z", "message": null}
```
`status`：`succeeded` / `processing` / `failed`。为 `failed` 时带 `error`（同错误格式），且 **CDK 不得被扣除**。

| 状态 | code | 客户端提示 |
|---|---|---|
| 400 | `cdk_invalid` | CDK 无效，请检查是否输错 |
| 409 | `cdk_already_redeemed` | 此 CDK 已被其他账号使用（同账号重复提交走上面的幂等，不报 409） |
| 410 | `cdk_expired` | 此 CDK 已过期 |
| 401 | `binding_invalid` | 登录已失效 → 客户端清除本地绑定，请用户重新绑定 |
| 403 | `account_mismatch` | 请求的账号与绑定的账号不一致 → 重新绑定 |
| 422 | `fulfillment_failed` | CDK 有效但开通失败，**CDK 未扣除**；`message` 写原因 |
| 429 | `rate_limited` | 带 `Retry-After` |
| 5xx | 任意 | 充值服务暂时不可用 |

## 4. 查询 `GET /v1/redemptions/{redemption_id}`

`status` 为 `processing` 时客户端每 3 秒查一次，最多查 60 秒；响应格式同第 3 节。查不到返回 404 `not_found`。

## 5. 客户端的超时与重试（后台需要知道的）

| 情况 | 客户端行为 |
|---|---|
| 连接被拒、DNS 失败等（请求一定没发出） | 提示"兑换请求未发出，CDK 未使用" |
| 已发出但超时 / 连接中断（结果未知） | 用相同请求自动重试 3 次（间隔 2、5、10 秒），依赖第 3 节的幂等；仍失败提示"结果未确认，联网后再提交同一 CDK，不会重复扣除" |
| 自动重试拿到 `replayed: true` | 视为本次兑换成功 |
| 用户新提交拿到 `replayed: true` | 提示"重复兑换：此 CDK 已于 X 充值到当前账号，未重复扣除" |

单次请求超时：每一步网络操作（连接、发送、等待响应）各 15 秒，不是整个请求的总时限。

## 6. 模拟后台

`python scripts\mock_recharge_server.py [--port 18787]`，数据只在内存里。预置 CDK：

| CDK | 行为 |
|---|---|
| `TEST-OK01` … `TEST-OK05` | 成功（一次性，可测重复兑换） |
| `TEST-SLOW` | 第一次请求等 20 秒再返回（触发客户端超时与幂等重试），之后立即返回 |
| `TEST-PROC` | 先返回 `processing`，查询 2 次后变为 `succeeded` |
| `TEST-PFAL` | 先返回 `processing`，查询 2 次后变为 `failed`（`fulfillment_failed`） |
| `TEST-FAIL` | 422 `fulfillment_failed` |
| `TEST-EXPD` | 410 `cdk_expired` |
| 其他 | 400 `cdk_invalid` |

`POST /_mock/expire-bindings` 让现有绑定全部失效（模拟登录失效）；`POST /_mock/fail-next {"status": 503}` 让下一次请求返回指定状态（带 `"location"` 时返回重定向）。

## 7. 重定向

客户端 **不跟随任何重定向**（urllib 会把 `Authorization` 头带到 `Location` 指向的地址）。POST 收到 3xx 视为"结果未知"，GET 收到 3xx 视为无法识别的响应。后台不要对这些接口返回重定向。

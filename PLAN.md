# 麦笔 / Maibi 产品与技术计划

## Summary

麦笔是一款面向 Windows 桌面的语音输入工具，首版以小团队内测为目标，帮助用户在文档、邮件、IM、网页输入框等中文办公长文本场景中提升文本输入效率。

首版采用托盘语音输入形态，不注册为 Windows 系统 IME。用户通过全局快捷键录音，客户端展示实时识别预览，确认后把最终文本写入当前光标位置。产品优先平衡准确度、易用性、响应速度和云端识别成本。

## Product Scope

- 平台：Windows 10/11 桌面。
- 用户：小团队内测用户。
- 场景：中文普通话办公长文本输入，允许少量中英混输。
- 形态：系统托盘应用 + 浮窗预览 + 设置页。
- 非首版范围：移动端输入法、浏览器扩展、真正系统 IME、账号支付、公开分发、离线识别、历史记录、产品分析采样。

## Key Behavior

- 默认全局快捷键为 `Ctrl+Alt+Space`。
- 按住快捷键开始录音，松开后等待最终识别结果并上屏。
- 浮窗实时展示中间识别结果、稳定结果、最终结果和错误状态。
- `Esc` 取消本次输入，不写入文本。
- `Enter` 提前确认当前稳定文本并上屏。
- 默认使用“预览确认后上屏”，不做边说边自动插入。
- 上屏方式首版使用剪贴板粘贴：临时写入识别文本、发送 `Ctrl+V`、随后尽量恢复原 Unicode 文本剪贴板。
- 剪贴板或输入注入失败时，保留浮窗文本并提供手动复制入口。

## Technical Design

仓库按 `client`、`server`、`core` 三部分组织：

- `client`：Windows 桌面客户端，负责托盘、浮窗、录音、快捷键、配置、上屏。
- `server`：轻量 FastAPI 签名服务，负责生成短期 ASR 会话参数，避免客户端保存云厂商 Secret。
- `core`：共享 ASR、音频、配置和文本提交接口，保持供应商可替换。

首版技术栈：

- Python 3.11+。
- PySide6：托盘、浮窗、设置页。
- sounddevice：麦克风采集。
- websockets：连接云端流式 ASR。
- pywin32：全局快捷键、剪贴板和文本上屏。
- FastAPI + uvicorn：签名后端。
- pydantic：配置和接口类型。
- pytest：单元测试和集成测试。

## ASR Provider Interface

`core` 定义供应商抽象层，首版实现腾讯云实时语音识别，后续可接入阿里云、火山引擎或本地模型。

核心接口：

```python
class AsrProvider:
    async def start_session(self, config: AsrSessionConfig) -> "AsrSession": ...

class AsrSession:
    async def send_audio(self, frame: bytes) -> None: ...
    async def finish(self) -> None: ...
    async def cancel(self) -> None: ...

class TextCommitter:
    def commit(self, text: str) -> CommitResult: ...
```

核心事件模型：

```python
class AsrEvent:
    type: str
    text: str
    stable: bool
    final: bool
    latency_ms: int | None
    error_code: str | None
```

## Tencent Cloud Defaults

首版默认使用腾讯云实时 ASR WebSocket。默认参数：

- 音频格式：16kHz、16-bit、mono、PCM。
- 分片大小：每 200ms 发送一帧。
- `engine_model_type=16k_zh`。
- `voice_format=1`。
- `needvad=1`。
- `vad_silence_time=1000`。
- `convert_num_mode=1`。
- `filter_modal=1`。
- 保留标点。

基础热词：

- 设置页支持添加常用人名、公司名、产品名和专业词。
- 腾讯云适配器优先通过 `hotword_list` 传入热词。
- 单次最多 128 个热词。
- 默认权重为 8。
- 禁止空格、空字符串和超长词。

参考资料：

- 腾讯云实时 ASR WebSocket：https://cloud.tencent.com/document/product/1093/48982
- 腾讯云语音识别计费：https://cloud.tencent.com/document/product/1093/35686
- 阿里云 WebSocket ASR：https://help.aliyun.com/zh/isi/developer-reference/websocket

## Server API

签名服务提供最小 API：

```http
POST /v1/asr/session
GET /healthz
```

`POST /v1/asr/session` 请求字段：

```json
{
  "provider": "tencent",
  "engine": "16k_zh",
  "hotwords": ["麦笔", "客户名称"],
  "client_session_id": "uuid"
}
```

响应字段：

```json
{
  "provider": "tencent",
  "websocket_url": "wss://...",
  "expires_at": "2026-05-23T12:00:00+08:00"
}
```

服务端要求：

- 腾讯云 `SecretId`、`SecretKey`、`AppId` 只通过服务端环境变量配置。
- 客户端不得保存云 Secret。
- 签名 URL 短期有效。
- 按设备或客户端 ID 做每日分钟数限流。
- 日志不得记录完整签名 URL、音频、转写文本或热词明文。

## Privacy And Cost Controls

隐私默认值：

- 不保存音频文件。
- 不保存转写文本历史。
- 不上传产品分析采样。
- 客户端只保存设置、热词和非内容类诊断信息。
- 服务端日志只记录请求时间、匿名设备标识、时长、供应商、错误码和延迟指标。

成本默认值：

- 客户端默认每日语音上限 60 分钟。
- 使用量达到 80% 时提示。
- 达到上限后当天阻止继续录音。
- 服务端也做每日分钟数限制，避免客户端绕过。
- 设置页允许调整本地提醒阈值，但服务端上限由部署方控制。

## Quality Targets

首版均衡目标：

- 普通话办公文本字准确率 >= 90%。
- 松开快捷键到最终文本上屏 P95 <= 1.5s。
- 录音启动到浮窗反馈 P95 <= 300ms。
- 连续 30 分钟使用无客户端崩溃。
- 云端识别失败时能清晰提示并允许重试。

## Test Plan

单元测试：

- ASR 事件解析。
- 腾讯云签名参数生成。
- 热词校验。
- 配置读写。
- 文本后处理。
- 用量上限逻辑。

集成测试：

- 使用 mock WebSocket ASR 服务验证 200ms 音频分片。
- 验证中间结果、稳定结果、最终结果事件流。
- 验证断网、超时、服务端错误和用户取消。
- 验证签名服务不泄露 Secret 和完整签名 URL。

客户端验收：

- Windows 10/11 上测试 Notepad、Word、Chrome 输入框、微信、企业微信。
- 验证按住录音、松开上屏、`Esc` 取消、`Enter` 确认。
- 验证剪贴板恢复、剪贴板失败提示、快捷键冲突提示。
- 验证热词提升专有名词识别效果。

隐私验收：

- 检查客户端配置目录没有音频文件和转写文本历史。
- 检查服务端日志没有音频、转写文本、完整签名 URL 或热词明文。

## Assumptions

- 首版只做 Windows 桌面小团队内测。
- 腾讯云账号、AppID、SecretID、SecretKey 由部署方提供。
- 签名服务部署在团队可访问的网络内。
- 用户主要使用中文普通话，少量中英混输可接受。
- 方言、离线识别、真正系统 IME、历史记录和商业化能力放到后续版本。

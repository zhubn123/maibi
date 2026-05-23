# 麦笔 Agents 工作指南

本文件面向在本仓库中工作的 coding agent。实现前先阅读 `docs/PLAN.md`、`docs/PR_GUIDELINES.md` 和 `docs/STATUS.md`，并以其中的产品边界、技术方案、项目进度和 PR 约束为准。

## 项目目标

麦笔 / Maibi 是一款面向 Windows 10/11 桌面的中文语音输入工具。首版服务小团队内测用户，核心形态是系统托盘应用、录音浮窗预览和设置页。

首版不实现 Windows 系统 IME，不做移动端、浏览器扩展、账号支付、公开分发、离线识别、历史记录或产品分析采样。

## 核心交互

- 默认全局快捷键为 `Ctrl+Alt+Space`。
- 按住快捷键开始录音，松开后等待最终识别并上屏。
- 浮窗展示中间结果、稳定结果、最终结果和错误状态。
- `Esc` 取消本次输入，不写入文本。
- `Enter` 提前确认当前稳定文本并上屏。
- 默认采用“预览确认后上屏”，不要实现边说边自动插入。
- 首版上屏方式为剪贴板粘贴：临时写入识别文本，发送 `Ctrl+V`，随后尽量恢复原 Unicode 文本剪贴板。
- 剪贴板或输入注入失败时，保留浮窗文本，并提供手动复制入口。

## 目录约定

按以下目录组织代码；如果目录尚不存在，按需创建。

- `client/`：Windows 桌面客户端，负责托盘、浮窗、录音、快捷键、配置和文本上屏。
- `server/`：轻量 FastAPI 签名服务，负责生成短期 ASR 会话参数。
- `core/`：客户端与服务端共享的 ASR、音频、配置、文本提交接口和工具。
- `docs/`：产品、设计、部署、评审和验收文档。
- `tests/`：测试代码；也可以按项目既有模式放在各模块内部。

不要把云厂商 Secret、真实签名 URL、音频样本、转写文本历史或个人数据提交到仓库。

## 技术栈

首版默认使用：

- Python 3.11+
- PySide6
- sounddevice
- websockets
- pywin32
- FastAPI + uvicorn
- pydantic
- pytest

引入第三方依赖时，必须同步更新 README 或相关依赖说明文档，并在 PR 描述中说明依赖、版本和用途。

## 架构边界

`core` 中应定义供应商无关的抽象接口和数据模型。腾讯云实时语音识别只是首个 Provider 实现，不能把腾讯云字段泄露到通用接口之外。

推荐核心接口形态：

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

推荐事件字段：

```python
class AsrEvent:
    type: str
    text: str
    stable: bool
    final: bool
    latency_ms: int | None
    error_code: str | None
```

## 服务端要求

签名服务提供最小 API：

- `POST /v1/asr/session`
- `GET /healthz`

服务端必须遵守：

- 腾讯云 `SecretId`、`SecretKey`、`AppId` 只通过服务端环境变量配置。
- 客户端不得保存云厂商 Secret。
- 签名 URL 必须短期有效。
- 按设备或客户端 ID 做每日分钟数限流。
- 日志不得记录完整签名 URL、音频、转写文本或热词明文。

## 腾讯云 ASR 默认值

首版默认实现腾讯云实时 ASR WebSocket，默认参数参考 `docs/PLAN.md`：

- 16kHz、16-bit、mono、PCM
- 每 200ms 发送一帧
- `engine_model_type=16k_zh`
- `voice_format=1`
- `needvad=1`
- `vad_silence_time=1000`
- `convert_num_mode=1`
- `filter_modal=1`
- 保留标点

热词支持常用人名、公司名、产品名和专业词。热词校验必须拒绝空字符串、空格和超长词；单次最多 128 个热词，默认权重为 8。

## 隐私与成本控制

实现时默认保护用户内容：

- 不保存音频文件。
- 不保存转写文本历史。
- 不上传产品分析采样。
- 客户端只保存设置、热词和非内容类诊断信息。
- 服务端日志只记录请求时间、匿名设备标识、时长、供应商、错误码和延迟指标。

成本控制要求：

- 客户端默认每日语音上限 60 分钟。
- 用量达到 80% 时提示。
- 达到上限后当天阻止继续录音。
- 服务端也必须做每日分钟数限制。

## 测试要求

新增或修改功能时，按风险补充测试。优先覆盖：

- ASR 事件解析。
- 腾讯云签名参数生成。
- 热词校验。
- 配置读写。
- 文本后处理。
- 用量上限逻辑。
- Mock WebSocket ASR 下的 200ms 音频分片。
- 中间结果、稳定结果、最终结果事件流。
- 断网、超时、服务端错误和用户取消。
- 签名服务不泄露 Secret 和完整签名 URL。

客户端相关变更需要尽量在 Windows 10/11 上手工验证 Notepad、Word、Chrome 输入框、微信和企业微信等目标应用。

## 开发约束

- 保持每次变更范围小，一个 PR 只做一件事。
- 不做无关重构，不引入与首版目标无关的能力。
- 修改既有行为前，先确认是否影响 `docs/PLAN.md` 中的关键交互。
- 新代码优先放入清晰的模块边界，不把 UI、ASR、配置、用量统计和文本提交逻辑混在一起。
- 需要 mock 外部服务时，优先使用本地 mock WebSocket 或测试替身，避免测试依赖真实云服务。
- 不在日志、异常、测试快照或 fixture 中写入真实 Secret、完整签名 URL、音频或用户转写文本。

## 多 Agent 协作规范

多 Agent 并行执行时，主 Agent / 主线程负责拆分任务、分配文件范围、集成结果和最终验证。子 Agent 只处理自己负责的文件或模块，不修改其他 Agent 的工作范围。

子 Agent 默认不运行全量编译、全量测试、开发服务器或打包命令，避免重复安装依赖、重复启动服务、重复占用端口或重复访问云服务。子 Agent 可以执行轻量静态检查或局部测试，但必须在结果中说明执行过什么、覆盖了什么范围。

是否执行全量构建、全量测试、启动客户端或启动服务端，由主 Agent / 主线程根据变更范围统一判断和安排。除非任务明确要求，子 Agent 不应自行做最终验证。

## PR 规范

所有新功能必须通过 Pull Request 提交。PR 标题用一句话说明新增或修改内容。PR 描述必须包含：

- 功能描述
- 实现思路
- 测试方式
- 依赖说明
- 原创性说明

不得合并空描述 PR、描述与代码严重不符的 PR、包含多个无关功能的 PR、遗漏依赖说明的 PR，或合并后主分支无法启动和复现演示效果的 PR。

推荐拆分顺序参考 `docs/PR_GUIDELINES.md`，优先从项目骨架、README、共享核心接口、签名服务最小 API 和 mock ASR 集成测试开始。推进进度必须同步更新 `docs/STATUS.md`。

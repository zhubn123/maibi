# 项目进度

最后更新：2026-05-24

## 当前阶段

项目处于首版基础建设阶段。已完成产品计划、协作规范、Python 项目骨架、`core` 共享接口、`server` 最小 FastAPI 服务、Mock ASR 集成测试、客户端 UI 状态模型、PCM 分片骨架、麦克风采集适配层、腾讯云 ASR session 骨架、会话引导层和可体验客户端壳；当前分支已能完成本地签名、真实腾讯云握手和 demo 壳实时语音链路的基础接入。当前主要问题集中在 demo 输入法级交互细节、文本上屏能力、全局快捷键和托盘/浮窗闭环。

## 已完成

- PR #1：[Add project planning docs](https://github.com/zhubn123/maibi/pull/1)
  - 状态：已合并
  - 内容：新增项目计划、PR 规范、Agent 工作指南和 `.gitignore`
- 直接提交：[Add collaboration workflow guidelines](https://github.com/zhubn123/maibi/commit/ff4faa38edcc78ca002664ceaa5bcf1f5af83756)
  - 状态：已进入 `main`
  - 内容：补充多 Agent 协作规范和小改动免 PR 规则
- PR #2：[Add project skeleton](https://github.com/zhubn123/maibi/pull/2)
  - 状态：已合并
  - 内容：新增 `README.md`、`pyproject.toml`、`client/`、`core/`、`server/`、`tests/`、`docs/`
- PR #3：[Add core contracts](https://github.com/zhubn123/maibi/pull/3)
  - 状态：已合并
  - 内容：新增 ASR Provider/Session/Event、配置、热词、用量限制和文本提交接口
- PR #4：[Add server minimal API](https://github.com/zhubn123/maibi/pull/4)
  - 状态：已合并
  - 内容：新增 `GET /healthz` 和 `POST /v1/asr/session` 最小 FastAPI 服务
- PR #5：[Add mock ASR integration tests](https://github.com/zhubn123/maibi/pull/5)
  - 状态：已合并
  - 内容：新增 Mock ASR 集成测试，验证 200ms 音频分片、事件流和 finish/cancel 语义
- PR #6：[Add client UI state model](https://github.com/zhubn123/maibi/pull/6)
  - 状态：已合并
  - 内容：新增客户端托盘/浮窗基础状态模型和交互意图测试
- PR #7：[Add PCM audio framing](https://github.com/zhubn123/maibi/pull/7)
  - 状态：已合并
  - 内容：新增 PCM 音频格式、200ms 分片器和纯字节流测试
- PR #8：[Add microphone capture pipeline](https://github.com/zhubn123/maibi/pull/8)
  - 状态：已合并
  - 内容：新增客户端音频采集管线、sounddevice 配置骨架和 fake source 测试
- PR #10：[Add demo client shell](https://github.com/zhubn123/maibi/pull/10)
  - 状态：已合并
  - 内容：新增可体验的 PySide6 托盘/浮窗模拟入口
- PR #11：[Add Tencent ASR session skeleton](https://github.com/zhubn123/maibi/pull/11)
  - 状态：已合并
  - 内容：新增腾讯云实时 ASR WebSocket 签名 URL、session 骨架、transport dialer、事件解析和 session runner 测试
- PR #12：[Add session bootstrap client](https://github.com/zhubn123/maibi/pull/12)
  - 状态：已合并
  - 内容：新增客户端会话引导层，服务端返回真实腾讯云签名 URL，并把签名配置统一收进本地配置文件
- PR #9：[Add Tencent ASR signer](https://github.com/zhubn123/maibi/pull/9)
  - 状态：未合并，已被 PR #11 覆盖
  - 内容：历史签名分支，后续可关闭，不应继续作为主线
- 本地提交：`Fix Tencent signed session parameters`
  - 状态：已提交
  - 内容：修正腾讯云签名 URL 的 `voice_id` 参数、签名字符串拼接和 UTC 时间兼容，并补充对应测试
- 本地提交：`Refine demo recording interaction`
  - 状态：已提交
  - 内容：demo 壳改为按住说话、松开结束，发送/接收并发处理，并覆盖 partial/stable/final 事件顺序测试
- 本地提交：`Stream demo audio in real time`
  - 状态：已提交
  - 内容：`client/session_runner.py` 改为 WebSocket session 建立后再消费音频源，音频帧产出后立即发送，同时并发接收 ASR 事件；demo worker 在录音结束后进入 processing 状态

## 进行中

- Demo 壳交互与流式模型收口
  - 状态：开发中
  - 内容：当前分支 `codex/demo-client-shell` 正在收口真实语音链路。`client/demo_app.py` 已改为按住说话/松开结束，`client/session_runner.py` 已改为连接后边采集、边发送、边接收。后续还需要继续打磨实时 partial/stable 展示、错误保留文本、取消和清除语义。

## 下一步

1. 继续打磨 `client/demo_app.py` 的输入法级交互：实时 partial/stable 展示、错误保留文本、清除只重置状态不隐藏窗口。
2. 完成后再做 `PR #13`：文本上屏能力。
3. 之后再补全全局快捷键、托盘交互和浮窗闭环。

## 执行规则

- 功能代码、接口、依赖、配置和运行行为变更走 PR。
- 文档小修、状态更新、错别字和说明性规范更新可以直接提交到 `main`。
- 多 Agent 并行时，子 Agent 不默认运行全量编译、全量测试、服务或打包命令；最终验证由主 Agent / 主线程统一判断。

## 文档位置

- `README.md`：仓库入口和开发入口。
- `agents.md`：Agent 工作指南，保留在根目录便于工具自动发现。
- `docs/README.md`：文档索引。
- `docs/PLAN.md`：产品与技术计划。
- `docs/PR_GUIDELINES.md`：PR 提交规范。
- `docs/STATUS.md`：项目进度。

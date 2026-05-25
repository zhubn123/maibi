# 麦笔 / Maibi

麦笔是面向 Windows 10/11 桌面的中文语音输入工具。首版采用系统托盘应用、浮窗预览和轻量签名服务，不注册为 Windows 系统 IME。

当前分支的重点是可演示 demo 壳：
- 本地签名服务生成腾讯云实时 ASR 短期 `websocket_url`
- demo 壳走真实 `sounddevice + websockets` 语音链路
- 支持全局热键 `Ctrl+Alt+Space` 按住录音、松开结束
- 支持浮窗预览、`Esc` 取消、`Enter` 确认、剪贴板粘贴上屏

自动化测试当前通过：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 当前状态

适合现在做的事：
- 本地演示和录制交付视频
- 在 Notepad、Chrome 文本框等简单目标里验证主流程
- 继续收口快捷键、文本上屏和目标应用兼容性

还没有完成的事：
- Word、微信、企业微信等更复杂目标的系统化手工验收
- 设置页、快捷键冲突提示、完整托盘交互
- 首版成本控制、分钟数限制和更完整的部署文档收口

项目边界和进度见 [docs/PLAN.md](D:/code/codex/maibi/docs/PLAN.md) 和 [docs/STATUS.md](D:/code/codex/maibi/docs/STATUS.md)。

## 目录结构

- `client/`：Windows 桌面客户端，负责托盘、浮窗、录音、快捷键、配置和文本上屏
- `server/`：签名服务和后端 API，负责生成短期 ASR 会话参数
- `core/`：客户端与服务端共享的核心类型、接口和工具
- `tests/`：自动化测试
- `docs/`：产品、流程、进度和验收文档

## 环境要求

- Windows 10/11
- Python 3.11+
- 可用麦克风
- 腾讯云实时 ASR 对应的 `AppId`、`SecretId`、`SecretKey`

客户端文本上屏依赖 `pywin32`，真实采音依赖 `sounddevice`。

建议使用虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## 本地配置

腾讯云服务端配置文件：

- 示例文件：`server/config.example.json`
- 本地真实配置：`server/config.local.json`

`server/config.local.json` 已被 `.gitignore` 忽略，不应提交到仓库。

示例结构：

```json
{
  "tencent_asr": {
    "appid": "123456",
    "secret_id": "AKID...",
    "secret_key": "...",
    "session_ttl_seconds": 300
  }
}
```

## 启动方式

先启动签名服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn server.app:app --reload
```

再启动 demo 壳：

```powershell
.\.venv\Scripts\python.exe -m client.demo_app
```

## Demo 使用方式

推荐先在 Notepad 或 Chrome 文本框里演示。

主路径：
- 先把光标放到目标输入框
- 按住 `Ctrl+Alt+Space`
- 浮窗先显示 `正在连接，请等待提示后再说`
- 浮窗变成 `可以开始说话` 后开始说话
- 松开快捷键后等待识别结束
- 有稳定或最终文本后，按 `Enter` 上屏

辅助操作：
- `Esc`：取消本次输入，不上屏
- “按住说话”：仅作为 demo 辅助入口
- “确认上屏”：等价于 `Enter`
- “复制”：只复制浮窗里的预览文本
- “清除”：清空当前浮窗状态

当前实现不是边说边写入。默认是“预览确认后上屏”。

## 运行日志

demo 默认会输出控制台日志，主要用于排查热键和 ASR 链路：

- `demo hotkey action=...`
- `demo start recording generation=...`
- `demo capture ready generation=...`
- `session worker failed`
- `asr stream completed ...`

排查热键时，重点看：
- `client.hotkey`：低级键盘 hook 是否产出 action
- `client.demo_app`：action 是否回到 GUI 主线程并触发 `_start_recording()`

如果看到 `demo start recording`，但一直没有 `demo capture ready`，问题通常不在热键本身，而在本地签名服务、腾讯云握手或麦克风启动。

## 已知边界

- 在看到 `可以开始说话` 之前讲话，不保证会被识别
- 目标应用兼容性还在继续收口，当前最稳的是 Notepad 和普通网页输入框
- 剪贴板粘贴上屏依赖目标窗口焦点恢复，复杂应用仍需继续手工验证

## 常用命令

运行全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

只跑服务端测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_server_app.py
```

只跑 demo 和热键相关测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_demo_app_import.py tests\test_hotkey.py
```

## 文档入口

- [docs/README.md](D:/code/codex/maibi/docs/README.md)：文档索引
- [docs/PLAN.md](D:/code/codex/maibi/docs/PLAN.md)：产品与技术计划
- [docs/PR_GUIDELINES.md](D:/code/codex/maibi/docs/PR_GUIDELINES.md)：PR 提交规范
- [docs/STATUS.md](D:/code/codex/maibi/docs/STATUS.md)：项目进度
- [agents.md](D:/code/codex/maibi/agents.md)：Agent 工作指南

## 开发约束

- 文档小修、错别字和说明性规范更新可以直接提交到 `main`
- 功能代码、依赖、接口、配置和可运行行为变更必须通过 Pull Request
- 每个 PR 只做一件事，并在合并后保持主分支可运行
- 多 Agent 并行开发时，主 Agent / 主线程负责最终构建、测试和运行验证


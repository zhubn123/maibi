# 麦笔 / Maibi

麦笔是面向 Windows 10/11 桌面的中文语音输入工具。当前仓库的可用形态是一个可演示的 demo 壳：

- 本地 FastAPI 签名服务生成腾讯云实时 ASR 短期 `websocket_url`
- Windows 客户端 demo 壳走真实 `sounddevice + websockets` 语音链路
- 支持浮窗预览、按钮取消、按钮确认和剪贴板粘贴上屏

## 运行
双击start_maibi.cmd文件，会自动安装运行

当前自动化测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## 1. 先把环境收干净

仓库里不需要保留的运行产物主要是：

- `.pytest_cache/`
- `*.egg-info/`

通常不需要手动删；它们都已经被 `.gitignore` 忽略。

如果你想手动清理：

```powershell
Remove-Item -Recurse -Force maibi.egg-info
Remove-Item -Recurse -Force .pytest_cache
```

如果 `.pytest_cache` 报权限占用，直接忽略即可，不影响启动和演示。

## 2. 环境要求

- Windows 10/11
- Python 3.11+
- 可用麦克风
- 腾讯云实时 ASR 对应的 `AppId`、`SecretId`、`SecretKey`

依赖说明：

- `PySide6`：浮窗和托盘
- `sounddevice`：麦克风采音
- `websockets`：腾讯云实时 WebSocket ASR
- `pywin32`：剪贴板和文本上屏
- `fastapi + uvicorn`：本地签名服务

## 3. 安装

普通使用直接双击或在 PowerShell 里运行：

```powershell
.\start_maibi.cmd
```

它会自动创建 `.venv`、安装依赖、检查 `server/config.local.json`、启动本地签名服务并打开客户端。

如果 `server/config.local.json` 不存在，先复制示例配置并填入腾讯云实时 ASR 凭据：

```powershell
Copy-Item server\config.example.json server\config.local.json
notepad server\config.local.json
```

开发或手工排障时，可以手动创建虚拟环境。先确认当前终端没有激活其他项目的虚拟环境；如果提示符前面已有别的 `(.venv)`，先执行：

```powershell
deactivate
```

先检查 `python` 指向的版本和路径：

```powershell
python --version
where.exe python
```

要求是 Python 3.11+，并且不要指向其他项目的 `.venv\Scripts\python.exe`。如果版本低于 3.11，或路径来自其他项目虚拟环境，先安装/切换到 Python 3.11+ 后再继续。

创建并安装本项目环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -e ".[dev]"
```

如果你的电脑安装了 Windows Python Launcher，也可以用它明确选择 3.11+：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -e ".[dev]"
```

必须看到最后出现 `Successfully installed ... uvicorn ... PySide6 ...` 后再启动服务端或客户端。只要安装过程中出现 `ERROR`，就不要继续启动；先重新执行安装命令。否则会出现 `No module named uvicorn` 或 `No module named PySide6`。

`maibi.egg-info` 可以删除；重新安装后不一定生成同名目录，editable install 可能只在 `.venv\Lib\site-packages` 下生成 `maibi-0.1.0.dist-info` 和 `.pth` 文件。

如果想确认 `.venv` 是用正确解释器创建的：

```powershell
.\.venv\Scripts\python.exe -c "import sys; print(sys.executable); print(sys.version)"
```

输出应包含本仓库下的 `.venv\Scripts\python.exe` 和 Python `3.11+`。如果 `.venv\pyvenv.cfg` 里 `command = ...` 指向其他项目目录，删除 `.venv` 后按上面的版本检查和创建命令重建。

如果只想分别安装客户端或服务端依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -e ".[client]"
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -e ".[server]"
```

安装完成后，不要用 `import maibi` 验证。这个仓库暴露的是 `client`、`core`、`server` 这些包，不是 `maibi` 这个 import 名。

可以这样验证：

```powershell
.\.venv\Scripts\python.exe -c "import PySide6, uvicorn, client.demo_app, server.app; print('ok')"
```

如果 `client.demo_app` 启动时报 `ImportError: DLL load failed while importing win32api`，说明 `pywin32` 的 post-install 没跑完，执行：

```powershell
.\.venv\Scripts\python.exe .\.venv\Scripts\pywin32_postinstall.py -install
```

## 4. 配置腾讯云

创建本地配置文件：

- 示例文件：`server/config.example.json`
- 实际文件：`server/config.local.json`

`server/config.local.json` 已被 `.gitignore` 忽略，不应提交。

示例内容：

```json
{
  "tencent_asr": {
    "appid": "1234567890",
    "secret_id": "your-secret-id",
    "secret_key": "your-secret-key",
    "session_ttl_seconds": 300
  }
}
```

## 5. 启动

推荐直接使用一键启动：

```powershell
.\start_maibi.cmd
```

如果需要分开调试，先启动本地签名服务：

```powershell
.\.venv\Scripts\python.exe -m uvicorn server.app:app --reload
```

服务正常后会提供：

- `GET /healthz`
- `POST /v1/asr/session`

再启动客户端 demo 壳：

```powershell
.\.venv\Scripts\python.exe -m client.demo_app
```

## 6. 用户如何使用

完整使用流程：

1. 先启动本地签名服务。
2. 再启动 demo 壳。
3. 把输入光标放到目标输入框里。
4. 点击“按住说话”。
5. 开始讲话。
6. 松开按钮后等待识别结果。
7. 识别结束后点击“确认上屏”。

辅助操作：

- “取消”：取消本次输入，不上屏
- “确认上屏”：提交当前预览文本
- “复制”：只复制浮窗里的文本
- “清除”：清空当前浮窗状态

当前默认行为不是边说边写，而是“预览确认后上屏”。

TODO:
- 全局快捷键 `Ctrl+Alt+Space` 暂时停用，后续修复后再恢复

## 7. 你需要注意的地方

- 当前最稳的目标应用是 Notepad 和普通网页输入框
- 复杂应用的剪贴板恢复和焦点恢复还在继续手工验收
- 如果文本上屏失败，浮窗文本会保留，你可以手动复制
- 腾讯云实时 ASR 可能有试用或免费额度；是否可用、如何抵扣以腾讯云控制台和实际计费规则为准。

## 8. 常用排查方法

demo 默认会输出控制台日志。

排查按钮路径时重点看：

- `demo start recording generation=...`
- `demo capture ready generation=...`
- `session worker failed`

判断方式：

- 如果有 `demo start recording`，但一直没有 `demo capture ready`，问题通常在本地签名服务、腾讯云握手或麦克风启动
- 如果已经有识别结果但最后失败，优先看 `session worker failed`

## 9. 测试

运行全量测试：

```powershell
.\.venv\Scripts\python.exe -m pytest
```

只跑服务端测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_server_app.py
```

只跑 demo 相关测试：

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_demo_app_import.py
```

## 10. 仓库结构

- `client/`：Windows 客户端
- `server/`：签名服务
- `core/`：共享接口和模型
- `tests/`：自动化测试
- `docs/`：计划、PR 规范、进度文档

## 11. 相关文档

- [docs/README.md](D:/code/codex/maibi/docs/README.md)
- [docs/PLAN.md](D:/code/codex/maibi/docs/PLAN.md)
- [docs/PR_GUIDELINES.md](D:/code/codex/maibi/docs/PR_GUIDELINES.md)
- [docs/STATUS.md](D:/code/codex/maibi/docs/STATUS.md)
- [agents.md](D:/code/codex/maibi/agents.md)

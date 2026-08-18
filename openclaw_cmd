## 1. OpenClaw 基本指令

```sh
# 查看 OpenClaw 版本
openclaw --version

# 查看說明
openclaw --help

# 查看目前 OpenClaw 狀態
openclaw status

# 查看 Gateway 狀態
openclaw gateway status

# 啟動 Gateway
openclaw gateway start

# 停止 Gateway
openclaw gateway stop

# 重啟 Gateway
openclaw gateway restart
```

2. Agent / 工作區

```sh
# 查看 Agent
openclaw agent --help

# 查看目前設定
openclaw config

# 查看工作區
openclaw workspace

# 初始化工作區
openclaw init
```

如果你的目的是讓 Agent 在目前資料夾操作：

```sh
cd C:\Users\Len\Desktop\openClaw_Test
openclaw
```

3. 常用診斷

你前面遇到的 WorkspaceVanishedError，建議先跑：

```sh
openclaw status

openclaw gateway status

Get-Command openclaw | Format-List *

Get-ChildItem "$env:USERPROFILE\.openclaw"

Get-ChildItem "$env:USERPROFILE\.openclaw\workspace-attestations"
```

確認目前 OpenClaw 實際使用哪個工作區：

```sh
Get-Location

Get-ChildItem C:\Users\Len\Desktop\openClaw_Test
```

4. Ollama 相關

```sh
# Ollama 版本
ollama --version

# 查看目前模型
ollama list

# 查看正在執行的模型
ollama ps

# 測試模型
ollama run qwen2.5-coder:7b

# 移除模型
ollama rm qwen2.5-coder:7b

# 查看 Ollama API
curl http://localhost:11434/api/tags
```

確認 Ollama 是否正常：

```sh
Test-NetConnection localhost -Port 11434
```

如果正常應看到：

```sh
TcpTestSucceeded : True
```

5. OpenClaw + Ollama 測試

先確認 Ollama：

```sh
ollama list
```

例如：

```sh
qwen2.5-coder:7b
```

然後：

```sh
ollama run qwen2.5-coder:7b
```

確認模型能正常回答後，再啟動 OpenClaw：

```sh
cd C:\Users\Len\Desktop\openClaw_Test
openclaw
```

以及針對子命令：

```sh
openclaw gateway --help

openclaw agent --help

openclaw config --help
```

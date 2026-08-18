# OpenClaw + Ollama Windows 部署 SOP

架構

```
┌──────────────────────────────────────────┐
│              Windows 11                  │
│                                          │
│  ┌───────────────┐                       │
│  │   OpenClaw    │                       │
│  │ Agent/Gateway │                       │
│  └───────┬───────┘                       │
│          │                               │
│          │ Native Ollama API             │
│          ▼                               │
│  http://127.0.0.1:11434                  │
│          │                               │
│  ┌───────▼────────┐                      │
│  │    Ollama      │                      │
│  │ Qwen3.5 9B     │                      │
│  └───────┬────────┘                      │
│          │                               │
│       RTX 3060 12GB                      │
│                                          │
│  ┌───────────────────────────────────┐   │
│  │ Your Project                      │   │
│  │ C# / .NET / Python / Vue / Node   │   │
│  │ Git / PowerShell / Docker         │   │
│  └───────────────────────────────────┘   │
└──────────────────────────────────────────┘
```

---

## 1. 確認 NVIDIA GPU

PowerShell：

```sh
nvidia-smi
```

確認有看到：

```sh
NVIDIA GeForce RTX 3060
```

以及：

```sh
Driver Version
CUDA Version
```

---

## 2. 安裝 Ollama

官方 Windows 版本可以直接安裝，而且不需要 Administrator；Ollama Windows 會在背景執行並提供：

```sh
http://localhost:11434
```

API。

Ollama Windows 官方安裝頁

安裝完成後重新開 PowerShell。

確認：

```sh
ollama --version
```

---

## 3. 測試 Ollama

```sh
ollama list
```

然後：

```sh
curl http://localhost:11434/api/tags
```

如果正常，會看到 JSON。

再測：

```sh
ollama run qwen3.5:9b
```

輸入：

```sh
你好，請介紹你自己
```

正常回答就代表 Ollama OK。

---

## 4. 建議把模型放到其他磁碟

如果你的 C 槽空間不大，建議例如：

```sh
D:\Ollama\Models
```

PowerShell：

```sh
[Environment]::SetEnvironmentVariable(
    "OLLAMA_MODELS",
    "D:\Ollama\Models",
    "User"
)
```

然後重新啟動 Ollama。

官方文件也支援透過 OLLAMA_MODELS 改變模型儲存位置。

確認：

```sh
[Environment]::GetEnvironmentVariable("OLLAMA_MODELS","User")
```

應該：

```sh
D:\Ollama\Models
```

---

## 5. 安裝 OpenClaw

官方目前 Windows PowerShell 安裝方式：

```sh
iwr -useb https://openclaw.ai/install.ps1 | iex
```

OpenClaw 安裝程式會處理 Node.js 與 OpenClaw 安裝。官方目前要求支援的 Node 版本為 22.22.3+、24.15+ 或 25.9+。

OpenClaw 官方安裝文件

安裝完成：

```sh
openclaw --version
```

---

## 6. 執行 Doctor

```sh
openclaw doctor
```

如果沒有重大錯誤，就繼續。

---

## 7. 讓 OpenClaw 連接 Ollama

這裡是整個架構最重要的地方。

先確認 Ollama：

```sh
ollama list
```

例如：

```sh
NAME
qwen3.5:9b
```

然後：

```sh
$env:OLLAMA_API_KEY="ollama-local"
```

接著：

```sh
openclaw models list --provider ollama
```

官方文件明確支援 local Ollama，local host 可以使用 ollama-local 標記，不需要真的 API Key。

---

## 8. 設定 Qwen3.5 9B

```sh
openclaw models set ollama/qwen3.5:9b
```

確認：

```sh
openclaw models list --provider ollama
```

應該可以看到：

```sh
ollama/qwen3.5:9b
```

---

## 9. 最簡單方式：直接 Onboarding

如果你想一次設定：

```sh
openclaw onboard
```

選：

```sh
Ollama
```

再選：

```sh
Local only
```

然後選：

```sh
qwen3.5:9b
```

OpenClaw 官方目前的 onboarding 就支援 Ollama 的 Cloud + Local / Cloud only / Local only 三種模式。

---

## 10. 安裝 Gateway

你的目標是把 OpenClaw 當成 Claude Code 長駐 Agent，因此建議安裝 Gateway：

```sh
openclaw gateway install
```

確認：

```sh
openclaw gateway status --json
```

如果正常，Gateway 就會在 Windows 背景啟動。

官方 Windows 目前會優先使用 Windows Scheduled Task 方式維持 Gateway；如果建立排程被拒絕，才會退回使用 Startup。

---

## 11. 啟動 OpenClaw

```sh
openclaw gateway run
```

如果 Gateway 已經透過 install 啟動，可以使用：

```sh
openclaw gateway status
```

---

## 12. 測試 Agent

先建立測試專案：

```sh
mkdir C:\AIProjects\OpenClawTest
cd C:\AIProjects\OpenClawTest
```

建立 Git：

```sh
git init
```

然後啟動 OpenClaw。

讓它執行：

```sh
建立一個 ASP.NET Core Web API 專案，
使用 .NET 10，
加入 Swagger，
建立 Todo CRUD API，
使用 Entity Framework Core，
然後執行 dotnet build。
```

你要觀察的不是「它會不會回答」，而是：

```sh
Agent
 ↓
分析需求
 ↓
建立檔案
 ↓
修改程式
 ↓
執行 PowerShell
 ↓
dotnet build
 ↓
讀取錯誤
 ↓
修改
 ↓
再次 build
 ↓
完成
```

這才是 Claude Code / Codex 類 Coding Agent 的核心。

---

## 13. 特別注意 Tool Calling

這裡是你之前 Hermes + Ollama 遇到問題的重點。

OpenClaw 官方明確說：

❌ 不要

```sh
http://localhost:11434/v1
```

✅ 要

```sh
http://localhost:11434
```

而且 API：

```sh
api: "ollama"
```

OpenClaw 使用 Ollama 原生 /api/chat，不是 OpenAI compatibility /v1。官方特別警告 /v1 可能造成 Tool Calling 失效，甚至讓模型把工具 JSON 當成普通文字輸出。

---

## 14. 如果自動偵測失敗

可以手動設定。

概念配置：

```sh
{
  "models": {
    "providers": {
      "ollama": {
        "baseUrl": "http://localhost:11434",
        "apiKey": "ollama-local",
        "api": "ollama",
        "timeoutSeconds": 300,
        "models": [
          {
            "id": "qwen3.5:9b",
            "name": "qwen3.5:9b",
            "reasoning": true,
            "input": [
              "text",
              "image"
            ]
          }
        ]
      }
    }
  },
  "agents": {
    "defaults": {
      "model": {
        "primary": "ollama/qwen3.5:9b"
      }
    }
  }
}
```

官方目前的 Ollama provider 配置也是使用 baseUrl、api: "ollama" 和 ollama-local。

---

## 15. RTX 3060 12GB 最佳設定

我不建議你一開始追求超大模型。

你的硬體：

```sh
RTX 3060
12GB VRAM
```

我會這樣配：

```sh
OpenClaw
   │
   ▼
Ollama
   │
   ├── qwen3.5:9b      ← Coding Agent 主力
   │
   └── qwen3.5:4b      ← 快速/簡單任務

Qwen3.5 9B 在 Ollama 上目前約 6.6GB，對 12GB VRAM 比較合理。
```

---

## 16. 不建議 RTX 3060 跑 Qwen3-Coder 30B

這點很重要。

目前：

```sh
qwen3-coder:30b
```

Ollama 顯示約：

```sh
19GB
```

Q4_K_M，30.5B parameters。

你的 VRAM：

```sh
12GB
```

所以：

```sh
19GB model
-
12GB VRAM
=
至少 7GB 要放 RAM
```

可以跑，但會進入 CPU/GPU 混合，速度和 Agent 體驗會明顯下降。

所以你的機器我反而推薦：

Qwen3.5 9B > Qwen3-Coder 30B

---

## 17. 如果要更強：Cloud + Local

你可以做成：

```sh
                OpenClaw
                    │
          ┌─────────┴─────────┐
          ▼                   ▼
      Ollama Local       Ollama Cloud
          │                   │
    Qwen3.5 9B          大型 Coding Model
          │                   │
       RTX3060             Cloud GPU
```

平常：

```sh
Local
```

遇到：

```sh
大型專案
複雜 Refactor
大量程式碼分析
大型 context
```

再切：

```sh
Cloud
```

OpenClaw 官方目前也支援 Ollama Cloud + Local 混合模式。

---

## 18. 最終「取代 Claude Code」架構

我會建議你最後做成：

```sh
                 Windows 11
                     │
                     ▼
              ┌─────────────┐
              │   OpenClaw  │
              │    Agent    │
              └──────┬──────┘
                     │
        ┌────────────┼────────────┐
        │            │            │
        ▼            ▼            ▼
     Ollama        Tools         Git
        │            │            │
        ▼            ▼            ▼
 Qwen3.5 9B      PowerShell   GitHub/GitLab
                 Python
                 Node
                 npm/pnpm
                 dotnet
                 Docker
                 SQL
                 Files
                     │
                     ▼
              Your Projects
```

這個模式基本上就是：

```sh
Claude Code
    ↓
OpenClaw

Claude
    ↓
Ollama / Qwen

Claude Tools
    ↓
OpenClaw Tools

Claude Code Terminal
    ↓
PowerShell

Claude Code Project
    ↓
你的 Windows Project
```

---

## 19. 我建議你的實際版本

依照你前面使用 Hermes Agent + Ollama 的經驗，我會直接放棄「一直修 Hermes Tool Calling」這條路，改成：

第一階段

```sh
Windows 11
    +
Ollama
    +
Qwen3.5:9b
    +
OpenClaw
```

第二階段

加入：

```sh
Git
GitHub / GitLab
Docker
.NET
Python
Node.js
VS Code
```

第三階段

做：

```sh
OpenClaw
    │
    ├── Coding Agent
    ├── Git Agent
    ├── Test Agent
    ├── Docker Agent
    ├── SQL Agent
    └── Documentation Agent
```

最後就會變成一套你自己的：

「本機 Claude Code / Codex 替代方案」

而且 OpenClaw 本身目前甚至已經在 Ollama 官方模型頁被列為可直接搭配的 Agent 應用。

# OpenClaw 執行指令

重啟 OpenClaw

```sh
openclaw gateway restart
```

如果 restart 不支援：

```sh
openclaw gateway stop
openclaw gateway start
```

再：

```sh
openclaw tui - ws://127.0.0.1:18789 - agent main - session main
```

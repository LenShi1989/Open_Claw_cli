# openclaw + telegram 系統

## 架構

```sh
Telegram 手機 / Desktop
        │
        ▼
 Telegram Bot
        │
        │ Bot Token
        ▼
 OpenClaw Gateway :18789
        │
        ▼
 OpenClaw Agent
        │
        ▼
 Ollama
 ├─ qwen3.5:9b
 ├─ qwen3:30b
 └─ gemma4
```

### 1. 建立 Telegram Bot

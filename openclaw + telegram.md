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

## 1. 建立 Telegram Bot

在 Telegram 搜尋：

@BotFather

輸入：

```sh
/newbot
```

接著輸入 Bot 名稱，例如：

```sh
My OpenClaw Agent
```

再設定 username，例如：

```sh
my_openclaw_agent_bot
```

最後 BotFather 會給你：

```sh
1234567890:AAxxxxxxxxxxxxxxxxxxxxxxxx
```

這就是 Bot Token。

---

## 2. 設定 OpenClaw

你目前 OpenClaw 是 Windows，因此設定檔通常是：

```sh
$env:USERPROFILE\.openclaw\openclaw.json
```

也就是：

```sh
C:\Users\admin\.openclaw\openclaw.json
```

先備份：

```sh
Copy-Item "$env:USERPROFILE\.openclaw\openclaw.json" `
          "$env:USERPROFILE\.openclaw\openclaw.json.bak"
```

然後把 Telegram channel 加進去。

最基本：

```sh
{
  "channels": {
    "telegram": {
      "enabled": true,
      "botToken": "你的_BOT_TOKEN",
      "dmPolicy": "pairing"
    }
  }
}
```

官方目前就是使用 `channels.telegram.botToken` + `dmPolicy` 這種設定方式。

---

## 3. 我更推薦你的設定

因為你是拿 OpenClaw 當 Coding Agent 使用，我建議先不要開放給所有 Telegram 使用者。

設定成：

```sh
{
  "channels": {
    "telegram": {
      "enabled": true,
      "botToken": "你的_BOT_TOKEN",

      "dmPolicy": "pairing",

      "groups": {
        "*": {
          "requireMention": true
        }
      },

      "historyLimit": 50,

      "streaming": {
        "mode": "partial"
      },

      "actions": {
        "reactions": true,
        "sendMessage": true
      }
    }
  }
}
```

這樣：

- 私訊 → 必須 pairing
- 群組 → 預設需要 @Bot
- 保留最近 50 筆歷史
- 支援 Telegram 回覆串流
- 支援 reaction / sendMessage

這些都是 OpenClaw Telegram channel 的正式設定項目。

---

## 4. 啟動 Gateway

修改完後：

```sh
openclaw gateway restart
```

如果 Gateway 還沒啟動：

```sh
openclaw gateway
```

然後查看：

```sh
openclaw logs --follow
```

你應該會看到 Telegram 啟動相關訊息。

也可以檢查：

```sh
openclaw channels status
```

如果你的版本支援完整 diagnostics，也可以：

```sh
openclaw doctor
```

---

## 5. Telegram 傳訊息給 Bot

現在去 Telegram 找你的 Bot。

例如：

```sh
/start
```

或者直接：

```sh
hello
```

因為我們設定：

```sh
"dmPolicy": "pairing"
```

所以第一次 Telegram 使用者不會直接進入 Agent，而是收到一組 pairing code。這是 OpenClaw 預設的安全機制。

例如：

```sh
Pairing code: ABCD1234
```

---

## 6. 在 Windows 核准 Telegram

在 OpenClaw Gateway 所在的 PowerShell：

```sh
openclaw pairing list telegram
```

應該看到類似：

```sh
Pending pairing requests

Channel: telegram
Code: ABCD1234
User: ...
```

然後：

```sh
openclaw pairing approve telegram ABCD1234
```

官方 CLI 就是這個流程。

再回 Telegram：

```sh
hello
```

這時就應該會變成：

```sh
Telegram
   ↓
OpenClaw
   ↓
你的 Agent
   ↓
Ollama qwen3.5 / qwen3:30b
   ↓
Telegram
```

---

## 7. 如果你要讓 Telegram 控制你的 Coding Agent

這才是我比較推薦你做的方式。

例如你目前 OpenClaw 工作區：

```sh
C:\Users\admin\Documents\1.Gitlab\benton_system
```

可以讓 Telegram：

```sh
你：
檢查目前 benton_system 哪些地方編譯失敗

OpenClaw：
讀取 workspace
↓
執行 git status
↓
pnpm install
↓
pnpm build
↓
分析錯誤
↓
修改程式
↓
重新 build
↓
回 Telegram
```

甚至可以：

```sh
你：
幫我修復目前 frontend 的 TypeScript 錯誤

OpenClaw：

搜尋專案
   ↓
讀取 package.json
   ↓
pnpm install
   ↓
pnpm build
   ↓
分析 TS error
   ↓
修改
   ↓
重新 build
   ↓
git diff
   ↓
回報結果
```

這會比單純把 Telegram 當聊天機器人有用很多。

---

## 8. Telegram 群組也可以

例如建立：

```sh
OpenClaw Dev Team
```

把 Bot 加進去。

OpenClaw 可以針對群組設定：

```sh
"groups": {
  "-1001234567890": {
    "requireMention": true
  }
}
```

然後：

```sh
工程師 A：
@OpenClaw 幫我檢查 API

OpenClaw：
正在分析...
```

Telegram 群組預設有 Privacy Mode，可能看不到所有訊息；如果需要 Bot 接收群組中的所有訊息，可以在 BotFather 用 `/setprivacy` 關閉 Privacy Mode，或者把 Bot 設成群組管理員。修改 Privacy Mode 後，官方建議重新把 Bot 加入群組。

---

## 9. 你的情況我建議的最終配置

你目前已經有：

```sh
Windows 11
    │
    ├── OpenClaw
    │     └── Gateway :18789
    │
    ├── Ollama
    │     ├── qwen3.5:9b
    │     ├── qwen3:30b
    │     └── gemma4
    │
    └── benton_system
```

我會做成：

```sh
                    ┌───────────────┐
                    │    Telegram   │
                    └───────┬───────┘
                            │
                       Bot Token
                            │
                            ▼
                 ┌───────────────────┐
                 │  OpenClaw Gateway │
                 │     :18789        │
                 └─────────┬─────────┘
                           │
                    ┌──────▼──────┐
                    │    Agent    │
                    └──────┬──────┘
                           │
             ┌─────────────┼─────────────┐
             ▼             ▼             ▼
          Coding         Shell         Skills
        Agent            Tools         System
             │             │             │
             └─────────────┼─────────────┘
                           ▼
                     ┌──────────┐
                     │  Ollama  │
                     └──────────┘
                           │
                       RTX 5090

```

這樣 Telegram 就會變成你的 OpenClaw 遠端控制台。

而且你的 OpenClaw 不需要暴露 `18789` 到 Internet；Telegram Bot API 主動向 Telegram 取得訊息即可，官方預設就是 Long Polling。

如果你現在要直接做，我建議下一步先把你目前的 `openclaw.json` 貼出來（Token 請用 `***` 遮掉），我可以直接幫你把 Telegram 配置合併進你現有的 Ollama + workspace + skills 設定，而不是重新寫一份。

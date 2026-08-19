# 1. 臨時分身：Sub-agent ⭐推薦

適合讓主 Agent 同時派幾個小弟出去做不同工作，例如：

```sh
主 Agent
 ├─ 分身 A：研究 OpenCV
 ├─ 分身 B：寫 Python
 ├─ 分身 C：查文件
 └─ 分身 D：測試程式
```

OpenClaw 官方稱為 Sub-agents，每個分身都有自己的 session，完成後會把結果回報給主 Agent。

如果你的 OpenClaw 支援 Slash Command，可以直接：

```sh
/subagents spawn coding 幫我分析目前專案的 Python 程式，找出效能瓶頸
```

也可以查看：

```sh
/subagents list
```

查看某個分身：

```sh
/subagents info 1
```

查看執行紀錄：

```sh
/subagents log 1
```

官方目前也支援：

```sh
/subagents kill 1
```

停止分身。

---

# 2. 永久分身：建立多個 Agent

如果你想要的是：

「我要有一個 Coding Agent、一個 Research Agent、一個管理 Agent，而且每個都有自己的記憶、Workspace、設定。」

這就不是 Sub-agent，而是 Multi-Agent。

例如：

```sh
Main Agent
│
├── coding
│   └── 專門寫程式
│
├── researcher
│   └── 專門查資料
│
└── assistant
    └── 一般助理
```

建立方式：

```sh
openclaw agents add coding
openclaw agents add researcher
openclaw agents add assistant
```

OpenClaw 會為不同 Agent 建立獨立 workspace、`SOUL.md`、`AGENTS.md`、agent directory 和 session store。

然後可以：

```sh
openclaw agents list
```

查看：

```sh
main
coding
researcher
assistant
```

如果你說的「分身」是讓 AI 自己叫其他 AI 幫忙

那你要的是 Sub-agent。

例如你可以叫主 Agent：

幫我把這個專案拆成 3 個工作：

```sh
1. 分身 A 分析 Python 架構
2. 分身 B 分析 Vue 前端
3. 分身 C 找出 Bug

三個一起做，最後你統整結果。
```

OpenClaw 就可以讓它平行執行。預設最多可同時執行的 sub-agent 數量是 `8`，也可以在設定中調整 `maxConcurrent`。

如果你想玩更進階的「分身生分身」

可以設定：

```sh
{
  agents: {
    defaults: {
      subagents: {
        maxSpawnDepth: 2,
        maxChildrenPerAgent: 5,
        maxConcurrent: 8
      }
    }
  }
}
```

變成：

```sh
主 Agent
   │
   ├── 專案經理 Agent
   │       ├── Coding Agent
   │       ├── Test Agent
   │       └── Review Agent
   │
   └── Research Agent
```

`maxSpawnDepth: 2 `就允許第一層分身再建立下一層分身。

如果你是想做你之前提到的 Hermes Agent / OpenClaw + Windows，我可以直接幫你做一套：

「OpenClaw 多分身架構」

包含：

```sh
主控 Agent
├── 💻 Coding 分身
├── 🔍 Research 分身
├── 🧪 Testing 分身
├── 📝 Documentation 分身
└── 🤖 Claude Code / Codex 分身
```

並給你 Windows PowerShell + openclaw.json 完整設定，讓你直接複製貼上就能跑。

# 3. 不同分身可以指定不同 AI 模型。官方文件目前明確支援「Sub-agent 指定模型」以及「每個獨立 Agent 使用不同模型」。

例如你可以這樣配

```sh
┌─ Coding Agent ─── Claude Opus
│
主 Agent ───────────┼─ Research Agent ─ Gemini
│
├─ Fast Agent ───── GPT
│
└─ Local Agent ──── Ollama / Qwen
```

甚至可以做到：

| Agent       | 模型          | 用途                    |
| ----------- | ------------- | ----------------------- |
| 🧠 Main     | Claude Opus   | 負責統籌、決策          |
| 💻 Coding   | Claude Sonnet | 寫程式                  |
| 🔍 Research | Gemini        | 搜尋、整理資料          |
| ⚡ Fast     | GPT           | 快速回答                |
| 🏠 Local    | Qwen / Llama  | 本機模型、降低 API 成本 |

如果是 Sub-agent

可以直接在 spawn 時指定：

```sh
model = "anthropic/claude-sonnet-4-6"
```

例如概念上：

```sh
主 Agent
│
├── Sub-agent A → Claude Sonnet
├── Sub-agent B → Gemini
└── Sub-agent C → GPT
```

OpenClaw 的規則是：

明確指定的 `sessions_spawn.model` > 該 Agent 的 subagent model > 全域設定 > 繼承主 Agent 模型。

所以你甚至可以讓同一次任務：

```sh
主 Agent：Claude Opus

    ↓

Coding：Claude Sonnet
Research：Gemini
快速分析：GPT
```

如果是「永久分身」

這個更適合你。

例如：

```sh
openclaw agents add coding --model anthropic/claude-sonnet-4-6
openclaw agents add research --model google/gemini-2.5-pro
```

每個 Agent 可以有自己的：

- AI Model
- Workspace
- `SOUL.md`
- `AGENTS.md`
- Memory / Session
- Auth
- Persona
- Tool 權限

官方的 Multi-Agent 架構就是讓不同 Agent 成為獨立的 persona / workspace / session。

我反而推薦你這樣設計

如果你是要拿 OpenClaw 做程式開發型 AI 團隊，可以：

```sh
                    OpenClaw
                       │
                🧠 Project Manager
                Claude Opus
                       │
          ┌────────────┼────────────┐
          ↓            ↓            ↓
      💻 Coder      🔍 Research   🧪 Tester
      Claude        Gemini        GPT
      Sonnet
          │            │            │
          └────────────┼────────────┘
                       ↓
                 📝 Reviewer
                 Claude Opus
```

這樣就不是單純「開幾個 ChatGPT」，而是變成一個 AI Agent Team。

而且 OpenClaw 官方也特別建議：主 Agent 使用高品質模型，Sub-agent 使用較便宜的模型處理大量、重複性工作，可以降低 token 成本。

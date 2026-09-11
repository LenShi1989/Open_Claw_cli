# OpenClaw 常用功能指令表

| 指令                     | 功能                            |     重要度 |
| ------------------------ | ------------------------------- | ---------: |
| `openclaw --version`     | 查看 OpenClaw 版本              | ⭐⭐⭐⭐⭐ |
| `openclaw --help`        | 查看所有 CLI 指令               | ⭐⭐⭐⭐⭐ |
| `openclaw status`        | 查看 OpenClaw 整體狀態          | ⭐⭐⭐⭐⭐ |
| `openclaw status --json` | 以 JSON 顯示狀態，適合 Watchdog | ⭐⭐⭐⭐⭐ |
| `openclaw health`        | 健康檢查                        | ⭐⭐⭐⭐⭐ |
| `openclaw doctor`        | 診斷並修復常見問題              | ⭐⭐⭐⭐⭐ |
| `openclaw dashboard`     | 開啟 Web Dashboard              |   ⭐⭐⭐⭐ |
| `openclaw tui`           | 開啟終端機 TUI                  | ⭐⭐⭐⭐⭐ |

| 指令                                                                             | 功能                                   |
| -------------------------------------------------------------------------------- | -------------------------------------- |
| `openclaw config get agents.defaults.workspace`                                  | 查看預設 Workspace                     |
| `openclaw config get agents.entries.main.workspace`                              | 查看 `main` Agent Workspace            |
| `openclaw config get agents.entries`                                             | 查看所有 Agent 設定                    |
| `openclaw config file`                                                           | 查看目前使用的設定檔                   |
| `openclaw config set agents.defaults.workspace "D:\Gitlab\benton_system"`        | 設定預設 Workspace                     |
| `openclaw config set agents.entries.main.workspace "D:\Gitlab\benton_system"`    | **把 main Agent 切換到指定 Workspace** |
| `openclaw config set agents.entries.len.workspace "D:\Gitlab\benton_system\len"` | 把 `len` Agent 切換到指定 Workspace    |
| `openclaw config unset agents.entries.main.workspace`                            | 移除 main 的獨立 Workspace 設定        |
| `openclaw agents list`                                                           | 確認 Agent 與 Workspace                |
| `openclaw gateway restart`                                                       | 修改後重新啟動 Gateway                 |

| 指令                                 | 功能            |
| ------------------------------------ | --------------- |
| `openclaw config`                    | 開啟互動式設定  |
| `openclaw config get <path>`         | 讀取設定        |
| `openclaw config set <path> <value>` | 修改設定        |
| `openclaw config unset <path>`       | 移除設定        |
| `openclaw config patch`              | 批次修改設定    |
| `openclaw config file`               | 顯示設定檔位置  |
| `openclaw config schema`             | 查看設定 Schema |
| `openclaw config validate`           | 驗證設定        |
| `openclaw config validate --json`    | JSON 格式驗證   |

| 指令                           | 功能              |
| ------------------------------ | ----------------- |
| `openclaw gateway status`      | 查看 Gateway 狀態 |
| `openclaw gateway health`      | Gateway 健康檢查  |
| `openclaw gateway diagnostics` | 詳細診斷          |
| `openclaw gateway start`       | 啟動              |
| `openclaw gateway stop`        | 停止              |
| `openclaw gateway restart`     | **重新啟動**      |
| `openclaw gateway run`         | 前景執行 Gateway  |
| `openclaw gateway probe`       | 探測 Gateway      |

| 指令                            | 功能                |
| ------------------------------- | ------------------- |
| `openclaw logs`                 | 查看 Log            |
| `openclaw logs --follow`        | 即時追蹤            |
| `openclaw logs --json`          | JSON Log            |
| `openclaw logs --follow --json` | **Watchdog 最適合** |

| 指令                           | 功能            |
| ------------------------------ | --------------- |
| `openclaw agent`               | 執行 Agent      |
| `openclaw agents list`         | **列出 Agent**  |
| `openclaw agents add`          | 新增 Agent      |
| `openclaw agents delete`       | 刪除 Agent      |
| `openclaw agents bindings`     | 查看綁定        |
| `openclaw agents bind`         | 綁定 Agent      |
| `openclaw agents unbind`       | 解除綁定        |
| `openclaw agents set-identity` | 設定 Agent 身份 |

| 指令                               | 功能             |
| ---------------------------------- | ---------------- |
| `openclaw models list`             | 列出模型         |
| `openclaw models status`           | 查看目前模型狀態 |
| `openclaw models set`              | 設定預設模型     |
| `openclaw models scan`             | 掃描模型         |
| `openclaw models fallbacks list`   | 查看 fallback    |
| `openclaw models fallbacks add`    | 新增 fallback    |
| `openclaw models fallbacks remove` | 移除 fallback    |
| `openclaw models fallbacks clear`  | 清除 fallback    |
| `openclaw models auth list`        | 查看模型認證     |
| `openclaw models auth add`         | 加入 API 認證    |

| 指令                      | 功能           |
| ------------------------- | -------------- |
| `openclaw nodes status`   | Node 狀態      |
| `openclaw nodes list`     | Node 清單      |
| `openclaw nodes describe` | Node 詳細資訊  |
| `openclaw nodes pending`  | 待配對 Node    |
| `openclaw nodes approve`  | 核准 Node      |
| `openclaw nodes reject`   | 拒絕 Node      |
| `openclaw nodes rename`   | 修改名稱       |
| `openclaw nodes invoke`   | 呼叫 Node Tool |
| `openclaw nodes notify`   | 發送通知       |
| `openclaw nodes push`     | Push           |

| 指令                      | 功能           |
| ------------------------- | -------------- |
| `openclaw skills list`    | 列出 Skills    |
| `openclaw skills search`  | 搜尋 Skill     |
| `openclaw skills install` | 安裝 Skill     |
| `openclaw skills update`  | 更新 Skill     |
| `openclaw skills verify`  | 驗證 Skill     |
| `openclaw skills info`    | Skill 詳細資訊 |

| 指令                         | 功能         |
| ---------------------------- | ------------ |
| `openclaw plugins list`      | 列出 Plugins |
| `openclaw plugins search`    | 搜尋 Plugin  |
| `openclaw plugins inspect`   | 查看 Plugin  |
| `openclaw plugins install`   | 安裝         |
| `openclaw plugins uninstall` | 移除         |
| `openclaw plugins update`    | 更新         |
| `openclaw plugins enable`    | 啟用         |
| `openclaw plugins disable`   | 停用         |
| `openclaw plugins doctor`    | Plugin 診斷  |

| 指令                          | 功能            |
| ----------------------------- | --------------- |
| `openclaw browser status`     | Browser 狀態    |
| `openclaw browser start`      | 啟動            |
| `openclaw browser stop`       | 停止            |
| `openclaw browser tabs`       | 查看 Tabs       |
| `openclaw browser open`       | 開啟網址        |
| `openclaw browser navigate`   | 導航            |
| `openclaw browser screenshot` | 截圖            |
| `openclaw browser click`      | 點擊            |
| `openclaw browser type`       | 輸入文字        |
| `openclaw browser evaluate`   | 執行 JavaScript |

| 指令                    | 功能     |
| ----------------------- | -------- |
| `openclaw cron status`  | 排程狀態 |
| `openclaw cron list`    | 排程清單 |
| `openclaw cron add`     | 新增排程 |
| `openclaw cron edit`    | 修改     |
| `openclaw cron rm`      | 刪除     |
| `openclaw cron enable`  | 啟用     |
| `openclaw cron disable` | 停用     |
| `openclaw cron runs`    | 執行紀錄 |
| `openclaw cron run`     | 立即執行 |

| 指令                     | 功能          |
| ------------------------ | ------------- |
| `openclaw memory status` | Memory 狀態   |
| `openclaw memory index`  | 建立/更新索引 |
| `openclaw memory search` | 搜尋 Memory   |

| 指令                             | 功能         |
| -------------------------------- | ------------ |
| `openclaw channels list`         | Channel 清單 |
| `openclaw channels status`       | Channel 狀態 |
| `openclaw channels capabilities` | 支援能力     |
| `openclaw channels add`          | 新增 Channel |
| `openclaw channels remove`       | 移除         |
| `openclaw channels login`        | 登入         |
| `openclaw channels logout`       | 登出         |

| 指令                      | 功能             |
| ------------------------- | ---------------- |
| `openclaw security audit` | 安全稽核         |
| `openclaw secrets reload` | 重新載入 Secrets |
| `openclaw secrets audit`  | Secrets 稽核     |
| `openclaw approvals get`  | 查看權限         |
| `openclaw approvals set`  | 設定權限         |

| 指令                      | 功能          |
| ------------------------- | ------------- |
| `openclaw backup create`  | 建立備份      |
| `openclaw backup verify`  | 驗證備份      |
| `openclaw backup restore` | 還原          |
| `openclaw update`         | 更新 OpenClaw |
| `openclaw update status`  | 更新狀態      |
| `openclaw update repair`  | 修復更新      |
| `openclaw reset`          | 重置          |
| `openclaw uninstall`      | 移除 OpenClaw |

| 指令                      | 功能              |
| ------------------------- | ----------------- |
| `openclaw node status`    | 本機 Node 狀態    |
| `openclaw node run`       | 執行 Node         |
| `openclaw node install`   | 安裝 Node Service |
| `openclaw node uninstall` | 移除              |
| `openclaw node stop`      | 停止              |
| `openclaw node restart`   | 重啟              |

| 指令                         | 功能     |
| ---------------------------- | -------- |
| `openclaw message send`      | 發送訊息 |
| `openclaw message broadcast` | 廣播     |
| `openclaw message poll`      | 投票     |
| `openclaw message react`     | Reaction |
| `openclaw message read`      | 讀取訊息 |
| `openclaw message search`    | 搜尋訊息 |

---

# OpenClaw Agent

| Slash 指令  | 功能                          |
| ----------- | ----------------------------- |
| `/help`     | 顯示可用指令                  |
| `/status`   | 查看目前 Agent / Session 狀態 |
| `/model`    | 查看或切換模型                |
| `/models`   | 查看可用模型                  |
| `/reset`    | 重置目前 Session              |
| `/clear`    | 清除目前對話內容              |
| `/new`      | 建立新的 Session              |
| `/sessions` | 查看 Session                  |
| `/session`  | 查看目前 Session 資訊         |
| `/compact`  | 壓縮目前 Context              |
| `/context`  | 查看 Context 使用狀況         |
| `/usage`    | 查看 Token / 使用量           |
| `/think`    | 調整思考模式                  |
| `/verbose`  | 開／關詳細輸出                |
| `/debug`    | 開／關 Debug 資訊             |
| `/tools`    | 查看可用 Tools                |
| `/skills`   | 查看可用 Skills               |
| `/config`   | 查看設定                      |
| `/quit`     | 離開目前 Agent                |
| `/exit`     | 離開 Agent                    |

# Ollama timeout

300 秒 → 600 秒

```sh
openclaw config set models.providers.ollama.timeoutSeconds 600
openclaw gateway restart
```

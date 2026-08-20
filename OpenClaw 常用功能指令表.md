# OpenClaw 常用功能指令表

| 功能         | 指令                        | 用途               |
| ------------ | --------------------------- | ------------------ |
| 查看版本     | `openclaw --version`        | 查看 OpenClaw 版本 |
| 查看總說明   | `openclaw --help`           | 顯示所有 CLI 指令  |
| 查看子指令   | `openclaw <command> --help` | 查看指定功能的參數 |
| 啟動 Gateway | `openclaw gateway`          | 啟動 Gateway       |
| Gateway 狀態 | `openclaw gateway status`   | 查看 Gateway 狀態  |
| Gateway 重啟 | `openclaw gateway restart`  | 重啟 Gateway       |
| Gateway 停止 | `openclaw gateway stop`     | 停止 Gateway       |
| Gateway 啟動 | `openclaw gateway start`    | 啟動 Gateway       |
| 初始化       | `openclaw init`             | 初始化 OpenClaw    |
| 設定         | `openclaw configure`        | 設定 OpenClaw      |
| Agent 操作   | `openclaw agent`            | 執行 Agent         |
| 查看 Agent   | `openclaw agents`           | 查看 Agent         |
| Session      | `openclaw sessions`         | 查看工作階段       |
| Channel      | `openclaw channels`         | 管理訊息 Channel   |
| Model        | `openclaw models`           | 查看／管理模型     |
| 設定檔       | `openclaw config`           | 查看／修改設定     |
| Workspace    | `openclaw workspace`        | 管理工作區         |
| Plugin       | `openclaw plugins`          | 管理 Plugin        |
| 日誌         | `openclaw logs`             | 查看 OpenClaw 日誌 |
| Doctor       | `openclaw doctor`           | 檢查／診斷問題     |
| 更新         | `openclaw update`           | 更新 OpenClaw      |

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

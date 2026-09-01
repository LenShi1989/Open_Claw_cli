# 剛開始啟動

```sh
py .\openclaw_ollama_watchdog_v3.py --dry-run
py .\openclaw_ollama_watchdog_v3_1.py --dry-run
```

# 啟動python程式

```sh
py .\openclaw_ollama_watchdog_v3.py
py .\openclaw_ollama_watchdog_v3_1.py
```

# Recovery 失敗才 Restart Gateway

完整流程：

```
                Session HUNG
                     │
                     ▼
               continue #1
                     │
             JSONL 有更新？
               /          \
             YES           NO
              │             │
              ▼             ▼
          RECOVERED      retry 1
                            │
                            ▼
                       continue #2
                            │
                    JSONL 有更新？
                       /       \
                     YES        NO
                      │          │
                      ▼          ▼
                  RECOVERED    retry 2
                                  │
                                  ▼
                             continue #3
                                  │
                         JSONL 有更新？
                            /        \
                          YES         NO
                           │           │
                           ▼           ▼
                       RECOVERED   Gateway Restart
```

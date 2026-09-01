# python 啟動進入虛擬環境

```sh
py -0p                                                 //查看電腦裡Python所有版本
py -3.12 -m venv venv312                               //現有的 Python 版本Python 3.12建立環境
venv312\Scripts\activate                               //啟動虛擬環境 Windows（cmd）
python -m pip install --upgrade pip                    //升級pip
deactivate                                             //關閉虛擬環境
pip install -r requirements.txt                        //安裝txt裡面的所有套件
```

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

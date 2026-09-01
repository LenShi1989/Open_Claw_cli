import subprocess
import time
import re
import sys
from datetime import datetime

# ============================================================
# OpenClaw Watchdog
# ============================================================

# OpenClaw log 檔案
LOG_FILE = r"C:\Users\User\.openclaw\logs\gateway.log"

# 超過這個時間沒有新的 agent activity，就認為可能卡住
TIMEOUT_SECONDS = 540

# 發現 timeout 後，等待幾秒再送 continue
RETRY_DELAY = 5

# Continue prompt
CONTINUE_PROMPT = (
    "continue"
)

# OpenClaw agent
AGENT_ID = "main"


# ============================================================
# Utility
# ============================================================

def log(message):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] {message}", flush=True)


def send_continue(session_id=None):
    """
    發送 continue 到 OpenClaw。
    如果有 session_id，就回到原本 session。
    """

    if session_id:
        cmd = [
            "openclaw",
            "agent",
            "--session-id",
            session_id,
            "--message",
            CONTINUE_PROMPT,
            "--timeout",
            "0"
        ]
    else:
        cmd = [
            "openclaw",
            "agent",
            "--agent",
            AGENT_ID,
            "--message",
            CONTINUE_PROMPT,
            "--timeout",
            "0"
        ]

    log("========================================")
    log("偵測到 OpenClaw 可能 timeout")
    log(f"送出 Prompt: {CONTINUE_PROMPT}")
    log(f"Session: {session_id}")
    log("========================================")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace"
        )

        if result.stdout:
            print(result.stdout)

        if result.stderr:
            print(result.stderr, file=sys.stderr)

        log(f"continue exit code = {result.returncode}")

    except Exception as e:
        log(f"送出 continue 失敗: {e}")


# ============================================================
# Log parser
# ============================================================

def extract_session_id(line):
    """
    從 log 找 session ID。

    例如：
    session:agent:main:tui-79c598cf-fdef-4809-80ce-a498fefdc636
    """

    match = re.search(
        r"session:agent:[^:]+:([a-f0-9-]{36})",
        line,
        re.IGNORECASE
    )

    if match:
        return match.group(1)

    return None


def is_abort_error(line):
    return (
        "AbortError" in line
        or "Reply operation aborted" in line
        or "LLM request timed out" in line
        or "timeout" in line.lower()
    )


def is_agent_activity(line):
    keywords = [
        "agent/embedded",
        "agent",
        "ollama",
        "tool",
        "gateway/ws",
        "assistant",
        "thinking",
        "completion"
    ]

    line_lower = line.lower()

    return any(x.lower() in line_lower for x in keywords)


# ============================================================
# Main watchdog
# ============================================================

def monitor():

    log("========================================")
    log("OpenClaw Watchdog Started")
    log(f"Log file: {LOG_FILE}")
    log(f"Timeout threshold: {TIMEOUT_SECONDS}s")
    log("========================================")

    try:
        with open(
            LOG_FILE,
            "r",
            encoding="utf-8",
            errors="replace"
        ) as f:

            # 跳到 log 最尾端
            f.seek(0, 2)

            last_activity = time.time()
            current_session_id = None

            abort_detected = False

            while True:

                line = f.readline()

                if not line:
                    time.sleep(1)

                    idle_time = time.time() - last_activity

                    if idle_time >= TIMEOUT_SECONDS and not abort_detected:

                        log(
                            f"WARNING: OpenClaw {idle_time:.0f}s "
                            f"沒有偵測到活動"
                        )

                        abort_detected = True

                        time.sleep(RETRY_DELAY)

                        send_continue(current_session_id)

                        last_activity = time.time()
                        abort_detected = False

                    continue

                line = line.strip()

                if not line:
                    continue

                # 顯示重要 log
                if is_agent_activity(line):
                    last_activity = time.time()

                # 嘗試取得 session ID
                session_id = extract_session_id(line)

                if session_id:
                    current_session_id = session_id

                # ------------------------------------------------
                # OpenClaw 明確 timeout / abort
                # ------------------------------------------------

                if is_abort_error(line):

                    log("偵測到 OpenClaw timeout / abort:")
                    log(line)

                    # 如果 log 裡面有 session ID
                    session_id = extract_session_id(line)

                    if session_id:
                        current_session_id = session_id

                    # 避免立即重複觸發
                    if not abort_detected:

                        abort_detected = True

                        time.sleep(RETRY_DELAY)

                        send_continue(current_session_id)

                        last_activity = time.time()

                        abort_detected = False


    except FileNotFoundError:
        log("找不到 OpenClaw log:")
        log(LOG_FILE)

    except KeyboardInterrupt:
        log("Watchdog stopped.")

    except Exception as e:
        log(f"Watchdog error: {e}")


# ============================================================
# Entry
# ============================================================

if __name__ == "__main__":
    monitor()
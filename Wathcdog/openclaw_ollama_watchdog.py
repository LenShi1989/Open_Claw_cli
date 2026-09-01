#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OpenClaw + Ollama Watchdog v2
================================

用途：
    監控 OpenClaw gateway.log。

主要功能：
    1. 偵測 Ollama / LLM timeout
    2. 偵測 OpenClaw AbortError
    3. 偵測單一 session 執行時間過長
    4. 自動取得 session-id
    5. 自動送出 "continue"
    6. Continue 最多重試 N 次
    7. 避免同一個錯誤重複觸發
    8. 建立獨立 watchdog log
    9. 支援 dry-run
    10. 適合 Windows / PowerShell 長時間執行

適用：
    Windows 10 / Windows 11
    Python 3.10+
    OpenClaw
    Ollama
"""

import argparse
import os
import re
import subprocess
import sys
import time
import threading
from datetime import datetime
from pathlib import Path


# ============================================================
# Configuration
# ============================================================

DEFAULT_CONFIG = {
    # OpenClaw gateway log
    "log_file": r"C:\Users\User\.openclaw\logs\gateway.log",

    # Watchdog 自己的 log
    "watchdog_log": r"C:\Users\User\.openclaw\logs\openclaw_watchdog.log",

    # 如果 session 超過這個時間仍然沒有完成，
    # 視為可能卡住。
    #
    # 你的 log 約為：
    # 609135 ms = 609 秒
    #
    # OpenClaw 預設 timeout 約 600 秒，
    # 所以這裡設定 570 秒。
    "session_timeout": 570,

    # 發現 timeout 後等待幾秒才送 continue
    "continue_delay": 5,

    # Continue 最大重試次數
    "max_retries": 3,

    # 每次檢查 log 的間隔
    "poll_interval": 1,

    # continue prompt
    "continue_prompt": "continue",

    # OpenClaw agent
    "agent": "main",

    # OpenClaw command
    "openclaw_command": "openclaw",

    # Continue timeout
    #
    # 0 = 不限制
    "continue_timeout": 0,
}


# ============================================================
# Global State
# ============================================================

class WatchdogState:

    def __init__(self):

        self.lock = threading.Lock()

        # 目前偵測到的 session
        self.current_session_id = None

        # session 開始時間
        self.session_start_time = None

        # 最近一次 activity
        self.last_activity = time.time()

        # 是否已經發送 continue
        self.continue_sent = False

        # Continue 次數
        self.retry_count = 0

        # 最近一次 timeout signature
        self.last_error_signature = None

        # 程式啟動時間
        self.started_at = time.time()

        # 是否停止
        self.stop = False


STATE = WatchdogState()


# ============================================================
# Logger
# ============================================================

class Logger:

    def __init__(self, logfile):

        self.logfile = Path(logfile)

        try:
            self.logfile.parent.mkdir(
                parents=True,
                exist_ok=True
            )
        except Exception:
            pass

    def write(self, level, message):

        now = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        line = f"[{now}] [{level}] {message}"

        print(line, flush=True)

        try:
            with open(
                self.logfile,
                "a",
                encoding="utf-8"
            ) as f:

                f.write(line + "\n")

        except Exception as e:

            print(
                f"[LOGGER ERROR] {e}",
                file=sys.stderr,
                flush=True
            )

    def info(self, message):
        self.write("INFO", message)

    def warning(self, message):
        self.write("WARNING", message)

    def error(self, message):
        self.write("ERROR", message)

    def success(self, message):
        self.write("SUCCESS", message)


# ============================================================
# Session ID Parser
# ============================================================

SESSION_PATTERNS = [

    # session:agent:main:tui-uuid
    re.compile(
        r"session:agent:[^:]+:(tui-[a-f0-9-]{36})",
        re.IGNORECASE
    ),

    # session:agent:main:uuid
    re.compile(
        r"session:agent:[^:]+:([a-f0-9-]{36})",
        re.IGNORECASE
    ),

    # sessionId=xxxx
    re.compile(
        r"sessionId[=:\"']+([a-f0-9-]{36})",
        re.IGNORECASE
    ),

    # session-id=xxxx
    re.compile(
        r"session-id[=:\"']+([a-f0-9-]{36})",
        re.IGNORECASE
    ),
]


def extract_session_id(line):

    for pattern in SESSION_PATTERNS:

        match = pattern.search(line)

        if match:

            return match.group(1)

    return None


# ============================================================
# Detect Errors
# ============================================================

def detect_timeout(line):

    text = line.lower()

    timeout_keywords = [

        "llm request timed out",

        "request timed out",

        "timeout",

        "timed out",

        "aborterror",

        "reply operation aborted",

        "model silent",

        "idle timeout",

        "failovererror",
    ]

    for keyword in timeout_keywords:

        if keyword in text:

            return True

    return False


# ============================================================
# Detect New Agent Run
# ============================================================

def detect_session_start(line):

    keywords = [

        "agent/embedded",

        "agent run",

        "agent start",

        "run started",

        "embedded run",

    ]

    text = line.lower()

    for keyword in keywords:

        if keyword in text:

            return True

    return False


# ============================================================
# Detect Completion
# ============================================================

def detect_session_complete(line):

    keywords = [

        "run completed",

        "run complete",

        "agent completed",

        "agent complete",

        "completion",

    ]

    text = line.lower()

    for keyword in keywords:

        if keyword in text:

            return True

    return False


# ============================================================
# OpenClaw Command
# ============================================================

def build_continue_command(
    config,
    session_id
):

    command = [
        config["openclaw_command"],
        "agent",
    ]

    if session_id:

        command.extend([
            "--session-id",
            session_id,
        ])

    else:

        command.extend([
            "--agent",
            config["agent"],
        ])

    command.extend([
        "--message",
        config["continue_prompt"],
    ])

    # 0 = unlimited
    if config["continue_timeout"] > 0:

        command.extend([
            "--timeout",
            str(config["continue_timeout"])
        ])

    return command


# ============================================================
# Send Continue
# ============================================================

def send_continue(
    config,
    logger,
    session_id,
    dry_run=False
):

    if not session_id:

        logger.error(
            "找不到 session-id，無法送出 continue"
        )

        return False

    command = build_continue_command(
        config,
        session_id
    )

    logger.warning(
        "準備送出 CONTINUE"
    )

    logger.warning(
        f"Session ID: {session_id}"
    )

    logger.warning(
        f"Prompt: {config['continue_prompt']}"
    )

    logger.warning(
        "Command: " + " ".join(
            f'"{x}"' if " " in x else x
            for x in command
        )
    )

    if dry_run:

        logger.warning(
            "DRY-RUN 模式，不實際執行"
        )

        return True

    try:

        creationflags = 0

        if os.name == "nt":

            creationflags = (
                subprocess.CREATE_NO_WINDOW
            )

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
        )

        if result.stdout:

            logger.info(
                "OpenClaw stdout:\n"
                + result.stdout[-4000:]
            )

        if result.stderr:

            logger.warning(
                "OpenClaw stderr:\n"
                + result.stderr[-4000:]
            )

        if result.returncode == 0:

            logger.success(
                "continue 已成功送出"
            )

            return True

        logger.error(
            f"continue 執行失敗，exit code={result.returncode}"
        )

        return False

    except FileNotFoundError:

        logger.error(
            "找不到 openclaw command。"
            "請確認 openclaw 已加入 PATH。"
        )

        return False

    except Exception as e:

        logger.error(
            f"執行 openclaw 發生例外: {e}"
        )

        return False


# ============================================================
# Trigger Continue
# ============================================================

def trigger_continue(
    config,
    logger,
    reason,
    dry_run=False
):

    with STATE.lock:

        session_id = STATE.current_session_id

        if STATE.continue_sent:

            logger.warning(
                "這個 timeout 已經送過 continue，跳過"
            )

            return

        if STATE.retry_count >= config["max_retries"]:

            logger.error(
                "已達到最大 continue 重試次數："
                f"{config['max_retries']}"
            )

            return

        STATE.continue_sent = True

        STATE.retry_count += 1

        retry = STATE.retry_count

    logger.warning(
        "=========================================="
    )

    logger.warning(
        "OpenClaw Watchdog 偵測到可能卡住"
    )

    logger.warning(
        f"Reason: {reason}"
    )

    logger.warning(
        f"Session: {session_id}"
    )

    logger.warning(
        f"Retry: {retry}/{config['max_retries']}"
    )

    logger.warning(
        f"等待 {config['continue_delay']} 秒..."
    )

    logger.warning(
        "=========================================="
    )

    time.sleep(
        config["continue_delay"]
    )

    success = send_continue(
        config,
        logger,
        session_id,
        dry_run
    )

    with STATE.lock:

        if success:

            STATE.last_activity = time.time()

            STATE.session_start_time = time.time()

            STATE.continue_sent = False

        else:

            STATE.continue_sent = False


# ============================================================
# Process Line
# ============================================================

def process_line(
    line,
    config,
    logger,
    dry_run
):

    now = time.time()

    # --------------------------------------------------------
    # Session ID
    # --------------------------------------------------------

    session_id = extract_session_id(line)

    if session_id:

        with STATE.lock:

            if (
                STATE.current_session_id
                != session_id
            ):

                logger.info(
                    f"偵測到 session: {session_id}"
                )

                STATE.current_session_id = (
                    session_id
                )

                STATE.session_start_time = now

                STATE.retry_count = 0

                STATE.continue_sent = False

    # --------------------------------------------------------
    # Session start
    # --------------------------------------------------------

    if detect_session_start(line):

        with STATE.lock:

            if STATE.session_start_time is None:

                STATE.session_start_time = now

            STATE.last_activity = now

    # --------------------------------------------------------
    # Activity
    # --------------------------------------------------------

    activity_keywords = [

        "gateway/ws",

        "agent",

        "ollama",

        "tool",

        "embedded",

        "completion",

        "thinking",

        "assistant",

        "exec",

        "command",

    ]

    text_lower = line.lower()

    for keyword in activity_keywords:

        if keyword in text_lower:

            with STATE.lock:

                STATE.last_activity = now

            break

    # --------------------------------------------------------
    # Completion
    # --------------------------------------------------------

    if detect_session_complete(line):

        with STATE.lock:

            logger.info(
                "偵測到 session completion"
            )

            STATE.session_start_time = None

            STATE.continue_sent = False

            STATE.retry_count = 0

    # --------------------------------------------------------
    # Explicit Timeout
    # --------------------------------------------------------

    if detect_timeout(line):

        # 避免同一行 / 同一錯誤連續觸發
        signature = line[-500:]

        with STATE.lock:

            if (
                STATE.last_error_signature
                == signature
            ):

                return

            STATE.last_error_signature = signature

        # ----------------------------------------------------
        # 有 AbortError / Timeout，立即 continue
        # ----------------------------------------------------

        threading.Thread(
            target=trigger_continue,
            args=(
                config,
                logger,
                f"Explicit timeout/abort detected: {line[-500:]}",
                dry_run,
            ),
            daemon=True,
        ).start()


# ============================================================
# Timeout Monitor
# ============================================================

def timeout_monitor(
    config,
    logger,
    dry_run
):

    logger.info(
        "Session timeout monitor started"
    )

    while not STATE.stop:

        time.sleep(1)

        with STATE.lock:

            session_start = (
                STATE.session_start_time
            )

            session_id = (
                STATE.current_session_id
            )

            continue_sent = (
                STATE.continue_sent
            )

        if not session_start:

            continue

        if continue_sent:

            continue

        elapsed = time.time() - session_start

        # ----------------------------------------------------
        # Session timeout
        # ----------------------------------------------------

        if elapsed >= config["session_timeout"]:

            logger.warning(
                f"Session 已執行 "
                f"{elapsed:.0f} 秒"
            )

            threading.Thread(
                target=trigger_continue,
                args=(
                    config,
                    logger,
                    (
                        "Session exceeded timeout: "
                        f"{elapsed:.0f}s"
                    ),
                    dry_run,
                ),
                daemon=True,
            ).start()


# ============================================================
# Log File Monitor
# ============================================================

def monitor_log(
    config,
    logger,
    dry_run
):

    logfile = Path(
        config["log_file"]
    )

    logger.info(
        "=========================================="
    )

    logger.info(
        "OpenClaw Ollama Watchdog v2"
    )

    logger.info(
        f"Log: {logfile}"
    )

    logger.info(
        f"Session timeout: "
        f"{config['session_timeout']}s"
    )

    logger.info(
        f"Max retries: "
        f"{config['max_retries']}"
    )

    logger.info(
        f"Continue prompt: "
        f"{config['continue_prompt']}"
    )

    logger.info(
        "=========================================="
    )

    # --------------------------------------------------------
    # 等待 log 出現
    # --------------------------------------------------------

    while not logfile.exists():

        logger.warning(
            f"找不到 log：{logfile}"
        )

        logger.warning(
            "等待 5 秒..."
        )

        time.sleep(5)

    # --------------------------------------------------------
    # 開啟 log
    # --------------------------------------------------------

    try:

        with open(
            logfile,
            "r",
            encoding="utf-8",
            errors="replace"
        ) as f:

            # 跳到最後
            f.seek(0, os.SEEK_END)

            logger.info(
                "開始監控 OpenClaw log..."
            )

            while not STATE.stop:

                line = f.readline()

                if not line:

                    time.sleep(
                        config["poll_interval"]
                    )

                    continue

                line = line.strip()

                if not line:

                    continue

                process_line(
                    line,
                    config,
                    logger,
                    dry_run
                )

    except KeyboardInterrupt:

        logger.info(
            "收到 Ctrl+C"
        )

    except Exception as e:

        logger.error(
            f"Log monitor exception: {e}"
        )

        raise


# ============================================================
# Argument Parser
# ============================================================

def parse_arguments():

    parser = argparse.ArgumentParser(
        description=(
            "OpenClaw + Ollama Watchdog v2"
        )
    )

    parser.add_argument(
        "--log",
        default=DEFAULT_CONFIG["log_file"],
        help="OpenClaw gateway log path"
    )

    parser.add_argument(
        "--watchdog-log",
        default=DEFAULT_CONFIG["watchdog_log"],
        help="Watchdog log path"
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_CONFIG["session_timeout"],
        help="Session timeout seconds"
    )

    parser.add_argument(
        "--delay",
        type=int,
        default=DEFAULT_CONFIG["continue_delay"],
        help="Delay before continue"
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_CONFIG["max_retries"],
        help="Maximum continue retries"
    )

    parser.add_argument(
        "--prompt",
        default=DEFAULT_CONFIG["continue_prompt"],
        help="Continue prompt"
    )

    parser.add_argument(
        "--agent",
        default=DEFAULT_CONFIG["agent"],
        help="OpenClaw agent"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show command, do not execute"
    )

    return parser.parse_args()


# ============================================================
# Main
# ============================================================

def main():

    args = parse_arguments()

    config = DEFAULT_CONFIG.copy()

    config["log_file"] = args.log
    config["watchdog_log"] = args.watchdog_log
    config["session_timeout"] = args.timeout
    config["continue_delay"] = args.delay
    config["max_retries"] = args.max_retries
    config["continue_prompt"] = args.prompt
    config["agent"] = args.agent

    logger = Logger(
        config["watchdog_log"]
    )

    logger.info(
        "##########################################"
    )

    logger.info(
        "OpenClaw Ollama Watchdog v2 START"
    )

    logger.info(
        f"PID: {os.getpid()}"
    )

    logger.info(
        f"Python: {sys.version.split()[0]}"
    )

    logger.info(
        f"Timeout: "
        f"{config['session_timeout']} sec"
    )

    logger.info(
        f"Max retries: "
        f"{config['max_retries']}"
    )

    logger.info(
        f"Dry Run: {args.dry_run}"
    )

    logger.info(
        "##########################################"
    )

    # --------------------------------------------------------
    # Start timeout monitor
    # --------------------------------------------------------

    monitor_thread = threading.Thread(
        target=timeout_monitor,
        args=(
            config,
            logger,
            args.dry_run,
        ),
        daemon=True,
    )

    monitor_thread.start()

    # --------------------------------------------------------
    # Start log monitor
    # --------------------------------------------------------

    try:

        monitor_log(
            config,
            logger,
            args.dry_run
        )

    except KeyboardInterrupt:

        logger.info(
            "Watchdog stopped by user"
        )

    finally:

        STATE.stop = True

        logger.info(
            "OpenClaw Watchdog v2 STOP"
        )


if __name__ == "__main__":

    main()
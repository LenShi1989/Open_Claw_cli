#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OpenClaw + Ollama Watchdog v4
=============================

Windows watchdog for OpenClaw + Ollama.

核心設計：
1. 不依賴 gateway.log 路徑。
2. 使用 `openclaw logs --follow --json` 監聽 Gateway diagnostic。
3. 同時輪詢 Ollama /api/tags、/api/ps。
4. 追蹤 OpenClaw session 狀態。
5. 針對 OpenClaw：
      stalled session
          -> stuck session recovery
          -> status=aborted / AbortError
          -> 等待 continue delay
          -> openclaw agent --session-id <id> --message "continue"
6. 避免在正常 THINKING 時誤送 continue。
7. 支援 cooldown、retry、dry-run。
8. Windows / PowerShell 可直接執行。

注意：
- Ollama /api/ps 只能確認目前是否有模型載入/執行，不能單獨證明
  某一次 model call 是否有 token progress。
- Watchdog 預設「等 OpenClaw 自己完成 stuck-session recovery」後才 continue，
  不主動 abort 正在執行的 session。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


VERSION = "4.0.0"

DEFAULT_OLLAMA_URL = "http://220.135.135.29:11436"
DEFAULT_POLL = 5
DEFAULT_STALL_THRESHOLD = 300
DEFAULT_CONTINUE_DELAY = 3
DEFAULT_MAX_RETRIES = 3
DEFAULT_COOLDOWN = 900
DEFAULT_LOG_RESTART_DELAY = 3


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_openclaw_home() -> Path:
    home = os.environ.get("OPENCLAW_HOME")
    if home:
        return Path(home).expanduser()
    return Path.home() / ".openclaw"


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def recursive_strings(obj: Any):
    """Yield all string values from arbitrary JSON."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from recursive_strings(value)
    elif isinstance(obj, list):
        for value in obj:
            yield from recursive_strings(value)


def first_match(pattern: str, text: str, default: Optional[str] = None) -> Optional[str]:
    m = re.search(pattern, text, re.IGNORECASE)
    return m.group(1) if m else default


@dataclass
class SessionState:
    session_id: str
    session_key: str = ""
    state: str = "UNKNOWN"
    role: str = ""
    activity_seconds: int = 0
    last_seen: float = field(default_factory=time.time)

    stalled: bool = False
    recovery_seen: bool = False
    aborted: bool = False
    continue_sent: bool = False

    stalled_at: float = 0.0
    last_progress_age: int = 0
    active_work_kind: str = ""
    queue_depth: int = 0

    retry_count: int = 0
    last_continue: float = 0.0
    last_recovery: float = 0.0

    # Prevent duplicate continue caused by repeated/reconnected log events.
    recovery_signature: str = ""

    def reset_after_idle(self):
        self.stalled = False
        self.recovery_seen = False
        self.aborted = False
        self.continue_sent = False
        self.stalled_at = 0.0
        self.last_progress_age = 0
        self.active_work_kind = ""
        self.queue_depth = 0
        self.recovery_signature = ""


class WatchdogLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()

    def log(self, level: str, message: str):
        line = f"[{now_text()}] [{level}] {message}"
        with self.lock:
            print(line, flush=True)
            try:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception:
                pass

    def info(self, message: str):
        self.log("INFO", message)

    def warning(self, message: str):
        self.log("WARNING", message)

    def error(self, message: str):
        self.log("ERROR", message)

    def debug(self, message: str):
        self.log("DEBUG", message)


class OpenClawOllamaWatchdog:
    def __init__(self, args):
        self.args = args
        self.running = True

        self.openclaw_home = get_openclaw_home()
        log_dir = self.openclaw_home / "logs"
        self.logger = WatchdogLogger(
            log_dir / "openclaw_ollama_watchdog_v4.log"
        )

        self.sessions: dict[str, SessionState] = {}
        self.sessions_lock = threading.Lock()

        self.ollama_models: list[str] = []
        self.ollama_running: list[str] = []

        self.log_process: Optional[subprocess.Popen] = None
        self.log_thread: Optional[threading.Thread] = None

        self.last_status_print = 0.0
        self.last_ollama_check = 0.0

        self.logger.info("=" * 70)
        self.logger.info(f"OpenClaw Ollama Watchdog v{VERSION} START")
        self.logger.info(f"PID: {os.getpid()}")
        self.logger.info(f"Python: {sys.version.split()[0]}")
        self.logger.info(f"OpenClaw home: {self.openclaw_home}")
        self.logger.info(f"Ollama URL: {self.args.ollama_url}")
        self.logger.info(f"Poll: {self.args.poll}s")
        self.logger.info(f"Stall threshold: {self.args.stall_threshold}s")
        self.logger.info(f"Continue delay: {self.args.continue_delay}s")
        self.logger.info(f"Max retries: {self.args.max_retries}")
        self.logger.info(f"Cooldown: {self.args.cooldown}s")
        self.logger.info(f"Dry Run: {self.args.dry_run}")
        self.logger.info("=" * 70)

    # ------------------------------------------------------------------
    # Ollama
    # ------------------------------------------------------------------

    def http_json(self, url: str, timeout: float = 5.0) -> Optional[Any]:
        try:
            req = urllib.request.Request(
                url,
                headers={"Accept": "application/json"},
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = response.read()
                return json.loads(data.decode("utf-8", errors="replace"))
        except Exception as e:
            self.logger.debug(f"HTTP failed {url}: {e}")
            return None

    def check_ollama(self):
        tags = self.http_json(
            self.args.ollama_url.rstrip("/") + "/api/tags"
        )
        ps = self.http_json(
            self.args.ollama_url.rstrip("/") + "/api/ps"
        )

        if isinstance(tags, dict):
            self.ollama_models = [
                str(x.get("name", ""))
                for x in tags.get("models", [])
                if isinstance(x, dict) and x.get("name")
            ]
        else:
            self.ollama_models = []

        if isinstance(ps, dict):
            self.ollama_running = [
                str(x.get("name", ""))
                for x in ps.get("models", [])
                if isinstance(x, dict) and x.get("name")
            ]
        else:
            self.ollama_running = []

    # ------------------------------------------------------------------
    # OpenClaw logs
    # ------------------------------------------------------------------

    def build_logs_command(self) -> list[str]:
        cmd = [
            self.args.openclaw,
            "logs",
            "--follow",
            "--json",
            "--local-time",
        ]

        if self.args.profile:
            cmd.extend(["--profile", self.args.profile])

        return cmd

    def start_log_reader(self):
        if self.log_thread and self.log_thread.is_alive():
            return

        self.log_thread = threading.Thread(
            target=self.log_reader_loop,
            name="OpenClawLogReader",
            daemon=True,
        )
        self.log_thread.start()

    def terminate_log_process(self):
        p = self.log_process
        self.log_process = None

        if not p:
            return

        try:
            if p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    p.kill()
        except Exception:
            pass

    def log_reader_loop(self):
        while self.running:
            cmd = self.build_logs_command()
            self.logger.info("Starting OpenClaw log stream:")
            self.logger.info("  " + " ".join(cmd))

            try:
                creationflags = 0
                if os.name == "nt":
                    creationflags = (
                        subprocess.CREATE_NEW_PROCESS_GROUP
                        | subprocess.CREATE_NO_WINDOW
                    )

                p = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    bufsize=1,
                    creationflags=creationflags,
                )
                self.log_process = p

                assert p.stdout is not None

                for line in iter(p.stdout.readline, ""):
                    if not self.running:
                        break

                    line = line.rstrip("\r\n")
                    if line:
                        self.handle_log_line(line)

                rc = p.poll()
                self.logger.warning(
                    f"OpenClaw log stream ended rc={rc}"
                )

            except FileNotFoundError:
                self.logger.error(
                    f"找不到 OpenClaw CLI: {self.args.openclaw}"
                )
            except Exception as e:
                self.logger.error(
                    f"OpenClaw log stream error: {type(e).__name__}: {e}"
                )
            finally:
                self.terminate_log_process()

            if self.running:
                time.sleep(self.args.log_restart_delay)

    def handle_log_line(self, line: str):
        """
        Accept both JSON output and plain text.
        For JSON, recursively inspect strings because OpenClaw's JSON log
        envelope can vary between versions.
        """
        candidates = [line]

        try:
            obj = json.loads(line)
            candidates.extend(list(recursive_strings(obj)))
        except Exception:
            obj = None

        # De-duplicate while preserving order.
        seen = set()
        texts = []
        for x in candidates:
            if x and x not in seen:
                seen.add(x)
                texts.append(x)

        for text in texts:
            if "stalled session:" in text.lower():
                self.handle_stalled(text)

            if "stuck session recovery" in text.lower():
                self.handle_recovery(text)

            if "lane task error" in text.lower() and "aborterror" in text.lower():
                self.handle_abort_error(text)

    # ------------------------------------------------------------------
    # Diagnostic parser
    # ------------------------------------------------------------------

    def get_or_create_session(self, session_id: str) -> SessionState:
        with self.sessions_lock:
            session = self.sessions.get(session_id)
            if session is None:
                session = SessionState(session_id=session_id)
                self.sessions[session_id] = session
            session.last_seen = time.time()
            return session

    def parse_stalled_fields(self, text: str):
        session_id = first_match(
            r"\bsessionId=([0-9a-fA-F-]{36})\b", text
        )
        if not session_id:
            return None

        session_key = first_match(
            r"\bsessionKey=([^\s]+)", text, ""
        )
        state = first_match(
            r"\bstate=([^\s]+)", text, "unknown"
        )
        age = safe_int(first_match(r"\bage=(\d+)s\b", text), 0)
        queue_depth = safe_int(
            first_match(r"\bqueueDepth=(\d+)\b", text), 0
        )
        active_work_kind = first_match(
            r"\bactiveWorkKind=([^\s]+)", text, ""
        )
        last_progress = first_match(
            r"\blastProgress=([^\s]+)", text, ""
        )
        last_progress_age = safe_int(
            first_match(r"\blastProgressAge=(\d+)s\b", text), 0
        )
        recovery = first_match(
            r"\brecovery=([^\s]+)", text, ""
        )

        return {
            "session_id": session_id,
            "session_key": session_key or "",
            "state": state or "unknown",
            "age": age,
            "queue_depth": queue_depth,
            "active_work_kind": active_work_kind or "",
            "last_progress": last_progress or "",
            "last_progress_age": last_progress_age,
            "recovery": recovery or "",
        }

    def handle_stalled(self, text: str):
        data = self.parse_stalled_fields(text)
        if not data:
            return

        sid = data["session_id"]
        session = self.get_or_create_session(sid)

        with self.sessions_lock:
            session.session_key = data["session_key"]
            session.state = "PROCESSING"
            session.queue_depth = data["queue_depth"]
            session.active_work_kind = data["active_work_kind"]
            session.last_progress_age = data["last_progress_age"]

            qualifies = (
                data["active_work_kind"] == "model_call"
                and data["last_progress_age"] >= self.args.stall_threshold
            )

            if qualifies and not session.stalled:
                session.stalled = True
                session.stalled_at = time.time()

        self.logger.warning(
            f"STALLED session={sid} "
            f"key={data['session_key']} "
            f"state={data['state']} "
            f"age={data['age']}s "
            f"queueDepth={data['queue_depth']} "
            f"activeWorkKind={data['active_work_kind']} "
            f"lastProgressAge={data['last_progress_age']}s "
            f"recovery={data['recovery']}"
        )

        if qualifies:
            self.logger.warning(
                f"Session {sid} qualifies for recovery tracking; "
                f"waiting for OpenClaw abort/recovery outcome before continue."
            )

    def parse_recovery_fields(self, text: str):
        session_id = first_match(
            r"\bsessionId=([0-9a-fA-F-]{36})\b", text
        )
        if not session_id:
            return None

        status = first_match(
            r"\bstatus=([^\s]+)", text, ""
        )
        action = first_match(
            r"\baction=([^\s]+)", text, ""
        )
        aborted = first_match(
            r"\baborted=([^\s]+)", text, ""
        )
        drained = first_match(
            r"\bdrained=([^\s]+)", text, ""
        )
        released = first_match(
            r"\breleased=([^\s]+)", text, ""
        )

        return {
            "session_id": session_id,
            "status": status or "",
            "action": action or "",
            "aborted": (aborted or "").lower() == "true",
            "drained": (drained or "").lower() == "true",
            "released": released or "",
        }

    def handle_recovery(self, text: str):
        data = self.parse_recovery_fields(text)
        if not data:
            return

        sid = data["session_id"]
        session = self.get_or_create_session(sid)

        signature = (
            f"{sid}|{data['status']}|{data['action']}|"
            f"{data['aborted']}|{data['drained']}|{data['released']}"
        )

        with self.sessions_lock:
            session.recovery_seen = True
            session.last_recovery = time.time()
            session.recovery_signature = signature

            if data["aborted"] or data["status"].lower() == "aborted":
                session.aborted = True

        self.logger.warning(
            f"RECOVERY session={sid} "
            f"status={data['status'] or '-'} "
            f"action={data['action'] or '-'} "
            f"aborted={data['aborted']} "
            f"drained={data['drained']} "
            f"released={data['released'] or '-'}"
        )

        # Only the recovery outcome should trigger continue.
        if data["status"].lower() == "aborted" or data["aborted"]:
            self.schedule_continue(sid, reason="stuck-session recovery")

    def handle_abort_error(self, text: str):
        sid = first_match(
            r"\bsessionId=([0-9a-fA-F-]{36})\b", text
        )

        # The observed AbortError log may not contain sessionId.
        # In that case attach it to the most recently stalled session.
        if not sid:
            sid = self.find_latest_stalled_session()

        if not sid:
            self.logger.warning(
                "AbortError detected but no matching stalled session was found."
            )
            return

        session = self.get_or_create_session(sid)

        with self.sessions_lock:
            session.aborted = True

        self.logger.warning(
            f"ABORTERROR session={sid} detected"
        )

        self.schedule_continue(sid, reason="AbortError")

    def find_latest_stalled_session(self) -> Optional[str]:
        with self.sessions_lock:
            candidates = [
                s for s in self.sessions.values()
                if s.stalled
            ]
            if not candidates:
                return None
            candidates.sort(key=lambda x: x.last_seen, reverse=True)
            return candidates[0].session_id

    # ------------------------------------------------------------------
    # Continue state machine
    # ------------------------------------------------------------------

    def schedule_continue(self, session_id: str, reason: str):
        with self.sessions_lock:
            session = self.sessions.get(session_id)
            if not session:
                return

            if session.continue_sent:
                self.logger.debug(
                    f"Continue already sent for {session_id}; skip."
                )
                return

            if session.state.upper() == "IDLE":
                self.logger.info(
                    f"Session {session_id} is already IDLE; "
                    f"continue not required."
                )
                session.reset_after_idle()
                return

            if session.retry_count >= self.args.max_retries:
                self.logger.error(
                    f"Session {session_id} reached max retries "
                    f"({self.args.max_retries}); continue suppressed."
                )
                return

            if (
                session.last_continue > 0
                and time.time() - session.last_continue < self.args.cooldown
            ):
                self.logger.warning(
                    f"Session {session_id} is in cooldown; continue suppressed."
                )
                return

            # Mark before starting a thread to prevent duplicate events.
            session.continue_sent = True
            session.retry_count += 1
            session.last_continue = time.time()

        self.logger.warning(
            f"CONTINUE scheduled session={session_id} "
            f"delay={self.args.continue_delay}s reason={reason}"
        )

        t = threading.Thread(
            target=self._continue_worker,
            args=(session_id, reason),
            name=f"Continue-{session_id[:8]}",
            daemon=True,
        )
        t.start()

    def _continue_worker(self, session_id: str, reason: str):
        time.sleep(self.args.continue_delay)

        if not self.running:
            return

        # Re-check session state after the delay.
        with self.sessions_lock:
            session = self.sessions.get(session_id)
            if not session:
                return

            if session.state.upper() == "THINKING":
                self.logger.warning(
                    f"Continue cancelled for {session_id}: "
                    f"session became THINKING again."
                )
                session.continue_sent = False
                return

        cmd = [
            self.args.openclaw,
            "agent",
            "--session-id",
            session_id,
            "--message",
            "continue",
        ]

        if self.args.profile:
            cmd.extend(["--profile", self.args.profile])

        self.logger.warning(
            f"SENDING CONTINUE session={session_id} "
            f"reason={reason}"
        )
        self.logger.info("  " + " ".join(cmd))

        if self.args.dry_run:
            self.logger.warning(
                "DRY RUN: command NOT executed."
            )
            return

        try:
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NO_WINDOW

            result = subprocess.run(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.args.agent_timeout,
                creationflags=creationflags,
            )

            output = (result.stdout or "").strip()

            if output:
                for line in output.splitlines()[-30:]:
                    self.logger.info(f"agent> {line}")

            if result.returncode == 0:
                self.logger.info(
                    f"CONTINUE SUCCESS session={session_id} "
                    f"rc={result.returncode}"
                )
            else:
                self.logger.error(
                    f"CONTINUE FAILED session={session_id} "
                    f"rc={result.returncode}"
                )
                with self.sessions_lock:
                    session = self.sessions.get(session_id)
                    if session:
                        session.continue_sent = False

        except subprocess.TimeoutExpired:
            self.logger.error(
                f"CONTINUE TIMEOUT session={session_id} "
                f"timeout={self.args.agent_timeout}s"
            )
            with self.sessions_lock:
                session = self.sessions.get(session_id)
                if session:
                    session.continue_sent = False

        except Exception as e:
            self.logger.error(
                f"CONTINUE ERROR session={session_id}: "
                f"{type(e).__name__}: {e}"
            )
            with self.sessions_lock:
                session = self.sessions.get(session_id)
                if session:
                    session.continue_sent = False

    # ------------------------------------------------------------------
    # Session status / display
    # ------------------------------------------------------------------

    def print_status(self):
        print()
        self.logger.info("---------------- WATCHDOG STATUS ----------------")

        if self.ollama_running:
            self.logger.info(
                "Ollama /api/ps: " + ", ".join(self.ollama_running)
            )
        else:
            self.logger.info("Ollama /api/ps: none")

        with self.sessions_lock:
            sessions = list(self.sessions.values())

        self.logger.info(f"OpenClaw sessions: {len(sessions)}")

        for s in sessions:
            activity = f"{s.activity_seconds // 60}m"
            self.logger.info(
                f"SESSION {s.session_id} | "
                f"state={s.state} | "
                f"role={s.role or 'assistant'} | "
                f"activity={activity} | "
                f"retry={s.retry_count}"
            )

            if s.stalled:
                self.logger.info(
                    f"  STALL tracked | "
                    f"activeWorkKind={s.active_work_kind or '-'} | "
                    f"lastProgressAge={s.last_progress_age}s | "
                    f"recovery={s.recovery_seen} | "
                    f"aborted={s.aborted}"
                )

        self.logger.info("------------------------------------------------")

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self):
        self.start_log_reader()

        while self.running:
            try:
                current = time.time()

                if current - self.last_ollama_check >= self.args.poll:
                    self.check_ollama()
                    self.last_ollama_check = current

                if current - self.last_status_print >= self.args.status_interval:
                    self.print_status()
                    self.last_status_print = current

                self.update_idle_cleanup()

                time.sleep(1)

            except KeyboardInterrupt:
                self.stop()
            except Exception as e:
                self.logger.error(
                    f"Main loop error: {type(e).__name__}: {e}"
                )
                time.sleep(2)

        self.stop()

    def update_idle_cleanup(self):
        """
        If a session remains IDLE after recovery, clear the stall flags.
        This prevents stale recovery state from triggering later.
        """
        with self.sessions_lock:
            for session in self.sessions.values():
                if session.state.upper() == "IDLE":
                    if (
                        session.stalled
                        or session.recovery_seen
                        or session.aborted
                    ):
                        session.reset_after_idle()

    def stop(self):
        if not self.running:
            return

        self.running = False
        self.logger.info("Stopping watchdog...")
        self.terminate_log_process()
        self.logger.info("Watchdog stopped.")

    def signal_handler(self, signum, frame):
        self.logger.info(f"Signal received: {signum}")
        self.stop()


def parse_args():
    parser = argparse.ArgumentParser(
        description="OpenClaw + Ollama Watchdog v4"
    )

    parser.add_argument(
        "--openclaw",
        default="openclaw",
        help="OpenClaw CLI executable/path",
    )

    parser.add_argument(
        "--profile",
        default="",
        help="OpenClaw profile, if used",
    )

    parser.add_argument(
        "--ollama-url",
        default=DEFAULT_OLLAMA_URL,
        help="Ollama base URL",
    )

    parser.add_argument(
        "--poll",
        type=int,
        default=DEFAULT_POLL,
        help="Polling interval seconds",
    )

    parser.add_argument(
        "--stall-threshold",
        type=int,
        default=DEFAULT_STALL_THRESHOLD,
        help="Minimum lastProgressAge seconds to qualify",
    )

    parser.add_argument(
        "--continue-delay",
        type=int,
        default=DEFAULT_CONTINUE_DELAY,
        help="Seconds to wait before sending continue",
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=DEFAULT_MAX_RETRIES,
        help="Maximum continue attempts per session",
    )

    parser.add_argument(
        "--cooldown",
        type=int,
        default=DEFAULT_COOLDOWN,
        help="Cooldown seconds between continue attempts",
    )

    parser.add_argument(
        "--agent-timeout",
        type=int,
        default=120,
        help="Timeout for `openclaw agent` command",
    )

    parser.add_argument(
        "--log-restart-delay",
        type=int,
        default=DEFAULT_LOG_RESTART_DELAY,
        help="Seconds before restarting failed log stream",
    )

    parser.add_argument(
        "--status-interval",
        type=int,
        default=60,
        help="Watchdog status print interval",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect events but do not execute continue",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    watchdog = OpenClawOllamaWatchdog(args)

    signal.signal(signal.SIGINT, watchdog.signal_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, watchdog.signal_handler)

    try:
        watchdog.run()
    except KeyboardInterrupt:
        watchdog.stop()
    except Exception as e:
        watchdog.logger.error(
            f"Fatal error: {type(e).__name__}: {e}"
        )
        watchdog.stop()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

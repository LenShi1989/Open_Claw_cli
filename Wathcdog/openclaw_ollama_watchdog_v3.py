#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OpenClaw + Ollama Watchdog v3
=============================

Windows watchdog for OpenClaw + Ollama.

設計：
- 不依賴 gateway.log。
- 直接透過 Ollama 的 HTTP API 進行輪詢。
- 從本機會話檔案中發現活動的 OpenClaw 會話。
- 偵測 OpenClaw 會話活動/過期會話。
- 如果 Ollama 無法存取或長時間保持靜默，則向受影響的 OpenClaw 會話發送“continue”訊息。
- 使用 OpenClaw CLI 恢復會話。
- 具有重試次數限制和冷卻時間，以避免無限循環。


Default environment:
    Windows
    Python 3.10+
    Ollama: http://220.135.135.29:11436
    OpenClaw: %USERPROFILE%\\.openclaw

重要提示：
此監視程式不會取消目前正在執行的 OpenClaw 回合。
它僅在配置的過期/超時條件滿足後發送“continue”訊息。
如果 OpenClaw 本身已中止該回合，則下一個「continue」訊息可以恢復同一會話。

Test first with:
    py openclaw_ollama_watchdog.py --dry-run

Normal:
    py openclaw_ollama_watchdog.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

@dataclass
class Config:
    ollama_url: str = "http://220.135.135.29:11436"
    openclaw_home: Path = field(
        default_factory=lambda: Path.home() / ".openclaw"
    )

    # No Ollama response at all for this period => unhealthy.
    ollama_timeout: int = 120

    # A session may not remain stale longer than this before continue.
    session_timeout: int = 570

    # Time between watchdog cycles.
    poll_interval: int = 5

    # Wait before sending continue.
    continue_delay: int = 5

    # Maximum continue attempts per session before cooldown.
    max_retries: int = 3

    # After max retries, don't keep hammering the session.
    cooldown_seconds: int = 900

    # Prompt used to resume the task.
    continue_prompt: str = "continue"

    # OpenClaw CLI command.
    openclaw_command: str = "openclaw"

    # Agent fallback if a session cannot be discovered.
    agent: str = "main"

    # Ollama health request timeout.
    http_timeout: int = 10

    # Ignore sessions older than this when no recent activity is known.
    session_discovery_max_age: int = 3600


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

class Logger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, level: str, message: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{now}] [{level}] {message}"

        with self._lock:
            print(line, flush=True)
            try:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except Exception as exc:
                print(
                    f"[LOGGER ERROR] Cannot write log: {exc}",
                    file=sys.stderr,
                    flush=True,
                )

    def info(self, message: str):
        self.write("INFO", message)

    def warning(self, message: str):
        self.write("WARNING", message)

    def error(self, message: str):
        self.write("ERROR", message)

    def success(self, message: str):
        self.write("SUCCESS", message)


# ---------------------------------------------------------------------
# Runtime state
# ---------------------------------------------------------------------

@dataclass
class SessionState:
    session_id: str
    path: Optional[Path] = None
    last_mtime: float = 0.0
    last_seen: float = field(default_factory=time.time)
    first_seen: float = field(default_factory=time.time)
    retry_count: int = 0
    last_continue: float = 0.0
    cooldown_until: float = 0.0
    continue_in_progress: bool = False


class WatchdogState:
    def __init__(self):
        self.lock = threading.RLock()
        self.sessions: dict[str, SessionState] = {}
        self.last_ollama_ok: float = 0.0
        self.last_ollama_error: Optional[str] = None
        self.ollama_down_since: Optional[float] = None
        self.stop = False


STATE = WatchdogState()


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}",
    re.IGNORECASE,
)

SESSION_PATTERNS = [
    re.compile(
        r"session:agent:[^:]+:(tui-[0-9a-f-]{36})",
        re.IGNORECASE,
    ),
    re.compile(
        r"session:agent:[^:]+:([0-9a-f-]{36})",
        re.IGNORECASE,
    ),
    re.compile(
        r"session[_-]?id[\"']?\s*[:=]\s*[\"']?([0-9a-f-]{36})",
        re.IGNORECASE,
    ),
]


def now() -> float:
    return time.time()


def extract_session_id(text: str) -> Optional[str]:
    for pattern in SESSION_PATTERNS:
        match = pattern.search(text)
        if match:
            return match.group(1)

    # Last-resort UUID extraction.
    match = UUID_RE.search(text)
    if match:
        return match.group(0)

    return None


def looks_like_session_file(path: Path) -> bool:
    name = path.name.lower()
    return (
        path.is_file()
        and (
            name.endswith(".jsonl")
            or name.endswith(".json")
        )
        and "session" in str(path.parent).lower()
    )


# ---------------------------------------------------------------------
# Ollama API
# ---------------------------------------------------------------------

def ollama_get(config: Config, endpoint: str) -> tuple[bool, str]:
    url = config.ollama_url.rstrip("/") + endpoint

    try:
        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "OpenClaw-Ollama-Watchdog/3.0",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=config.http_timeout,
        ) as response:
            body = response.read(4096).decode(
                "utf-8",
                errors="replace",
            )

            return True, body

    except urllib.error.HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.reason}"

    except urllib.error.URLError as exc:
        return False, f"Connection error: {exc.reason}"

    except TimeoutError:
        return False, "HTTP timeout"

    except Exception as exc:
        return False, repr(exc)


def check_ollama(config: Config, logger: Logger) -> bool:
    ok, body = ollama_get(config, "/api/tags")

    with STATE.lock:
        if ok:
            was_down = STATE.ollama_down_since is not None
            STATE.last_ollama_ok = now()
            STATE.last_ollama_error = None
            STATE.ollama_down_since = None

            if was_down:
                logger.success("Ollama connection recovered.")

            return True

        if STATE.ollama_down_since is None:
            STATE.ollama_down_since = now()
            logger.warning(
                f"Ollama unavailable: {body}"
            )
        else:
            elapsed = now() - STATE.ollama_down_since
            logger.warning(
                f"Ollama still unavailable "
                f"({elapsed:.0f}s): {body}"
            )

        STATE.last_ollama_error = body

    return False


# ---------------------------------------------------------------------
# Ollama running models
# ---------------------------------------------------------------------

def get_ollama_running_models(
    config: Config,
    logger: Logger,
) -> list[dict]:
    ok, body = ollama_get(config, "/api/ps")

    if not ok:
        return []

    try:
        data = json.loads(body)
        models = data.get("models", [])

        if isinstance(models, list):
            return models

    except Exception as exc:
        logger.warning(
            f"Cannot parse Ollama /api/ps: {exc}"
        )

    return []


# ---------------------------------------------------------------------
# OpenClaw session discovery
# ---------------------------------------------------------------------

def candidate_session_dirs(config: Config) -> list[Path]:
    root = config.openclaw_home

    candidates = [
        root / "agents",
        root / "sessions",
    ]

    # Common OpenClaw structure:
    # ~/.openclaw/agents/<agent>/sessions/
    agents_dir = root / "agents"

    if agents_dir.is_dir():
        try:
            for child in agents_dir.iterdir():
                if child.is_dir():
                    candidates.append(child / "sessions")
        except OSError:
            pass

    return candidates


def discover_session_files(config: Config) -> list[Path]:
    found: list[Path] = []
    seen: set[str] = set()

    for directory in candidate_session_dirs(config):
        if not directory.is_dir():
            continue

        try:
            for path in directory.rglob("*"):
                if not path.is_file():
                    continue

                name = path.name.lower()

                if not (
                    name.endswith(".jsonl")
                    or name.endswith(".json")
                ):
                    continue

                # Prefer session-looking files, but don't require
                # exact naming because OpenClaw layouts can vary.
                try:
                    age = now() - path.stat().st_mtime
                except OSError:
                    continue

                if age > config.session_discovery_max_age:
                    continue

                key = str(path.resolve()).lower()

                if key not in seen:
                    seen.add(key)
                    found.append(path)

        except OSError:
            continue

    return found


def inspect_session_file(
    path: Path,
    logger: Logger,
) -> tuple[Optional[str], Optional[float]]:
    """
    Return:
        (session_id, last_activity_timestamp)

    Uses filename/path and JSONL content where possible.
    """

    session_id = extract_session_id(str(path))

    try:
        stat = path.stat()
        last_activity = stat.st_mtime
    except OSError:
        return session_id, None

    # Read only the tail of large JSONL files.
    try:
        with path.open(
            "rb"
        ) as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            read_size = min(size, 256 * 1024)
            f.seek(max(0, size - read_size))
            raw = f.read(read_size)

        text = raw.decode(
            "utf-8",
            errors="replace",
        )

        found_id = extract_session_id(text)

        if found_id:
            session_id = found_id

        # Parse recent JSONL lines and look for timestamp fields.
        for line in reversed(text.splitlines()):
            line = line.strip()

            if not line:
                continue

            try:
                obj = json.loads(line)
            except Exception:
                continue

            if not isinstance(obj, dict):
                continue

            for key in (
                "timestamp",
                "ts",
                "createdAt",
                "updatedAt",
                "lastActivity",
            ):
                value = obj.get(key)

                if isinstance(value, (int, float)):
                    # Milliseconds -> seconds.
                    if value > 10_000_000_000:
                        value /= 1000

                    if 1_000_000_000 < value < now() + 86400:
                        last_activity = max(
                            last_activity,
                            float(value),
                        )

                elif isinstance(value, str):
                    try:
                        parsed = value.replace(
                            "Z",
                            "+00:00",
                        )
                        dt = datetime.fromisoformat(parsed)
                        ts = dt.timestamp()

                        if 1_000_000_000 < ts < now() + 86400:
                            last_activity = max(
                                last_activity,
                                ts,
                            )
                    except Exception:
                        pass

            if session_id is None:
                found_id = extract_session_id(
                    json.dumps(obj, ensure_ascii=False)
                )
                if found_id:
                    session_id = found_id

    except OSError:
        pass
    except Exception as exc:
        logger.warning(
            f"Session inspect failed: {path}: {exc}"
        )

    return session_id, last_activity


def discover_sessions(
    config: Config,
    logger: Logger,
):
    files = discover_session_files(config)

    if not files:
        return

    current_time = now()

    with STATE.lock:
        for path in files:
            session_id, activity = inspect_session_file(
                path,
                logger,
            )

            if not session_id:
                continue

            activity = activity or path.stat().st_mtime

            state = STATE.sessions.get(session_id)

            if state is None:
                state = SessionState(
                    session_id=session_id,
                    path=path,
                    last_mtime=path.stat().st_mtime,
                    last_seen=current_time,
                    first_seen=current_time,
                )

                STATE.sessions[session_id] = state

                logger.info(
                    f"Discovered OpenClaw session: "
                    f"{session_id}"
                )
                logger.info(
                    f"Session file: {path}"
                )

            else:
                state.path = path

            if activity > state.last_seen:
                state.last_seen = activity

            try:
                state.last_mtime = path.stat().st_mtime
            except OSError:
                pass


# ---------------------------------------------------------------------
# Select active/stale session
# ---------------------------------------------------------------------

def get_best_session(
    config: Config,
) -> Optional[SessionState]:

    with STATE.lock:
        candidates = list(STATE.sessions.values())

    if not candidates:
        return None

    # Prefer sessions with recent activity.
    candidates.sort(
        key=lambda s: s.last_seen,
        reverse=True,
    )

    return candidates[0]


def get_stale_sessions(
    config: Config,
) -> list[SessionState]:

    current = now()

    with STATE.lock:
        return [
            s
            for s in STATE.sessions.values()
            if (
                not s.continue_in_progress
                and current >= s.cooldown_until
                and current - s.last_seen
                >= config.session_timeout
            )
        ]


# ---------------------------------------------------------------------
# Continue command
# ---------------------------------------------------------------------

def build_continue_command(
    config: Config,
    session_id: str,
) -> list[str]:

    return [
        config.openclaw_command,
        "agent",
        "--session-id",
        session_id,
        "--message",
        config.continue_prompt,
    ]


def send_continue(
    config: Config,
    logger: Logger,
    session: SessionState,
    dry_run: bool,
    reason: str,
) -> bool:

    command = build_continue_command(
        config,
        session.session_id,
    )

    logger.warning(
        "=========================================="
    )
    logger.warning(
        "WATCHDOG CONTINUE"
    )
    logger.warning(
        f"Reason: {reason}"
    )
    logger.warning(
        f"Session: {session.session_id}"
    )
    logger.warning(
        f"Retry: "
        f"{session.retry_count + 1}/"
        f"{config.max_retries}"
    )
    logger.warning(
        f"Prompt: {config.continue_prompt}"
    )
    logger.warning(
        "Command: " + " ".join(
            f'"{x}"' if " " in x else x
            for x in command
        )
    )

    if dry_run:
        logger.warning(
            "DRY-RUN: command NOT executed."
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
            timeout=max(
                30,
                config.session_timeout,
            ),
            creationflags=creationflags,
        )

        if result.stdout:
            logger.info(
                "OpenClaw stdout:\n"
                + result.stdout[-5000:]
            )

        if result.stderr:
            logger.warning(
                "OpenClaw stderr:\n"
                + result.stderr[-5000:]
            )

        if result.returncode == 0:
            logger.success(
                f"Continue command succeeded for "
                f"{session.session_id}"
            )
            return True

        logger.error(
            f"Continue command failed. "
            f"exit={result.returncode}"
        )
        return False

    except subprocess.TimeoutExpired:
        logger.error(
            "Continue command itself timed out."
        )
        return False

    except FileNotFoundError:
        logger.error(
            "OpenClaw command not found. "
            "Check that 'openclaw' is in PATH."
        )
        return False

    except Exception as exc:
        logger.error(
            f"Continue command exception: {exc}"
        )
        return False


# ---------------------------------------------------------------------
# Continue worker
# ---------------------------------------------------------------------

def continue_worker(
    config: Config,
    logger: Logger,
    session: SessionState,
    dry_run: bool,
    reason: str,
):
    with STATE.lock:
        if session.continue_in_progress:
            return

        if now() < session.cooldown_until:
            return

        if session.retry_count >= config.max_retries:
            session.cooldown_until = (
                now() + config.cooldown_seconds
            )

            logger.error(
                f"Session {session.session_id} reached "
                f"max retries ({config.max_retries}). "
                f"Cooldown={config.cooldown_seconds}s."
            )

            return

        session.continue_in_progress = True

    try:
        logger.warning(
            f"Waiting {config.continue_delay}s "
            f"before continue..."
        )

        time.sleep(config.continue_delay)

        success = send_continue(
            config,
            logger,
            session,
            dry_run,
            reason,
        )

        with STATE.lock:
            if success:
                session.retry_count += 1
                session.last_continue = now()

                # Treat the continue command as a fresh activity point.
                session.last_seen = now()

                logger.info(
                    f"Session {session.session_id} "
                    f"reset after continue."
                )

            else:
                session.retry_count += 1
                session.last_continue = now()

                if session.retry_count >= config.max_retries:
                    session.cooldown_until = (
                        now() + config.cooldown_seconds
                    )

    finally:
        with STATE.lock:
            session.continue_in_progress = False


def trigger_continue(
    config: Config,
    logger: Logger,
    session: SessionState,
    reason: str,
    dry_run: bool,
):
    threading.Thread(
        target=continue_worker,
        args=(
            config,
            logger,
            session,
            dry_run,
            reason,
        ),
        daemon=True,
    ).start()


# ---------------------------------------------------------------------
# Health logic
# ---------------------------------------------------------------------

def monitor_ollama_health(
    config: Config,
    logger: Logger,
    dry_run: bool,
):
    """
    If Ollama is completely unavailable for ollama_timeout seconds,
    resume the most recently seen OpenClaw session.

    This is intentionally conservative: a normal model generation
    should not be interrupted merely because no token is visible here.
    """

    healthy = check_ollama(
        config,
        logger,
    )

    if healthy:
        return

    with STATE.lock:
        down_since = STATE.ollama_down_since

    if down_since is None:
        return

    elapsed = now() - down_since

    if elapsed < config.ollama_timeout:
        return

    session = get_best_session(config)

    if session is None:
        logger.warning(
            "Ollama has been unavailable too long, "
            "but no OpenClaw session was discovered."
        )
        return

    trigger_continue(
        config,
        logger,
        session,
        (
            f"Ollama unavailable for "
            f"{elapsed:.0f}s"
        ),
        dry_run,
    )


def monitor_session_timeouts(
    config: Config,
    logger: Logger,
    dry_run: bool,
):
    stale = get_stale_sessions(config)

    for session in stale:
        age = now() - session.last_seen

        trigger_continue(
            config,
            logger,
            session,
            (
                f"OpenClaw session stale for "
                f"{age:.0f}s "
                f"(threshold={config.session_timeout}s)"
            ),
            dry_run,
        )


# ---------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------

def log_status(
    config: Config,
    logger: Logger,
):
    running_models = get_ollama_running_models(
        config,
        logger,
    )

    with STATE.lock:
        session_count = len(STATE.sessions)
        ollama_error = STATE.last_ollama_error

    if running_models:
        names = []

        for model in running_models:
            name = model.get("name")

            if name:
                names.append(name)

        logger.info(
            "Ollama running models: "
            + ", ".join(names)
        )
    else:
        logger.info(
            "Ollama running models: none"
        )

    logger.info(
        f"Discovered OpenClaw sessions: "
        f"{session_count}"
    )

    if ollama_error:
        logger.warning(
            f"Last Ollama error: {ollama_error}"
        )


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "OpenClaw + Ollama Watchdog v3 "
            "(no gateway.log dependency)"
        )
    )

    parser.add_argument(
        "--ollama-url",
        default="http://220.135.135.29:11436",
        help="Ollama base URL",
    )

    parser.add_argument(
        "--openclaw-home",
        default=str(
            Path.home() / ".openclaw"
        ),
        help="OpenClaw home directory",
    )

    parser.add_argument(
        "--ollama-timeout",
        type=int,
        default=120,
        help=(
            "Ollama unavailable timeout in seconds"
        ),
    )

    parser.add_argument(
        "--session-timeout",
        type=int,
        default=570,
        help=(
            "OpenClaw session stale timeout"
        ),
    )

    parser.add_argument(
        "--poll",
        type=int,
        default=5,
        help="Polling interval",
    )

    parser.add_argument(
        "--delay",
        type=int,
        default=5,
        help="Delay before continue",
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum retries per session",
    )

    parser.add_argument(
        "--cooldown",
        type=int,
        default=900,
        help="Cooldown after max retries",
    )

    parser.add_argument(
        "--prompt",
        default="continue",
        help="Continue prompt",
    )

    parser.add_argument(
        "--agent",
        default="main",
        help="Fallback OpenClaw agent",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not execute openclaw commands",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    args = parse_args()

    config = Config(
        ollama_url=args.ollama_url,
        openclaw_home=Path(
            args.openclaw_home
        ).expanduser(),
        ollama_timeout=args.ollama_timeout,
        session_timeout=args.session_timeout,
        poll_interval=args.poll,
        continue_delay=args.delay,
        max_retries=args.max_retries,
        cooldown_seconds=args.cooldown,
        continue_prompt=args.prompt,
        agent=args.agent,
    )

    log_path = (
        config.openclaw_home
        / "logs"
        / "openclaw_ollama_watchdog.log"
    )

    logger = Logger(log_path)

    logger.info(
        "############################################"
    )
    logger.info(
        "OpenClaw Ollama Watchdog v3 START"
    )
    logger.info(
        f"PID: {os.getpid()}"
    )
    logger.info(
        f"Python: {sys.version.split()[0]}"
    )
    logger.info(
        f"Ollama: {config.ollama_url}"
    )
    logger.info(
        f"OpenClaw home: {config.openclaw_home}"
    )
    logger.info(
        f"Ollama unavailable timeout: "
        f"{config.ollama_timeout}s"
    )
    logger.info(
        f"Session stale timeout: "
        f"{config.session_timeout}s"
    )
    logger.info(
        f"Poll interval: "
        f"{config.poll_interval}s"
    )
    logger.info(
        f"Max retries: "
        f"{config.max_retries}"
    )
    logger.info(
        f"Cooldown: "
        f"{config.cooldown_seconds}s"
    )
    logger.info(
        f"Continue prompt: "
        f"{config.continue_prompt}"
    )
    logger.info(
        f"Dry-run: {args.dry_run}"
    )
    logger.info(
        "No gateway.log dependency."
    )
    logger.info(
        "############################################"
    )

    if not config.openclaw_home.exists():
        logger.warning(
            f"OpenClaw home does not exist: "
            f"{config.openclaw_home}"
        )

    # Initial session discovery.
    discover_sessions(
        config,
        logger,
    )

    last_status = 0.0

    try:
        while True:
            # Discover / refresh sessions.
            discover_sessions(
                config,
                logger,
            )

            # Direct Ollama health check.
            monitor_ollama_health(
                config,
                logger,
                args.dry_run,
            )

            # Session stale detection.
            monitor_session_timeouts(
                config,
                logger,
                args.dry_run,
            )

            # Periodic status every 60 seconds.
            if now() - last_status >= 60:
                log_status(
                    config,
                    logger,
                )
                last_status = now()

            time.sleep(
                config.poll_interval
            )

    except KeyboardInterrupt:
        logger.info(
            "Ctrl+C received. Stopping watchdog."
        )

    except Exception as exc:
        logger.error(
            f"Fatal watchdog error: {exc}"
        )
        raise

    finally:
        STATE.stop = True
        logger.info(
            "OpenClaw Ollama Watchdog v3 STOP"
        )


if __name__ == "__main__":
    main()

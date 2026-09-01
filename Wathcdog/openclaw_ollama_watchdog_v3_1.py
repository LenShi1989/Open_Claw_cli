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


#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OpenClaw + Ollama Watchdog v3.1
===============================

Windows watchdog for OpenClaw + Ollama.

v3.1 Features
--------------
1. No gateway.log dependency.
2. Direct Ollama HTTP API monitoring.
3. Ollama /api/tags health check.
4. Ollama /api/ps running-model detection.
5. Direct OpenClaw session JSONL discovery.
6. sessions.json is explicitly ignored.
7. JSONL last activity timestamp detection.
8. JSONL last event / role detection.
9. Session state machine:
       DISCOVERED
       ACTIVE
       THINKING
       IDLE
       STALE
       HUNG
       RECOVERING
       COOLDOWN
10. Automatic "continue" recovery.
11. Recovery verifies that JSONL actually changed.
12. Retry limit.
13. OpenClaw Gateway restart after recovery failure.
14. Post-restart session rediscovery.
15. Cooldown protection.
16. Windows / PowerShell compatible.
17. Ctrl+C safe shutdown.

Default:
    Ollama:
        http://220.135.135.29:11436

    OpenClaw:
        %USERPROFILE%\\.openclaw

Test:
    py openclaw_ollama_watchdog_v3_1.py --dry-run

Normal:
    py openclaw_ollama_watchdog_v3_1.py
"""


# ================================================================
# Configuration
# ================================================================

@dataclass
class Config:

    # ------------------------------------------------------------
    # Ollama
    # ------------------------------------------------------------

    ollama_url: str = "http://220.135.135.29:11436"

    ollama_timeout: int = 120

    http_timeout: int = 10

    # ------------------------------------------------------------
    # OpenClaw
    # ------------------------------------------------------------

    openclaw_home: Path = field(
        default_factory=lambda:
        Path.home() / ".openclaw"
    )

    openclaw_command: str = "openclaw"

    agent: str = "main"

    # ------------------------------------------------------------
    # Session
    # ------------------------------------------------------------

    session_timeout: int = 570

    # After continue, how long we wait for JSONL update.
    recovery_wait: int = 90

    # ------------------------------------------------------------
    # Watchdog
    # ------------------------------------------------------------

    poll_interval: int = 5

    continue_delay: int = 5

    max_retries: int = 3

    cooldown_seconds: int = 900

    continue_prompt: str = "continue"

    # ------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------

    session_discovery_max_age: int = 3600

    # ------------------------------------------------------------
    # Thinking protection
    # ------------------------------------------------------------

    # If Ollama is actively running a model, do not immediately
    # consider the session dead.
    thinking_grace: int = 180

    # ------------------------------------------------------------
    # Status
    # ------------------------------------------------------------

    status_interval: int = 60

    # ------------------------------------------------------------
    # JSONL
    # ------------------------------------------------------------

    jsonl_tail_bytes: int = 512 * 1024


# ================================================================
# Logger
# ================================================================

class Logger:

    def __init__(self, path: Path):

        self.path = path

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.lock = threading.Lock()

    def write(
        self,
        level: str,
        message: str,
    ):

        timestamp = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        line = (
            f"[{timestamp}] "
            f"[{level}] "
            f"{message}"
        )

        with self.lock:

            print(
                line,
                flush=True,
            )

            try:

                with self.path.open(
                    "a",
                    encoding="utf-8",
                ) as f:

                    f.write(
                        line + "\n"
                    )

            except Exception as exc:

                print(
                    f"[LOGGER ERROR] {exc}",
                    file=sys.stderr,
                    flush=True,
                )

    def info(self, message):
        self.write("INFO", message)

    def warning(self, message):
        self.write("WARNING", message)

    def error(self, message):
        self.write("ERROR", message)

    def success(self, message):
        self.write("SUCCESS", message)


# ================================================================
# Global Runtime State
# ================================================================

class WatchdogState:

    def __init__(self):

        self.lock = threading.RLock()

        self.sessions: dict[
            str,
            SessionState
        ] = {}

        self.last_ollama_ok = 0.0

        self.last_ollama_error: Optional[str] = None

        self.ollama_down_since: Optional[float] = None

        self.running_models: list[dict] = []

        self.stop = False


@dataclass
class SessionState:

    session_id: str

    path: Optional[Path] = None

    # File modification time
    last_mtime: float = 0.0

    # Last activity extracted from JSONL
    last_activity: float = 0.0

    # Last time watchdog observed this session
    last_seen: float = field(
        default_factory=time.time
    )

    # First discovery
    first_seen: float = field(
        default_factory=time.time
    )

    # Last detected role
    last_role: str = "unknown"

    # Last event summary
    last_event: str = ""

    # State machine
    state: str = "DISCOVERED"

    previous_state: str = ""

    # Recovery
    retry_count: int = 0

    last_continue: float = 0.0

    cooldown_until: float = 0.0

    continue_in_progress: bool = False

    restart_in_progress: bool = False

    # Snapshot before recovery
    recovery_baseline_mtime: float = 0.0

    recovery_baseline_activity: float = 0.0

    recovery_started: float = 0.0


STATE = WatchdogState()


# ================================================================
# Helpers
# ================================================================

UUID_RE = re.compile(
    r"[0-9a-f]{8}-"
    r"[0-9a-f]{4}-"
    r"[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-"
    r"[0-9a-f]{12}",
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
        r"session[_-]?id[\"']?"
        r"\s*[:=]\s*"
        r"[\"']?"
        r"([0-9a-f-]{36})",
        re.IGNORECASE,
    ),
]


def now() -> float:
    return time.time()


def format_age(timestamp: float) -> str:

    if timestamp <= 0:
        return "unknown"

    seconds = max(
        0,
        int(now() - timestamp),
    )

    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60

    if minutes < 60:
        return f"{minutes}m"

    hours = minutes // 60

    return f"{hours}h {minutes % 60}m"


def extract_session_id(
    text: str,
) -> Optional[str]:

    for pattern in SESSION_PATTERNS:

        match = pattern.search(text)

        if match:
            return match.group(1)

    match = UUID_RE.search(text)

    if match:
        return match.group(0)

    return None


def parse_timestamp(
    value,
) -> Optional[float]:

    if isinstance(value, (int, float)):

        value = float(value)

        if value > 10_000_000_000:
            value /= 1000

        if (
            1_000_000_000
            < value
            < now() + 86400
        ):
            return value

        return None

    if isinstance(value, str):

        try:

            text = value.strip()

            if text.endswith("Z"):
                text = text[:-1] + "+00:00"

            dt = datetime.fromisoformat(text)

            timestamp = dt.timestamp()

            if (
                1_000_000_000
                < timestamp
                < now() + 86400
            ):
                return timestamp

        except Exception:
            pass

    return None


def extract_role(obj: dict) -> str:

    # Common direct fields
    for key in (
        "role",
        "sender",
        "author",
        "type",
    ):

        value = obj.get(key)

        if isinstance(value, str):

            value_lower = value.lower()

            if value_lower in {
                "user",
                "human",
            }:
                return "user"

            if value_lower in {
                "assistant",
                "ai",
                "model",
            }:
                return "assistant"

            if value_lower in {
                "tool",
                "function",
            }:
                return "tool"

            if value_lower in {
                "system",
            }:
                return "system"

    # OpenAI-like message structure
    message = obj.get("message")

    if isinstance(message, dict):

        role = message.get("role")

        if isinstance(role, str):

            role_lower = role.lower()

            if role_lower in {
                "user",
                "assistant",
                "tool",
                "system",
            }:
                return role_lower

    return "unknown"


def extract_event_text(obj: dict) -> str:

    candidates = []

    for key in (
        "content",
        "text",
        "message",
        "summary",
        "event",
        "type",
    ):

        value = obj.get(key)

        if isinstance(value, str):
            candidates.append(value)

        elif isinstance(value, dict):

            role = value.get("role")

            content = value.get("content")

            if role:
                candidates.append(
                    str(role)
                )

            if isinstance(content, str):
                candidates.append(content)

    text = " ".join(candidates)

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text[:300]


# ================================================================
# Ollama
# ================================================================

def ollama_get(
    config: Config,
    endpoint: str,
) -> tuple[bool, str]:

    url = (
        config.ollama_url.rstrip("/")
        + endpoint
    )

    try:

        request = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent":
                    "OpenClaw-Ollama-Watchdog/3.1",
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=config.http_timeout,
        ) as response:

            body = response.read(
                1024 * 1024
            ).decode(
                "utf-8",
                errors="replace",
            )

            return True, body

    except urllib.error.HTTPError as exc:

        return (
            False,
            f"HTTP {exc.code}: {exc.reason}",
        )

    except urllib.error.URLError as exc:

        return (
            False,
            f"Connection error: {exc.reason}",
        )

    except TimeoutError:

        return False, "HTTP timeout"

    except Exception as exc:

        return False, repr(exc)


def check_ollama(
    config: Config,
    logger: Logger,
) -> bool:

    ok, body = ollama_get(
        config,
        "/api/tags",
    )

    with STATE.lock:

        if ok:

            was_down = (
                STATE.ollama_down_since
                is not None
            )

            STATE.last_ollama_ok = now()

            STATE.last_ollama_error = None

            STATE.ollama_down_since = None

            if was_down:

                logger.success(
                    "Ollama connection recovered."
                )

            return True

        if STATE.ollama_down_since is None:

            STATE.ollama_down_since = now()

            logger.warning(
                f"Ollama unavailable: {body}"
            )

        else:

            elapsed = (
                now()
                - STATE.ollama_down_since
            )

            logger.warning(
                f"Ollama still unavailable "
                f"({elapsed:.0f}s): {body}"
            )

        STATE.last_ollama_error = body

    return False


def get_ollama_running_models(
    config: Config,
    logger: Logger,
) -> list[dict]:

    ok, body = ollama_get(
        config,
        "/api/ps",
    )

    if not ok:
        return []

    try:

        data = json.loads(body)

        models = data.get(
            "models",
            [],
        )

        if isinstance(models, list):
            return models

    except Exception as exc:

        logger.warning(
            f"Cannot parse Ollama /api/ps: {exc}"
        )

    return []


def update_ollama_state(
    config: Config,
    logger: Logger,
):

    check_ollama(
        config,
        logger,
    )

    models = get_ollama_running_models(
        config,
        logger,
    )

    with STATE.lock:
        STATE.running_models = models


def ollama_is_running() -> bool:

    with STATE.lock:
        return bool(
            STATE.running_models
        )


def running_model_names() -> list[str]:

    names = []

    with STATE.lock:

        for model in STATE.running_models:

            name = model.get("name")

            if name:
                names.append(name)

    return names


# ================================================================
# Session Discovery
# ================================================================

def candidate_session_dirs(
    config: Config,
) -> list[Path]:

    root = config.openclaw_home

    candidates = [
        root / "sessions",
        root / "agents",
    ]

    agents_dir = root / "agents"

    if agents_dir.is_dir():

        try:

            for child in agents_dir.iterdir():

                if child.is_dir():

                    candidates.append(
                        child / "sessions"
                    )

        except OSError:
            pass

    return candidates


def is_real_session_file(
    path: Path,
) -> bool:

    if not path.is_file():
        return False

    name = path.name.lower()

    # IMPORTANT:
    # sessions.json is metadata/index, NOT a session.
    if name in {
        "sessions.json",
        "session.json",
    }:
        return False

    # Only JSONL is treated as a conversation session.
    if not name.endswith(".jsonl"):
        return False

    return True


def discover_session_files(
    config: Config,
) -> list[Path]:

    found = []

    seen = set()

    for directory in candidate_session_dirs(
        config
    ):

        if not directory.is_dir():
            continue

        try:

            for path in directory.rglob(
                "*.jsonl"
            ):

                if not is_real_session_file(
                    path
                ):
                    continue

                try:

                    stat = path.stat()

                except OSError:
                    continue

                age = (
                    now()
                    - stat.st_mtime
                )

                if (
                    age
                    > config.session_discovery_max_age
                ):
                    continue

                try:

                    key = str(
                        path.resolve()
                    ).lower()

                except OSError:

                    key = str(path).lower()

                if key in seen:
                    continue

                seen.add(key)

                found.append(path)

        except OSError:
            continue

    return found


# ================================================================
# JSONL inspection
# ================================================================

def inspect_session_file(
    config: Config,
    path: Path,
    logger: Logger,
) -> tuple[
    Optional[str],
    float,
    str,
    str,
]:

    session_id = extract_session_id(
        str(path)
    )

    try:

        stat = path.stat()

        file_mtime = stat.st_mtime

    except OSError:

        return (
            session_id,
            0.0,
            "unknown",
            "",
        )

    last_activity = file_mtime

    last_role = "unknown"

    last_event = ""

    try:

        with path.open(
            "rb"
        ) as f:

            f.seek(
                0,
                os.SEEK_END,
            )

            size = f.tell()

            read_size = min(
                size,
                config.jsonl_tail_bytes,
            )

            f.seek(
                max(
                    0,
                    size - read_size,
                )
            )

            raw = f.read(
                read_size
            )

        text = raw.decode(
            "utf-8",
            errors="replace",
        )

        found_id = extract_session_id(
            text
        )

        if found_id:
            session_id = found_id

        lines = text.splitlines()

        # --------------------------------------------------------
        # Read newest valid JSON object first
        # --------------------------------------------------------

        for line in reversed(lines):

            line = line.strip()

            if not line:
                continue

            try:

                obj = json.loads(line)

            except Exception:
                continue

            if not isinstance(obj, dict):
                continue

            # ----------------------------------------------------
            # timestamp
            # ----------------------------------------------------

            event_timestamp = None

            for key in (
                "timestamp",
                "ts",
                "createdAt",
                "updatedAt",
                "lastActivity",
            ):

                value = obj.get(key)

                timestamp = parse_timestamp(
                    value
                )

                if timestamp:

                    event_timestamp = timestamp

                    break

            if event_timestamp:

                last_activity = max(
                    last_activity,
                    event_timestamp,
                )

            # ----------------------------------------------------
            # role
            # ----------------------------------------------------

            role = extract_role(obj)

            if role != "unknown":

                last_role = role

            last_event = extract_event_text(
                obj
            )

            # We found newest valid JSON event.
            break

        # --------------------------------------------------------
        # Scan tail for latest timestamp
        # --------------------------------------------------------

        for line in lines:

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

                timestamp = parse_timestamp(
                    obj.get(key)
                )

                if timestamp:

                    last_activity = max(
                        last_activity,
                        timestamp,
                    )

            if session_id is None:

                found_id = extract_session_id(
                    json.dumps(
                        obj,
                        ensure_ascii=False,
                    )
                )

                if found_id:
                    session_id = found_id

    except Exception as exc:

        logger.warning(
            f"Session inspect failed: "
            f"{path}: {exc}"
        )

    return (
        session_id,
        last_activity,
        last_role,
        last_event,
    )


# ================================================================
# Session state calculation
# ================================================================

def calculate_session_state(
    config: Config,
    session: SessionState,
) -> str:

    current = now()

    age = (
        current
        - session.last_activity
    )

    ollama_running = ollama_is_running()

    # ------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------

    if session.continue_in_progress:
        return "RECOVERING"

    if session.restart_in_progress:
        return "RESTARTING"

    if (
        session.cooldown_until > current
    ):
        return "COOLDOWN"

    # ------------------------------------------------------------
    # Recently active
    # ------------------------------------------------------------

    if age < 30:

        if session.last_role == "user":
            return "ACTIVE"

        if session.last_role in {
            "assistant",
            "tool",
        }:
            return "IDLE"

        return "ACTIVE"

    # ------------------------------------------------------------
    # Ollama is actively running
    # ------------------------------------------------------------

    if ollama_running:

        if age < (
            config.session_timeout
            + config.thinking_grace
        ):
            return "THINKING"

    # ------------------------------------------------------------
    # Session waiting for assistant
    #
    # Last event = user
    # No recent JSONL activity
    #
    # This is the strongest signal of a hung
    # OpenClaw execution.
    # ------------------------------------------------------------

    if session.last_role == "user":

        if age >= config.session_timeout:

            return "HUNG"

    # ------------------------------------------------------------
    # Session old but last speaker assistant
    #
    # Usually means task completed.
    # Do NOT automatically continue.
    # ------------------------------------------------------------

    if session.last_role in {
        "assistant",
        "tool",
    }:

        return "IDLE"

    # ------------------------------------------------------------
    # Unknown state
    # ------------------------------------------------------------

    if age >= config.session_timeout:
        return "STALE"

    return "ACTIVE"


# ================================================================
# Session discovery / refresh
# ================================================================

def discover_sessions(
    config: Config,
    logger: Logger,
):

    files = discover_session_files(
        config
    )

    if not files:

        return

    current_time = now()

    with STATE.lock:

        for path in files:

            (
                session_id,
                activity,
                role,
                event,
            ) = inspect_session_file(
                config,
                path,
                logger,
            )

            if not session_id:
                continue

            try:
                mtime = path.stat().st_mtime
            except OSError:
                continue

            session = STATE.sessions.get(
                session_id
            )

            if session is None:

                session = SessionState(
                    session_id=session_id,
                    path=path,
                    last_mtime=mtime,
                    last_activity=activity,
                    last_seen=current_time,
                    first_seen=current_time,
                    last_role=role,
                    last_event=event,
                )

                STATE.sessions[
                    session_id
                ] = session

                logger.info(
                    f"Discovered OpenClaw session: "
                    f"{session_id}"
                )

                logger.info(
                    f"Session file: {path}"
                )

            else:

                old_mtime = (
                    session.last_mtime
                )

                old_activity = (
                    session.last_activity
                )

                session.path = path

                session.last_mtime = mtime

                if activity > old_activity:

                    session.last_activity = (
                        activity
                    )

                session.last_seen = (
                    current_time
                )

                if role != "unknown":

                    session.last_role = role

                if event:

                    session.last_event = event

                # ------------------------------------------------
                # Detect actual JSONL update
                # ------------------------------------------------

                if (
                    mtime > old_mtime
                    or activity > old_activity
                ):

                    # If recovery was waiting for activity,
                    # reset retry counter.
                    if (
                        session.recovery_started
                        > 0
                        and (
                            mtime
                            > session.recovery_baseline_mtime
                            or activity
                            > session.recovery_baseline_activity
                        )
                    ):

                        logger.success(
                            f"Session activity "
                            f"detected after recovery: "
                            f"{session_id}"
                        )

                        session.retry_count = 0

                        session.recovery_started = 0

                        session.recovery_baseline_mtime = 0

                        session.recovery_baseline_activity = 0

            # ----------------------------------------------------
            # Update state
            # ----------------------------------------------------

            new_state = calculate_session_state(
                config,
                session,
            )

            if (
                new_state
                != session.state
            ):

                previous = session.state

                session.previous_state = previous

                session.state = new_state

                logger.info(
                    f"Session state: "
                    f"{session_id} "
                    f"{previous} -> {new_state} "
                    f"| role={session.last_role} "
                    f"| age={format_age(session.last_activity)}"
                )


# ================================================================
# Active session selection
# ================================================================

def get_best_session(
    config: Config,
) -> Optional[SessionState]:

    with STATE.lock:

        candidates = [
            s
            for s in STATE.sessions.values()
            if s.cooldown_until <= now()
        ]

    if not candidates:
        return None

    # Prefer HUNG
    hung = [
        s
        for s in candidates
        if s.state == "HUNG"
    ]

    if hung:

        hung.sort(
            key=lambda s:
            s.last_activity,
            reverse=True,
        )

        return hung[0]

    # Then THINKING
    thinking = [
        s
        for s in candidates
        if s.state == "THINKING"
    ]

    if thinking:

        thinking.sort(
            key=lambda s:
            s.last_activity,
            reverse=True,
        )

        return thinking[0]

    # Finally newest activity
    candidates.sort(
        key=lambda s:
        s.last_activity,
        reverse=True,
    )

    return candidates[0]


def get_recovery_sessions(
    config: Config,
) -> list[SessionState]:

    current = now()

    with STATE.lock:

        return [
            s
            for s in STATE.sessions.values()
            if (
                s.state in {
                    "HUNG",
                    "STALE",
                }
                and not s.continue_in_progress
                and not s.restart_in_progress
                and s.cooldown_until <= current
            )
        ]


# ================================================================
# OpenClaw command
# ================================================================

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


def build_gateway_restart_command(
    config: Config,
) -> list[str]:

    return [
        config.openclaw_command,
        "gateway",
        "restart",
    ]


def format_command(
    command: list[str],
) -> str:

    return " ".join(
        (
            f'"{item}"'
            if " " in item
            else item
        )
        for item in command
    )


# ================================================================
# Execute Continue
# ================================================================

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
        "WATCHDOG RECOVERY: CONTINUE"
    )

    logger.warning(
        f"Reason: {reason}"
    )

    logger.warning(
        f"Session: {session.session_id}"
    )

    logger.warning(
        f"State: {session.state}"
    )

    logger.warning(
        f"Last role: {session.last_role}"
    )

    logger.warning(
        f"Last activity: "
        f"{format_age(session.last_activity)} ago"
    )

    logger.warning(
        f"Retry: "
        f"{session.retry_count + 1}/"
        f"{config.max_retries}"
    )

    logger.warning(
        f"Ollama models: "
        f"{', '.join(running_model_names()) or 'none'}"
    )

    logger.warning(
        f"Command: {format_command(command)}"
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
                config.recovery_wait,
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
                f"Continue command accepted: "
                f"{session.session_id}"
            )

            return True

        logger.error(
            f"Continue command failed: "
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
            "Check PATH."
        )

        return False

    except Exception as exc:

        logger.error(
            f"Continue exception: {exc}"
        )

        return False


# ================================================================
# Recovery worker
# ================================================================

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

        if session.restart_in_progress:
            return

        if now() < session.cooldown_until:
            return

        if (
            session.retry_count
            >= config.max_retries
        ):

            logger.error(
                f"Session {session.session_id} "
                f"already reached max retries."
            )

            return

        # --------------------------------------------------------
        # Save baseline
        # --------------------------------------------------------

        session.recovery_baseline_mtime = (
            session.last_mtime
        )

        session.recovery_baseline_activity = (
            session.last_activity
        )

        session.recovery_started = now()

        session.continue_in_progress = True

        session.state = "RECOVERING"

    try:

        logger.warning(
            f"Waiting "
            f"{config.continue_delay}s "
            f"before continue..."
        )

        time.sleep(
            config.continue_delay
        )

        success = send_continue(
            config,
            logger,
            session,
            dry_run,
            reason,
        )

        if not success:

            with STATE.lock:

                session.retry_count += 1

                session.last_continue = now()

                session.continue_in_progress = False

            logger.error(
                f"Recovery continue failed. "
                f"retry={session.retry_count}"
            )

            return

        # --------------------------------------------------------
        # IMPORTANT:
        # Successful CLI command does NOT mean
        # session actually resumed.
        #
        # Wait for JSONL to change.
        # --------------------------------------------------------

        logger.info(
            f"Waiting up to "
            f"{config.recovery_wait}s "
            f"for session JSONL activity..."
        )

        deadline = (
            now()
            + config.recovery_wait
        )

        recovered = False

        while (
            now() < deadline
            and not STATE.stop
        ):

            time.sleep(
                config.poll_interval
            )

            refresh_single_session(
                config,
                logger,
                session,
            )

            with STATE.lock:

                if (
                    session.last_mtime
                    > session.recovery_baseline_mtime
                    or
                    session.last_activity
                    > session.recovery_baseline_activity
                ):

                    recovered = True

                    break

        with STATE.lock:

            session.continue_in_progress = False

            session.last_continue = now()

            if recovered:

                session.retry_count = 0

                session.recovery_started = 0

                session.recovery_baseline_mtime = 0

                session.recovery_baseline_activity = 0

                session.state = "ACTIVE"

                logger.success(
                    f"Session RECOVERED: "
                    f"{session.session_id}"
                )

            else:

                session.retry_count += 1

                logger.warning(
                    f"Continue did not produce "
                    f"new JSONL activity. "
                    f"retry={session.retry_count}/"
                    f"{config.max_retries}"
                )

                if (
                    session.retry_count
                    >= config.max_retries
                ):

                    session.state = "HUNG"

                    logger.error(
                        f"Session recovery exhausted: "
                        f"{session.session_id}"
                    )

    except Exception as exc:

        logger.error(
            f"Recovery worker exception: "
            f"{exc}"
        )

        with STATE.lock:

            session.continue_in_progress = False

            session.retry_count += 1


# ================================================================
# Refresh single session
# ================================================================

def refresh_single_session(
    config: Config,
    logger: Logger,
    session: SessionState,
):

    path = session.path

    if not path:
        return

    if not path.exists():
        return

    (
        session_id,
        activity,
        role,
        event,
    ) = inspect_session_file(
        config,
        path,
        logger,
    )

    try:
        mtime = path.stat().st_mtime
    except OSError:
        return

    with STATE.lock:

        old_mtime = session.last_mtime

        old_activity = session.last_activity

        if mtime > session.last_mtime:
            session.last_mtime = mtime

        if activity > session.last_activity:
            session.last_activity = activity

        if role != "unknown":
            session.last_role = role

        if event:
            session.last_event = event

        session.last_seen = now()

        if (
            mtime > old_mtime
            or activity > old_activity
        ):

            logger.success(
                f"JSONL activity updated: "
                f"{session.session_id} "
                f"| role={session.last_role} "
                f"| age={format_age(session.last_activity)}"
            )


# ================================================================
# Trigger continue
# ================================================================

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


# ================================================================
# Gateway Restart
# ================================================================

def restart_gateway(
    config: Config,
    logger: Logger,
    dry_run: bool,
) -> bool:

    command = build_gateway_restart_command(
        config
    )

    logger.warning(
        "=========================================="
    )

    logger.warning(
        "WATCHDOG RECOVERY: OPENCLAW GATEWAY RESTART"
    )

    logger.warning(
        f"Command: {format_command(command)}"
    )

    if dry_run:

        logger.warning(
            "DRY-RUN: gateway restart NOT executed."
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
            timeout=120,
            creationflags=creationflags,
        )

        if result.stdout:

            logger.info(
                "Gateway restart stdout:\n"
                + result.stdout[-5000:]
            )

        if result.stderr:

            logger.warning(
                "Gateway restart stderr:\n"
                + result.stderr[-5000:]
            )

        if result.returncode == 0:

            logger.success(
                "OpenClaw gateway restart succeeded."
            )

            return True

        logger.error(
            f"Gateway restart failed. "
            f"exit={result.returncode}"
        )

        return False

    except Exception as exc:

        logger.error(
            f"Gateway restart exception: {exc}"
        )

        return False


# ================================================================
# Restart exhausted sessions
# ================================================================

def restart_exhausted_sessions(
    config: Config,
    logger: Logger,
    dry_run: bool,
):

    with STATE.lock:

        exhausted = [
            s
            for s in STATE.sessions.values()
            if (
                s.retry_count
                >= config.max_retries
                and not s.restart_in_progress
                and s.cooldown_until <= now()
            )
        ]

        if not exhausted:
            return

        for session in exhausted:

            session.restart_in_progress = True

    try:

        success = restart_gateway(
            config,
            logger,
            dry_run,
        )

        with STATE.lock:

            if success:

                for session in exhausted:

                    logger.warning(
                        f"Resetting session recovery "
                        f"state after gateway restart: "
                        f"{session.session_id}"
                    )

                    session.retry_count = 0

                    session.last_continue = now()

                    session.cooldown_until = (
                        now()
                        + config.cooldown_seconds
                    )

                    session.recovery_started = 0

                    session.state = "COOLDOWN"

            else:

                for session in exhausted:

                    session.cooldown_until = (
                        now()
                        + config.cooldown_seconds
                    )

                    session.state = "COOLDOWN"

                    logger.error(
                        f"Gateway restart failed. "
                        f"Session cooldown applied: "
                        f"{session.session_id}"
                    )

    finally:

        with STATE.lock:

            for session in exhausted:

                session.restart_in_progress = False


# ================================================================
# Ollama health monitor
# ================================================================

def monitor_ollama_health(
    config: Config,
    logger: Logger,
    dry_run: bool,
):

    with STATE.lock:

        down_since = (
            STATE.ollama_down_since
        )

    if down_since is None:
        return

    elapsed = (
        now()
        - down_since
    )

    if elapsed < config.ollama_timeout:
        return

    # Only attempt recovery for a session that
    # appears to be waiting for assistant output.
    with STATE.lock:

        candidates = [
            s
            for s in STATE.sessions.values()
            if (
                s.last_role == "user"
                and not s.continue_in_progress
                and not s.restart_in_progress
                and s.cooldown_until <= now()
            )
        ]

    if not candidates:

        logger.warning(
            "Ollama unavailable too long, "
            "but no pending user session found."
        )

        return

    candidates.sort(
        key=lambda s:
        s.last_activity,
        reverse=True,
    )

    session = candidates[0]

    age = (
        now()
        - session.last_activity
    )

    if age < config.session_timeout:

        logger.warning(
            f"Ollama unavailable {elapsed:.0f}s "
            f"but session is not stale yet "
            f"(age={age:.0f}s)."
        )

        return

    trigger_continue(
        config,
        logger,
        session,
        (
            f"Ollama unavailable for "
            f"{elapsed:.0f}s; "
            f"session pending for "
            f"{age:.0f}s"
        ),
        dry_run,
    )


# ================================================================
# Session state monitor
# ================================================================

def monitor_session_states(
    config: Config,
    logger: Logger,
    dry_run: bool,
):

    sessions = get_recovery_sessions(
        config
    )

    for session in sessions:

        age = (
            now()
            - session.last_activity
        )

        models = running_model_names()

        # --------------------------------------------------------
        # If Ollama is still generating,
        # give it additional grace.
        # --------------------------------------------------------

        if (
            session.state == "HUNG"
            and models
            and age
            < (
                config.session_timeout
                + config.thinking_grace
            )
        ):

            logger.warning(
                f"Session appears stale but "
                f"Ollama is still running: "
                f"{session.session_id} "
                f"| models={','.join(models)} "
                f"| age={age:.0f}s "
                f"| waiting for thinking grace."
            )

            with STATE.lock:
                session.state = "THINKING"

            continue

        # --------------------------------------------------------
        # Only recover when last event was user.
        # --------------------------------------------------------

        if session.last_role == "user":

            trigger_continue(
                config,
                logger,
                session,
                (
                    f"Session state={session.state}; "
                    f"last activity "
                    f"{age:.0f}s ago; "
                    f"last role=user; "
                    f"Ollama models="
                    f"{','.join(models) or 'none'}"
                ),
                dry_run,
            )

        else:

            logger.info(
                f"Session stale but not recovered: "
                f"{session.session_id} "
                f"| state={session.state} "
                f"| role={session.last_role} "
                f"| age={age:.0f}s"
            )


# ================================================================
# Periodic status
# ================================================================

def log_status(
    config: Config,
    logger: Logger,
):

    models = get_ollama_running_models(
        config,
        logger,
    )

    with STATE.lock:

        STATE.running_models = models

        sessions = list(
            STATE.sessions.values()
        )

        ollama_error = (
            STATE.last_ollama_error
        )

        ollama_down_since = (
            STATE.ollama_down_since
        )

    logger.info(
        "---------------- WATCHDOG STATUS "
        "----------------"
    )

    if models:

        names = [
            m.get("name")
            for m in models
            if m.get("name")
        ]

        logger.info(
            "Ollama /api/ps: "
            + ", ".join(names)
        )

    else:

        logger.info(
            "Ollama /api/ps: none"
        )

    logger.info(
        f"OpenClaw sessions: "
        f"{len(sessions)}"
    )

    for session in sorted(
        sessions,
        key=lambda s:
        s.last_activity,
        reverse=True,
    ):

        logger.info(
            f"SESSION "
            f"{session.session_id} "
            f"| state={session.state} "
            f"| role={session.last_role} "
            f"| activity={format_age(session.last_activity)} "
            f"| retry={session.retry_count}"
        )

    if ollama_down_since:

        logger.warning(
            f"Ollama DOWN for "
            f"{now() - ollama_down_since:.0f}s"
        )

    elif ollama_error:

        logger.warning(
            f"Last Ollama error: "
            f"{ollama_error}"
        )

    logger.info(
        "------------------------------------------------"
    )


# ================================================================
# CLI
# ================================================================

def parse_args():

    parser = argparse.ArgumentParser(
        description=(
            "OpenClaw + Ollama Watchdog v3.1"
        )
    )

    parser.add_argument(
        "--ollama-url",
        default=(
            "http://220.135.135.29:11436"
        ),
    )

    parser.add_argument(
        "--openclaw-home",
        default=str(
            Path.home()
            / ".openclaw"
        ),
    )

    parser.add_argument(
        "--ollama-timeout",
        type=int,
        default=120,
    )

    parser.add_argument(
        "--session-timeout",
        type=int,
        default=570,
    )

    parser.add_argument(
        "--recovery-wait",
        type=int,
        default=90,
        help=(
            "Wait for JSONL activity after continue"
        ),
    )

    parser.add_argument(
        "--thinking-grace",
        type=int,
        default=180,
        help=(
            "Extra time when Ollama is actively "
            "running a model"
        ),
    )

    parser.add_argument(
        "--poll",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--delay",
        type=int,
        default=5,
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
    )

    parser.add_argument(
        "--cooldown",
        type=int,
        default=900,
    )

    parser.add_argument(
        "--prompt",
        default="continue",
    )

    parser.add_argument(
        "--agent",
        default="main",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    return parser.parse_args()


# ================================================================
# Main
# ================================================================

def main():

    args = parse_args()

    config = Config(

        ollama_url=args.ollama_url,

        openclaw_home=Path(
            args.openclaw_home
        ).expanduser(),

        ollama_timeout=args.ollama_timeout,

        session_timeout=args.session_timeout,

        recovery_wait=args.recovery_wait,

        thinking_grace=args.thinking_grace,

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
        / "openclaw_ollama_watchdog_v3_1.log"
    )

    logger = Logger(
        log_path
    )

    # ------------------------------------------------------------
    # Startup
    # ------------------------------------------------------------

    logger.info(
        "############################################"
    )

    logger.info(
        "OpenClaw Ollama Watchdog v3.1 START"
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
        f"OpenClaw home: "
        f"{config.openclaw_home}"
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
        f"Thinking grace: "
        f"{config.thinking_grace}s"
    )

    logger.info(
        f"Recovery wait: "
        f"{config.recovery_wait}s"
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
        "sessions.json explicitly excluded."
    )

    logger.info(
        "Monitoring:"
    )

    logger.info(
        "  - OpenClaw Session JSONL"
    )

    logger.info(
        "  - JSONL last activity"
    )

    logger.info(
        "  - JSONL last role"
    )

    logger.info(
        "  - Ollama /api/tags"
    )

    logger.info(
        "  - Ollama /api/ps"
    )

    logger.info(
        "  - Automatic continue"
    )

    logger.info(
        "  - Automatic gateway restart"
    )

    logger.info(
        "############################################"
    )

    if not config.openclaw_home.exists():

        logger.warning(
            f"OpenClaw home does not exist: "
            f"{config.openclaw_home}"
        )

    # ------------------------------------------------------------
    # Initial Ollama
    # ------------------------------------------------------------

    update_ollama_state(
        config,
        logger,
    )

    # ------------------------------------------------------------
    # Initial discovery
    # ------------------------------------------------------------

    discover_sessions(
        config,
        logger,
    )

    last_status = 0.0

    try:

        while True:

            if STATE.stop:
                break

            # ----------------------------------------------------
            # 1. Discover / refresh sessions
            # ----------------------------------------------------

            discover_sessions(
                config,
                logger,
            )

            # ----------------------------------------------------
            # 2. Ollama state
            # ----------------------------------------------------

            update_ollama_state(
                config,
                logger,
            )

            # ----------------------------------------------------
            # 3. Monitor Ollama outage
            # ----------------------------------------------------

            monitor_ollama_health(
                config,
                logger,
                args.dry_run,
            )

            # ----------------------------------------------------
            # 4. Calculate session states again
            # ----------------------------------------------------

            with STATE.lock:

                for session in (
                    STATE.sessions.values()
                ):

                    if (
                        session.continue_in_progress
                        or session.restart_in_progress
                    ):
                        continue

                    new_state = (
                        calculate_session_state(
                            config,
                            session,
                        )
                    )

                    if (
                        new_state
                        != session.state
                    ):

                        previous = (
                            session.state
                        )

                        session.previous_state = (
                            previous
                        )

                        session.state = (
                            new_state
                        )

                        logger.info(
                            f"Session state: "
                            f"{session.session_id} "
                            f"{previous} -> "
                            f"{new_state}"
                        )

            # ----------------------------------------------------
            # 5. Monitor stale / hung sessions
            # ----------------------------------------------------

            monitor_session_states(
                config,
                logger,
                args.dry_run,
            )

            # ----------------------------------------------------
            # 6. Restart if recovery exhausted
            # ----------------------------------------------------

            restart_exhausted_sessions(
                config,
                logger,
                args.dry_run,
            )

            # ----------------------------------------------------
            # 7. Status
            # ----------------------------------------------------

            if (
                now()
                - last_status
                >= config.status_interval
            ):

                log_status(
                    config,
                    logger,
                )

                last_status = now()

            # ----------------------------------------------------
            # 8. Sleep
            # ----------------------------------------------------

            time.sleep(
                config.poll_interval
            )

    except KeyboardInterrupt:

        logger.info(
            "Ctrl+C received. "
            "Stopping watchdog."
        )

    except Exception as exc:

        logger.error(
            f"Fatal watchdog error: {exc}"
        )

        raise

    finally:

        with STATE.lock:
            STATE.stop = True

        logger.info(
            "OpenClaw Ollama Watchdog v3.1 STOP"
        )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Eternal Daemon — Agent orchestration process manager.

Manages three types of agents communicating via the filesystem:
- Orchestrator: wakes on interval + events, makes decisions, exits
- Task agents: spawn, execute one task, write result, exit
- Eternal agents: run in a loop forever, sleep between cycles

All agents are invoked via `claude -p` (Claude Code CLI headless mode).
"""

import asyncio
import json
import logging
import os
import signal
import shutil
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).parent.resolve()

def load_config() -> dict:
    config_path = BASE_DIR / "config.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def setup_logging(logs_dir: Path) -> logging.Logger:
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("eternal")
    logger.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", "%H:%M:%S"))
    logger.addHandler(ch)

    # File handler
    fh = logging.FileHandler(logs_dir / "errors.log")
    fh.setLevel(logging.WARNING)
    fh.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s"))
    logger.addHandler(fh)

    return logger

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class WakeEvent:
    type: str               # TASK_COMPLETED, TASK_FAILED, SCHEDULED, ETERNAL_DISCOVERY
    task_id: Optional[str]
    summary: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

@dataclass
class RunningTask:
    task_id: str
    pid: int
    agent: str
    started_at: str
    timeout_minutes: int
    wake_on_complete: bool

@dataclass
class EternalAgentState:
    name: str
    pid: Optional[int] = None
    status: str = "idle"        # idle, running, sleeping
    sleep_until: Optional[float] = None
    last_cycle_end: Optional[str] = None

# ---------------------------------------------------------------------------
# Task YAML parsing
# ---------------------------------------------------------------------------

REQUIRED_TASK_FIELDS = {"id", "agent", "prompt", "output_path"}

def parse_task_yaml(path: Path) -> Optional[dict]:
    """Parse and validate a task YAML file. Returns None if invalid."""
    try:
        with open(path) as f:
            task = yaml.safe_load(f)
        if not isinstance(task, dict):
            return None
        missing = REQUIRED_TASK_FIELDS - set(task.keys())
        if missing:
            return None
        # Defaults
        task.setdefault("priority", "normal")
        task.setdefault("wake_on_complete", False)
        task.setdefault("timeout_minutes", 10)
        task.setdefault("allowed_tools", "Read,Write,Glob,Grep")
        task.setdefault("depends_on", [])
        return task
    except Exception:
        return None

def parse_result_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter from an agent's output file."""
    try:
        text = path.read_text()
        if not text.startswith("---"):
            return {"status": "unknown", "summary": "No frontmatter found"}
        end = text.index("---", 3)
        fm = yaml.safe_load(text[3:end])
        return fm if isinstance(fm, dict) else {}
    except Exception:
        return {"status": "unknown", "summary": "Failed to parse frontmatter"}

# ---------------------------------------------------------------------------
# History logging (append-only JSONL)
# ---------------------------------------------------------------------------

def append_history(logs_dir: Path, entry: dict):
    entry["logged_at"] = datetime.now(timezone.utc).isoformat()
    with open(logs_dir / "history.jsonl", "a") as f:
        f.write(json.dumps(entry) + "\n")

# ---------------------------------------------------------------------------
# State file management
# ---------------------------------------------------------------------------

def save_running_state(state_dir: Path, running_tasks: dict[str, RunningTask]):
    data = {tid: asdict(rt) for tid, rt in running_tasks.items()}
    with open(state_dir / "running.json", "w") as f:
        json.dump(data, f, indent=2)

def build_prompt_md(
    state_dir: Path,
    logs_dir: Path,
    wake_events: list[WakeEvent],
    running_tasks: dict[str, RunningTask],
    eternal_agents: dict[str, EternalAgentState],
    tasks_dir: Path,
) -> str:
    """Build the ephemeral prompt.md that the orchestrator receives."""
    now = datetime.now(timezone.utc).isoformat()
    lines = [f"## Current Time\n{now}\n"]

    # Wake reasons
    lines.append("## Wake Reason")
    if not wake_events:
        lines.append("- SCHEDULED: Regular interval check")
    else:
        for ev in wake_events:
            tid = f" {ev.task_id} —" if ev.task_id else ""
            lines.append(f"- {ev.type}:{tid} {ev.summary}")
    lines.append("")

    # Running task agents
    running_list = [rt for rt in running_tasks.values()]
    lines.append(f"## Currently Running Task Agents ({len(running_list)})")
    if not running_list:
        lines.append("(none)")
    else:
        for rt in running_list:
            lines.append(f"- {rt.task_id} | agent: {rt.agent} | started: {rt.started_at} | timeout: {rt.timeout_minutes} min")
    lines.append("")

    # Recently completed (last 20 from history.jsonl)
    lines.append("## Recently Completed")
    history_path = logs_dir / "history.jsonl"
    recent = []
    if history_path.exists():
        all_lines = history_path.read_text().strip().split("\n")
        for line in all_lines[-20:]:
            try:
                entry = json.loads(line)
                if entry.get("event") == "task_completed":
                    recent.append(entry)
            except json.JSONDecodeError:
                pass
    if not recent:
        lines.append("(none)")
    else:
        for entry in recent[-10:]:
            lines.append(f"- {entry.get('task_id', '?')} | {entry.get('finished_at', '?')} | {entry.get('summary', '?')}")
    lines.append("")

    # Eternal agents
    lines.append(f"## Eternal Agents ({len(eternal_agents)} configured)")
    for name, ea in eternal_agents.items():
        lines.append(f"\n### {name}")
        lines.append(f"- Status: {ea.status.upper()}")
        if ea.status == "sleeping" and ea.sleep_until:
            remaining = max(0, ea.sleep_until - time.time())
            lines.append(f"- Wakes in: {int(remaining // 60)} min {int(remaining % 60)} sec")
        if ea.last_cycle_end:
            lines.append(f"- Last cycle ended: {ea.last_cycle_end}")
        # Latest discovery
        disc_path = BASE_DIR / "agents" / "eternal" / name / "discoveries.md"
        if disc_path.exists():
            disc_lines = disc_path.read_text().strip().split("\n")
            if disc_lines:
                lines.append(f"- Latest discovery: {disc_lines[-1]}")
        # Memory size
        mem_path = BASE_DIR / "agents" / "eternal" / name / "memory.md"
        if mem_path.exists():
            size = mem_path.stat().st_size
            lines.append(f"- Memory size: {size / 1024:.1f}KB")
    lines.append("")

    # Pending tasks count
    pending = list((tasks_dir / "pending").glob("*.yaml"))
    lines.append(f"## Pending Tasks ({len(pending)})")
    if not pending:
        lines.append("(none)")
    else:
        for p in pending:
            task = parse_task_yaml(p)
            if task:
                lines.append(f"- {task['id']} | agent: {task['agent']} | priority: {task.get('priority', 'normal')}")
    lines.append("")

    result = "\n".join(lines)
    (state_dir / "prompt.md").write_text(result)
    return result

# ---------------------------------------------------------------------------
# Agent invocation helpers
# ---------------------------------------------------------------------------

def build_claude_cmd(
    system_prompt_path: Path,
    prompt_text: str,
    allowed_tools: str,
    model: str,
    timeout_minutes: int,
) -> list[str]:
    """Build the claude -p command."""
    cmd = [
        "claude", "-p",
        "--system-prompt", system_prompt_path.read_text(),
        "--allowedTools", allowed_tools,
        "--model", model,
    ]
    return cmd

async def run_claude(
    system_prompt_path: Path,
    prompt_text: str,
    allowed_tools: str,
    model: str,
    timeout_minutes: int,
    logger: logging.Logger,
    label: str = "agent",
    output_log_path: Optional[Path] = None,
) -> tuple[int, str]:
    """Run claude -p and return (exit_code, stdout).

    timeout_minutes=0 means no timeout (run indefinitely).
    If output_log_path is set, stdout is also written there for observability.
    """
    cmd = build_claude_cmd(system_prompt_path, prompt_text, allowed_tools, model, timeout_minutes)

    timeout_str = f"{timeout_minutes}m" if timeout_minutes > 0 else "none"
    logger.info(f"[{label}] Spawning claude -p (timeout: {timeout_str})")
    logger.debug(f"[{label}] Tools: {allowed_tools}")

    # Remove CLAUDECODE env var to allow nested sessions
    env = os.environ.copy()
    env.pop("CLAUDECODE", None)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        if timeout_minutes > 0:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt_text.encode()),
                timeout=timeout_minutes * 60,
            )
        else:
            stdout, stderr = await proc.communicate(input=prompt_text.encode())
    except asyncio.TimeoutError:
        logger.warning(f"[{label}] Timed out after {timeout_minutes} min, killing")
        proc.kill()
        await proc.wait()
        return -1, ""

    exit_code = proc.returncode
    output = stdout.decode() if stdout else ""

    # Write output to log file for observability
    if output_log_path:
        output_log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_log_path, "a") as f:
            f.write(f"\n--- [{label}] {datetime.now(timezone.utc).isoformat()} (exit: {exit_code}) ---\n")
            f.write(output[:5000] if output else "(no output)")
            f.write("\n")

    if stderr:
        logger.debug(f"[{label}] stderr: {stderr.decode()[:500]}")
    if exit_code != 0:
        logger.warning(f"[{label}] Exited with code {exit_code}")
    else:
        logger.info(f"[{label}] Completed successfully")

    return exit_code, output

# ---------------------------------------------------------------------------
# Daemon
# ---------------------------------------------------------------------------

class EternalDaemon:
    def __init__(self):
        self.config = load_config()
        self.logger = setup_logging(BASE_DIR / self.config["paths"]["logs_dir"])
        self.tasks_dir = BASE_DIR / self.config["paths"]["tasks_dir"]
        self.state_dir = BASE_DIR / self.config["paths"]["state_dir"]
        self.logs_dir = BASE_DIR / self.config["paths"]["logs_dir"]
        self.agents_dir = BASE_DIR / self.config["paths"]["agents_dir"]
        self.output_dir = BASE_DIR / self.config["paths"]["output_dir"]

        self.running_tasks: dict[str, RunningTask] = {}
        self.wake_queue: list[WakeEvent] = []
        self.orchestrator_running = False
        self.orchestrator_pid: Optional[int] = None
        self.eternal_agents: dict[str, EternalAgentState] = {}

        self.shutting_down = False
        self._task_futures: dict[str, asyncio.Task] = {}
        self._eternal_futures: dict[str, asyncio.Task] = {}

    # -- Directory setup --

    def ensure_dirs(self):
        for sub in ["pending", "running", "completed", "failed"]:
            (self.tasks_dir / sub).mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Init memory file if missing
        mem = self.state_dir / "orchestrator_memory.md"
        if not mem.exists():
            mem.write_text("# Orchestrator Memory\n\n(Empty — write anything here to remember it across runs.)\n")

        # Init todo if missing
        todo = self.state_dir / "todo.yaml"
        if not todo.exists():
            todo.write_text("# Persistent task queue — orchestrator reads/writes this\ntasks: []\n")

    # -- Crash recovery --

    def recover_running_tasks(self):
        """On startup, check tasks/running/ for orphaned tasks."""
        running_dir = self.tasks_dir / "running"
        for yaml_file in running_dir.glob("*.yaml"):
            task = parse_task_yaml(yaml_file)
            if not task:
                continue
            pid = task.get("pid")
            if pid and self._pid_alive(pid):
                self.logger.info(f"Recovering running task {task['id']} (pid {pid})")
                self.running_tasks[task["id"]] = RunningTask(
                    task_id=task["id"],
                    pid=pid,
                    agent=task["agent"],
                    started_at=task.get("started_at", "unknown"),
                    timeout_minutes=task.get("timeout_minutes", 10),
                    wake_on_complete=task.get("wake_on_complete", False),
                )
            else:
                self.logger.warning(f"Orphaned task {task['id']} — marking as failed")
                task["status"] = "failed"
                task["error"] = "daemon_restart: process not found"
                task["finished_at"] = datetime.now(timezone.utc).isoformat()
                with open(yaml_file, "w") as f:
                    yaml.dump(task, f)
                shutil.move(str(yaml_file), str(self.tasks_dir / "failed" / yaml_file.name))
                # Also move any prompt file
                prompt_file = running_dir / f"{yaml_file.stem}.prompt.md"
                if prompt_file.exists():
                    prompt_file.unlink()

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    # -- Discover eternal agents --

    def discover_eternal_agents(self):
        eternal_dir = self.agents_dir / "eternal"
        if not eternal_dir.exists():
            return
        for agent_dir in eternal_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            config_path = agent_dir / "config.yaml"
            if not config_path.exists():
                continue
            name = agent_dir.name
            self.eternal_agents[name] = EternalAgentState(name=name)
            self.logger.info(f"Discovered eternal agent: {name}")

    # -- Task agent lifecycle --

    async def watch_pending_tasks(self):
        """Poll tasks/pending/ for new task files."""
        pending_dir = self.tasks_dir / "pending"
        while not self.shutting_down:
            try:
                for yaml_file in sorted(pending_dir.glob("*.yaml")):
                    task = parse_task_yaml(yaml_file)
                    if not task:
                        self.logger.warning(f"Invalid task file: {yaml_file.name}, moving to failed")
                        shutil.move(str(yaml_file), str(self.tasks_dir / "failed" / yaml_file.name))
                        continue

                    # Check dependencies
                    deps = task.get("depends_on", [])
                    if deps:
                        completed_ids = {p.stem for p in (self.tasks_dir / "completed").glob("*.yaml")}
                        failed_ids = {p.stem for p in (self.tasks_dir / "failed").glob("*.yaml")}
                        # If any dep failed, fail this task too
                        if any(d in failed_ids for d in deps):
                            task["status"] = "failed"
                            task["error"] = "dependency_failed"
                            task["finished_at"] = datetime.now(timezone.utc).isoformat()
                            with open(yaml_file, "w") as f:
                                yaml.dump(task, f)
                            shutil.move(str(yaml_file), str(self.tasks_dir / "failed" / yaml_file.name))
                            self.logger.warning(f"Task {task['id']} failed: dependency_failed")
                            continue
                        # If not all deps completed, skip for now
                        if not all(d in completed_ids for d in deps):
                            continue

                    # Check concurrency limit
                    max_concurrent = self.config["agents"]["max_concurrent"]
                    if len(self.running_tasks) >= max_concurrent:
                        break  # Wait for a slot

                    # Spawn the task
                    await self.spawn_task_agent(yaml_file, task)

            except Exception as e:
                self.logger.error(f"Error in watch_pending_tasks: {e}")

            await asyncio.sleep(3)  # Poll every 3 seconds

    async def spawn_task_agent(self, yaml_path: Path, task: dict):
        """Move task to running/ and spawn claude -p."""
        task_id = task["id"]
        agent_name = task["agent"]
        template_path = self.agents_dir / "templates" / f"{agent_name}.md"

        if not template_path.exists():
            self.logger.error(f"No template for agent '{agent_name}', failing task {task_id}")
            task["status"] = "failed"
            task["error"] = f"Missing template: {agent_name}.md"
            task["finished_at"] = datetime.now(timezone.utc).isoformat()
            with open(yaml_path, "w") as f:
                yaml.dump(task, f)
            shutil.move(str(yaml_path), str(self.tasks_dir / "failed" / yaml_path.name))
            return

        # Build prompt
        prompt_text = f"""## Task
{task['prompt']}

## Output Instructions
Write your results to: {task['output_path']}

Use this YAML frontmatter format at the top of your output file:
---
task_id: {task_id}
status: completed|failed|error
summary: "One sentence summary of what you did"
error_message: "Only if status is failed/error"
---

Then write your full output below the frontmatter.
"""

        # Move to running
        started_at = datetime.now(timezone.utc).isoformat()
        task["started_at"] = started_at
        running_yaml = self.tasks_dir / "running" / yaml_path.name
        with open(yaml_path, "w") as f:
            yaml.dump(task, f)
        shutil.move(str(yaml_path), str(running_yaml))

        # Write prompt file
        prompt_path = self.tasks_dir / "running" / f"{yaml_path.stem}.prompt.md"
        prompt_path.write_text(prompt_text)

        self.logger.info(f"Spawning task agent: {task_id} (agent: {agent_name})")

        # Track it
        rt = RunningTask(
            task_id=task_id,
            pid=0,  # Will be set by the future
            agent=agent_name,
            started_at=started_at,
            timeout_minutes=task.get("timeout_minutes", self.config["agents"]["default_timeout_minutes"]),
            wake_on_complete=task.get("wake_on_complete", False),
        )
        self.running_tasks[task_id] = rt
        save_running_state(self.state_dir, self.running_tasks)

        # Spawn async
        future = asyncio.create_task(
            self._run_task_agent(task_id, template_path, prompt_text, task, running_yaml, prompt_path)
        )
        self._task_futures[task_id] = future

    async def _run_task_agent(
        self,
        task_id: str,
        template_path: Path,
        prompt_text: str,
        task: dict,
        running_yaml: Path,
        prompt_path: Path,
    ):
        model = self.config["claude"]["model"]
        allowed_tools = task.get("allowed_tools", "Read,Write,Glob,Grep")
        timeout = task.get("timeout_minutes", self.config["agents"]["default_timeout_minutes"])

        exit_code, output = await run_claude(
            system_prompt_path=template_path,
            prompt_text=prompt_text,
            allowed_tools=allowed_tools,
            model=model,
            timeout_minutes=timeout,
            logger=self.logger,
            label=f"task:{task_id}",
            output_log_path=self.logs_dir / f"task-{task_id}.log",
        )

        # Read result from output file
        output_path = BASE_DIR / task["output_path"]
        finished_at = datetime.now(timezone.utc).isoformat()
        result_summary = "No output file found"
        status = "failed" if exit_code != 0 else "completed"

        if output_path.exists():
            fm = parse_result_frontmatter(output_path)
            status = fm.get("status", status)
            result_summary = fm.get("summary", result_summary)

        if exit_code == -1:
            status = "failed"
            result_summary = f"Timed out after {timeout} minutes"

        # Update task YAML
        task["finished_at"] = finished_at
        task["exit_code"] = exit_code
        task["status"] = status
        task["result_summary"] = result_summary

        # Move to completed or failed
        dest_dir = self.tasks_dir / ("completed" if status == "completed" else "failed")
        with open(running_yaml, "w") as f:
            yaml.dump(task, f)
        shutil.move(str(running_yaml), str(dest_dir / running_yaml.name))

        # Cleanup prompt file
        if prompt_path.exists():
            prompt_path.unlink()

        # Remove from running
        self.running_tasks.pop(task_id, None)
        self._task_futures.pop(task_id, None)
        save_running_state(self.state_dir, self.running_tasks)

        # Log to history
        append_history(self.logs_dir, {
            "event": "task_completed" if status == "completed" else "task_failed",
            "task_id": task_id,
            "agent": task["agent"],
            "started_at": task.get("started_at"),
            "finished_at": finished_at,
            "status": status,
            "summary": result_summary,
        })

        self.logger.info(f"Task {task_id} -> {status}: {result_summary}")

        # Wake orchestrator?
        should_wake = (
            task.get("wake_on_complete", False)
            or status in ("failed", "error")
            and self.config["wake_on"].get("task_failed", True)
        )
        if should_wake:
            event_type = "TASK_COMPLETED" if status == "completed" else "TASK_FAILED"
            self.wake_queue.append(WakeEvent(
                type=event_type,
                task_id=task_id,
                summary=result_summary,
            ))
            if not self.orchestrator_running:
                asyncio.create_task(self.run_orchestrator())

    # -- Orchestrator lifecycle --

    async def run_orchestrator(self):
        """Run the orchestrator agent."""
        if self.orchestrator_running:
            self.logger.debug("Orchestrator already running, wake events queued")
            return
        if self.shutting_down:
            return

        self.orchestrator_running = True
        lock_path = self.state_dir / "orchestrator.lock"

        try:
            # Build prompt
            prompt_md = build_prompt_md(
                state_dir=self.state_dir,
                logs_dir=self.logs_dir,
                wake_events=self.wake_queue,
                running_tasks=self.running_tasks,
                eternal_agents=self.eternal_agents,
                tasks_dir=self.tasks_dir,
            )
            self.wake_queue.clear()

            # Load orchestrator memory
            memory_path = self.state_dir / "orchestrator_memory.md"
            memory = memory_path.read_text() if memory_path.exists() else ""

            full_prompt = f"{memory}\n\n---\n\n{prompt_md}"

            system_prompt_path = BASE_DIR / self.config["orchestrator"]["system_prompt"]
            if not system_prompt_path.exists():
                self.logger.error(f"Orchestrator system prompt not found: {system_prompt_path}")
                return

            # Write lock
            lock_path.write_text(str(os.getpid()))

            model = self.config["claude"].get("orchestrator_model", self.config["claude"]["model"])
            timeout = self.config["orchestrator"].get("timeout_minutes", 15)
            allowed_tools = self.config["orchestrator"].get("allowed_tools", "Read,Write,Edit,Glob,Grep")

            self.logger.info("=== Orchestrator waking up ===")

            exit_code, output = await run_claude(
                system_prompt_path=system_prompt_path,
                prompt_text=full_prompt,
                allowed_tools=allowed_tools,
                model=model,
                timeout_minutes=timeout,
                logger=self.logger,
                label="orchestrator",
                output_log_path=self.logs_dir / "orchestrator_output.log",
            )

            append_history(self.logs_dir, {
                "event": "orchestrator_run",
                "exit_code": exit_code,
                "wake_reasons": [asdict(ev) for ev in self.wake_queue],  # Any that arrived during run
            })

            self.logger.info(f"=== Orchestrator done (exit: {exit_code}) ===")

        except Exception as e:
            self.logger.error(f"Orchestrator error: {e}")
        finally:
            self.orchestrator_running = False
            if lock_path.exists():
                lock_path.unlink()

            # If new wake events arrived during the run, run again
            if self.wake_queue and not self.shutting_down:
                self.logger.info("New wake events during orchestrator run, re-waking")
                asyncio.create_task(self.run_orchestrator())

    async def orchestrator_timer(self):
        """Wake the orchestrator on a regular interval."""
        interval = self.config["orchestrator"]["interval_minutes"] * 60
        # Wait a bit on startup to let things settle
        await asyncio.sleep(5)
        # Run immediately on startup
        await self.run_orchestrator()

        while not self.shutting_down:
            await asyncio.sleep(interval)
            if not self.shutting_down:
                self.wake_queue.append(WakeEvent(
                    type="SCHEDULED",
                    task_id=None,
                    summary=f"Regular {self.config['orchestrator']['interval_minutes']}-minute interval",
                ))
                await self.run_orchestrator()

    # -- Eternal agent lifecycle --

    async def run_eternal_agent_loop(self, name: str):
        """Main loop for an eternal agent — run, sleep, repeat."""
        agent_dir = self.agents_dir / "eternal" / name
        config_path = agent_dir / "config.yaml"

        with open(config_path) as f:
            agent_config = yaml.safe_load(f)

        template_path = agent_dir / "template.md"
        memory_path = agent_dir / "memory.md"
        discoveries_path = agent_dir / "discoveries.md"
        sleep_path = agent_dir / "sleep.yaml"
        interrupt_path = agent_dir / "interrupt.md"

        if not template_path.exists():
            self.logger.error(f"Eternal agent {name}: missing template.md")
            return

        # Ensure memory exists
        if not memory_path.exists():
            memory_path.write_text("# Memory\n\n(First cycle — no prior memory.)\n")
        if not discoveries_path.exists():
            discoveries_path.write_text("")

        model = self.config["claude"]["model"]
        allowed_tools = agent_config.get("allowed_tools", "Read,Write,Edit,Glob,Grep,WebFetch,WebSearch")
        # Eternal agents have no timeout by default — they run as long as they need
        timeout = agent_config.get("timeout_minutes", 0)
        default_sleep = agent_config.get("default_sleep_minutes", 60)
        max_sleep = agent_config.get("max_sleep_minutes", 360)
        min_sleep = agent_config.get("min_sleep_minutes", 5)

        while not self.shutting_down:
            ea = self.eternal_agents[name]
            ea.status = "running"

            # Build prompt
            memory = memory_path.read_text() if memory_path.exists() else "(no memory yet)"

            interrupt_msg = "None"
            if interrupt_path.exists():
                content = interrupt_path.read_text().strip()
                if content:
                    interrupt_msg = content
                    interrupt_path.write_text("")  # Clear after reading

            prompt = f"""## Your Memory (everything you know)

{memory}

---

## Interrupt Message
{interrupt_msg}

---

Continue your work from where you left off. Remember: before finishing, you MUST update your memory file and write your sleep preferences."""

            self.logger.info(f"[eternal:{name}] Starting cycle")

            exit_code, output = await run_claude(
                system_prompt_path=template_path,
                prompt_text=prompt,
                allowed_tools=allowed_tools,
                model=model,
                timeout_minutes=timeout,
                logger=self.logger,
                label=f"eternal:{name}",
                output_log_path=self.logs_dir / f"eternal-{name}.log",
            )

            ea.status = "sleeping"
            ea.last_cycle_end = datetime.now(timezone.utc).isoformat()

            # Log the cycle
            append_history(self.logs_dir, {
                "event": "eternal_cycle",
                "agent": name,
                "exit_code": exit_code,
                "finished_at": ea.last_cycle_end,
            })

            # Determine sleep duration
            sleep_minutes = default_sleep
            if sleep_path.exists():
                try:
                    sleep_data = yaml.safe_load(sleep_path.read_text())
                    if isinstance(sleep_data, dict) and "sleep_minutes" in sleep_data:
                        sleep_minutes = int(sleep_data["sleep_minutes"])
                        sleep_minutes = max(min_sleep, min(max_sleep, sleep_minutes))
                except Exception:
                    pass

            self.logger.info(f"[eternal:{name}] Sleeping for {sleep_minutes} min")
            ea.sleep_until = time.time() + sleep_minutes * 60

            # Sleep, but check for interrupts
            sleep_end = time.time() + sleep_minutes * 60
            while time.time() < sleep_end and not self.shutting_down:
                # Check for interrupt
                if interrupt_path.exists() and interrupt_path.read_text().strip():
                    self.logger.info(f"[eternal:{name}] Interrupted during sleep!")
                    break
                await asyncio.sleep(5)  # Check every 5 seconds

            ea.sleep_until = None

    # -- Signal handling --

    def handle_shutdown(self, signum, frame):
        self.logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutting_down = True

    # -- Main --

    async def run(self):
        self.logger.info("=" * 50)
        self.logger.info("Eternal Daemon starting")
        self.logger.info(f"Base directory: {BASE_DIR}")
        self.logger.info("=" * 50)

        self.ensure_dirs()
        self.recover_running_tasks()
        self.discover_eternal_agents()

        # Signal handlers
        signal.signal(signal.SIGINT, self.handle_shutdown)
        signal.signal(signal.SIGTERM, self.handle_shutdown)

        # Start all loops
        tasks = [
            asyncio.create_task(self.watch_pending_tasks()),
            asyncio.create_task(self.orchestrator_timer()),
        ]

        # Start eternal agent loops
        for name in self.eternal_agents:
            future = asyncio.create_task(self.run_eternal_agent_loop(name))
            self._eternal_futures[name] = future
            tasks.append(future)

        self.logger.info(f"Running with {len(self.eternal_agents)} eternal agents")
        self.logger.info(f"Orchestrator interval: {self.config['orchestrator']['interval_minutes']} min")
        self.logger.info(f"Max concurrent tasks: {self.config['agents']['max_concurrent']}")
        self.logger.info("Watching tasks/pending/ for new tasks...")
        self.logger.info("")

        # Wait until shutdown
        try:
            await asyncio.gather(*tasks, return_exceptions=True)
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")

        # Graceful shutdown
        self.logger.info("Saving state before exit...")
        save_running_state(self.state_dir, self.running_tasks)
        self.logger.info("Daemon stopped.")


def main():
    daemon = EternalDaemon()
    asyncio.run(daemon.run())


if __name__ == "__main__":
    main()

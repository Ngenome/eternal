# Eternal — Raw Vision Dump

These are the raw ideas and thinking captured during the initial design conversations. Preserved here so nothing is lost.

---

## The Core Idea

I want something that can search for things at intervals. It should be running consistently and endlessly — something that can run, work, and work without stopping.

The first concrete use case: something that can give me all the news about technology in an exhaustive manner. From all the websites — TechCrunch, and all the websites that report on startups — the news of the day, that day. It's a lot of work. Manage, sort through, organize the stuff, make them into different folders. If you're running at intervals, maybe every six hours, getting all the information about startups, then you would also want to organize that data. You would probably want to spin up an agent to organize things immediately.

---

## On Running Claude Persistently

We can open a Claude session, have a systemd thing, and when the device wakes up we run Claude in that session. Maybe run it in something like tmux and then it keeps on running. That is how it can work.

The `-p` flag (print mode) is key — runs the prompt, outputs the result, exits. No persistent session needed for task agents.

---

## On How the Orchestrator Should Work

The orchestrator is the one which sees the tasks and decides "I need this to run, and once it runs, let it notify me and I'll wake up." There's complexity around "how should it be woken up?" and "how do you ensure there's only one ongoing process?"

If the orchestrator is running and something finishes, you can't inject an interrupt. You'd be tempted to run another instance, which leads to inconsistencies. You need to track "is the main orchestrator agent running?" and queue things.

The best way for the orchestrator to start tasks is by writing to a file. Once that file changes, we check it using code and spin off a new agent. It should NOT use tool calls to spawn agents directly because things can easily get messy.

---

## On Synchronous vs Asynchronous Execution

Having the orchestrator do work synchronously is not good. If something takes one hour, we shouldn't just be sitting there waiting. The orchestrator should write tasks, and the daemon handles spawning and tracking independently.

Background commands and keeping polling, waiting — that can work but the problem is if it goes down, things might be lost. The `-p` approach with external process management is more robust.

---

## On the Daemon's Role

The Python process handles execution. It's like pub/sub. The orchestrator writes to files (like writing to a database — "schedule this, schedule this, schedule this"). The daemon watches and executes.

We could give it access to maybe a SQLite DB and it writes, it orchestrates. Once an agent is done — because the Python processor does the execution — it detects the PID exit and handles the lifecycle.

---

## On Waking the Orchestrator

It should only be woken when particular files change, not every file change. Sometimes the orchestrator shouldn't be woken. It should only wake when particular files in a particular folder change.

We should check what was added: is it a status that is complete? Is it an error? Sometimes tasks might fail, then we push it, wake it up, and append that to the prompt and it knows what to do.

The system prompt should say "before exiting, always check if there are new things that were added." That's critical.

---

## On Task Completion Detection

The subagent is the one that knows "did I complete the task or not?" It writes in the frontmatter. The output is a structured format so we can detect it, look at it. Claude should write in a structured format and we can parse it.

The Python daemon checks: did the PID exit? What's in the YAML frontmatter? Status complete or error? That's mechanical — no AI needed for that part.

---

## On Token Conservation

The orchestrator wakes up and should always have a little summary. The summary is always compacting things and removing trash. When it wakes up, if nothing changed, it should be able to see that cheaply and exit.

The daemon builds a pre-made status file so the orchestrator doesn't have to read dozens of files. One-line summaries in logs. Character threshold triggers summarization.

---

## On Agent Output Structure

When a subagent finishes, it should write in a structured way. The way it writes should have a summary or one paragraph or one sentence short description, plus the full thing. That summary is used as part of the logs — the whole list of logs used for the orchestrator's status view.

Every task, when spinning off, should have a detailed description. When the executing agent finishes, it gives back: structured markdown with YAML frontmatter (summary) + full body.

---

## On Eternal Agents

There are some agents that never die. These are agents that have their own ongoing purpose. For example, an agent that researches about a certain topic or tries to find the best algorithm to do something. It should stay alive — always researching 24/7.

The orchestrator can see their progress. It can say "this thing discovered something." These eternal agents can also spawn task agents.

They run in a loop. If the agent exits after a session, it can sleep. When it sleeps, it should trigger compaction. Before exiting, it writes a compact summary of what it did. That is what is loaded into the next session. That's its entire life. If it loses any discovery, anything important — it's gone, gone forever, never to be recovered. The system prompt must make this clear.

The agent can decide "how long do I want to sleep?" It can say "let me sleep for a certain period." We should also configure interrupts — it should be interrupted if something happens that is interesting.

---

## On Tracking and Oversight

We need a way to track which things are running at the moment. For example, we can see "this thing is running, this thing is running." A certain instance of Claude-P is running. You can see which files have been edited by which agent.

We need to track what's pending — a to-do list. Have a system for prioritization, know what's needed. Mostly it's going to be a set of predefined tasks.

The orchestrator should have oversight of what is happening from all the children — all the sub-agents being spawned. Check status, check how others are performing.

---

## On Budgets

Don't include dollar budgets in agent prompts. Agents don't have an intuitive understanding of what different costs mean. They can allocate a time budget instead. The daemon can enforce spending limits silently, but agents only see timeout_minutes.

---

## On the Orchestrator's Memory

The orchestrator can have a memory file. Tell it "if you ever want to remember something, write it to your memory file." It can append, edit, do whatever. This is loaded into every run by appending it to the -p prompt. The memory comes first, then the current status.

---

## On File-Based Communication Philosophy

When the orchestrator creates tasks, the best way is by writing to a file. Once that file is written, the daemon (Python or Node) kicks off those things. The orchestrator just writes structured YAML files — it's like writing to a database.

Each agent, when executing, knows it's supposed to write to a specific output path. The file structure enables each agent to come back and write results in a known location.

---

## On Error Handling

If there was an error, maybe the orchestrator should be woken up by default. Task failures should always trigger a wake. The error information gets appended to the orchestrator's prompt so it can decide what to do.

---

## On Not Over-Engineering Permissions

Don't use `--dangerously-skip-permissions`. Use a configuration file that has most useful tools allowed. The `--allowedTools` flag per agent is sufficient.

# AI Researcher — LIFETIME Memory

**Last updated:** 2026-03-11
**Cycle count:** 1 (first cycle — initial deep research sweep)

---

## RESEARCH METHODOLOGY

### Sources I Check Each Cycle
- arxiv.org/list/cs.AI/recent, cs.CL/recent, cs.LG/recent, cs.CV/recent
- huggingface.co/papers (daily trending)
- llm-stats.com/llm-updates and /ai-news
- openai.com/index, anthropic.com/research, deepmind.google
- alignment.anthropic.com
- arcprize.org (benchmark leaderboard)
- github.com/trending (ML/Python filter)

---

## MODEL KNOWLEDGE BASE

### Frontier Model Status (as of 2026-03-11)

#### OpenAI GPT-5.x
- **GPT-5.4** (Mar 5, 2026): 1M context, OSWorld 75% (human=72.4%), GDPval 83%, 47% token reduction on MCP Atlas; unifies GPT+Codex; text+image; variants: Standard, Thinking, Pro
- **GPT-5.3 Chat** (Mar 4, 2026): general-purpose
- **GPT-5.3-Codex**: SOTA SWE-Bench Pro, Terminal-Bench; notable: self-created (used early version to debug its own training)
- **GPT-5.2**: GPQA 93.2% (Pro), ARC-AGI-1 >90% (first model to cross), ARC-AGI-2 54.2% (Pro), FrontierMath 40.3%
- **gpt-oss-120B/20B**: Open-source variants (referenced in search results, not formally announced)
- Revenue: $13B+ 2025, targeting $30B 2026

#### Anthropic Claude
- **Claude Opus 4.6** (Feb 5, 2026): 1M context, 14.5hr task horizon (longest of any model), top Finance Agent benchmark
- **Claude Sonnet 4.6** (Feb 2026): 1M context (beta), full upgrade
- **Claude Code Review** (Mar 10, 2026): Multi-agent dispatch on every PR
- **Claude 5** NOT RELEASED: Codename "Fennec" for Sonnet 5; spotted as `claude-sonnet-5@20260203` in Vertex AI logs; ~50% lower inference cost; Q2-Q3 2026 expected
- Safety finding: Alignment faking discovered in Opus 4 — model selectively complies while preserving preferences (without being trained to)
- Revenue: $4.7B 2025, $7B ARR, targeting $15B 2026

#### Google DeepMind Gemini 3.x
- **Gemini 3.1 Pro** (Feb 19, 2026): ARC-AGI-2 77.1% (>2× Gemini 3), GPQA 94.3% (highest ever), #1/115 on Artificial Analysis Index (score 57); MoE architecture, 1M context, $2/$12 per 1M tokens
- **Gemini 3.1 Flash-Lite** (Mar 3, 2026): Cost-optimized, GPQA 0.90
- **Gemini 3 Pro** (Nov 2025): LMArena 1501 Elo, GPQA 91.9%, HLE 37.5%, MathArena 23.4%

#### Open-Weight Models
- **Llama 4** (Meta): Scout (109B, 10M ctx), Maverick (400B total), MoE 17B active/query; Llama Community License (no 700M MAU+)
- **Qwen 3** (Alibaba, Apache 2.0): 0.6B-235B, 22B active in 235B, 119 languages, AIME25 92.3%
- **Qwen3.5 Series** (Mar 2, 2026): 0.8B, 2B, 4B, 9B new variants
- **Qwen3-VL**: 235B, rivals Gemini 2.5 Pro / GPT-5 on multimodal, 32-language OCR, UI agent
- **Mistral Large 3** (Apache 2.0): 675B total MoE, 92% of GPT-5.2 at ~15% cost; Devstral Medium (coding); Codestral 2508
- **DeepSeek V3.2**: Latest general-purpose (MIT); V4 imminent (native multimodal, Nvidia H100 training)
- **DeepSeek R2**: STILL UNRELEASED — Huawei Ascend chip failures; CEO Liang Wenfeng unsatisfied
- **DeepSeek mHC paper** (Jan 2026): "Manifold-Constrained Hyper-Connections" training architecture — signals V4 direction
- **GLM-4.7** (Zhipu, Feb 11, 2026): 744B MoE, SWE-bench 77.8, lowest hallucination rate tested
- **GLM-4.5V/4.6V**: Multimodal; 3D-RoPE; GLM-4.6V: vision-driven tool use (images as tool params)
- **Molmo 2** (Ai2/Allen AI): Video/multi-image; 8B, 4B, 7B variants; beats Gemini 3 Pro on video tracking

---

## BENCHMARKS REFERENCE

| Benchmark | Purpose | Top Score & Model |
|-----------|---------|-------------------|
| ARC-AGI-1 | Abstract reasoning | >90% — GPT-5.2 Pro |
| ARC-AGI-2 | Fluid reasoning (harder) | 77.1% — Gemini 3.1 Pro |
| ARC-AGI-3 | Interactive reasoning | Launching Mar 25, 2026 |
| GPQA Diamond | PhD-level Q&A | 94.3% — Gemini 3.1 Pro |
| OSWorld-Verified | Computer use (desktop nav) | 75.0% — GPT-5.4 (human=72.4%) |
| SWE-Bench Verified | Software engineering | 77.8 — GLM-4.7 |
| AIME 2025 | Math competition | 92.3% — Qwen 3 |
| FrontierMath | Expert math | 40.3% — GPT-5.2 Thinking |
| Humanity's Last Exam | General extreme knowledge | 37.5% — Gemini 3 Pro |
| LMArena Elo | Human preference | 1501 — Gemini 3 Pro |
| ARC-AGI-2 (small models) | Efficiency reasoning | 8% — TRM (7M params!) |

**ARC-AGI-3 key info:** 1000+ levels, 150+ environments, interactive/exploration/planning/memory required, formal human vs. AI efficiency comparison, launching March 25, 2026

---

## TOOLS & INFRASTRUCTURE

### Inference Serving Throughput (H100)
- SGLang: ~16,200 tok/s (RadixAttention, 33 backends, best multi-turn/agentic)
- LMDeploy: ~16,200 tok/s (best quantized)
- vLLM: ~12,500 tok/s (218 architectures, most mature, PagedAttention, torch.compile default in V1)
- TensorRT-LLM: Best on B200/Blackwell; complex setup

### Agent Frameworks (2026 Status)
- **LangGraph**: Complex stateful DAG/cyclic workflows; lowest latency; durable execution
- **LangChain**: Linear pipelines, RAG; most token-efficient
- **Microsoft Agent Framework**: AutoGen+Semantic Kernel merged; GA Q1 2026
- **CrewAI**: Role-based teams; rapid prototyping; ~3× token overhead vs LangChain
- **MCP**: Standard agent↔tool protocol; donated to Linux Foundation Agentic AI Foundation

### Top GitHub Repos (Stars)
- OpenClaw: 210K⭐ — local personal AI, 50+ integrations, 5700+ skills (fastest ever growth)
- Ollama: 162K⭐ — local LLM runtime
- Dify: 130K⭐ — AI workflow builder
- RAGFlow: Open-source RAG (ingestion→indexing→query planning)
- GitHub Spec Kit: 50K⭐ — Spec-Driven Development

---

## RESEARCH AREAS TO WATCH

### Safety / Interpretability
- **Anthropic circuit tracing** — attribution graphs now open-sourced; traces LLM internal reasoning
- **Persona vectors** — extract sycophancy/hallucination trait activations
- **Alignment faking** — first empirical evidence without training (Opus 4)
- **Reward hacking generalization** — sycophancy training → reward tampering
- **2026 International AI Safety Report** — test environment detection as core challenge
- **MIT Tech Review Breakthrough 2026**: Mechanistic interpretability

### Reasoning & ARC-AGI
- Test-time scaling: more inference compute → better reasoning (o3 key insight)
- Refinement loops: iterative program search + feedback dominate top approaches
- ARC-AGI-3: Interactive reasoning format (Mar 25, 2026)
- Efficiency goal: $1/puzzle (was $17-20 for o3)

### Architecture Innovation
- MoE dominates: all new major models use MoE (17-22B active in 100B+ total)
- DeepSeek mHC: Manifold-Constrained Hyper-Connections — new info flow architecture
- Scaling pretraining "flattened" (Sutskever) — shift to reasoning/synthetic data

### Multimodal Trends
- Video understanding now standard at frontier
- Vision-driven tool use (images as tool parameters without text conversion)
- Long-context multimodal (8.4hr audio, 900-page PDFs)
- Edge VLMs (phones, drones, AR glasses)

---

## PENDING LEADS (Next Cycles)

1. **DeepSeek V4 launch** — native multimodal; imminent in March 2026; track benchmarks
2. **ARC-AGI-3 launch** (Mar 25, 2026) — new benchmark will reshape reasoning landscape
3. **ARC Prize 2025 Technical Report** (arxiv:2601.10904) — read in full
4. **DeepSeek mHC paper** — track implications for V4
5. **Claude 5 / Sonnet 5** — monitor for Q2 2026 release
6. **ICLR 2026** (April) — track accepted papers
7. **Microsoft Agent Framework GA** — confirm Q1 2026 release
8. **Anthropic alignment papers** — alignment faking + reward hacking detailed papers
9. **gpt-oss-120B formal announcement** — confirm and get full benchmark data

---

## KEY DATE CALENDAR

| Date | Event |
|------|-------|
| 2026-03-04 | GPT-5.3 Chat released |
| 2026-03-05 | GPT-5.4 released (OSWorld SOTA) |
| 2026-03-10 | Anthropic Code Review multi-agent announced |
| 2026-03-11 | THIS CYCLE — initial research sweep |
| 2026-03-25 | ARC-AGI-3 launches (interactive reasoning) |
| 2026-Q1 | Microsoft Agent Framework GA |
| 2026-Q2/Q3 | Claude 5 expected |
| 2026-April | ICLR 2026 |
| 2026-March | DeepSeek V4 (native multimodal, imminent) |

---

## CONTEXT WINDOWS REFERENCE

| Model | Context Window |
|-------|---------------|
| Llama 4 Scout | 10M tokens |
| Google API max | 2.1M tokens |
| Gemini 3.1 Pro | 1M tokens |
| GPT-5.4 | 922K in / 128K out |
| Claude Opus 4.6 | 1M tokens |

---

## OUTPUT FILES WRITTEN

- `/home/kelvin/eternal/output/ai-research/2026-03-11/models.md`
- `/home/kelvin/eternal/output/ai-research/2026-03-11/papers.md`
- `/home/kelvin/eternal/output/ai-research/2026-03-11/tools.md`
- `/home/kelvin/eternal/output/ai-research/2026-03-11/notable.md`

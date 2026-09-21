# Design Spec: Open-Source LLM Support for Help & Recommendation Agents

- **Date:** 2026-09-20
- **Issues:** Implements #11; explicitly excludes #12 (see Out of scope)
- **Status:** Approved. Implementation by @aadib2; unit tests and live validation by the coding agent on return.
- **Approach:** Standardize both agents on the OpenAI **chat-completions** API via the existing `openai` SDK, with a configurable `base_url` so any OpenAI-compatible server works: Ollama, vLLM, LM Studio, llama.cpp server, LocalAI — or hosted OpenAI (default).

## 1. Problem

Every chat-LLM call in FireLink is coupled to a closed hosted vendor:

| Component | File | SDK | Model | Capability used |
|---|---|---|---|---|
| Help Agent (SMS) | `backend/app/services/agents/help_agent.py` | `anthropic` | `claude-sonnet-4-6` | tool calling (`notify_dispatch`) |
| Recommendation Agent | `backend/app/services/agents/recommendation_agent.py` → `base_agent.py` | `openai` | `gpt-4o-mini` | JSON mode (`response_format`) |

As an open-source digital public good, FireLink needs a fully local option: cost (per-message API spend), privacy (SMS messages contain sensitive household data), and vendor independence.

## 2. Decisions

- **D1 — Chat completions, not the Responses API.** Ollama, vLLM, LM Studio, and llama.cpp all implement `/v1/chat/completions`; none implement OpenAI's newer Responses API. The Responses API would recreate the lock-in this task removes. Chat completions supports both tools (function calling) and JSON mode, which covers everything the agents use today.
- **D2 — One vendor dialect; drop the `anthropic` SDK.** Both agents speak OpenAI chat-completions. Hosted OpenAI remains the closed default; any OpenAI-compatible local server is a drop-in via `base_url`.
- **D3 — Defaults unchanged.** With no new env vars set, the stack runs hosted OpenAI exactly as it does today (modulo D2: the Help Agent's closed default moves from Claude to an OpenAI model). Local models are opt-in.
- **D4 — Scope: chat agents only.** Embeddings stay `text-embedding-3-small` + Pinecone (1536-dim index). Swapping embeddings requires re-ingestion and is a follow-up (issue #11 marks it optional). `OPENAI_API_KEY` therefore remains a required env var.
- **D5 — Issue #12 refactor excluded.** The Help Agent keeps its one-shot, full-context prompt. The new `llm.py` interface is shaped so the tool-driven/agentic-loop redesign (#12) can land on top later without another rewrite.

## 3. Architecture

New module `backend/app/services/llm.py` (~150 lines) — the only place that talks to an LLM server:

- `get_client()` — lazy singleton `AsyncOpenAI`:
  - `base_url` from `OPENAI_BASE_URL`; unset → hosted `api.openai.com` (today's behavior); e.g. `http://localhost:11434/v1` → local Ollama.
  - `api_key` = `OPENAI_API_KEY`; when a custom `base_url` is set and no key exists, use a placeholder (local servers ignore keys). No `base_url` and no key → loud `RuntimeError` at construction (keeps the fail-loud style of `base_agent.py`).
- `ToolCall(name: str, arguments: dict)` and `LLMResult(text: str | None, tool_calls: list[ToolCall])` — normalized result types bridging providers' dialects (only OpenAI dialect remains, but normalization still absorbs the JSON-string `arguments` quirk).
- `async complete_sms(model, system, user, tools) -> LLMResult` — Help Agent path. Sends OpenAI-format function tools; normalizes `message.tool_calls` into `ToolCall`s.
- `async complete_json(model, system, user, temperature=0.3) -> dict` — Recommendation Agent path. Sends `response_format={"type": "json_object"}` and owns the recovery parser moved from `base_agent.py`: `json.loads` → markdown-fence / first-`{...}` extraction (DOTALL) → raise.

## 4. Configuration

| Var | Default | Meaning |
|---|---|---|
| `OPENAI_BASE_URL` | unset → hosted OpenAI | e.g. `http://localhost:11434/v1` (Ollama), any OpenAI-compatible server |
| `HELP_MODEL` | `gpt-4o` | Help Agent model; `gpt-4o` chosen to match Claude Sonnet's tool-reliability class for the emergency `notify_dispatch` decision |
| `RECOMMENDATION_MODEL` | `gpt-4o-mini` | preserves the current default |

- New `backend/.env.example` documenting all vars — the root `.gitignore` already whitelists `!.env.example`. `backend/.env` (real secrets) is never modified.
- `OPENAI_API_KEY` stays required (embeddings still use it, `ingest.py` / `rag_query.py`).

## 5. File-by-file changes

- **`backend/app/services/llm.py` (new)** — module described in section 3.
- **`backend/app/services/agents/help_agent.py`** — remove `anthropic` import and `_call_claude`; call `llm.complete_sms`. Convert `NOTIFY_DISPATCH_TOOL` to the OpenAI function schema (`{"type": "function", "function": {"name", "description", "parameters"}}`). Tool-call handling reads the normalized `ToolCall`. One-shot flow, dispatch ack message, system prompt, and context assembly are unchanged.
- **`backend/app/services/agents/base_agent.py`** — `call_llm` delegates to `llm.complete_json`; remove direct `AsyncOpenAI` construction and the inline recovery parser. Model name from `RECOMMENDATION_MODEL`. Kafka producer logic untouched. `recommendation_agent.py` requires no changes.
- **`backend/app/services/knowledge/rag_query.py`** — remove the module-level `import anthropic` (it would crash once the dependency is gone), the commented-out legacy `call_claude`/`query_agent`/`build_prompt` block, and the broken `__main__` block (it references names that no longer exist — running the module crashes today). Active helpers (`load_mock_users`, `serialize_user_profile`, `retrieve_chunks`, `PROJECT_ROOT`) unchanged.
- **`backend/requirements.txt`** — remove `anthropic==0.125.0` (and with it the anyio pin workaround from commit 2efca83) and `groq` (zero code references; if ever needed, Groq is reachable via `OPENAI_BASE_URL`).
- **`backend/test/smoke_test.py`** — `HELP_AGENT_KEYS` becomes `("OPENAI_API_KEY", "PINECONE_API_KEY")` (embeddings still OpenAI; Anthropic key no longer needed); update the section label text.
- **`backend/docker-compose.yml`** — pass `OPENAI_BASE_URL`, `HELP_MODEL`, `RECOMMENDATION_MODEL` through to `backend` and `recommendation-agent`; drop `ANTHROPIC_API_KEY`; add `extra_hosts: ["host.docker.internal:host-gateway"]` to those two services so containers can reach host Ollama at `http://host.docker.internal:11434/v1`. Hybrid dev-mode (`make dev-api`) uses plain `http://localhost:11434/v1`.
- **`docs/architecture-breakdown.md`, `docs/streaming-pipeline.md`** — update the provider table; add a "Local models" section: Ollama setup, recommended model `qwen3.5:27b` (solid function-calling + JSON; available locally), and caveats (`deepseek-r1:7b` is unsuitable — reasoning model, not tool-trained, emits think traces; `llama3.2:3b` / `granite4.1:3b` work for smoke tests but are weaker at tool reliability).

## 6. Error handling

- **Malformed JSON tool arguments** (local models do this occasionally): `complete_sms` retries the call once, then propagates — the SMS route already maps failures to HTTP 502 with a logged exception (`app/routes/sms.py`), so externally visible behavior is unchanged.
- **JSON mode unsupported by a server**: the recovery parser in `complete_json` still extracts valid JSON from raw text; worst case a clear error propagates.
- **No `OPENAI_BASE_URL` and no `OPENAI_API_KEY`**: loud `RuntimeError` at client construction.

## 7. Testing & acceptance

**Unit tests (new, by the coding agent):**

- `backend/test/test_llm.py` (pytest, added to a new `requirements-dev.txt`, runnable via a `make unit` target) — fake responses, no network, no running stack:
  - `complete_sms` passes the function-tool schema through correctly (fake client captures request kwargs),
  - `tool_calls` normalization including JSON-string `arguments` parsing and the malformed-arguments retry,
  - `complete_json` recovery parser: clean JSON, markdown-fenced JSON, JSON embedded in prose, garbage → raises.

**Live validation (Ollama, by the coding agent, with the implementer):**

- Set `OPENAI_BASE_URL=http://localhost:11434/v1`, `HELP_MODEL=qwen3.5:27b`, `RECOMMENDATION_MODEL=qwen3.5:27b`.
- `make sms`: an emergency case fires `notify_dispatch` (tool call round-trips); an info case returns a clean 1–3 sentence reply.
- `make sms-replay` and `make test` pass.
- `firelink.recommendations` Kafka stream carries valid `{advisory, reasoning, risk_level, generated_at}` JSON.

**Acceptance criteria (from issue #11):**

- [ ] `HELP_MODEL` / `RECOMMENDATION_MODEL` overridable via env, defaulting to current-vendor-equivalent behavior
- [ ] Help Agent produces SMS replies through an OSS model with working `notify_dispatch` tool calls
- [ ] Recommendation Agent emits valid `{advisory, reasoning, risk_level, generated_at}` JSON through an OSS model
- [ ] `make sms` and `make test` pass with the alternative provider
- [ ] Docs updated (`docs/architecture-breakdown.md`, `docs/streaming-pipeline.md`)

## 8. Out of scope

- Embedding model swap + embedding centralization (Pinecone index is fixed at 1536 dims; requires re-ingestion) — follow-up.
- Issue #12: tool-driven lazy-context Help Agent, unified tool registry shared with the MCP server, agentic loop.
- README rework (issue #10).
- Any modification to `backend/.env`.

## 9. Known risk

Open PR #9 ("Backend", opened May) touches backend files and will likely conflict with these changes — close or rebase it separately before merging this work.

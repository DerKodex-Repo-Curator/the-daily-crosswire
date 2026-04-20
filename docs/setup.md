# Setup

This is what to do on a fresh machine to get The Daily Crosswire running.

## Prerequisites

- **Docker Desktop 4.x+** (or any docker-compose v2 runtime). Tested on macOS;
  should work on Linux and WSL2 without changes.
- **An OpenAI-compatible chat endpoint.** Options:
  - [OpenAI](https://platform.openai.com/): easiest.
  - [OpenRouter](https://openrouter.ai/): access to Anthropic, Mistral, Meta,
    Google, etc. under the OpenAI protocol.
  - [Groq](https://console.groq.com/): fast open-weights inference.
  - Local: `vLLM`, `Ollama`, `LM Studio`, `llama.cpp` with an OpenAI-compatible
    server. See the "Swapping LLM providers" section below.
- **(Optional) Ollama for local embeddings.** The default config points
  embeddings at `http://host.docker.internal:11434/v1` with
  `EMBEDDING_MODEL=nomic-embed-text`. If you don't have Ollama running, either
  install it ([ollama.com](https://ollama.com/)) and `ollama pull nomic-embed-text`,
  or leave `EMBEDDING_API_BASE` and `EMBEDDING_API_KEY` blank so embeddings
  fall back to your chat provider.

## First-time bring-up

```bash
# 1. Copy the env template and edit it.
cp .env.example .env

# 2. (One-time) Pull the embedding model if you're using local Ollama.
ollama pull nomic-embed-text   # ~274 MB, fast on CPU

# 3. Start the stack.
docker compose up -d --build

# 4. Smoke-test that every service came up.
curl -sf http://localhost:8000/api/health                    # {"status":"ok"}
curl -sf -o /dev/null -w "%{http_code}\n" http://localhost:5173/
curl -sf "http://localhost:8890/search?q=test&format=json" | head -c 200
docker exec newspaper-db-1 psql -U np -d newspaper \
  -c "SELECT extname, extversion FROM pg_extension WHERE extname='vector';"
```

All four must succeed before declaring the stack healthy. If anything fails,
see [operations.md](operations.md#troubleshooting).

## Environment variables

Everything lives in `.env` at the repo root. The example file documents each
key inline. The important ones:

| Key                     | Default                                         | Notes                                                                 |
| ----------------------- | ----------------------------------------------- | --------------------------------------------------------------------- |
| `DATABASE_URL`          | `postgresql+psycopg://np:np@db:5432/newspaper`  | Don't change unless running the backend outside docker-compose.       |
| `SEARXNG_URL`           | `http://searxng:8080`                           | Service-to-service name. Not the host port (8890).                    |
| `OPENAI_API_BASE`       | `https://api.openai.com/v1`                     | Any OpenAI-compatible chat endpoint.                                  |
| `OPENAI_API_KEY`        | `sk-replace-me`                                 | **Required.** Replace with a real key.                                |
| `OPENAI_MODEL`          | `gpt-4o-mini`                                   | The model name your provider expects. e.g. `anthropic/claude-sonnet-4.6` for OpenRouter. |
| `EMBEDDING_API_BASE`    | _(empty, falls back to `OPENAI_API_BASE`)_      | Separate endpoint for embeddings. Useful for mixing providers.        |
| `EMBEDDING_API_KEY`     | _(empty, falls back to `OPENAI_API_KEY`)_       | Separate key for embeddings.                                          |
| `EMBEDDING_MODEL`       | `nomic-embed-text`                              | Default assumes local Ollama. Set to `text-embedding-3-small` if using OpenAI. |
| `EMBEDDING_DIM`         | `768`                                           | Must match the model's output dimension. See "Changing embedding dim" below. |
| `DEDUP_SIM_THRESHOLD`   | `0.88`                                          | Cross-issue semantic dedup threshold (against `story_log`). Lower is more aggressive. |
| `SELECT_INTRA_SIM_THRESHOLD` | `0.75`                                     | Intra-issue safety-net dedup threshold, applied after the LLM dedup pass on title+summary embeddings. Looser than cross-issue because same-day outlets paraphrase heavily. |
| `SELECT_BATCH_SIZE`     | `10`                                            | Max candidates shown to the LLM `select` call per chunk. Topics with more items are batched. |
| `SELECT_MAX_KEPT_PER_BATCH` | `5`                                         | Hard cap on how many items a single select batch can keep. The prompt asks the LLM to rank best-first; the code slices as a safety net. |
| `LLM_TIMEOUT_SECONDS`   | `300`                                           | Per-LLM-call runtime timeout (enforced via `asyncio.wait_for`). Some proxies silently hang; SDK-level timeouts alone don't always save you. |
| `LLM_MAX_RETRIES`       | `3`                                             | Attempts per LLM call before the batch is dropped. Applies to timeout + parse failures. |
| `OLLAMA_API_BASE`       | _(empty)_                                       | Optional: when both this and `OLLAMA_MODEL` are set, the agent switches to `langchain-ollama` native tool calling instead of the OpenAI-compat shim. Should NOT include `/v1`. Example: `http://host.docker.internal:11434`. |
| `OLLAMA_MODEL`          | _(empty)_                                       | Ollama model tag, e.g. `qwen3:14b`. Only used when `OLLAMA_API_BASE` is also set. |
| `RSS_POLL_INTERVAL_HOURS` | `1`                                           | How often the global RSS poller runs. etag/modified make repeat polls cheap. |

After editing `.env`, recreate the backend so the new env is loaded:

```bash
docker compose up -d --force-recreate backend
```

`docker compose restart backend` is NOT enough: it re-reads code but not
the env_file.

## Swapping LLM providers

### OpenAI

```
OPENAI_API_BASE=https://api.openai.com/v1
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
EMBEDDING_API_BASE=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DIM=1536           # see note below if changing from 768
```

### OpenRouter (chat) + local Ollama (embeddings)

```
OPENAI_API_BASE=https://openrouter.ai/api/v1
OPENAI_API_KEY=sk-or-v1-...
OPENAI_MODEL=anthropic/claude-sonnet-4.6

EMBEDDING_API_BASE=http://host.docker.internal:11434/v1
EMBEDDING_API_KEY=ollama
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
```

### Fully local (Ollama native, recommended for local)

Use the `OLLAMA_*` override instead of the OpenAI-compat shim. Native mode
goes through Ollama's `/api/chat` tool-calling path, which is materially
more reliable for the structured-output calls the agent makes.

```
# Leave the OPENAI_* chat vars as-is; the override takes precedence.
OLLAMA_API_BASE=http://host.docker.internal:11434
OLLAMA_MODEL=qwen3:14b

EMBEDDING_API_BASE=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
```

**Model choice for local.** `qwen3:14b` is the current recommendation: it
handles the flat `{keep_ids, lead_id}` tool-calling schema cleanly and
stays under `LLM_TIMEOUT_SECONDS` on Apple Silicon. `qwen3.5:9b` is
faster/newer but has open Ollama bugs on its tool-call template
(issues [14493](https://github.com/ollama/ollama/issues/14493) and
[14745](https://github.com/ollama/ollama/issues/14745)). Avoid until
fixed. Gemma 4 26B MoE hangs on any nested list-of-objects schema.

### Fully local via OpenAI-compat shim (fallback)

If you prefer to keep a single transport path, you can point
`OPENAI_API_BASE` at Ollama's compat endpoint instead:

```
OPENAI_API_BASE=http://host.docker.internal:11434/v1
OPENAI_API_KEY=ollama
OPENAI_MODEL=qwen3:14b

EMBEDDING_API_BASE=
EMBEDDING_API_KEY=
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIM=768
```

Quality trade-off: the agent's `select`, `draft`, `critique`,
`editorial`, and `dedup` nodes rely on structured output
(`with_structured_output`). Small local models often produce unparseable
JSON. If drafts come back empty, look at the issue's warnings for
`OutputParserException`. Either use a bigger local model, switch to
Ollama native mode above (more reliable structured output), or use a
hosted provider.

## Changing the embedding dimension

The pgvector columns are fixed at 768. If you swap to an embedding model
with a different dimension (e.g. OpenAI's `text-embedding-3-small` at 1536),
you need to migrate:

```bash
# 1. Edit EMBEDDING_DIM in .env.example AND .env to the new value.
# 2. Write a migration that swaps the Vector(768) columns to Vector(N).
#    See backend/alembic/versions/6c90dd2ce7e1_switch_embedding_dim_to_768.py
#    for a template; change NEW_DIM and the downgrade constants.
# 3. docker compose exec backend alembic upgrade head
# 4. Recreate the backend so it picks up the new EMBEDDING_DIM:
#    docker compose up -d --force-recreate backend
# 5. Clear stored embeddings (optional; they're the old dim):
docker exec newspaper-db-1 psql -U np -d newspaper \
  -c "UPDATE news_items SET embedding = NULL; UPDATE story_log SET rendered_title_embedding = NULL;"
```

Existing stories will be re-embedded on the next agent run.

## Using the app

1. Open <http://localhost:5173>.
2. Go to **Configs** → **New config**.
3. Pick a schedule: "Every N days" (interval) or "Specific weekdays"
   (cron-style). Set the run hour in UTC. Both schedule kinds honor it
   (interval mode anchors the N-day cycle to the next occurrence of that
   UTC hour, so every fire lands on the same hour).
4. Pick an **output language** (`English`, `Spanish`, `French`,
   `Italian`, `Portuguese`, `German`). Drafts, the editorial, the
   masthead strings, and the long-form date are rendered in this
   language. The agent translates multilingual source candidates into
   the target language at draft time.
5. Save. Then add one or more **Topics**. For each topic:
   - Optionally add domain filters (`arxiv.org`, `theverge.com`).
   - Optionally add search hints (free text, e.g. "prefer academic coverage").
   - Optionally add RSS feed URLs. Topics without feeds will use SearXNG.
6. Back on the config page, click **Generate now**. On an Apple M4 Pro
   with 48 GB unified RAM the run takes 15-30 minutes depending on LLM
   latency and topic count. The "Last run" card updates when it finishes.
7. Open the **Newspapers** tab or click through from the config page to
   preview the rendered issue. **Print / Save as PDF** uses the browser's
   native dialog.

## Ongoing behavior

- **The global RSS poller** (APScheduler) runs every hour and refreshes all
  feeds across all configs. It only requests what has changed (etag +
  last-modified), so unchanged feeds are nearly free.
- **Per-config generation jobs** fire according to each config's schedule.
  Interval configs use `IntervalTrigger(days=N)`; weekdays configs use
  `CronTrigger(day_of_week=..., hour=run_hour)`.
- **Inactive configs** don't run. Toggle the **Active** checkbox on the
  config page to pause without deleting.
- **Scheduled jobs persist across restarts** (via APScheduler's
  SQLAlchemyJobStore). They're also re-registered from the DB on every
  backend startup, so the source of truth is `newspaper_configs.active`.

## Troubleshooting

Common failure modes:

- **`OPENAI_API_KEY is not configured`** when the agent runs: you forgot to
  replace `sk-replace-me`. Update `.env` and recreate the backend
  (`docker compose up -d --force-recreate backend`).
- **Embedding endpoint refuses connection.** If using local Ollama, make
  sure it is running (`ollama serve` or Ollama.app running in the
  menu bar). `host.docker.internal` resolves to the host from inside
  containers on Mac/Windows; on Linux you may need
  `--add-host=host.docker.internal:host-gateway`.
- **SearXNG returns 502 to feedparser.** Some hosts block the default
  feedparser user-agent. The default user-agent is overridden to a
  browser-ish string in `backend/app/services/rss.py`. If you add a feed
  that still fails, check the backend logs: `docker compose logs backend -f`.
- **Port 5433/8890 already in use.** Another project is using them. Stop
  that service, or edit the `ports:` block in `docker-compose.yml` to pick
  different host ports.
- **`docker compose up` fails with "outside of rootfs".** A known Docker
  Desktop issue with individual-file bind mounts. All mounts in this repo
  are directory-level (except the read-only project-root mount), so this
  shouldn't happen. If it does, check whether someone edited
  `docker-compose.yml` to mount individual files.

See [operations.md](operations.md#troubleshooting) for a deeper list,
including "agent failed" / "puzzle generation failed" / "scheduler not
firing" debugging.

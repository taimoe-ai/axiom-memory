# Axiom

**One memory, every AI.**

AI memory as an MCP server — one brain shared by ChatGPT,
Claude (Code / Desktop / claude.ai), Gemini CLI, and any other MCP client.

Every AI app today keeps its own siloed memory: what ChatGPT knows about you,
Claude doesn't, and none of it is yours. Axiom is a self-hosted memory server
you own — your assistants read and write the same curated facts through MCP,
and the data lives in your Postgres, exportable to plain markdown at any time.

Memories are curated facts (one per record), not conversation logs. Postgres is
the source of truth; a markdown export gives you a human-readable, git-friendly
mirror.

## Features

- **Shared across apps** — ChatGPT, claude.ai, Claude Code, Gemini CLI, and any
  MCP client talk to the same memory over streamable HTTP or local stdio.
- **Curated, not logged** — `remember` stores one fact per record with
  server-side dedup screening; no conversation-log landfill.
- **Hybrid recall** — full-text search + trigram + pgvector semantic similarity
  (Gemini embeddings), decayed by recency. CJK-friendly. On a miss it returns
  the full memory index so the caller can re-query.
- **Episodic layer** — `log_event` captures cheap one-line ambient signals that
  never enter recall; `axiom review` clusters recent events and surfaces
  recurring patterns as candidates for promotion to a real memory.
- **Graceful degradation** — no Gemini key? Recall is lexical-only and nothing
  breaks.
- **Your data, portable** — `axiom export` dumps everything to markdown for a
  git-friendly backup.
- **Real auth** — Google OAuth (with Dynamic Client Registration for
  ChatGPT/claude.ai connectors) plus a static service token for headless
  callers, coexisting on the same endpoint.

## Architecture

```
Claude Code / Gemini CLI / any MCP client
        │  streamable HTTP, Authorization: Bearer <token>
        ▼
   axiom MCP server  (FastMCP)
        │
        ▼
   PostgreSQL  ──►  markdown export (git backup)
   (hybrid recall: FTS + trigram + pgvector semantic
    similarity via Gemini embeddings, decayed by recency)
```

MCP tools: `remember`, `recall`, `forget`, `list_memories`, `log_event`.
CLI: `axiom serve`, `axiom export`, `axiom review`, `axiom embed`.

## Quick start

Requires [uv](https://docs.astral.sh/uv/) and Docker.

```sh
git clone https://github.com/taimoe-ai/axiom-memory && cd axiom-memory
docker compose up -d          # local Postgres (pgvector)
cp .env.example .env
uv run axiom serve            # stdio MCP server (migrations run on first call)
```

Register with Claude Code (local stdio, no auth needed):

```sh
claude mcp add axiom -- uv --directory /path/to/axiom run axiom serve
```

Then paste [instructions/USAGE.md](instructions/USAGE.md) into each client's
system prompt / custom instructions so models know when to call the tools.

## Connecting clients to a deployed server

Point Claude Code at the HTTP server — it detects the OAuth flow and opens a
browser to log in with Google:

```sh
claude mcp add --transport http axiom https://axiom.example.com/mcp
```

ChatGPT: Settings → Connectors → Add custom connector →
`https://axiom.example.com/mcp` (it discovers OAuth and walks through the
Google login). claude.ai: Settings → Connectors → Add custom connector, same
URL.

Headless scripts (curl, CI, cron) skip OAuth with the service token:

```sh
curl -s https://axiom.example.com/mcp \
  -H "Authorization: Bearer $AXIOM_SERVICE_TOKEN" \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

## Self-hosting

Runs the app and Postgres together on one box over the compose network:

```sh
cp .env.example .env    # fill in the variables below
docker compose --profile full up -d --build
```

The app serves streamable HTTP on `$PORT` (8080) at `/mcp`. Memory access is
stateless, but the OAuth proxy keeps client registrations and encrypted
upstream tokens in a named volume (`oauth_state`) so restarts don't force
ChatGPT/Claude to re-authenticate.

The OAuth flow needs a public HTTPS endpoint (e.g. a Cloudflare Tunnel) that
forwards `/.well-known/*`, `/authorize`, `/token`, `/register` and
`/auth/callback` in addition to `/mcp`.

### Configuration

| Variable | Purpose |
| --- | --- |
| `AXIOM_DATABASE_URL` | Postgres DSN (compose wires this up for you) |
| `AXIOM_BASE_URL` | Public origin the OAuth endpoints are served from |
| `AXIOM_GOOGLE_CLIENT_ID` / `AXIOM_GOOGLE_CLIENT_SECRET` | Google OAuth web app, redirect URI `<base_url>/auth/callback` |
| `AXIOM_ALLOWED_EMAILS` | Comma-separated allowlist for Google login |
| `AXIOM_SERVICE_TOKEN` | Static bearer token for headless callers |
| `AXIOM_GEMINI_API_KEY` | Enables semantic recall (768-dim Gemini embeddings); empty = lexical-only |
| `POSTGRES_PASSWORD` | Database password (compose) |

All three OAuth variables must be set together; leave them empty for local
stdio use, which needs no auth at all. After enabling `AXIOM_GEMINI_API_KEY`
on an existing database, run `axiom embed` once to backfill vectors.

## Development

```sh
docker compose up -d          # local Postgres
uv run pytest                 # tests (uses a separate axiom_test database)
uv run axiom serve --transport http   # http://127.0.0.1:8080/mcp
uv run axiom export           # dump all memories to ./exports as markdown
```

Auth internals are documented in `src/axiom/auth.py`; schema lives in
`src/axiom/migrations/`.

## Status

Personal project, actively used daily by its author. Issues and PRs are
welcome, but no support or stability guarantees yet — the MCP tool surface may
still change.

## License

[MIT](LICENSE)

# 🤖 Telegram MCP SSE Agent  
**Session 8 – Telegram-Triggered Multi-MCP Agent**

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-blue.svg" alt="Python 3.9+">
  <img src="https://img.shields.io/badge/MCP-SSE_Transport-green.svg" alt="MCP SSE Transport">
  <img src="https://img.shields.io/badge/Telegram-Bot-blue.svg" alt="Telegram Bot">
  <img src="https://img.shields.io/badge/Status-Active-success.svg" alt="Status: Active">
</div>

---

## 🚀 Overview

This workspace orchestrates a reasoning agent that **wakes up when a Telegram bot receives a message**, reasons over the user’s request, and dispatches work to multiple **Model Context Protocol (MCP)** servers.  

- The **Telegram bridge server** exposes messages via **Server-Sent Events (SSE) MCP transport**.  
- The **agent** consumes those events, enters a **perception → plan → act** loop, and calls specialized MCP servers (math, docs, web, Gmail, Google Sheets) over **stdio** or **HTTP/SSE**.

---

## 🧩 Architecture Overview

Telegram Bot ──> mcp_server_telegram_sse.py (SSE transport with MCP tools)
                           │
                           ▼
                     agent.py (perception → plan → act loop)
                           │
        ┌──────────────────┴─────────────────┐
        ▼                                    ▼
  stdio MCP servers                   HTTP/SSE MCP servers
  (mcp_server_1/2/3.py)          (gmail, gsheet, telegram)


1) **Telegram MCP SSE Server** (`mcp_server_telegram_sse.py`)  
- Hosts `/webhook` for Telegram updates, queues messages, and exposes MCP tools (`next_telegram_message`, `latest_telegram_message`) over `SseServerTransport`.  
- Optionally spawns `agent.py` after each webhook.

2) **Agent Runtime** (`agent.py`)  
- Waits for Telegram SSE events, uses `core/` infrastructure (context, memory, strategy) and `modules/` (perception, decision, action) to reason and call MCP tools via a `MultiMCP` dispatcher.

3) **Specialized MCP Servers**  
- `mcp_server_1.py` – arithmetic & demo tools (**stdio**).  
- `mcp_server_2.py` – document utilities.  
- `mcp_server_3.py` – web search/fetch.  
- `mcp_server_gmail.py` – Gmail REST bridge (**HTTP**).  
- `mcp_server_gsheet.py` – Google Sheets creation & updates (**HTTP**).  
- Additional servers can be declared in `config/profiles.yaml`.

---
## Running the Stack

1. **Start MCP Servers** (separate shells/tmux panes)
   ```bash
   uv run mcp_server_telegram_sse.py   # :8081
   uv run mcp_server_gmail.py          # :8082
   uv run mcp_server_gsheet.py         # :8083
   uv run mcp_server_1.py              # stdio (repeat for server_2/server_3)
   ```

2. **Expose Telegram Webhook**  
   Point your bot’s webhook to `https://<public-host>/webhook` (use `ngrok http 8081` or similar).

3. **Run the Agent**  
   ```bash
   uv run agent.py
   ```
   The agent blocks until a Telegram message arrives, then enters the plan/act loop, optionally writing results to Google Sheets and emailing links via the Gmail MCP.

---

## Key MCP Tools

| Server | Tool | Description |
| --- | --- | --- |
| `mcp_server_telegram_sse.py` | `next_telegram_message`, `latest_telegram_message` | Consume queued Telegram messages over SSE transport. |
| `mcp_server_gmail.py` | `send_email` | Uses Gmail REST API (base64url MIME) to send messages. |
| `mcp_server_gsheet.py` | `create_sheet`, `write_data` | Calls Google Sheets API to create spreadsheets and write ranges. |
| `mcp_server_1.py` | `add`, `sqrt`, `subtract`, … | Math/demo utilities (stdio transport). |
| `mcp_server_2.py` | Document parsing/search tools. |
| `mcp_server_3.py` | Web search and content fetch. |

Add new servers by editing `config/profiles.yaml -> mcp_servers`.

## Repository Layout

| Path | Purpose |
| --- | --- |
| `agent.py` | Entry point: listens for Telegram messages, runs the reasoning loop, outputs final answers, and writes results to Sheets/email. |
| `core/` | Session management, strategy loop, context/memory persistence, MultiMCP dispatcher. |
| `modules/` | Perception, decision, action parsing, model management, and tool/memory helpers. |
| `mcp_server_*.py` | Individual MCP servers (stdio or HTTP/SSE). |
| `config/profiles.yaml` | Agent persona, LLM selection, memory config, and MCP server registry. |
| `documents/`, `faiss_index/` | Local document corpus & vector index. |
| `pyproject.toml`, `uv.lock` | Dependency definitions for `uv`/`pip`. |

---
## 🗺️ Visual Flow (Mermaid)

### Telegram → Agent Orchestration (High-Level)
```mermaid
graph LR
    A[User] -->|Message| B[Telegram Bot]
    B -->|Webhook| C[Ngrok/Public URL]
    C -->|POST /webhook| D[Telegram MCP SSE Server]
    D -->|SSE /mcp| E[Agent]
    E -->|Orchestrates| F[Multi-MCP Servers]
    F -->|Results| E
    E -->|Reply/Email/Sheet| D
    D -->|Telegram API| B
    B -->|Message| A


sequenceDiagram
    participant U as User
    participant T as Telegram Bot
    participant W as Webhook (/webhook)
    participant S as Telegram MCP SSE
    participant A as Agent (perception→plan→act)
    participant M as MultiMCP
    participant G as Gmail MCP
    participant H as GSheet MCP
    participant D as Docs MCP
    participant Wb as Web MCP

    U->>T: Send message
    T->>W: Webhook POST (JSON update)
    W->>S: Queue message + expose via MCP tools
    A->>S: Connect via SSE (/mcp)
    S->>A: Stream new message event

    A->>A: Perception (intent/entities)
    A->>A: Plan (tool selection/strategy)
    A->>M: Execute tool call(s)

    alt Needs web data
      M->>Wb: web_fetch/web_summary
      Wb->>M: results
    end
    alt Needs spreadsheet
      M->>H: create_sheet/write_data
      H->>M: sheet URL / write results
    end
    alt Needs email
      M->>G: send_email (sheet link or results)
      G->>M: confirmation
    end

    M->>A: Aggregated results
    A->>S: Final answer
    S->>T: sendMessage
    T->>U: Response delivered


import asyncio
import json
import logging
import os
from contextlib import suppress
from typing import Any, Dict, Set
import subprocess
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse, StreamingResponse


load_dotenv()


logger = logging.getLogger("telegram_sse_server")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Telegram SSE Bridge")

# Global state for broadcasting messages to connected SSE clients.
app.state.event_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
app.state.clients: Set[asyncio.Queue[Dict[str, Any]]] = set()
app.state.clients_lock = asyncio.Lock()
app.state.latest_message: Dict[str, Any] | None = None
app.state.broadcast_task: asyncio.Task | None = None

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    logger.warning(
        "Environment variable TELEGRAM_BOT_TOKEN is not set. Telegram webhook validation may fail."
    )


async def broadcast_loop() -> None:
    """Read messages from the central queue and fan them out to all clients."""
    while True:
        message = await app.state.event_queue.get()
        async with app.state.clients_lock:
            if not app.state.clients:
                logger.debug("No SSE clients connected; message queued but not delivered.")
            # Iterate over a copy to avoid set size changes during iteration.
            for client_queue in list(app.state.clients):
                # Only block the broadcaster if the client queue is full.
                await client_queue.put(message)
        app.state.event_queue.task_done()


@app.on_event("startup")
async def startup_event() -> None:
    logger.info("Starting Telegram SSE bridge server.")
    app.state.broadcast_task = asyncio.create_task(broadcast_loop())


@app.on_event("shutdown")
async def shutdown_event() -> None:
    logger.info("Shutting down Telegram SSE bridge server.")
    broadcast_task: asyncio.Task | None = app.state.broadcast_task
    if broadcast_task is not None:
        broadcast_task.cancel()
        with suppress(asyncio.CancelledError):
            await broadcast_task


def extract_text_message(update: Dict[str, Any]) -> Dict[str, Any] | None:
    """Extract sender and text content from a Telegram update payload."""
    message = update.get("message") or update.get("edited_message") or {}
    text = message.get("text")
    if not text:
        return None

    sender_info = message.get("from") or {}
    sender = (
        sender_info.get("username")
        or sender_info.get("first_name")
        or str(sender_info.get("id", "unknown"))
    )

    return {"sender": sender, "text": text, "raw": update}


@app.post("/webhook")
async def telegram_webhook(request: Request) -> JSONResponse:
    try:
        update = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload.",
        ) from exc

    logger.debug("Received Telegram update: %s", update)
    extracted = extract_text_message(update)
    if extracted is None:
        logger.info("Received Telegram update without text message; ignoring.")
        return JSONResponse({"ok": True, "ignored": True})

    app.state.latest_message = extracted
    await app.state.event_queue.put(extracted)

    try:
        subprocess.Popen(
        ["uv", "run", "agent.py"],  # run agent.py in a new process
        cwd=os.path.dirname(__file__),  # run from current folder
        )
        logger.info("🚀 Triggered agent.py subprocess.")
    except Exception as e:
        logger.error(f"Failed to start agent.py: {e}")
    logger.info("Queued message from %s: %s", extracted["sender"], extracted["text"])
    return JSONResponse({"ok": True})


@app.get("/events")
async def sse_events() -> StreamingResponse:
    client_queue: asyncio.Queue[Dict[str, Any]] = asyncio.Queue(maxsize=10)

    async with app.state.clients_lock:
        app.state.clients.add(client_queue)
        logger.info("Client connected. Total SSE clients: %s", len(app.state.clients))

    async def event_generator() -> Any:
        try:
            while True:
                message = await client_queue.get()
                payload = json.dumps({"query": message["text"]})
                yield f"data: {payload}\n\n"
        except asyncio.CancelledError:
            raise
        finally:
            async with app.state.clients_lock:
                app.state.clients.discard(client_queue)
                logger.info(
                    "Client disconnected. Total SSE clients: %s",
                    len(app.state.clients),
                )

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
    }
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=headers,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "mcp_server_telegram_sse:app",
        host="127.0.0.1",
        port=8081,
        log_level="info",
        reload=False,
    )

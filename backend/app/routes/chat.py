"""Streaming chat endpoint.

POST /chat -> Server-Sent Events. We stream the agent's run via `astream_events`, emitting:
  - token       : an LLM text delta
  - tool_start  : the agent invoked a Spotify tool (id + name + input)
  - tool_end    : a tool finished (id + name + duration + how many items came back)
  - done        : the turn completed
  - error       : something failed (surfaced to the client instead of dropping the stream)

`id` on the tool events is the run's `run_id`, so the client can pair an end with its start
even when several tools run concurrently. The frontend renders these as a per-turn trace of
what the agent actually did.

Conversation memory is keyed by `thread_id = session_id` via the agent's checkpointer.

The same event stream is mirrored into a TurnRecorder (see turnlog.py), which writes one
JSONL record per turn. Note that tool *results* are recorded but deliberately not sent to
the client — the frontend renders the agent's prose, not the raw Spotify payloads.
"""

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from ..schemas import ChatRequest
from ..turnlog import TurnRecorder

router = APIRouter()

logger = logging.getLogger(__name__)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    agent = request.app.state.agent

    async def event_stream():
        config = {"configurable": {"thread_id": req.session_id}}
        inputs = {"messages": [HumanMessage(content=req.message)]}
        rec = TurnRecorder(req.session_id, req.message)
        try:
            async for event in agent.astream_events(inputs, config=config, version="v2"):
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    text = chunk.content if isinstance(chunk.content, str) else ""
                    if text:
                        rec.on_token(text)
                        yield _sse("token", {"text": text})
                elif kind == "on_chat_model_end":
                    output = event["data"].get("output")
                    rec.on_usage(getattr(output, "usage_metadata", None))
                elif kind == "on_tool_start":
                    tool_input = event["data"].get("input")
                    rec.on_tool_start(event["name"], tool_input)
                    yield _sse(
                        "tool_start",
                        {"id": event["run_id"], "name": event["name"], "input": tool_input},
                    )
                elif kind == "on_tool_end":
                    summary = rec.on_tool_end(event["name"], event["data"].get("output"))
                    yield _sse(
                        "tool_end",
                        {"id": event["run_id"], "name": event["name"], **summary},
                    )
            yield _sse("done", {})
        except Exception as exc:  # noqa: BLE001 - surface any failure to the client
            rec.fail(exc)
            logger.exception("turn %s failed", rec.turn_id)
            yield _sse("error", {"message": str(exc)})
        finally:
            # Also covers a client disconnecting mid-stream, which cancels this generator.
            duration_ms = rec.flush()
            logger.info(
                "turn %s session=%s tools=%d %dms",
                rec.turn_id,
                req.session_id,
                rec.tool_count,
                duration_ms,
            )

    return StreamingResponse(event_stream(), media_type="text/event-stream")

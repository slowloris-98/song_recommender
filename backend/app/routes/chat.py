"""Streaming chat endpoint.

POST /chat -> Server-Sent Events. We stream the agent's run via `astream_events`, emitting:
  - token       : an LLM text delta
  - tool_start  : the agent invoked a Spotify tool (name + input)
  - tool_end    : a tool finished
  - done        : the turn completed
  - error       : something failed (surfaced to the client instead of dropping the stream)

Conversation memory is keyed by `thread_id = session_id` via the agent's checkpointer.
"""

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage

from ..schemas import ChatRequest

router = APIRouter()


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    agent = request.app.state.agent

    async def event_stream():
        config = {"configurable": {"thread_id": req.session_id}}
        inputs = {"messages": [HumanMessage(content=req.message)]}
        try:
            async for event in agent.astream_events(inputs, config=config, version="v2"):
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"]
                    text = chunk.content if isinstance(chunk.content, str) else ""
                    if text:
                        yield _sse("token", {"text": text})
                elif kind == "on_tool_start":
                    yield _sse(
                        "tool_start",
                        {"name": event["name"], "input": event["data"].get("input")},
                    )
                elif kind == "on_tool_end":
                    yield _sse("tool_end", {"name": event["name"]})
            yield _sse("done", {})
        except Exception as exc:  # noqa: BLE001 - surface any failure to the client
            yield _sse("error", {"message": str(exc)})

    return StreamingResponse(event_stream(), media_type="text/event-stream")

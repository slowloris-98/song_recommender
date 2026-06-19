"""LangGraph ReAct agent: the LLM + Spotify MCP tools + per-session memory.

`MemorySaver` (an in-memory checkpointer) stores conversation state keyed by `thread_id`
(we use the frontend's session_id), giving multi-turn memory. For production, swap
MemorySaver for a persistent checkpointer (e.g. SqliteSaver/PostgresSaver).
"""

from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

from .prompts import RECOMMENDATION_AGENT_SYSTEM_PROMPT


def build_agent(llm, tools):
    return create_agent(
        llm,
        tools,
        system_prompt=RECOMMENDATION_AGENT_SYSTEM_PROMPT,
        checkpointer=MemorySaver(),
    )

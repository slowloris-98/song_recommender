const BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

// POST /chat and consume the Server-Sent Events stream.
// Calls onEvent({ event, data }) for each SSE message (token / tool_start / tool_end / done / error).
export async function streamChat({ sessionId, message, onEvent, signal }) {
  const resp = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
    signal,
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`Request failed: ${resp.status}`);
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE messages are separated by a blank line.
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";
    for (const block of blocks) {
      const ev = parseSSE(block);
      if (ev) onEvent(ev);
    }
  }
}

function parseSSE(block) {
  let event = "message";
  let data = "";
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }
  if (!data) return null;
  try {
    return { event, data: JSON.parse(data) };
  } catch {
    return { event, data: {} };
  }
}

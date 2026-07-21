import { useCallback, useRef, useState } from "react";
import { streamChat } from "../api";

// Persist a session_id so the backend keeps conversation memory across page reloads.
function getSessionId() {
  let id = localStorage.getItem("session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("session_id", id);
  }
  return id;
}

// Mark every still-running step as failed. A turn can die mid-tool (backend error, MCP
// server down), and without this those steps spin forever.
const failOpenSteps = (steps = []) =>
  steps.map((s) => (s.status === "running" ? { ...s, status: "error" } : s));

export function useChat() {
  // messages: [{ role, content, steps?: [{ id, name, input, status, ms, count }] }]
  //   role   : "user" | "assistant"
  //   status : "running" | "done" | "error"
  const [messages, setMessages] = useState([]);
  const [busy, setBusy] = useState(false);
  const sessionId = useRef(getSessionId());

  const send = useCallback(
    async (text) => {
      if (!text.trim() || busy) return;
      setBusy(true);
      setMessages((m) => [
        ...m,
        { role: "user", content: text },
        { role: "assistant", content: "", steps: [] },
      ]);

      // Mutate the last (assistant) message as the stream arrives.
      const updateAssistant = (fn) =>
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = fn(copy[copy.length - 1]);
          return copy;
        });

      try {
        await streamChat({
          sessionId: sessionId.current,
          message: text,
          onEvent: ({ event, data }) => {
            if (event === "token") {
              updateAssistant((a) => ({ ...a, content: a.content + data.text }));
            } else if (event === "tool_start") {
              updateAssistant((a) => ({
                ...a,
                steps: [
                  ...(a.steps || []),
                  { id: data.id, name: data.name, input: data.input, status: "running" },
                ],
              }));
            } else if (event === "tool_end") {
              // Pair by id rather than name so concurrent calls to the same tool don't
              // close each other's step.
              updateAssistant((a) => ({
                ...a,
                steps: (a.steps || []).map((s) =>
                  s.id === data.id
                    ? { ...s, status: "done", ms: data.ms, count: data.count }
                    : s
                ),
              }));
            } else if (event === "error") {
              updateAssistant((a) => ({
                ...a,
                steps: failOpenSteps(a.steps),
                content: a.content + `\n\n[error: ${data.message}]`,
              }));
            }
          },
        });
      } catch (e) {
        updateAssistant((a) => ({
          ...a,
          steps: failOpenSteps(a.steps),
          content: a.content + `\n\n[error: ${e.message}]`,
        }));
      } finally {
        setBusy(false);
      }
    },
    [busy]
  );

  return { messages, busy, send };
}

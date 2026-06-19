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

export function useChat() {
  // messages: [{ role: "user" | "assistant", content: string, tools?: string[] }]
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
        { role: "assistant", content: "", tools: [] },
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
              updateAssistant((a) => ({ ...a, tools: [...(a.tools || []), data.name] }));
            } else if (event === "error") {
              updateAssistant((a) => ({
                ...a,
                content: a.content + `\n\n[error: ${data.message}]`,
              }));
            }
          },
        });
      } catch (e) {
        updateAssistant((a) => ({ ...a, content: a.content + `\n\n[error: ${e.message}]` }));
      } finally {
        setBusy(false);
      }
    },
    [busy]
  );

  return { messages, busy, send };
}

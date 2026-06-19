import { useState } from "react";
import { useChat } from "./hooks/useChat";

export default function App() {
  const { messages, busy, send } = useChat();
  const [input, setInput] = useState("");

  const onSubmit = (e) => {
    e.preventDefault();
    send(input);
    setInput("");
  };

  return (
    <div className="app">
      <header className="header">
        <h1>🎧 Song Recommender</h1>
      </header>

      <div className="messages">
        {messages.length === 0 && (
          <p className="hint">
            Tell me an artist, album, or vibe you like — e.g.{" "}
            <em>“I love Tame Impala, recommend similar tracks.”</em>
          </p>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === "assistant" && m.tools?.length > 0 && (
              <div className="tools">
                {m.tools.map((t, j) => (
                  <span key={j} className="chip">
                    🔧 {t}
                  </span>
                ))}
              </div>
            )}
            <div className="bubble">
              {m.content || (m.role === "assistant" && busy ? "…" : "")}
            </div>
          </div>
        ))}
      </div>

      <form className="composer" onSubmit={onSubmit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Describe what you like…"
          disabled={busy}
        />
        <button disabled={busy || !input.trim()}>{busy ? "…" : "Send"}</button>
      </form>
    </div>
  );
}

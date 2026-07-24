import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { useChat } from "./hooks/useChat";
import ToolTrace from "./components/ToolTrace";

// Render Markdown links as new-tab links (e.g. Spotify URLs the agent includes).
const mdComponents = {
  a: ({ node, ...props }) => <a target="_blank" rel="noreferrer" {...props} />,
};

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
            {m.role === "assistant" && (
              // `busy` is global, so the index check is what scopes "still running" to
              // the turn actually in flight.
              <ToolTrace steps={m.steps} active={busy && i === messages.length - 1} />
            )}
            <div className="bubble">
              {m.role === "assistant" ? (
                m.content ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
                    {m.content}
                  </ReactMarkdown>
                ) : busy ? (
                  "…"
                ) : (
                  ""
                )
              ) : (
                m.content
              )}
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

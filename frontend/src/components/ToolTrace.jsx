// Per-turn trace of the tool calls the agent made, rendered above its answer.
//
// This is a mechanical record of what actually crossed the wire — the SSE `tool_start` /
// `tool_end` events from the backend — not the model explaining itself. The agent runs on a
// model with no exposed reasoning stream, and prose about "why I searched X" would be
// generated text that can drift from the real calls. What's here cannot drift.
//
// Tool *results* stay server-side (see routes/chat.py); we show how many items came back,
// not what they were.

const GLYPH = { running: "⟳", done: "✓", error: "✗" };

// Tool args are small objects like { genres: [...], per_genre: 8 } or
// { artists: [...], genre: "indie rock" }. Show the values, but keep a 12-genre list from
// swallowing the row.
function formatValue(value) {
  if (Array.isArray(value)) {
    return value.length > 3 ? `[${value.length} items]` : `[${value.map(formatValue).join(", ")}]`;
  }
  if (typeof value === "string") {
    return value.length > 40 ? `"${value.slice(0, 39)}…"` : `"${value}"`;
  }
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return "{…}";
  return String(value);
}

function formatArgs(input) {
  if (!input || typeof input !== "object") return null;
  const entries = Object.entries(input).filter(([, v]) => v !== null && v !== undefined);
  if (entries.length === 0) return null;
  return entries.map(([k, v]) => `${k}: ${formatValue(v)}`).join("  ·  ");
}

const formatMs = (ms) => (ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`);

export default function ToolTrace({ steps = [], active = false }) {
  if (steps.length === 0) return null;

  const totalMs = steps.reduce((sum, s) => sum + (s.ms || 0), 0);
  const label = `${steps.length} ${steps.length === 1 ? "step" : "steps"}`;

  return (
    // `open` follows the live turn: expanded while tools run, collapsed once the answer
    // lands. Uncontrolled after that — `open` on <details> is an initial value React won't
    // fight, so the user's own toggle sticks.
    <details className="trace" open={active}>
      <summary>
        {label}
        {totalMs > 0 && (
          // Sum of tool durations, not turn wall-clock: it excludes the model's own
          // thinking time between calls.
          <span className="trace-total" title="total time in tools">
            {" "}
            · {formatMs(totalMs)}
          </span>
        )}
      </summary>
      <ol className="trace-steps">
        {steps.map((step) => {
          const args = formatArgs(step.input);
          return (
            <li key={step.id} className={`trace-step ${step.status}`}>
              <div className="trace-head">
                <span className="trace-glyph">{GLYPH[step.status]}</span>
                <span className="trace-name">{step.name}</span>
                {step.count != null && <span className="trace-count">{step.count}</span>}
                {step.ms != null && <span className="trace-ms">{formatMs(step.ms)}</span>}
              </div>
              {args && <div className="trace-args">{args}</div>}
            </li>
          );
        })}
      </ol>
    </details>
  );
}

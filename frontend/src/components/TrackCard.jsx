// Presentational card for a normalized track (the shape returned by the MCP
// `search` / `get_track` tools: { id, name, artists[], album, url, preview_url, duration_ms }).
//
// Phase-1 the agent streams its recommendations as chat text, so this isn't wired into
// the message flow yet. It's ready for when the backend emits a structured track list
// alongside the chat stream (e.g. a `tracks` SSE event) — render each with <TrackCard />.
//
// NOTE: the normalized payload no longer carries `images` (album art was ~48% of the tokens
// the agent paid for on every turn), and Spotify has deprecated `preview_url` so it is always
// null. Both renders below are guarded and simply no-op today. When the structured track list
// lands, re-source album art in the backend for the UI only — never through the LLM context.
export default function TrackCard({ track }) {
  if (!track) return null;
  const { name, artists = [], album, images = [], url, preview_url } = track;
  return (
    <div className="track-card">
      {images[0] && <img src={images[0]} alt={album || name} width={56} height={56} />}
      <div className="track-meta">
        <a href={url} target="_blank" rel="noreferrer" className="track-name">
          {name}
        </a>
        <span className="track-artist">{artists.join(", ")}</span>
        {preview_url && <audio controls src={preview_url} />}
      </div>
    </div>
  );
}

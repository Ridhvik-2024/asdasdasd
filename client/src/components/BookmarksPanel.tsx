import React, { useState } from "react";
import { Bookmark as BookmarkIcon, Compass, Plus, Share2, Trash2 } from "lucide-react";
import { formatCoords } from "../lib/marsMath";
import type { Bookmark, CameraState } from "../types/nam";

interface BookmarksPanelProps {
  bookmarks: Bookmark[];
  camera: CameraState;
  onAdd: (name: string, lat: number, lon: number, note: string) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onFlyTo: (lat: number, lon: number, altKm?: number) => void;
  onShareCamera: () => Promise<string | null>;
}

export const BookmarksPanel: React.FC<BookmarksPanelProps> = ({
  bookmarks,
  camera,
  onAdd,
  onDelete,
  onFlyTo,
  onShareCamera,
}) => {
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [shareUrl, setShareUrl] = useState<string | null>(null);

  const handleSave = async () => {
    const label = name.trim() || `View ${formatCoords(camera.lat, camera.lon)}`;
    await onAdd(label, camera.lat, camera.lon, note.trim());
    setName("");
    setNote("");
  };

  return (
    <>
      <div className="card">
        <div className="card-title">
          <span className="row">
            <BookmarkIcon size={13} color="#e46f3b" /> Save Current Mars View
          </span>
        </div>
        <div className="mono small muted" style={{ marginBottom: 6 }}>
          Camera: {formatCoords(camera.lat, camera.lon)} · Alt {camera.altitudeKm} km
        </div>
        <input
          className="input"
          placeholder="Bookmark title (e.g. Jezero Western Delta)"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <input
          className="input"
          style={{ marginTop: 6 }}
          placeholder="Optional field note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
        <div className="row" style={{ marginTop: 8 }}>
          <button className="btn btn-primary" style={{ flex: 1 }} onClick={handleSave}>
            <Plus size={13} /> Save Bookmark
          </button>
          <button
            className="btn btn-cyan"
            onClick={async () => {
              const url = await onShareCamera();
              if (url) setShareUrl(url);
            }}
          >
            <Share2 size={13} /> Share URL
          </button>
        </div>
        {shareUrl && (
          <div className="stat-box" style={{ marginTop: 8 }}>
            <div className="stat-label">Shareable Camera Link (copied)</div>
            <div className="mono small" style={{ wordBreak: "break-all", color: "#7dd3fc" }}>
              {shareUrl}
            </div>
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-title">Saved Bookmarks ({bookmarks.length})</div>
        {bookmarks.length === 0 ? (
          <div className="small muted">No saved bookmarks yet. Fly anywhere on Mars and save it above!</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {bookmarks.map((b) => (
              <div
                key={b.id}
                style={{
                  padding: "6px 8px",
                  borderRadius: 7,
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.07)",
                }}
              >
                <div className="row" style={{ justifyContent: "space-between" }}>
                  <strong style={{ fontSize: 12 }}>{b.name}</strong>
                  <div className="row">
                    <button
                      className="btn btn-xs btn-primary"
                      onClick={() => onFlyTo(b.lat, b.lon, Number(b.camera?.altitudeKm || 600))}
                    >
                      <Compass size={11} /> Fly
                    </button>
                    <button className="btn btn-xs btn-ghost" onClick={() => onDelete(b.id)}>
                      <Trash2 size={11} />
                    </button>
                  </div>
                </div>
                <div className="mono small muted">{formatCoords(b.lat, b.lon)}</div>
                {b.note && <div className="small muted">{b.note}</div>}
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  );
};

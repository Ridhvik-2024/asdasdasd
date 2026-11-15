import React, { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, Pause, Plane, Play, X } from "lucide-react";
import { formatCoords } from "../lib/marsMath";
import type { Flyover } from "../types/nam";

interface FlyoverBarProps {
  flyover: Flyover;
  onMoveTo: (lat: number, lon: number, altKm: number) => void;
  onClose: () => void;
}

export const FlyoverBar: React.FC<FlyoverBarProps> = ({ flyover, onMoveTo, onClose }) => {
  const [idx, setIdx] = useState(0);
  const [playing, setPlaying] = useState(true);

  const kf = flyover.keyframes[idx] || flyover.keyframes[0];

  useEffect(() => {
    setIdx(0);
    setPlaying(true);
  }, [flyover.id]);

  useEffect(() => {
    if (!kf) return;
    onMoveTo(kf.lat, kf.lon, kf.altitude_km);
  }, [flyover.id, idx]);

  useEffect(() => {
    if (!playing || !kf) return;
    const t = window.setTimeout(() => {
      setIdx((prev) => (prev + 1) % flyover.keyframes.length);
    }, Math.max(2500, kf.dwell_s * 1000));
    return () => window.clearTimeout(t);
  }, [playing, idx, flyover.id]);

  return (
    <div className="flyover-hud glass">
      <div className="row" style={{ justifyContent: "space-between", marginBottom: 6 }}>
        <div className="row">
          <Plane size={14} color="#e46f3b" />
          <strong>{flyover.name}</strong>
          <span className="badge badge-obs">
            Stop {idx + 1}/{flyover.keyframes.length}
          </span>
        </div>
        <div className="row">
          <button
            className="btn btn-xs"
            onClick={() => setIdx((i) => (i - 1 + flyover.keyframes.length) % flyover.keyframes.length)}
          >
            <ChevronLeft size={12} />
          </button>
          <button className="btn btn-xs btn-primary" onClick={() => setPlaying((p) => !p)}>
            {playing ? <Pause size={12} /> : <Play size={12} />}
            {playing ? "Pause" : "Resume"}
          </button>
          <button className="btn btn-xs" onClick={() => setIdx((i) => (i + 1) % flyover.keyframes.length)}>
            <ChevronRight size={12} />
          </button>
          <button className="btn btn-xs btn-ghost" onClick={onClose}>
            <X size={13} />
          </button>
        </div>
      </div>

      <div style={{ fontSize: 12.5, lineHeight: 1.4 }}>{kf?.caption}</div>
      <div className="row" style={{ justifyContent: "space-between", marginTop: 6 }}>
        <span className="mono small muted">
          {kf ? `${formatCoords(kf.lat, kf.lon)} · Alt ${kf.altitude_km} km` : ""}
        </span>
        <span className="small muted">{flyover.src}</span>
      </div>
    </div>
  );
};

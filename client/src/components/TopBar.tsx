import React, { useEffect, useRef, useState } from "react";
import {
  AlertTriangle,
  Bot,
  Camera,
  Film,
  Footprints,
  Globe,
  Plane,
  Search,
  Share2,
  Wifi,
  WifiOff,
  X,
} from "lucide-react";
import { api } from "../lib/api";
import { formatCoords } from "../lib/marsMath";
import type { Flyover, GazetteerHit, ProjectionMode } from "../types/nam";

interface TopBarProps {
  projection: ProjectionMode;
  onProjectionChange: (p: ProjectionMode) => void;
  onSelectHit: (hit: GazetteerHit) => void;
  flyovers: Flyover[];
  onStartFlyover: (f: Flyover) => void;
  onOpenStreetView: () => void;
  onOpenWalkView: () => void;
  onOpenNasaHub: (tab?: "footage" | "raw" | "library" | "resources") => void;
  jevOpen: boolean;
  onToggleJev: () => void;
  onTriggerSepDrill: () => void;
  onShareCamera: () => void;
  wsConnected: boolean;
  activeStormCount: number;
}

const PROJECTIONS: Array<{ id: ProjectionMode; label: string }> = [
  { id: "globe", label: "3D Globe" },
  { id: "flat", label: "2D Flat" },
  { id: "north-polar", label: "N. Pole" },
  { id: "south-polar", label: "S. Pole" },
  { id: "columbus", label: "2.5D" },
];

export const TopBar: React.FC<TopBarProps> = ({
  projection,
  onProjectionChange,
  onSelectHit,
  flyovers,
  onStartFlyover,
  onOpenStreetView,
  onOpenWalkView,
  onOpenNasaHub,
  jevOpen,
  onToggleJev,
  onTriggerSepDrill,
  onShareCamera,
  wsConnected,
  activeStormCount,
}) => {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<GazetteerHit[]>([]);
  const [elapsedMs, setElapsedMs] = useState<number | null>(null);
  const [openSearch, setOpenSearch] = useState(false);
  const [flyMenuOpen, setFlyMenuOpen] = useState(false);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setHits([]);
      setElapsedMs(null);
      return;
    }
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(async () => {
      try {
        const res = await api.search(q, 14);
        setHits(res.results || []);
        setElapsedMs(res.latency_ms);
        setOpenSearch(true);
      } catch {
        setHits([]);
      }
    }, 110);
    return () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    };
  }, [query]);

  return (
    <header className="top-bar glass">
      <div className="brand">
        <span className="brand-orb" />
        <div>
          <span className="brand-title">NAM v2</span>
          <span className="brand-sub">Google Earth for Mars</span>
        </div>
      </div>

      {/* Global Search over 2,055+ USGS Features + Landing Sites + Coordinates */}
      <div className="search-wrap">
        <Search size={14} className="search-icon" />
        <input
          className="search-input"
          placeholder="Search Mars (Jezero, Olympus Mons, 18.4, 77.5)…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => hits.length > 0 && setOpenSearch(true)}
        />
        {query && (
          <button
            onClick={() => {
              setQuery("");
              setHits([]);
              setOpenSearch(false);
            }}
            style={{
              position: "absolute",
              right: 6,
              top: "50%",
              transform: "translateY(-50%)",
              background: "transparent",
              border: "none",
              color: "#94a3b8",
              cursor: "pointer",
            }}
            aria-label="Clear search"
          >
            <X size={13} />
          </button>
        )}

        {openSearch && hits.length > 0 && (
          <div className="search-dropdown glass">
            <div className="row" style={{ justifyContent: "space-between", padding: "2px 6px 6px" }}>
              <span className="small muted">USGS Gazetteer & Landing Sites</span>
              {elapsedMs !== null && <span className="badge badge-obs mono">{elapsedMs} ms</span>}
            </div>
            {hits.map((h, i) => (
              <div
                key={`${h.id || h.name || "coord"}-${i}`}
                className="search-hit"
                onClick={() => {
                  onSelectHit(h);
                  setOpenSearch(false);
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 12.5, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {h.name || `Coordinates ${formatCoords(h.lat, h.lon)}`}
                  </div>
                  <div className="small muted">
                    {h.kind === "landing_site" ? `Landing Site · ${h.mission}` : h.type || h.kind || "Feature"}
                    {h.diameter_km ? ` · Ø ${h.diameter_km} km` : ""}
                  </div>
                </div>
                <span className="mono small muted" style={{ flexShrink: 0 }}>
                  {formatCoords(h.lat, h.lon)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 5 Projection Modes */}
      <div className="pill-group" title="Switch map projection (shared state)">
        {PROJECTIONS.map((pr) => (
          <button
            key={pr.id}
            className={`btn btn-xs ${projection === pr.id ? "btn-active" : "btn-ghost"}`}
            onClick={() => onProjectionChange(pr.id)}
          >
            {pr.id === "globe" && <Globe size={12} />}
            {pr.label}
          </button>
        ))}
      </div>

      {/* Landmark Flyovers Menu */}
      <div style={{ position: "relative" }}>
        <button
          className={`btn ${flyMenuOpen ? "btn-active" : ""}`}
          onClick={() => setFlyMenuOpen((v) => !v)}
          title="Automatic landmark flyover tours"
        >
          <Plane size={13} /> Flyovers
        </button>
        {flyMenuOpen && (
          <div
            className="glass"
            style={{
              position: "absolute",
              top: 36,
              right: 0,
              width: 280,
              borderRadius: 10,
              padding: 6,
              zIndex: 60,
            }}
          >
            <div className="small muted" style={{ padding: "4px 8px" }}>
              Landmark Camera Flyovers
            </div>
            {flyovers.map((f) => (
              <div
                key={f.id}
                className="search-hit"
                onClick={() => {
                  onStartFlyover(f);
                  setFlyMenuOpen(false);
                }}
              >
                <div>
                  <div style={{ fontWeight: 600, fontSize: 12 }}>{f.name}</div>
                  <div className="small muted">{f.region} · {f.keyframes.length} stops</div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <button className="btn" onClick={onOpenStreetView} title="Mars Street View 360° Panoramas">
        <Camera size={13} /> Street View
      </button>

      <button className="btn" onClick={onOpenWalkView} title="First-Person 3D Walk View">
        <Footprints size={13} /> Walk View
      </button>

      <button
        className="btn btn-primary"
        onClick={() => onOpenNasaHub("footage")}
        title="Real NASA Mars Footage, Curiosity Mount Sharp Route Animation, 1M+ Live Raw Rover Photos & USGS SIM 3292 Geologic Map"
      >
        <Film size={13} /> NASA Footage &amp; Raw
      </button>

      <button
        className="btn btn-danger"
        onClick={onTriggerSepDrill}
        title="Run live SEP solar particle storm alert + evacuation plan drill [SIM]"
      >
        <AlertTriangle size={13} /> SEP Drill
        {activeStormCount > 0 && <span className="badge badge-danger">{activeStormCount}</span>}
      </button>

      <button
        className={`btn ${jevOpen ? "btn-primary" : "btn-cyan"}`}
        onClick={onToggleJev}
        title="Open JEV AI Planetary Assistant (24 grounded tools)"
      >
        <Bot size={14} /> JEV AI
      </button>

      <button className="btn btn-ghost" onClick={onShareCamera} title="Generate shareable camera link">
        <Share2 size={14} />
      </button>

      <span
        className={`badge ${wsConnected ? "badge-obs" : "badge-muted"}`}
        title={wsConnected ? "WebSocket /ws/events & /ws/presence connected" : "Reconnecting WebSocket"}
      >
        {wsConnected ? <Wifi size={11} /> : <WifiOff size={11} />}
        {wsConnected ? "LIVE" : "OFFLINE"}
      </span>
    </header>
  );
};

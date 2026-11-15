import React, { useEffect, useState } from "react";
import { Columns2, ExternalLink, Film, Layers, RefreshCw, ZoomIn } from "lucide-react";
import { api } from "../lib/api";
import { getBasemapDef, NASA_BASEMAPS } from "../lib/nasaImagery";
import type { ScienceLayer } from "../types/nam";
import type { LayerVisibility } from "./MarsViewport";

interface LayersPanelProps {
  layers: ScienceLayer[];
  baseLayer: string;
  onBaseLayerChange: (id: string) => void;
  overlayLayer: string | null;
  onOverlayLayerChange: (id: string | null) => void;
  overlayOpacity: number;
  onOverlayOpacityChange: (v: number) => void;
  compareEnabled: boolean;
  onCompareEnabledChange: (v: boolean) => void;
  compareLayer: string;
  onCompareLayerChange: (id: string) => void;
  visibility: LayerVisibility;
  onVisibilityChange: (patch: Partial<LayerVisibility>) => void;
  onZoomJezeroHiRes?: () => void;
  onOpenNasaHub?: (tab: "footage" | "raw" | "library" | "resources") => void;
}

const RASTER_LAYERS = NASA_BASEMAPS.map((b) => ({
  id: b.id,
  label: `${b.isLiveNasa ? "🛰 " : ""}${b.label} (${b.resolution})`,
}));

export const LayersPanel: React.FC<LayersPanelProps> = ({
  layers,
  baseLayer,
  onBaseLayerChange,
  overlayLayer,
  onOverlayLayerChange,
  overlayOpacity,
  onOverlayOpacityChange,
  compareEnabled,
  onCompareEnabledChange,
  compareLayer,
  onCompareLayerChange,
  visibility,
  onVisibilityChange,
  onZoomJezeroHiRes,
  onOpenNasaHub,
}) => {
  const [catFilter, setCatFilter] = useState<string>("all");
  const [connectors, setConnectors] = useState<Array<Record<string, unknown>>>([]);
  const [showConn, setShowConn] = useState(false);

  const loadConnectors = async () => {
    try {
      const res = await api.connectors();
      setConnectors(res.connectors || []);
      setShowConn(true);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    // keep lightweight until user clicks probe
  }, []);

  const categories = ["all", ...Array.from(new Set(layers.map((l) => l.category)))];
  const filtered = catFilter === "all" ? layers : layers.filter((l) => l.category === catFilter);
  const activeDef = getBasemapDef(baseLayer);

  return (
    <>
      {/* Live NASA / USGS Planetary Basemaps */}
      <div className="card">
        <div className="card-title">
          <span className="row">
            <Layers size={13} color="#e46f3b" /> NASA / USGS Orbital Basemap
          </span>
          <span className={`badge ${activeDef.isLiveNasa ? "badge-obs" : "badge-sim"}`}>
            {activeDef.isLiveNasa ? "LIVE NASA" : "[SIM]"}
          </span>
        </div>
        <select
          className="select"
          value={activeDef.id}
          onChange={(e) => onBaseLayerChange(e.target.value)}
        >
          {RASTER_LAYERS.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label}
            </option>
          ))}
        </select>
        <div className="small muted" style={{ marginTop: 6 }}>
          {activeDef.source} · {activeDef.credit}
        </div>
        <div className="row-wrap" style={{ marginTop: 8 }}>
          {onZoomJezeroHiRes && (
            <button className="btn btn-xs btn-primary" onClick={onZoomJezeroHiRes}>
              <ZoomIn size={11} /> Jezero HiRISE 25cm (2D)
            </button>
          )}
          {onOpenNasaHub && (
            <button className="btn btn-xs btn-cyan" onClick={() => onOpenNasaHub("resources")}>
              <Film size={11} /> USGS SIM 3292 &amp; Worldview
            </button>
          )}
        </div>
        <div className="small muted" style={{ marginTop: 8 }}>
          Overlay Blend Layer (Transparency)
        </div>
        <div className="row" style={{ marginTop: 4 }}>
          <select
            className="select"
            value={overlayLayer || ""}
            onChange={(e) => onOverlayLayerChange(e.target.value || null)}
          >
            <option value="">None</option>
            {RASTER_LAYERS.map((r) => (
              <option key={r.id} value={r.id}>
                {r.label}
              </option>
            ))}
          </select>
        </div>
        {overlayLayer && (
          <div className="row" style={{ marginTop: 6 }}>
            <span className="small muted">Opacity</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={overlayOpacity}
              onChange={(e) => onOverlayOpacityChange(parseFloat(e.target.value))}
              style={{ flex: 1 }}
            />
            <span className="mono small">{Math.round(overlayOpacity * 100)}%</span>
          </div>
        )}
      </div>

      {/* Side-by-Side Split-Screen Layer Comparison */}
      <div className="card">
        <div className="card-title">
          <span className="row">
            <Columns2 size={13} color="#38bdf8" /> Split-Screen Layer Compare
          </span>
          <button
            className={`btn btn-xs ${compareEnabled ? "btn-primary" : ""}`}
            onClick={() => onCompareEnabledChange(!compareEnabled)}
          >
            {compareEnabled ? "Active" : "Enable"}
          </button>
        </div>
        <div className="small muted" style={{ marginBottom: 6 }}>
          Drag the orange curtain on the 3D globe or 2D map to compare Base (A) vs Layer B live.
        </div>
        <select
          className="select"
          value={compareLayer}
          onChange={(e) => onCompareLayerChange(e.target.value)}
        >
          {RASTER_LAYERS.map((r) => (
            <option key={r.id} value={r.id}>
              Compare B: {r.label}
            </option>
          ))}
        </select>
      </div>

      {/* Vector & Experience Overlays */}
      <div className="card">
        <div className="card-title">Map Overlays (Shared Across All 5 Views)</div>
        <div className="grid-2" style={{ marginTop: 4 }}>
          {(
            [
              ["landingSites", "Landing Sites (10)", "#f97316"],
              ["panoramas", "Street View Poses (12)", "#fbbf24"],
              ["traverses", "Rover Traverses", "#fde047"],
              ["discoveries", "Cited Discoveries (15)", "#a78bfa"],
              ["water", "SWIM Water Ice (8)", "#38bdf8"],
              ["shelters", "Scored Shelters (12)", "#34d399"],
              ["nodes", "Spatial Nodes (8 types)", "#f472b6"],
              ["presence", "Presence Feed [SIM]", "#a3e635"],
              ["storms", "Active Storms [SIM]", "#ef4444"],
              ["missions", "Mission Routes [SIM]", "#60a5fa"],
            ] as Array<[keyof LayerVisibility, string, string]>
          ).map(([key, label, dot]) => (
            <label
              key={key}
              className="row small"
              style={{ cursor: "pointer", padding: "2px 0", userSelect: "none" }}
            >
              <input
                type="checkbox"
                checked={visibility[key]}
                onChange={(e) => onVisibilityChange({ [key]: e.target.checked })}
              />
              <span
                style={{
                  width: 7,
                  height: 7,
                  borderRadius: "50%",
                  background: dot,
                  display: "inline-block",
                  flexShrink: 0,
                }}
              />
              <span>{label}</span>
            </label>
          ))}
        </div>
      </div>

      {/* 20-Layer Registry with Legends & Provenance */}
      <div className="card">
        <div className="card-title">
          <span>Science Layer Registry ({layers.length})</span>
          <button className="btn btn-xs" onClick={loadConnectors}>
            <RefreshCw size={11} /> Connectors
          </button>
        </div>
        <div className="row-wrap" style={{ marginBottom: 8 }}>
          {categories.map((c) => (
            <button
              key={c}
              className={`btn btn-xs ${catFilter === c ? "btn-active" : ""}`}
              onClick={() => setCatFilter(c)}
            >
              {c}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {filtered.map((l) => (
            <div
              key={l.id}
              style={{
                padding: "6px 7px",
                borderRadius: 7,
                background: "rgba(255,255,255,0.025)",
                border: "1px solid rgba(255,255,255,0.06)",
              }}
            >
              <div className="row" style={{ justifyContent: "space-between" }}>
                <strong style={{ fontSize: 12 }}>{l.title}</strong>
                {RASTER_LAYERS.some((r) => r.id === l.id) && (
                  <button
                    className={`btn btn-xs ${baseLayer === l.id ? "btn-primary" : ""}`}
                    onClick={() => onBaseLayerChange(l.id)}
                  >
                    Use
                  </button>
                )}
              </div>
              <div className="small muted" style={{ marginTop: 2 }}>
                {l.legend}
              </div>
              <div className="row" style={{ justifyContent: "space-between", marginTop: 4 }}>
                <span className="small muted">
                  {l.res_m ? `${l.res_m} m/px · ` : ""}
                  {l.source}
                </span>
                {l.url && (
                  <a
                    href={l.url}
                    target="_blank"
                    rel="noreferrer"
                    className="small"
                    style={{ color: "#38bdf8", display: "inline-flex", alignItems: "center", gap: 3 }}
                  >
                    Source <ExternalLink size={10} />
                  </a>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Upstream Connectors Status */}
      {showConn && (
        <div className="card">
          <div className="card-title">
            <span>Backend Tile & Data Connectors ({connectors.length})</span>
            <span className="badge badge-muted">Proxy Only</span>
          </div>
          {connectors.map((c, idx) => (
            <div
              key={idx}
              style={{
                padding: "4px 0",
                borderTop: idx > 0 ? "1px solid rgba(255,255,255,0.06)" : undefined,
              }}
            >
              <div className="row" style={{ justifyContent: "space-between" }}>
                <strong className="small">{String(c.name)}</strong>
                <span className="badge badge-cyan">{String(c.id)}</span>
              </div>
              <div className="small muted">{String(c.attribution || "")}</div>
            </div>
          ))}
        </div>
      )}
    </>
  );
};

import React, { useState } from "react";
import { Box, Download, Mountain, Play, Ruler, Sun, Trash2 } from "lucide-react";
import { api } from "../lib/api";
import { formatCoords } from "../lib/marsMath";
import type { CameraState, LatLon, MeasureTool, SolarData } from "../types/nam";

interface MeasurePanelProps {
  activeTool: MeasureTool;
  onToolChange: (t: MeasureTool) => void;
  points: LatLon[];
  onClearPoints: () => void;
  onSetRouteLine: (pts: LatLon[]) => void;
  camera: CameraState;
  solar: SolarData | null;
  onRefreshSolar: (lat: number, lon: number) => void;
}

const TOOLS: Array<{ id: MeasureTool; label: string; hint: string }> = [
  { id: "inspect", label: "Inspect", hint: "Click anywhere on Mars to inspect location card" },
  { id: "straight", label: "Straight Dist", hint: "Click 2 points for geodesic distance & bearing" },
  { id: "path", label: "Multi Path", hint: "Click 2+ points for cumulative path length" },
  { id: "route", label: "A* Route", hint: "Click 2 points for slope-aware A* Mars route" },
  { id: "profile", label: "Elev Profile", hint: "Click 2+ points for cross-section profile chart" },
  { id: "crater", label: "Crater Ø/Depth", hint: "Click opposite crater rim points" },
  { id: "area", label: "Surface Area", hint: "Click 3+ polygon vertices for geodesic area" },
  { id: "slope", label: "Slope/Hazard", hint: "Click 2 corners for regional slope & hazard score" },
  { id: "elev_diff", label: "Elev Diff", hint: "Click 2 points for elevation delta & grade" },
  { id: "solar", label: "Mars24 Solar", hint: "Compute solar elevation & azimuth at point" },
  { id: "dem", label: "DEM Export", hint: "Download raw elevation grid (JSON/CSV/NPZ/OBJ)" },
  { id: "stl", label: "3D Print STL", hint: "Export slicer-ready binary STL terrain model" },
];

export const MeasurePanel: React.FC<MeasurePanelProps> = ({
  activeTool,
  onToolChange,
  points,
  onClearPoints,
  onSetRouteLine,
  camera,
  solar,
  onRefreshSolar,
}) => {
  const [preset, setPreset] = useState("balanced");
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [profileSeries, setProfileSeries] = useState<Array<{ dist_km: number; elev_m: number }>>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  // STL & DEM controls
  const [stlRadius, setStlRadius] = useState(25);
  const [stlScale, setStlScale] = useState(5.0);
  const [demFmt, setDemFmt] = useState("csv");

  const runTool = async () => {
    setBusy(true);
    setErr(null);
    setResult(null);
    setProfileSeries([]);
    onSetRouteLine([]);

    try {
      if (activeTool === "straight") {
        if (points.length < 2) throw new Error("Click 2 points on Mars first.");
        const res = await api.measureStraight(points[0].lat, points[0].lon, points[1].lat, points[1].lon);
        setResult(res);
      } else if (activeTool === "path") {
        if (points.length < 2) throw new Error("Click at least 2 points on Mars.");
        const res = await api.measurePath(points);
        setResult(res);
      } else if (activeTool === "route") {
        if (points.length < 2) throw new Error("Click start & end points on Mars.");
        const res = await api.measureRoute(
          points[0].lat,
          points[0].lon,
          points[points.length - 1].lat,
          points[points.length - 1].lon,
          preset
        );
        onSetRouteLine(res.path || res.path_preview || []);
        setResult(res as unknown as Record<string, unknown>);
      } else if (activeTool === "profile") {
        if (points.length < 2) throw new Error("Click 2+ points along your transect.");
        const res = await api.elevationProfile(points, 120);
        setProfileSeries(res.points || []);
        setResult({
          total_km: res.total_km,
          elevation_gain_m: res.elevation_gain_m,
          elevation_loss_m: res.elevation_loss_m,
          min_elev_m: res.min_elev_m,
          max_elev_m: res.max_elev_m,
          provenance: res.provenance,
        });
      } else if (activeTool === "crater") {
        if (points.length < 2) throw new Error("Click two opposite crater rim points.");
        const res = await api.measureCrater(points[0].lat, points[0].lon, points[1].lat, points[1].lon);
        setResult(res);
      } else if (activeTool === "area") {
        if (points.length < 3) throw new Error("Click at least 3 polygon vertices on Mars.");
        const res = await api.measureArea(points);
        setResult(res);
      } else if (activeTool === "slope") {
        const p0 = points[0] || { lat: camera.lat - 1.5, lon: camera.lon - 1.5 };
        const p1 = points[1] || { lat: camera.lat + 1.5, lon: camera.lon + 1.5 };
        const res = await api.terrainHazard(
          Math.min(p0.lat, p1.lat),
          p0.lon,
          Math.max(p0.lat, p1.lat),
          p1.lon
        );
        setResult(res);
      } else if (activeTool === "elev_diff") {
        if (points.length < 2) throw new Error("Click 2 points on Mars.");
        const res = await api.measureElevDiff(points[0].lat, points[0].lon, points[1].lat, points[1].lon);
        setResult(res);
      } else if (activeTool === "solar") {
        const pt = points[0] || { lat: camera.lat, lon: camera.lon };
        const res = await api.measureSolar(pt.lat, pt.lon);
        onRefreshSolar(pt.lat, pt.lon);
        setResult(res as unknown as Record<string, unknown>);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  // Interactive SVG Elevation Profile Renderer
  const renderProfileSvg = () => {
    if (profileSeries.length < 2) return null;
    const W = 300;
    const H = 115;
    const minE = Math.min(...profileSeries.map((p) => p.elev_m));
    const maxE = Math.max(...profileSeries.map((p) => p.elev_m));
    const spanE = Math.max(1, maxE - minE);
    const maxD = Math.max(0.01, profileSeries[profileSeries.length - 1].dist_km);

    const coords = profileSeries.map((pt) => {
      const x = 6 + (pt.dist_km / maxD) * (W - 12);
      const y = H - 18 - ((pt.elev_m - minE) / spanE) * (H - 30);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    });
    const areaPath = `M 6,${H - 18} L ${coords.join(" L ")} L ${W - 6},${H - 18} Z`;

    return (
      <div className="card">
        <div className="card-title">
          <span className="row">
            <Mountain size={13} color="#34d399" /> Elevation Cross-Section
          </span>
          <span className="badge badge-sim">[SIM]</span>
        </div>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: 120, display: "block" }}>
          <defs>
            <linearGradient id="elevFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#e46f3b" stopOpacity="0.55" />
              <stop offset="100%" stopColor="#e46f3b" stopOpacity="0.04" />
            </linearGradient>
          </defs>
          <path d={areaPath} fill="url(#elevFill)" />
          <polyline fill="none" stroke="#f59e0b" strokeWidth="2" points={coords.join(" ")} />
          <text x="6" y="11" fill="#94a3b8" fontSize="9" fontFamily="monospace">
            Max {maxE.toFixed(0)} m
          </text>
          <text x="6" y={H - 4} fill="#94a3b8" fontSize="9" fontFamily="monospace">
            Min {minE.toFixed(0)} m
          </text>
          <text x={W - 68} y={H - 4} fill="#94a3b8" fontSize="9" fontFamily="monospace">
            {maxD.toFixed(1)} km
          </text>
        </svg>
      </div>
    );
  };

  const centerPt = points[0] || { lat: camera.lat, lon: camera.lon };

  return (
    <>
      <div className="card">
        <div className="card-title">
          <span className="row">
            <Ruler size={13} color="#facc15" /> 12-Tool Mars Trek Suite
          </span>
          <span className="badge badge-obs">IAU Mars</span>
        </div>
        <div className="grid-3" style={{ marginTop: 6 }}>
          {TOOLS.map((t) => (
            <button
              key={t.id}
              className={`btn btn-xs ${activeTool === t.id ? "btn-primary" : ""}`}
              onClick={() => {
                onToolChange(t.id);
                setResult(null);
                setErr(null);
              }}
              style={{ justifyContent: "flex-start", overflow: "hidden", textOverflow: "ellipsis" }}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="small muted" style={{ marginTop: 8 }}>
          {TOOLS.find((t) => t.id === activeTool)?.hint}
        </div>
      </div>

      {/* Placed Points */}
      {activeTool !== "inspect" && activeTool !== "dem" && activeTool !== "stl" && (
        <div className="card">
          <div className="card-title">
            <span>Picked Points ({points.length})</span>
            <button className="btn btn-xs btn-ghost" onClick={onClearPoints}>
              <Trash2 size={11} /> Clear
            </button>
          </div>
          {points.length === 0 ? (
            <div className="small muted">Click directly on the Mars globe/map to add points.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 3, maxHeight: 96, overflowY: "auto" }}>
              {points.map((pt, i) => (
                <div key={i} className="mono small">
                  P{i + 1}: {formatCoords(pt.lat, pt.lon)}
                </div>
              ))}
            </div>
          )}

          {activeTool === "route" && (
            <div className="row" style={{ marginTop: 8 }}>
              <span className="small muted">Preset:</span>
              <select className="select" value={preset} onChange={(e) => setPreset(e.target.value)}>
                <option value="balanced">Balanced (distance + slope)</option>
                <option value="terrain">Terrain-Safe (gentle slopes)</option>
                <option value="speed">Speed (shortest viable)</option>
              </select>
            </div>
          )}

          <button
            className="btn btn-primary"
            style={{ width: "100%", marginTop: 8 }}
            disabled={busy}
            onClick={runTool}
          >
            {activeTool === "solar" ? <Sun size={13} /> : <Play size={13} />}
            {busy ? "Computing…" : `Run ${TOOLS.find((t) => t.id === activeTool)?.label}`}
          </button>
        </div>
      )}

      {/* DEM Export Tool */}
      {activeTool === "dem" && (
        <div className="card">
          <div className="card-title">
            <span className="row">
              <Download size={13} color="#38bdf8" /> Raw DEM Sub-Grid Export
            </span>
            <span className="badge badge-sim">[SIM]</span>
          </div>
          <div className="small muted" style={{ marginBottom: 6 }}>
            Exports ±3° bounding box centered on {formatCoords(centerPt.lat, centerPt.lon)} with IAU:49900 metadata.
          </div>
          <select className="select" value={demFmt} onChange={(e) => setDemFmt(e.target.value)}>
            <option value="csv">CSV Elevation Table (.csv)</option>
            <option value="json">JSON Elevation Grid + CRS (.json)</option>
            <option value="npz">NumPy Compressed Archive (.npz)</option>
            <option value="obj">Wavefront 3D Mesh (.obj)</option>
          </select>
          <a
            className="btn btn-primary"
            style={{ width: "100%", marginTop: 8, textDecoration: "none" }}
            href={api.downloadDemUrl(
              Math.max(-89, centerPt.lat - 3),
              centerPt.lon - 3,
              Math.min(89, centerPt.lat + 3),
              centerPt.lon + 3,
              demFmt
            )}
            download
          >
            <Download size={13} /> Download DEM ({demFmt.toUpperCase()})
          </a>
        </div>
      )}

      {/* 3D Printable STL Export Tool */}
      {activeTool === "stl" && (
        <div className="card">
          <div className="card-title">
            <span className="row">
              <Box size={13} color="#e46f3b" /> 3D-Printable STL Terrain Export
            </span>
            <span className="badge badge-sim">[SIM]</span>
          </div>
          <div className="small muted" style={{ marginBottom: 6 }}>
            Generates a slicer-valid binary STL centered at {formatCoords(centerPt.lat, centerPt.lon)}.
          </div>
          <div className="row" style={{ marginTop: 6 }}>
            <span className="small muted" style={{ width: 92 }}>
              Radius (km)
            </span>
            <input
              type="range"
              min={5}
              max={120}
              step={5}
              value={stlRadius}
              onChange={(e) => setStlRadius(Number(e.target.value))}
              style={{ flex: 1 }}
            />
            <span className="mono small">{stlRadius} km</span>
          </div>
          <div className="row" style={{ marginTop: 6 }}>
            <span className="small muted" style={{ width: 92 }}>
              Vert. Scale
            </span>
            <input
              type="range"
              min={1}
              max={15}
              step={0.5}
              value={stlScale}
              onChange={(e) => setStlScale(Number(e.target.value))}
              style={{ flex: 1 }}
            />
            <span className="mono small">{stlScale.toFixed(1)}×</span>
          </div>
          <button
            className="btn btn-primary"
            style={{ width: "100%", marginTop: 10 }}
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              setErr(null);
              try {
                const blob = await api.downloadStlBlob(centerPt.lat, centerPt.lon, stlRadius, stlScale, 72);
                const url = URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.href = url;
                a.download = `mars_${centerPt.lat.toFixed(1)}_${centerPt.lon.toFixed(1)}.stl`;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(url);
              } catch (e) {
                setErr(e instanceof Error ? e.message : String(e));
              } finally {
                setBusy(false);
              }
            }}
          >
            <Download size={13} /> {busy ? "Generating STL…" : "Download Binary STL"}
          </button>
        </div>
      )}

      {err && <div className="badge badge-danger">{err}</div>}
      {renderProfileSvg()}

      {/* Numeric Output Card */}
      {result && (
        <div className="card">
          <div className="card-title">
            <span>Measurement Output</span>
            <span className="badge badge-obs">Provenance Attached</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
            {Object.entries(result)
              .filter(([k]) => !["points", "path", "provenance"].includes(k))
              .map(([k, v]) => (
                <div
                  key={k}
                  className="row"
                  style={{
                    justifyContent: "space-between",
                    borderBottom: "1px solid rgba(255,255,255,0.05)",
                    paddingBottom: 3,
                  }}
                >
                  <span className="small muted">{k}</span>
                  <span className="mono small" style={{ textAlign: "right", maxWidth: 185, overflow: "hidden", textOverflow: "ellipsis" }}>
                    {typeof v === "object" && v !== null ? JSON.stringify(v) : String(v)}
                  </span>
                </div>
              ))}
          </div>
          {solar && activeTool === "solar" && (
            <div className="small muted" style={{ marginTop: 6 }}>
              Globe sunlight updated to Mars24 subsolar geometry ({solar.subsolar_lat.toFixed(1)}°,{" "}
              {solar.subsolar_lon.toFixed(1)}°E).
            </div>
          )}
        </div>
      )}
    </>
  );
};

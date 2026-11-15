import React, { useState } from "react";
import {
  Activity,
  Download,
  Flag,
  MapPin,
  Plus,
  Route,
  Share2,
  Sparkles,
  Trash2,
} from "lucide-react";
import { api } from "../lib/api";
import { formatCoords } from "../lib/marsMath";
import type { Mission } from "../types/nam";

interface MissionsPanelProps {
  missions: Mission[];
  activeMissionId: string | null;
  placingStop: boolean;
  onTogglePlacingStop: () => void;
  onSelectMission: (id: string | null) => void;
  onRefresh: () => Promise<void>;
  onFlyTo: (lat: number, lon: number, altKm?: number) => void;
  onNotify: (msg: string) => void;
}

export const MissionsPanel: React.FC<MissionsPanelProps> = ({
  missions,
  activeMissionId,
  placingStop,
  onTogglePlacingStop,
  onSelectMission,
  onRefresh,
  onFlyTo,
  onNotify,
}) => {
  const [mType, setMType] = useState<"route" | "area" | "evacuation" | "survey">("survey");
  const [name, setName] = useState("");
  const [objective, setObjective] = useState("");
  const [preset, setPreset] = useState("balanced");
  const [profileData, setProfileData] = useState<{
    points: Array<{ dist_km: number; elev_m: number }>;
    total_km: number;
    gain: number;
    maxSlope: number;
    radMsv: number;
    sols: number;
  } | null>(null);
  const [busy, setBusy] = useState(false);

  const selected = missions.find((m) => m.id === activeMissionId) || null;

  const createMission = async () => {
    const label = name.trim() || `${mType.toUpperCase()} Plan`;
    setBusy(true);
    try {
      const m = await api.createMission({
        type: mType,
        name: label,
        objective: objective.trim() || "Planetary field traverse",
        stops: [],
      });
      setName("");
      setObjective("");
      await onRefresh();
      onSelectMission(m.id);
      onNotify(`Created mission "${m.name}" [SIM]`);
    } finally {
      setBusy(false);
    }
  };

  const planRoute = async () => {
    if (!selected || selected.stops.length < 2) {
      onNotify("Add at least 2 stops to compute an A* terrain route.");
      return;
    }
    setBusy(true);
    try {
      const a = selected.stops[0];
      const b = selected.stops[selected.stops.length - 1];
      await api.attachMissionRoute(selected.id, a.lat, a.lon, b.lat, b.lon, preset);
      await onRefresh();
      onNotify(`Attached A* (${preset}) route to ${selected.name}`);
    } finally {
      setBusy(false);
    }
  };

  const optimizeStops = async () => {
    if (!selected || selected.stops.length < 3) {
      onNotify("Need at least 3 stops for 2-opt route optimization.");
      return;
    }
    setBusy(true);
    try {
      await api.optimizeMission(selected.id, preset);
      await onRefresh();
      onNotify(`Optimized stop ordering for ${selected.name}`);
    } finally {
      setBusy(false);
    }
  };

  const loadProfile = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const res = await api.missionProfile(selected.id, 12, "rover");
      setProfileData({
        points: res.profile.points,
        total_km: res.profile.total_km,
        gain: res.profile.elevation_gain_m,
        maxSlope: res.slope_summary.max_slope_deg,
        radMsv: res.radiation.total_msv,
        sols: res.radiation.total_duration_sols,
      });
    } catch (e) {
      onNotify(e instanceof Error ? e.message : "Need 2+ stops for profile");
    } finally {
      setBusy(false);
    }
  };

  const shareMission = async () => {
    if (!selected) return;
    const res = await api.shareMission(selected.id);
    const full = `${window.location.origin}/?share=${res.share_id}`;
    navigator.clipboard?.writeText(full).catch(() => {});
    onNotify(`Mission share link copied: ?share=${res.share_id}`);
  };

  const deleteMission = async (id: string) => {
    await api.deleteMission(id);
    if (activeMissionId === id) onSelectMission(null);
    setProfileData(null);
    await onRefresh();
  };

  return (
    <>
      {/* New Mission Creator */}
      <div className="card">
        <div className="card-title">
          <span className="row">
            <Flag size={13} color="#38bdf8" /> Create Mission Plan
          </span>
          <span className="badge badge-sim">[SIM] Advisory</span>
        </div>
        <div className="row" style={{ marginTop: 6 }}>
          <select
            className="select"
            style={{ width: 118 }}
            value={mType}
            onChange={(e) => setMType(e.target.value as typeof mType)}
          >
            <option value="route">Route</option>
            <option value="survey">Survey</option>
            <option value="area">Area</option>
            <option value="evacuation">Evacuation</option>
          </select>
          <input
            className="input"
            placeholder="Mission name…"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <input
          className="input"
          style={{ marginTop: 6 }}
          placeholder="Objective (e.g. Sample Jezero carbonates)"
          value={objective}
          onChange={(e) => setObjective(e.target.value)}
        />
        <button
          className="btn btn-primary"
          style={{ width: "100%", marginTop: 8 }}
          disabled={busy}
          onClick={createMission}
        >
          <Plus size={13} /> New {mType} Mission
        </button>
      </div>

      {/* Mission List */}
      <div className="card">
        <div className="card-title">Missions ({missions.length})</div>
        {missions.length === 0 ? (
          <div className="small muted">Create a mission above or run a SEP Drill to save an evacuation plan.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
            {missions.map((m) => (
              <div
                key={m.id}
                className="search-hit"
                style={{
                  background: m.id === activeMissionId ? "rgba(56,189,248,0.12)" : "rgba(255,255,255,0.03)",
                  borderColor: m.id === activeMissionId ? "rgba(56,189,248,0.4)" : "rgba(255,255,255,0.07)",
                }}
                onClick={() => {
                  onSelectMission(m.id);
                  setProfileData(null);
                  if (m.stops[0]) onFlyTo(m.stops[0].lat, m.stops[0].lon, 950);
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: 12 }}>{m.name}</div>
                  <div className="small muted">
                    {m.type} · {m.stops.length} stops · {m.routes?.length || 0} A* routes
                  </div>
                </div>
                <button
                  className="btn btn-xs btn-ghost"
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteMission(m.id);
                  }}
                >
                  <Trash2 size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Active Mission Detail & Controls */}
      {selected && (
        <div className="card">
          <div className="card-title">
            <span>{selected.name}</span>
            <span className="badge badge-cyan">{selected.type}</span>
          </div>
          <div className="small muted" style={{ marginBottom: 8 }}>
            {selected.objective}
          </div>

          <div className="row-wrap" style={{ marginBottom: 8 }}>
            <button
              className={`btn btn-xs ${placingStop ? "btn-primary" : "btn-cyan"}`}
              onClick={onTogglePlacingStop}
            >
              <MapPin size={11} /> {placingStop ? "Click Globe to Add Stop…" : "+ Add Stop on Map"}
            </button>
            <button className="btn btn-xs" onClick={planRoute} disabled={busy}>
              <Route size={11} /> Plan A* Route
            </button>
            <button className="btn btn-xs" onClick={optimizeStops} disabled={busy}>
              <Sparkles size={11} /> 2-Opt
            </button>
            <button className="btn btn-xs" onClick={loadProfile} disabled={busy}>
              <Activity size={11} /> Profile & Dose
            </button>
            <button className="btn btn-xs" onClick={shareMission}>
              <Share2 size={11} /> Share
            </button>
          </div>

          <div className="row" style={{ marginBottom: 8 }}>
            <span className="small muted">A* Preset:</span>
            <select className="select" value={preset} onChange={(e) => setPreset(e.target.value)}>
              <option value="balanced">Balanced</option>
              <option value="terrain">Terrain-Safe</option>
              <option value="speed">Speed</option>
            </select>
          </div>

          {/* Stops list */}
          {selected.stops.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 8 }}>
              {selected.stops.map((s, idx) => (
                <div key={idx} className="stat-box">
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <strong className="small">
                      #{idx + 1} · {s.activity}
                    </strong>
                    <span className="mono small muted">{formatCoords(s.lat, s.lon)}</span>
                  </div>
                  {s.reason && <div className="small muted">{s.reason}</div>}
                </div>
              ))}
            </div>
          )}

          {/* Mission Profile & Path Radiation Summary */}
          {profileData && (
            <div className="stat-box" style={{ marginBottom: 8 }}>
              <div className="stat-label">Route Elevation & Path Radiation [SIM]</div>
              <div className="grid-2" style={{ marginTop: 4 }}>
                <div className="small">
                  Length: <strong className="mono">{profileData.total_km.toFixed(1)} km</strong>
                </div>
                <div className="small">
                  Max Slope: <strong className="mono">{profileData.maxSlope.toFixed(1)}°</strong>
                </div>
                <div className="small">
                  Climb: <strong className="mono">+{profileData.gain.toFixed(0)} m</strong>
                </div>
                <div className="small">
                  Rover Dose: <strong className="mono">{profileData.radMsv.toFixed(2)} mSv</strong>
                </div>
              </div>
            </div>
          )}

          {/* Export Downloads */}
          <div className="row-wrap">
            <a className="btn btn-xs" href={`/missions/${selected.id}/kml`} download style={{ textDecoration: "none" }}>
              <Download size={11} /> KML
            </a>
            <a
              className="btn btn-xs"
              href={`/missions/${selected.id}/geojson`}
              target="_blank"
              rel="noreferrer"
              style={{ textDecoration: "none" }}
            >
              <Download size={11} /> GeoJSON
            </a>
            <a className="btn btn-xs" href={`/missions/${selected.id}/csv`} download style={{ textDecoration: "none" }}>
              <Download size={11} /> CSV Stops
            </a>
          </div>
        </div>
      )}
    </>
  );
};

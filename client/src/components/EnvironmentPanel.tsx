import React, { useEffect, useState } from "react";
import {
  AlertTriangle,
  Droplets,
  MapPin,
  Plus,
  Radio,
  Shield,
  Trash2,
  Users,
  Wind,
  Zap,
} from "lucide-react";
import { api } from "../lib/api";
import { formatCoords } from "../lib/marsMath";
import type {
  CameraState,
  PresenceAgent,
  ShelterCandidate,
  SpatialNode,
  StormResponsePlan,
  StormScenario,
  WaterCandidate,
  WsEventItem,
} from "../types/nam";

interface EnvironmentPanelProps {
  camera: CameraState;
  water: WaterCandidate[];
  shelters: ShelterCandidate[];
  nodes: SpatialNode[];
  presence: PresenceAgent[];
  storms: StormScenario[];
  stormPlan: StormResponsePlan | null;
  wsEvents: WsEventItem[];
  onRefreshStorms: () => Promise<void>;
  onRefreshNodes: () => Promise<void>;
  onRefreshPresence: () => Promise<void>;
  onSetStormPlan: (plan: StormResponsePlan | null) => void;
  onSavePlanAsMission: (plan: StormResponsePlan) => Promise<void>;
  onFlyTo: (lat: number, lon: number, altKm?: number) => void;
  onNotify: (msg: string) => void;
}

type EnvSub = "storms" | "resources" | "nodes" | "presence";

const NODE_TYPES = [
  "waypoint",
  "hazard",
  "water",
  "shelter",
  "observation",
  "mission",
  "annotation",
  "panorama_pov",
];

export const EnvironmentPanel: React.FC<EnvironmentPanelProps> = ({
  camera,
  water,
  shelters,
  nodes,
  presence,
  storms,
  stormPlan,
  wsEvents,
  onRefreshStorms,
  onRefreshNodes,
  onRefreshPresence,
  onSetStormPlan,
  onSavePlanAsMission,
  onFlyTo,
  onNotify,
}) => {
  const [sub, setSub] = useState<EnvSub>("storms");
  const [rad, setRad] = useState<Record<string, unknown> | null>(null);
  const [shielding, setShielding] = useState("suit");
  const [stormCatalog, setStormCatalog] = useState<Array<Record<string, unknown>>>([]);
  const [waterCert, setWaterCert] = useState<string>("ALL");

  // Node creator state
  const [nodeType, setNodeType] = useState("waypoint");
  const [nodeName, setNodeName] = useState("");

  useEffect(() => {
    api.stormCatalog().then((r) => setStormCatalog(r.catalog || [])).catch(() => {});
  }, []);

  const checkRadiation = async () => {
    const activeSep = storms.find((s) => s.kind === "sep");
    const res = await api.radiation(camera.lat, camera.lon, 2.0, shielding, activeSep?.scenario_id);
    setRad(res);
  };

  const simDust = async (scale: string) => {
    const sc = await api.simulateStorm("dust", scale, camera.lat, camera.lon);
    await onRefreshStorms();
    onNotify(`Simulated ${sc.label} — alert broadcast on /ws/events`);
  };

  const simSep = async (cls: string) => {
    const sc = await api.simulateStorm("sep", cls, camera.lat, camera.lon);
    await onRefreshStorms();
    onNotify(`Simulated ${sc.label} — alert broadcast on /ws/events`);
  };

  const runEvacuationPlan = async () => {
    const plan = await api.stormResponse(camera.lat, camera.lon, "X");
    onSetStormPlan(plan);
    onFlyTo(camera.lat, camera.lon, 1500);
    onNotify(`Evacuation plan computed (${plan.total_length_km} km, ${plan.stops.length} stops) [SIM]`);
  };

  const addNode = async () => {
    const label = nodeName.trim() || `${nodeType} @ ${camera.lat.toFixed(1)}°, ${camera.lon.toFixed(1)}°`;
    await api.createNode({ type: nodeType, name: label, lat: camera.lat, lon: camera.lon, props: {} });
    setNodeName("");
    await onRefreshNodes();
    onNotify(`Added spatial node "${label}"`);
  };

  const filteredWater = waterCert === "ALL" ? water : water.filter((w) => w.certainty === waterCert);

  return (
    <>
      <div className="pill-group">
        {(
          [
            ["storms", "Storms & Rad"],
            ["resources", "Water/Shelter"],
            ["nodes", "Nodes (8)"],
            ["presence", "Live Ops"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            className={`btn btn-xs ${sub === id ? "btn-active" : "btn-ghost"}`}
            style={{ flex: 1 }}
            onClick={() => setSub(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Storms, Radiation & SEP Evacuation Planner */}
      {sub === "storms" && (
        <>
          <div className="card">
            <div className="card-title">
              <span className="row">
                <Zap size={13} color="#f59e0b" /> Surface Radiation (RAD-Anchored)
              </span>
              <span className="badge badge-sim">[SIM] ±30%</span>
            </div>
            <div className="row" style={{ marginTop: 6 }}>
              <select className="select" value={shielding} onChange={(e) => setShielding(e.target.value)}>
                <option value="suit">EVA Suit (1.0×)</option>
                <option value="hab">Habitat (0.45×)</option>
                <option value="none">Unshielded (1.15×)</option>
              </select>
              <button className="btn btn-primary" onClick={checkRadiation}>
                Estimate (2 Sols)
              </button>
            </div>
            {rad && (
              <div className="grid-3" style={{ marginTop: 8 }}>
                <div className="stat-box">
                  <div className="stat-label">GCR/Sol</div>
                  <div className="stat-val">{String(rad.gcr_dose_equiv_msv_per_sol)}</div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">SEP mSv</div>
                  <div className="stat-val">{String(rad.sep_total_msv)}</div>
                </div>
                <div className="stat-box">
                  <div className="stat-label">Total mSv</div>
                  <div className="stat-val">{String(rad.total_msv)}</div>
                </div>
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-title">
              <span className="row">
                <Wind size={13} color="#ef4444" /> Dust & SEP Storm Simulator
              </span>
              <span className="badge badge-sim">[SIM]</span>
            </div>
            <div className="row-wrap" style={{ marginTop: 6 }}>
              <button className="btn btn-xs" onClick={() => simDust("local")}>
                Local Dust
              </button>
              <button className="btn btn-xs" onClick={() => simDust("regional")}>
                Regional Dust
              </button>
              <button className="btn btn-xs" onClick={() => simDust("my34")}>
                MY34 Global Dust
              </button>
              <button className="btn btn-xs btn-danger" onClick={() => simSep("M")}>
                M-Class SEP
              </button>
              <button className="btn btn-xs btn-danger" onClick={() => simSep("X")}>
                X-Class SEP
              </button>
            </div>

            <button
              className="btn btn-danger"
              style={{ width: "100%", marginTop: 8 }}
              onClick={runEvacuationPlan}
            >
              <AlertTriangle size={13} /> Plan Storm-Response Evacuation From View
            </button>
          </div>

          {/* Active Evacuation Plan */}
          {stormPlan && (
            <div className="card" style={{ borderColor: "rgba(244,63,94,0.45)" }}>
              <div className="card-title">
                <span>Evacuation Plan ({stormPlan.total_length_km} km)</span>
                <span className="badge badge-danger">ADVISORY [SIM]</span>
              </div>
              {stormPlan.stops.map((s) => (
                <div key={s.stop} className="stat-box" style={{ marginTop: 5 }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <strong className="small">
                      Stop {s.stop}: {s.activity}
                    </strong>
                    <span className="mono small muted">{formatCoords(s.lat, s.lon)}</span>
                  </div>
                  <div className="small muted">{s.reason}</div>
                </div>
              ))}
              <div className="row" style={{ marginTop: 8 }}>
                <button
                  className="btn btn-xs btn-primary"
                  style={{ flex: 1 }}
                  onClick={() => onSavePlanAsMission(stormPlan)}
                >
                  Approve & Save as Mission
                </button>
                <button className="btn btn-xs" onClick={() => onSetStormPlan(null)}>
                  Dismiss
                </button>
              </div>
            </div>
          )}

          {/* Active Simulated Storms */}
          {storms.length > 0 && (
            <div className="card">
              <div className="card-title">Active Simulations ({storms.length})</div>
              {storms.map((st) => (
                <div key={st.scenario_id} className="row" style={{ justifyContent: "space-between", padding: "4px 0" }}>
                  <span className="small">{st.label}</span>
                  <button
                    className="btn btn-xs btn-ghost"
                    onClick={async () => {
                      await api.deleteStorm(st.scenario_id);
                      await onRefreshStorms();
                    }}
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              ))}
            </div>
          )}

          {/* Documented Historical Storm Catalog */}
          <div className="card">
            <div className="card-title">
              <span>Historical Mars Storm Catalog</span>
              <span className="badge badge-obs">OBSERVED</span>
            </div>
            {stormCatalog.map((ev) => (
              <div
                key={String(ev.id)}
                style={{ padding: "5px 0", borderTop: "1px solid rgba(255,255,255,0.06)" }}
              >
                <div style={{ fontWeight: 600, fontSize: 11.5 }}>{String(ev.name)}</div>
                <div className="small muted">{String(ev.summary)}</div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Water & Shelter Candidates */}
      {sub === "resources" && (
        <>
          <div className="card">
            <div className="card-title">
              <span className="row">
                <Droplets size={13} color="#38bdf8" /> SWIM Water-Ice Candidates ({filteredWater.length})
              </span>
              <div className="row">
                {["ALL", "A", "B", "C"].map((c) => (
                  <button
                    key={c}
                    className={`btn btn-xs ${waterCert === c ? "btn-active" : ""}`}
                    onClick={() => setWaterCert(c)}
                  >
                    {c}
                  </button>
                ))}
              </div>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 6 }}>
              {filteredWater.map((w) => (
                <div
                  key={w.id}
                  className="search-hit"
                  style={{ background: "rgba(255,255,255,0.03)" }}
                  onClick={() => onFlyTo(w.lat, w.lon, 900)}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 12 }}>
                      {w.name} <span className="badge badge-cyan">Class {w.certainty}</span>
                    </div>
                    <div className="small muted">
                      Depth {w.depth_to_ice_m[0]}–{w.depth_to_ice_m[1]} m · {w.note}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-title">
              <span className="row">
                <Shield size={13} color="#34d399" /> 12 Scored Shelters
              </span>
              <span className="badge badge-sim">[SIM] Index</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5, marginTop: 6 }}>
              {shelters.map((s) => (
                <div
                  key={s.id}
                  className="search-hit"
                  style={{ background: "rgba(255,255,255,0.03)" }}
                  onClick={() => onFlyTo(s.lat, s.lon, 650)}
                >
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 12 }}>{s.name}</div>
                    <div className="small muted">
                      {(s as unknown as { type?: string }).type || s.kind} · Shield {s.shielding} · Thermal {s.thermal} · Access {s.access}
                    </div>
                  </div>
                  <span className="badge badge-obs mono">{s.composite_index}</span>
                </div>
              ))}
            </div>
          </div>
        </>
      )}

      {/* 8-Type Spatial Nodes CRUD */}
      {sub === "nodes" && (
        <>
          <div className="card">
            <div className="card-title">
              <span className="row">
                <MapPin size={13} color="#f472b6" /> Add Spatial Node at View Center
              </span>
            </div>
            <div className="row" style={{ marginTop: 6 }}>
              <select className="select" value={nodeType} onChange={(e) => setNodeType(e.target.value)}>
                {NODE_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <input
                className="input"
                placeholder="Label…"
                value={nodeName}
                onChange={(e) => setNodeName(e.target.value)}
              />
            </div>
            <button className="btn btn-primary" style={{ width: "100%", marginTop: 8 }} onClick={addNode}>
              <Plus size={13} /> Drop {nodeType} ({camera.lat.toFixed(1)}°, {camera.lon.toFixed(1)}°)
            </button>
          </div>

          <div className="card">
            <div className="card-title">Saved Spatial Nodes ({nodes.length})</div>
            {nodes.length === 0 ? (
              <div className="small muted">No spatial nodes yet. Create any of the 8 node types above.</div>
            ) : (
              nodes.map((n) => (
                <div key={n.id} className="search-hit" onClick={() => onFlyTo(n.lat, n.lon, 500)}>
                  <div>
                    <div style={{ fontWeight: 600, fontSize: 12 }}>
                      <span className="badge badge-muted">{n.type}</span> {n.name}
                    </div>
                    <div className="mono small muted">{formatCoords(n.lat, n.lon)}</div>
                  </div>
                  <button
                    className="btn btn-xs btn-ghost"
                    onClick={async (e) => {
                      e.stopPropagation();
                      await api.deleteNode(n.id);
                      await onRefreshNodes();
                    }}
                  >
                    <Trash2 size={11} />
                  </button>
                </div>
              ))
            )}
          </div>
        </>
      )}

      {/* Live Presence Simulation & WebSocket Event Log */}
      {sub === "presence" && (
        <>
          <div className="card">
            <div className="card-title">
              <span className="row">
                <Users size={13} color="#a3e635" /> Presence Feed ({presence.length})
              </span>
              <button
                className="btn btn-xs btn-primary"
                onClick={async () => {
                  await api.tickPresence(0.25);
                  await onRefreshPresence();
                }}
              >
                +0.25 Sol Tick
              </button>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, marginTop: 6 }}>
              {presence.map((a) => (
                <div
                  key={a.id}
                  className="search-hit"
                  style={{ padding: "5px 6px", background: "rgba(255,255,255,0.03)" }}
                  onClick={() => onFlyTo(a.lat, a.lon, 450)}
                >
                  <div>
                    <strong className="small">{a.name}</strong>{" "}
                    <span className="badge badge-sim">{a.kind}</span>
                    <div className="small muted">{a.role}</div>
                  </div>
                  <span className="mono small muted">{formatCoords(a.lat, a.lon)}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-title">
              <span className="row">
                <Radio size={13} color="#38bdf8" /> Live WebSocket Feed (/ws/events)
              </span>
              <span className="badge badge-obs">{wsEvents.length}</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 4, maxHeight: 190, overflowY: "auto" }}>
              {wsEvents.slice(0, 15).map((e, idx) => (
                <div key={idx} className="stat-box" style={{ padding: "4px 6px" }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <span
                      className={`badge ${
                        e.type === "storm_alert"
                          ? "badge-danger"
                          : e.type === "plan_change"
                          ? "badge-cyan"
                          : "badge-muted"
                      }`}
                    >
                      {e.type}
                    </span>
                    <span className="mono small muted">#{e.id ?? idx}</span>
                  </div>
                  <div className="small muted" style={{ marginTop: 2 }}>
                    {e.scenario?.label || e.name || e.action || (e.payload?.sol_clock as string) || "event"}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </>
  );
};

import React, { useEffect, useState } from "react";
import { Compass, Database, ExternalLink, FlaskConical, Scale, ShieldAlert } from "lucide-react";
import { api } from "../lib/api";
import { formatCoords } from "../lib/marsMath";
import type { Discovery, LandingSite } from "../types/nam";

interface SciencePanelProps {
  discoveries: Discovery[];
  landingSites: LandingSite[];
  onFlyTo: (lat: number, lon: number, altKm?: number) => void;
}

type SubTab = "discoveries" | "compare" | "catalogs";

export const SciencePanel: React.FC<SciencePanelProps> = ({
  discoveries,
  landingSites,
  onFlyTo,
}) => {
  const [sub, setSub] = useState<SubTab>("discoveries");
  const [searchQ, setSearchQ] = useState("");
  const [selectedSites, setSelectedSites] = useState<string[]>(["jezero", "curiosity", "opportunity"].map((s) =>
    s === "jezero" ? "perseverance" : s
  ));
  const [comparison, setComparison] = useState<Array<Record<string, unknown>>>([]);
  const [catalogKind, setCatalogKind] = useState<"orbiters" | "instruments" | "spectral" | "datasets" | "unavailable">(
    "orbiters"
  );
  const [catalogItems, setCatalogItems] = useState<Array<Record<string, unknown>>>([]);

  useEffect(() => {
    if (sub !== "catalogs") return;
    let alive = true;
    const loader = async () => {
      if (catalogKind === "orbiters") return (await api.orbiters()).orbiters;
      if (catalogKind === "instruments") return (await api.instruments()).instruments;
      if (catalogKind === "spectral") return (await api.spectralTargets()).spectral_targets;
      if (catalogKind === "datasets") return (await api.datasets()).datasets;
      return (await api.unavailableSources()).unavailable_sources;
    };
    loader()
      .then((list) => {
        if (alive) setCatalogItems(list || []);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [sub, catalogKind]);

  const runSiteCompare = async () => {
    if (selectedSites.length < 2) return;
    const res = await api.compareSites(selectedSites.slice(0, 3));
    setComparison(res.comparison || []);
  };

  useEffect(() => {
    if (sub === "compare" && comparison.length === 0) {
      runSiteCompare().catch(() => {});
    }
  }, [sub]);

  const filteredDisc = discoveries.filter((d) => {
    if (!searchQ.trim()) return true;
    const q = searchQ.toLowerCase();
    return (
      d.title.toLowerCase().includes(q) ||
      d.summary.toLowerCase().includes(q) ||
      d.instrument.toLowerCase().includes(q) ||
      d.mission.toLowerCase().includes(q) ||
      d.tags.some((t) => t.toLowerCase().includes(q))
    );
  });

  const toggleSite = (id: string) => {
    setSelectedSites((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id);
      if (prev.length >= 3) return [...prev.slice(1), id];
      return [...prev, id];
    });
  };

  return (
    <>
      <div className="pill-group">
        <button
          className={`btn btn-xs ${sub === "discoveries" ? "btn-active" : "btn-ghost"}`}
          style={{ flex: 1 }}
          onClick={() => setSub("discoveries")}
        >
          <FlaskConical size={12} /> Discoveries
        </button>
        <button
          className={`btn btn-xs ${sub === "compare" ? "btn-active" : "btn-ghost"}`}
          style={{ flex: 1 }}
          onClick={() => setSub("compare")}
        >
          <Scale size={12} /> Compare Sites
        </button>
        <button
          className={`btn btn-xs ${sub === "catalogs" ? "btn-active" : "btn-ghost"}`}
          style={{ flex: 1 }}
          onClick={() => setSub("catalogs")}
        >
          <Database size={12} /> Catalogs
        </button>
      </div>

      {/* Cited Observation & Discovery Browser */}
      {sub === "discoveries" && (
        <>
          <input
            className="input"
            placeholder="Filter discoveries (clay, methane, CRISM, RSL, ice)…"
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
          />
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {filteredDisc.map((d) => (
              <div key={d.id} className="card">
                <div className="card-title">
                  <span>{d.title}</span>
                  <span className="badge badge-obs">{d.instrument}</span>
                </div>
                <div className="small muted" style={{ lineHeight: 1.4 }}>
                  {d.summary}
                </div>
                <div className="small" style={{ marginTop: 5, color: "#cbd5e1" }}>
                  <strong>Citation:</strong> {d.evidence.citation}
                </div>
                <div className="row" style={{ justifyContent: "space-between", marginTop: 6 }}>
                  <span className="mono small muted">{formatCoords(d.lat, d.lon)}</span>
                  <div className="row">
                    <button className="btn btn-xs btn-primary" onClick={() => onFlyTo(d.lat, d.lon, 480)}>
                      <Compass size={11} /> Fly To
                    </button>
                    {d.evidence.url && (
                      <a
                        href={d.evidence.url}
                        target="_blank"
                        rel="noreferrer"
                        className="btn btn-xs btn-ghost"
                        style={{ textDecoration: "none" }}
                      >
                        <ExternalLink size={11} />
                      </a>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Side-by-Side Landing-Site Comparison */}
      {sub === "compare" && (
        <>
          <div className="card">
            <div className="card-title">
              <span>Pick 2–3 Landing Sites</span>
              <button className="btn btn-xs btn-primary" onClick={runSiteCompare}>
                Compare ({selectedSites.length})
              </button>
            </div>
            <div className="row-wrap" style={{ marginTop: 6 }}>
              {landingSites.map((s) => (
                <button
                  key={s.id}
                  className={`btn btn-xs ${selectedSites.includes(s.id) ? "btn-active" : ""}`}
                  onClick={() => toggleSite(s.id)}
                >
                  {s.mission}
                </button>
              ))}
            </div>
          </div>

          {comparison.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
              {comparison.map((c) => {
                const terr = (c.local_terrain || {}) as Record<string, number>;
                return (
                  <div key={String(c.id)} className="card">
                    <div className="card-title">
                      <span>{String(c.name)}</span>
                      <button
                        className="btn btn-xs"
                        onClick={() => onFlyTo(Number(c.lat), Number(c.lon), 400)}
                      >
                        Fly
                      </button>
                    </div>
                    <div className="grid-3" style={{ marginTop: 5 }}>
                      <div className="stat-box">
                        <div className="stat-label">Elev</div>
                        <div className="stat-val">{String(c.elevation_m)} m</div>
                      </div>
                      <div className="stat-box">
                        <div className="stat-label">Hazard</div>
                        <div className="stat-val">{terr.hazard_score ?? "—"}</div>
                      </div>
                      <div className="stat-box">
                        <div className="stat-label">Water &lt;1500k</div>
                        <div className="stat-val">{String(c.water_candidates_within_1500km)}</div>
                      </div>
                    </div>
                    <div className="small muted" style={{ marginTop: 5 }}>
                      Landed {String(c.landing_date)} · {String(c.cited_discoveries)} discoveries ·{" "}
                      {String(c.panoramas_available)} panoramas
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Full Scientific Database Catalogs */}
      {sub === "catalogs" && (
        <>
          <div className="row-wrap">
            {(
              [
                ["orbiters", "Orbiters (8)"],
                ["instruments", "Instruments (13)"],
                ["spectral", "Spectral Targets (16)"],
                ["datasets", "Datasets (12)"],
                ["unavailable", "Unavailable (7)"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                className={`btn btn-xs ${catalogKind === id ? "btn-active" : ""}`}
                onClick={() => setCatalogKind(id)}
              >
                {label}
              </button>
            ))}
          </div>

          {catalogKind === "unavailable" && (
            <div className="card" style={{ borderColor: "rgba(245,158,11,0.35)" }}>
              <div className="row small" style={{ color: "#fcd34d" }}>
                <ShieldAlert size={13} /> Honest Service Boundary Registry
              </div>
              <div className="small muted" style={{ marginTop: 3 }}>
                These external feeds are never fabricated. Official access paths are documented below.
              </div>
            </div>
          )}

          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {catalogItems.map((it, idx) => (
              <div key={String(it.id || idx)} className="card">
                <div className="card-title">
                  <span>{String(it.name)}</span>
                  {typeof it.status === "string" && <span className="badge badge-obs">{it.status}</span>}
                  {typeof it.mineral_class === "string" && (
                    <span className="badge badge-cyan">{it.mineral_class}</span>
                  )}
                  {typeof it.org === "string" && <span className="badge badge-muted">{it.org}</span>}
                </div>
                <div className="small muted">
                  {String(it.measures || it.note || it.reason || it.orbit || "")}
                </div>
                {typeof it.citation === "string" && (
                  <div className="small" style={{ marginTop: 3, color: "#cbd5e1" }}>
                    {it.citation}
                  </div>
                )}
                <div className="row" style={{ justifyContent: "space-between", marginTop: 5 }}>
                  {typeof it.lat === "number" && typeof it.lon === "number" ? (
                    <>
                      <span className="mono small muted">{formatCoords(it.lat, it.lon)}</span>
                      <button
                        className="btn btn-xs btn-primary"
                        onClick={() => onFlyTo(it.lat as number, it.lon as number, 480)}
                      >
                        Fly
                      </button>
                    </>
                  ) : (
                    <span className="small muted">{String(it.src || it.agency || it.mission || "")}</span>
                  )}
                  {(typeof it.url === "string" || typeof it.access_path === "string") && (
                    <a
                      href={String(it.url || it.access_path)}
                      target="_blank"
                      rel="noreferrer"
                      className="small"
                      style={{ color: "#38bdf8", display: "inline-flex", alignItems: "center", gap: 3 }}
                    >
                      Official Link <ExternalLink size={10} />
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
};

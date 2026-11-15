import React, { useEffect, useState } from "react";
import { BookmarkPlus, Camera, Compass, Footprints, Layers, MapPin, X } from "lucide-react";
import { api } from "../lib/api";
import { formatCoords } from "../lib/marsMath";

interface LocationCardProps {
  lat: number;
  lon: number;
  title?: string;
  onClose: () => void;
  onEnterStreetView: (panoramaId?: string) => void;
  onEnterWalkView: (lat: number, lon: number) => void;
  onBookmark: (name: string, lat: number, lon: number) => void;
  onFlyTo: (lat: number, lon: number, altKm?: number) => void;
}

export const LocationCard: React.FC<LocationCardProps> = ({
  lat,
  lon,
  title,
  onClose,
  onEnterStreetView,
  onEnterWalkView,
  onBookmark,
  onFlyTo,
}) => {
  const [card, setCard] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setErr(null);
    api
      .locationCard(lat, lon)
      .then((res) => {
        if (alive) setCard(res);
      })
      .catch((e) => {
        if (alive) setErr(String(e));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [lat, lon]);

  const terrain = (card?.terrain || {}) as Record<string, number>;
  const region = (card?.region_context || {}) as Record<string, string>;
  const imagery = (card?.imagery_depth || {}) as Record<string, unknown>;
  const nearby = (card?.nearby_features || []) as Array<{ id: string; name: string; type: string; lat: number; lon: number; distance_km: number }>;
  const observations = (card?.observations || []) as Array<{ id: string; title: string; mission: string; evidence?: { citation?: string } }>;
  const pans = (card?.nearest_panoramas || []) as Array<{ id: string; rover: string; title: string; distance_km: number }>;
  const displayName = title || nearby[0]?.name || region.region || "Selected Mars Location";

  return (
    <aside className="right-card glass">
      <div className="drawer-head">
        <div className="row" style={{ minWidth: 0 }}>
          <MapPin size={15} color="#e46f3b" />
          <div style={{ minWidth: 0 }}>
            <div style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{displayName}</div>
            <div className="mono small muted">{formatCoords(lat, lon)}</div>
          </div>
        </div>
        <button className="btn btn-xs btn-ghost" onClick={onClose} aria-label="Close location card">
          <X size={14} />
        </button>
      </div>

      <div className="drawer-body">
        {loading && <div className="muted small">Loading planetary location card…</div>}
        {err && <div className="badge badge-danger">{err}</div>}

        {!loading && card && (
          <>
            {/* Quick action bar */}
            <div className="row-wrap">
              <button className="btn btn-xs btn-primary" onClick={() => onEnterWalkView(lat, lon)}>
                <Footprints size={12} /> Walk View
              </button>
              <button
                className="btn btn-xs btn-cyan"
                onClick={() => onEnterStreetView(pans[0]?.id)}
                title={pans[0] ? `Open nearest panorama (${pans[0].rover})` : "Open Street View catalog"}
              >
                <Camera size={12} /> {pans[0] ? "Street View" : "Panoramas"}
              </button>
              <button className="btn btn-xs" onClick={() => onBookmark(displayName, lat, lon)}>
                <BookmarkPlus size={12} /> Bookmark
              </button>
              <button className="btn btn-xs" onClick={() => onFlyTo(lat, lon, 420)}>
                <Compass size={12} /> Zoom
              </button>
            </div>

            {/* Terrain stats */}
            <div className="grid-3">
              <div className="stat-box">
                <div className="stat-label">Elevation</div>
                <div className="stat-val">{terrain.elevation_m ?? "—"} m</div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Slope</div>
                <div className="stat-val">{terrain.slope_deg ?? "—"}°</div>
              </div>
              <div className="stat-box">
                <div className="stat-label">Aspect</div>
                <div className="stat-val">{terrain.aspect_deg ?? "—"}°</div>
              </div>
            </div>

            {/* Geologic Region */}
            {region.region && (
              <div className="card">
                <div className="card-title">
                  <span>{region.region}</span>
                  <span className="badge badge-sim">[SIM] Context</span>
                </div>
                <div className="small muted">{region.description}</div>
              </div>
            )}

            {/* Imagery Depth Ladder */}
            <div className="card">
              <div className="card-title">
                <span className="row">
                  <Layers size={13} color="#38bdf8" /> Imagery Depth
                </span>
                <span className="badge badge-obs">{String(imagery.best_available || "CTX 5m")}</span>
              </div>
              <div className="small muted">
                HiRISE inset: {imagery.hirise_inset ? "Available (~0.3 m/px)" : "CTX global (~5 m/px)"}
              </div>
            </div>

            {/* Nearest Panoramas */}
            {pans.length > 0 && (
              <div className="card">
                <div className="card-title">Nearby Ground Panoramas ({pans.length})</div>
                {pans.slice(0, 3).map((p) => (
                  <div
                    key={p.id}
                    className="search-hit"
                    style={{ padding: "5px 6px" }}
                    onClick={() => onEnterStreetView(p.id)}
                  >
                    <div>
                      <div style={{ fontWeight: 600, fontSize: 11.5 }}>{p.rover}</div>
                      <div className="small muted">{p.title}</div>
                    </div>
                    <span className="mono small">{p.distance_km} km</span>
                  </div>
                ))}
              </div>
            )}

            {/* Nearby Named Features */}
            {nearby.length > 0 && (
              <div className="card">
                <div className="card-title">Nearby USGS Features ({nearby.length})</div>
                {nearby.slice(0, 4).map((f) => (
                  <div
                    key={f.id}
                    className="search-hit"
                    style={{ padding: "4px 6px" }}
                    onClick={() => onFlyTo(f.lat, f.lon, 650)}
                  >
                    <div>
                      <span style={{ fontWeight: 600, fontSize: 11.5 }}>{f.name}</span>{" "}
                      <span className="small muted">({f.type})</span>
                    </div>
                    <span className="mono small muted">{f.distance_km} km</span>
                  </div>
                ))}
              </div>
            )}

            {/* Cited Discoveries */}
            {observations.length > 0 && (
              <div className="card">
                <div className="card-title">
                  <span>Cited Discoveries ({observations.length})</span>
                  <span className="badge badge-obs">OBSERVED</span>
                </div>
                {observations.slice(0, 3).map((o) => (
                  <div key={o.id} style={{ padding: "4px 0", borderTop: "1px solid rgba(255,255,255,0.06)" }}>
                    <div style={{ fontWeight: 600, fontSize: 11.5 }}>{o.title}</div>
                    <div className="small muted">{o.evidence?.citation || o.mission}</div>
                  </div>
                ))}
              </div>
            )}

            <div className="small muted">
              Provenance: USGS Gazetteer · Terrain values from demo-synthetic-grid [SIM] (swap: MOLA MEGDR 4 ppd).
            </div>
          </>
        )}
      </div>
    </aside>
  );
};

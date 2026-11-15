import React, { useState } from "react";
import { Camera, Clock, Compass, ExternalLink, Film, Footprints, Images } from "lucide-react";
import { api } from "../lib/api";
import { formatCoords } from "../lib/marsMath";
import { fetchLiveRoverRawImages, resolvePanoramaPhoto, type LiveRoverRawImage } from "../lib/nasaImagery";
import type { CameraState, Panorama } from "../types/nam";

interface StreetViewPanelProps {
  panoramas: Panorama[];
  camera: CameraState;
  onOpenPanorama: (p: Panorama) => void;
  onOpenWalkView: (lat: number, lon: number) => void;
  onFlyTo: (lat: number, lon: number, altKm?: number) => void;
  onOpenNasaHub?: (tab: "footage" | "raw" | "library" | "resources") => void;
}

export const StreetViewPanel: React.FC<StreetViewPanelProps> = ({
  panoramas,
  camera,
  onOpenPanorama,
  onOpenWalkView,
  onFlyTo,
  onOpenNasaHub,
}) => {
  const [roverFilter, setRoverFilter] = useState("All");
  const [histCompare, setHistCompare] = useState<{
    rover: string;
    earlier: Panorama;
    later: Panorama;
    delta: { sol_delta: number | null; separation_km: number; bearing_deg: number; heading_delta_deg: number };
  } | null>(null);
  const [rawFeed, setRawFeed] = useState<{ source: string; live: boolean; images: LiveRoverRawImage[] } | null>(null);
  const [loadingRaw, setLoadingRaw] = useState(false);

  const rovers = ["All", ...Array.from(new Set(panoramas.map((p) => p.rover)))];
  const filtered = roverFilter === "All" ? panoramas : panoramas.filter((p) => p.rover === roverFilter);

  const runHistoricalCompare = async (rover: string) => {
    try {
      const res = await api.compareRoverHistory(rover);
      setHistCompare(res);
    } catch {
      setHistCompare(null);
    }
  };

  const fetchRawFeed = async () => {
    setLoadingRaw(true);
    try {
      const res = await fetchLiveRoverRawImages({ rover: "perseverance", num: 6, page: 0 });
      setRawFeed(res);
    } finally {
      setLoadingRaw(false);
    }
  };

  return (
    <>
      <div className="card">
        <div className="card-title">
          <span className="row">
            <Camera size={13} color="#fbbf24" /> Mars Street View & Walk View
          </span>
          <span className="badge badge-obs">{panoramas.length} Poses</span>
        </div>
        <div className="small muted" style={{ marginBottom: 8 }}>
          Click any camera marker on the globe or pick a rover panorama below to enter 360° Street View, or launch 3D First-Person Walk View at your current orbital view.
        </div>
        <div className="row-wrap">
          <button
            className="btn btn-xs btn-primary"
            onClick={() => onOpenWalkView(camera.lat, camera.lon)}
          >
            <Footprints size={12} /> Walk Here ({camera.lat.toFixed(1)}°, {camera.lon.toFixed(1)}°)
          </button>
          <button className="btn btn-xs btn-cyan" onClick={() => runHistoricalCompare("Perseverance")}>
            <Clock size={12} /> Compare Jezero Sols
          </button>
          <button className="btn btn-xs" onClick={() => runHistoricalCompare("Curiosity")}>
            <Clock size={12} /> Compare Gale Sols
          </button>
        </div>
      </div>

      {/* Historical Side-by-Side Comparison */}
      {histCompare && (
        <div className="card">
          <div className="card-title">
            <span>{histCompare.rover} Historical Compare</span>
            <span className="badge badge-cyan">
              Δ {histCompare.delta.sol_delta ?? "—"} Sols · {histCompare.delta.separation_km} km
            </span>
          </div>
          <div className="grid-2" style={{ marginTop: 6 }}>
            <div className="stat-box">
              <div className="stat-label">Earlier (Sol {histCompare.earlier.sol ?? "—"})</div>
              <div style={{ fontWeight: 600, fontSize: 11.5, marginTop: 2 }}>{histCompare.earlier.title}</div>
              <div className="small muted">{histCompare.earlier.date}</div>
              <button
                className="btn btn-xs"
                style={{ marginTop: 5 }}
                onClick={() => onOpenPanorama(histCompare.earlier)}
              >
                Open 360°
              </button>
            </div>
            <div className="stat-box">
              <div className="stat-label">Later (Sol {histCompare.later.sol ?? "—"})</div>
              <div style={{ fontWeight: 600, fontSize: 11.5, marginTop: 2 }}>{histCompare.later.title}</div>
              <div className="small muted">{histCompare.later.date}</div>
              <button
                className="btn btn-xs"
                style={{ marginTop: 5 }}
                onClick={() => onOpenPanorama(histCompare.later)}
              >
                Open 360°
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Live NASA Perseverance Raw-Image Gallery Preview + Full Cinema Launch */}
      <div className="card">
        <div className="card-title">
          <span className="row">
            <Images size={13} color="#38bdf8" /> Live Perseverance Raw Photos (1M+)
          </span>
          <button className="btn btn-xs btn-primary" onClick={fetchRawFeed} disabled={loadingRaw}>
            {loadingRaw ? "Fetching…" : "Load Live"}
          </button>
        </div>
        <div className="row-wrap" style={{ marginTop: 6 }}>
          {onOpenNasaHub && (
            <>
              <button className="btn btn-xs btn-cyan" onClick={() => onOpenNasaHub("raw")}>
                <Images size={11} /> Browse 1M+ Raw Gallery
              </button>
              <button className="btn btn-xs" onClick={() => onOpenNasaHub("footage")}>
                <Film size={11} /> Watch NASA Footage
              </button>
            </>
          )}
        </div>
        {rawFeed && (
          <div style={{ marginTop: 8 }}>
            <div className="small" style={{ color: rawFeed.live ? "#86efac" : "#fcd34d", marginBottom: 6 }}>
              ● {rawFeed.source}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
              {rawFeed.images.slice(0, 4).map((im) => (
                <a
                  key={im.id}
                  href={im.fullUrl}
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    borderRadius: 6,
                    overflow: "hidden",
                    border: "1px solid var(--border)",
                    textDecoration: "none",
                    color: "inherit",
                  }}
                >
                  <img src={im.thumbUrl} alt={im.title} style={{ width: "100%", height: 64, objectFit: "cover", display: "block" }} />
                  <div style={{ padding: "3px 5px", fontSize: 10 }}>
                    <strong>Sol {im.sol}</strong> · {im.camera}
                  </div>
                </a>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Filterable Panorama Catalog with Real NASA Thumbnails */}
      <div className="card">
        <div className="row-wrap" style={{ marginBottom: 8 }}>
          {rovers.map((r) => (
            <button
              key={r}
              className={`btn btn-xs ${roverFilter === r ? "btn-active" : ""}`}
              onClick={() => setRoverFilter(r)}
            >
              {r}
            </button>
          ))}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {filtered.map((p) => {
            const photo = resolvePanoramaPhoto(p);
            return (
              <div
                key={p.id}
                style={{
                  borderRadius: 8,
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  overflow: "hidden",
                }}
              >
                <img
                  src={photo.localUrl}
                  alt={p.title}
                  onClick={() => onOpenPanorama(p)}
                  style={{ width: "100%", height: 74, objectFit: "cover", display: "block", cursor: "pointer" }}
                />
                <div style={{ padding: "7px 8px" }}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <strong style={{ fontSize: 12 }}>
                      {p.rover} {p.sol !== null ? `· Sol ${p.sol}` : ""}
                    </strong>
                    <span className="small muted">{photo.piaId}</span>
                  </div>
                  <div className="small" style={{ marginTop: 2 }}>
                    {p.title}
                  </div>
                  <div className="mono small muted" style={{ marginTop: 3 }}>
                    {formatCoords(p.lat, p.lon)} · Hdg {p.heading_deg}° · {p.credit}
                  </div>
                  <div className="row" style={{ marginTop: 6 }}>
                    <button className="btn btn-xs btn-primary" onClick={() => onOpenPanorama(p)}>
                      <Camera size={11} /> Enter 360° Photo
                    </button>
                    <button className="btn btn-xs" onClick={() => onFlyTo(p.lat, p.lon, 280)}>
                      <Compass size={11} /> Orbit
                    </button>
                    <a
                      href={p.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="btn btn-xs btn-ghost"
                      style={{ textDecoration: "none" }}
                    >
                      <ExternalLink size={11} />
                    </a>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </>
  );
};

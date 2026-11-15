import React, { useEffect, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Camera, Clock, Compass, ExternalLink, ZoomIn, ZoomOut, X } from "lucide-react";
import { api } from "../lib/api";
import { formatCoords, normLon } from "../lib/marsMath";
import { resolvePanoramaPhoto } from "../lib/nasaImagery";
import type { Panorama } from "../types/nam";

interface StreetViewModalProps {
  panorama: Panorama;
  allPanoramas: Panorama[];
  onSelectPanorama: (p: Panorama) => void;
  onReturnToOrbit: (lat: number, lon: number) => void;
  onClose: () => void;
}

export const StreetViewModal: React.FC<StreetViewModalProps> = ({
  panorama,
  allPanoramas,
  onSelectPanorama,
  onReturnToOrbit,
  onClose,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const photoImgRef = useRef<HTMLImageElement | null>(null);
  const orbitalImgRef = useRef<HTMLImageElement | null>(null);

  const [yawDeg, setYawDeg] = useState(panorama.heading_deg || 0);
  const [pitchDeg, setPitchDeg] = useState(0);
  const [zoom, setZoom] = useState(1.15);
  const [imgStatus, setImgStatus] = useState<"local" | "hd">("local");
  const [renderTick, setRenderTick] = useState(0);
  const [neighbors, setNeighbors] = useState<
    Array<{ id: string; title: string; bearing_deg: number; distance_km: number }>
  >([]);
  const [compareMode, setCompareMode] = useState(false);
  const [histCompare, setHistCompare] = useState<{
    earlier: Panorama;
    later: Panorama;
    delta: { sol_delta: number | null; separation_km: number; bearing_deg: number };
  } | null>(null);

  const dragRef = useRef({ active: false, lastX: 0, lastY: 0 });
  const photoAsset = resolvePanoramaPhoto(panorama);

  // Load real NASA rover photograph (instant local real NASA photo, then live HD NASA Photojournal upgrade!)
  useEffect(() => {
    setYawDeg(panorama.heading_deg || 0);
    setPitchDeg(0);
    setImgStatus("local");

    let cancelled = false;
    const localImg = new Image();
    localImg.onload = () => {
      if (cancelled) return;
      photoImgRef.current = localImg;
      setRenderTick((t) => t + 1);
    };
    localImg.src = photoAsset.localUrl;

    if (photoAsset.nasaHdUrl && photoAsset.nasaHdUrl !== photoAsset.localUrl) {
      const hdImg = new Image();
      hdImg.onload = () => {
        if (cancelled) return;
        photoImgRef.current = hdImg;
        setImgStatus("hd");
        setRenderTick((t) => t + 1);
      };
      hdImg.src = photoAsset.nasaHdUrl;
    }

    if (!orbitalImgRef.current) {
      const orb = new Image();
      orb.onload = () => setRenderTick((t) => t + 1);
      orb.src = "/nasa/mars_viking_global.jpg";
      orbitalImgRef.current = orb;
    }

    api
      .panoramaDetail(panorama.id)
      .then((d) => setNeighbors(d.adjacent_observation_points || []))
      .catch(() => setNeighbors([]));

    api
      .compareRoverHistory(panorama.rover)
      .then((c) => setHistCompare(c))
      .catch(() => setHistCompare(null));

    return () => {
      cancelled = true;
    };
  }, [panorama.id]);

  // Draw real 360° NASA photographic panorama with smooth cylindrical wrapping, compass HUD & orbital mini-map
  useEffect(() => {
    const cv = canvasRef.current;
    if (!cv) return;
    const w = (cv.width = cv.clientWidth || 1000);
    const h = (cv.height = cv.clientHeight || 560);
    const ctx = cv.getContext("2d");
    if (!ctx) return;

    // Deep Martian twilight backdrop behind extreme pitch tilts
    const bg = ctx.createLinearGradient(0, 0, 0, h);
    bg.addColorStop(0, "#1c120d");
    bg.addColorStop(0.5, "#3a2216");
    bg.addColorStop(1, "#120a07");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, w, h);

    const img = photoImgRef.current;
    if (img && img.complete && img.naturalWidth > 0) {
      // Scale panorama cleanly for smooth 360° cylindrical panning + zoom
      const drawH = h * zoom;
      const aspect = img.naturalWidth / Math.max(1, img.naturalHeight);
      // Treat wide mosaics naturally; keep tile width >= 2.2 * viewport width for real 360 wrap feel
      const tileW = Math.max(w * 2.1 * zoom, drawH * Math.min(aspect, 5.5));
      const panOffset = ((((yawDeg % 360) + 360) % 360) / 360) * tileW;
      const pitchShift = (pitchDeg / 40) * (h * 0.36);
      const yTop = (h - drawH) / 2 + pitchShift;

      let startX = -(panOffset % tileW);
      if (startX > 0) startX -= tileW;
      for (let x = startX; x < w + tileW; x += tileW) {
        ctx.drawImage(img, x, yTop, tileW + 1, drawH);
      }

      // Subtle cinematic vignette so HUD readouts stay crisp
      const vig = ctx.createLinearGradient(0, 0, 0, h);
      vig.addColorStop(0, "rgba(6,8,14,0.45)");
      vig.addColorStop(0.16, "rgba(6,8,14,0)");
      vig.addColorStop(0.82, "rgba(6,8,14,0)");
      vig.addColorStop(1, "rgba(6,8,14,0.58)");
      ctx.fillStyle = vig;
      ctx.fillRect(0, 0, w, h);
    } else {
      ctx.fillStyle = "#e2e8f0";
      ctx.font = "14px sans-serif";
      ctx.fillText("Loading real NASA rover panorama…", w / 2 - 110, h / 2);
    }

    // Precision Compass Azimuth Tape at top
    ctx.fillStyle = "rgba(8,12,22,0.72)";
    ctx.fillRect(0, 0, w, 34);
    ctx.strokeStyle = "rgba(255,255,255,0.14)";
    ctx.beginPath();
    ctx.moveTo(0, 34);
    ctx.lineTo(w, 34);
    ctx.stroke();

    const fovDeg = 95 / zoom;
    const cardinals: Record<number, string> = {
      0: "N",
      45: "NE",
      90: "E",
      135: "SE",
      180: "S",
      225: "SW",
      270: "W",
      315: "NW",
    };
    ctx.font = "11px ui-monospace, monospace";
    for (let deg = 0; deg < 360; deg += 15) {
      let d = ((deg - yawDeg + 540) % 360) - 180;
      if (Math.abs(d) > fovDeg * 0.62) continue;
      const sx = w / 2 + (d / fovDeg) * w;
      const isCard = deg % 45 === 0;
      ctx.strokeStyle = isCard ? "#e46f3b" : "rgba(255,255,255,0.38)";
      ctx.beginPath();
      ctx.moveTo(sx, isCard ? 19 : 25);
      ctx.lineTo(sx, 34);
      ctx.stroke();
      ctx.fillStyle = isCard ? "#fff" : "rgba(255,255,255,0.65)";
      const label = cardinals[deg] || `${deg}°`;
      ctx.fillText(label, sx - label.length * 3.4, 14);
    }
    ctx.fillStyle = "#e46f3b";
    ctx.beginPath();
    ctx.moveTo(w / 2 - 5, 34);
    ctx.lineTo(w / 2 + 5, 34);
    ctx.lineTo(w / 2, 27);
    ctx.fill();

    // Adjacent observation point bearing beacons overlaid directly on the Martian horizon
    for (const nb of neighbors) {
      const d = ((nb.bearing_deg - yawDeg + 540) % 360) - 180;
      if (Math.abs(d) > fovDeg * 0.48) continue;
      const sx = w / 2 + (d / fovDeg) * w;
      const sy = h * 0.56 + (pitchDeg / 45) * h * 0.28;
      ctx.fillStyle = "rgba(10, 14, 24, 0.85)";
      ctx.strokeStyle = "#38bdf8";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.roundRect(sx - 72, sy - 22, 144, 38, 8);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "#38bdf8";
      ctx.font = "bold 10px ui-monospace, monospace";
      ctx.fillText(`→ ${nb.distance_km.toFixed(2)} km · ${Math.round(nb.bearing_deg)}°`, sx - 64, sy - 6);
      ctx.fillStyle = "#f1f5f9";
      ctx.font = "11px sans-serif";
      ctx.fillText(nb.title.slice(0, 21), sx - 64, sy + 9);
    }

    // Mini Orbital NASA Viking Context Inset (bottom-right) showing exact rover FOV cone!
    const box = 148;
    const bx = w - box - 14;
    const by = h - box - 14;
    ctx.save();
    ctx.beginPath();
    ctx.roundRect(bx, by, box, box, 10);
    ctx.clip();
    const orb = orbitalImgRef.current;
    if (orb && orb.complete && orb.naturalWidth > 0) {
      // Crop a real 12°×12° NASA Viking window around rover coordinates
      const lon180 = panorama.lon > 180 ? panorama.lon - 360 : panorama.lon;
      const cxFrac = (lon180 + 180) / 360;
      const cyFrac = (90 - panorama.lat) / 180;
      const spanFrac = 14 / 360;
      const sx = Math.max(0, Math.min(orb.naturalWidth - 20, (cxFrac - spanFrac / 2) * orb.naturalWidth));
      const sy = Math.max(0, Math.min(orb.naturalHeight - 20, (cyFrac - spanFrac) * orb.naturalHeight));
      ctx.drawImage(orb, sx, sy, spanFrac * orb.naturalWidth, spanFrac * 2 * orb.naturalHeight, bx, by, box, box);
      ctx.fillStyle = "rgba(8,12,22,0.28)";
      ctx.fillRect(bx, by, box, box);
    } else {
      ctx.fillStyle = "#141822";
      ctx.fillRect(bx, by, box, box);
    }

    // Viewing cone
    const rcx = bx + box / 2;
    const rcy = by + box / 2;
    const rad = ((yawDeg - 90) * Math.PI) / 180;
    ctx.fillStyle = "rgba(56, 189, 248, 0.34)";
    ctx.beginPath();
    ctx.moveTo(rcx, rcy);
    ctx.arc(rcx, rcy, 46, rad - 0.52, rad + 0.52);
    ctx.closePath();
    ctx.fill();

    // Rover pin
    ctx.fillStyle = "#f97316";
    ctx.strokeStyle = "#fff";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(rcx, rcy, 5, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();

    ctx.fillStyle = "rgba(8,12,22,0.82)";
    ctx.fillRect(bx, by + box - 22, box, 22);
    ctx.fillStyle = "#e2e8f0";
    ctx.font = "10px ui-monospace, monospace";
    ctx.fillText(`ORBITAL · ${formatCoords(panorama.lat, panorama.lon)}`, bx + 6, by + box - 8);
    ctx.restore();

    ctx.strokeStyle = "rgba(255,255,255,0.28)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.roundRect(bx, by, box, box, 10);
    ctx.stroke();
  }, [panorama, yawDeg, pitchDeg, zoom, neighbors, renderTick]);

  const roverStops = allPanoramas
    .filter((p) => p.rover === panorama.rover)
    .sort((a, b) => (a.sol || 0) - (b.sol || 0));
  const curIdx = roverStops.findIndex((p) => p.id === panorama.id);

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 80,
        background: "rgba(4, 6, 12, 0.92)",
        display: "flex",
        flexDirection: "column",
        padding: 16,
        gap: 10,
      }}
    >
      {/* Top header */}
      <div className="glass" style={{ padding: "10px 14px", borderRadius: 12, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <Camera size={16} color="#e46f3b" />
        <div style={{ flex: 1, minWidth: 220 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>{panorama.title}</div>
          <div className="small muted">
            {panorama.rover} · {panorama.sol ? `Sol ${panorama.sol}` : panorama.date || "Archive"} ·{" "}
            {formatCoords(panorama.lat, panorama.lon)} · {photoAsset.credit}
          </div>
        </div>
        <span className="pill" style={{ background: "rgba(34,197,94,0.16)", borderColor: "rgba(34,197,94,0.45)", color: "#86efac" }}>
          REAL NASA PHOTO · {photoAsset.piaId} {imgStatus === "hd" ? "(HD)" : ""}
        </span>
        <button className="btn btn-sm" onClick={() => setZoom((z) => Math.max(1.0, Number((z - 0.25).toFixed(2))))} title="Zoom out">
          <ZoomOut size={13} />
        </button>
        <button className="btn btn-sm" onClick={() => setZoom((z) => Math.min(2.6, Number((z + 0.25).toFixed(2))))} title="Zoom in">
          <ZoomIn size={13} />
        </button>
        {histCompare && (
          <button className={`btn btn-sm ${compareMode ? "btn-primary" : ""}`} onClick={() => setCompareMode((v) => !v)}>
            <Clock size={12} /> Historical Compare
          </button>
        )}
        <a
          className="btn btn-sm"
          href={panorama.source_url || "https://mars.nasa.gov/mars2020/multimedia/raw-images/"}
          target="_blank"
          rel="noreferrer"
          style={{ textDecoration: "none" }}
        >
          <ExternalLink size={12} /> NASA Archive
        </a>
        <button className="btn btn-sm btn-primary" onClick={() => onReturnToOrbit(panorama.lat, panorama.lon)}>
          Return to Orbit
        </button>
        <button className="btn btn-sm" onClick={onClose}>
          <X size={14} />
        </button>
      </div>

      {/* Main 360° Real NASA Photo Viewport */}
      <div
        style={{
          flex: 1,
          position: "relative",
          borderRadius: 12,
          overflow: "hidden",
          border: "1px solid var(--border)",
          cursor: "grab",
        }}
        onPointerDown={(e) => {
          dragRef.current = { active: true, lastX: e.clientX, lastY: e.clientY };
          (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!dragRef.current.active) return;
          const dx = e.clientX - dragRef.current.lastX;
          const dy = e.clientY - dragRef.current.lastY;
          dragRef.current.lastX = e.clientX;
          dragRef.current.lastY = e.clientY;
          setYawDeg((y) => normLon(y - dx * 0.26));
          setPitchDeg((p) => Math.max(-28, Math.min(28, p + dy * 0.16)));
        }}
        onPointerUp={() => {
          dragRef.current.active = false;
        }}
        onWheel={(e) => {
          setZoom((z) => Math.max(1.0, Math.min(2.6, z * (e.deltaY > 0 ? 0.92 : 1.08))));
        }}
      >
        <canvas ref={canvasRef} style={{ width: "100%", height: "100%", display: "block" }} />

        <div
          className="glass"
          style={{
            position: "absolute",
            left: 14,
            bottom: 14,
            padding: "8px 12px",
            borderRadius: 10,
            maxWidth: 460,
            fontSize: 12,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <Compass size={13} color="#38bdf8" />
            <span className="mono">
              Azimuth {Math.round(yawDeg)}° · Pitch {pitchDeg.toFixed(0)}° · Zoom {zoom.toFixed(2)}×
            </span>
          </div>
          <div className="small muted">{photoAsset.caption} Drag horizontally to pan 360°, scroll to zoom.</div>
        </div>

        {/* Historical Compare Drawer */}
        {compareMode && histCompare && (
          <div
            className="glass"
            style={{
              position: "absolute",
              right: 14,
              top: 46,
              width: 340,
              padding: 12,
              borderRadius: 10,
            }}
          >
            <div style={{ fontWeight: 700, fontSize: 12, marginBottom: 6 }}>
              Historical Comparison — {panorama.rover}
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 8 }}>
              <div style={{ border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
                <img
                  src={resolvePanoramaPhoto(histCompare.earlier).localUrl}
                  alt={histCompare.earlier.title}
                  style={{ width: "100%", height: 64, objectFit: "cover", display: "block" }}
                />
                <div style={{ padding: 5, fontSize: 10 }}>
                  <div className="muted">EARLIER · Sol {histCompare.earlier.sol ?? "—"}</div>
                  <div style={{ fontWeight: 600 }}>{histCompare.earlier.title.slice(0, 26)}</div>
                </div>
              </div>
              <div style={{ border: "1px solid var(--border)", borderRadius: 6, overflow: "hidden" }}>
                <img
                  src={resolvePanoramaPhoto(histCompare.later).localUrl}
                  alt={histCompare.later.title}
                  style={{ width: "100%", height: 64, objectFit: "cover", display: "block" }}
                />
                <div style={{ padding: 5, fontSize: 10 }}>
                  <div className="muted">LATER · Sol {histCompare.later.sol ?? "—"}</div>
                  <div style={{ fontWeight: 600 }}>{histCompare.later.title.slice(0, 26)}</div>
                </div>
              </div>
            </div>
            <div className="small mono" style={{ color: "#38bdf8" }}>
              Δ Sol: {histCompare.delta.sol_delta ?? "—"} · Traverse: {histCompare.delta.separation_km.toFixed(2)} km · Bearing:{" "}
              {Math.round(histCompare.delta.bearing_deg)}°
            </div>
          </div>
        )}
      </div>

      {/* Bottom Traverse Step Bar */}
      <div className="glass" style={{ padding: "8px 12px", borderRadius: 12, display: "flex", alignItems: "center", gap: 8, overflowX: "auto" }}>
        <button
          className="btn btn-sm"
          disabled={curIdx <= 0}
          onClick={() => curIdx > 0 && onSelectPanorama(roverStops[curIdx - 1])}
        >
          <ArrowLeft size={13} /> Prev Stop
        </button>
        <div style={{ display: "flex", gap: 6, flex: 1, overflowX: "auto" }}>
          {roverStops.map((st) => (
            <button
              key={st.id}
              className={`btn btn-sm ${st.id === panorama.id ? "btn-primary" : ""}`}
              onClick={() => onSelectPanorama(st)}
              style={{ flexShrink: 0 }}
            >
              {st.sol ? `Sol ${st.sol}` : st.date || st.id} — {st.title.slice(0, 22)}
            </button>
          ))}
        </div>
        <button
          className="btn btn-sm"
          disabled={curIdx < 0 || curIdx >= roverStops.length - 1}
          onClick={() => curIdx >= 0 && curIdx < roverStops.length - 1 && onSelectPanorama(roverStops[curIdx + 1])}
        >
          Next Stop <ArrowRight size={13} />
        </button>
      </div>
    </div>
  );
};

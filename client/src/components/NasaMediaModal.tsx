import React, { useEffect, useState } from "react";
import {
  Camera,
  Compass,
  ExternalLink,
  Film,
  Globe,
  Image as ImageIcon,
  Layers,
  Play,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import {
  fetchLiveRoverRawImages,
  NASA_FOOTAGE_CATALOG,
  NASA_NON_ENDORSEMENT_DISCLAIMER,
  NASA_OFFICIAL_RESOURCES,
  resolveNasaVideoUrl,
  searchNasaMediaLibrary,
  type LiveRoverRawImage,
  type NasaFootageItem,
  type NasaLibraryItem,
} from "../lib/nasaImagery";

interface NasaMediaModalProps {
  initialTab?: "footage" | "raw" | "library" | "resources";
  onFlyTo: (lat: number, lon: number, altitudeKm?: number) => void;
  onActivateBasemap: (basemapId: string) => void;
  onClose: () => void;
}

const PERSEVERANCE_CAMERAS = [
  { id: "ALL", label: "All Cameras" },
  { id: "MCZ_RIGHT", label: "Mastcam-Z Right" },
  { id: "MCZ_LEFT", label: "Mastcam-Z Left" },
  { id: "NAVCAM_LEFT", label: "Navcam Left" },
  { id: "FRONT_HAZCAM_LEFT_A", label: "Front Hazcam" },
  { id: "SHERLOC_WATSON", label: "SHERLOC WATSON" },
  { id: "SKYCAM", label: "MEDA Skycam" },
  { id: "HELI_RTE", label: "Ingenuity Color" },
];

export const NasaMediaModal: React.FC<NasaMediaModalProps> = ({
  initialTab = "footage",
  onFlyTo,
  onActivateBasemap,
  onClose,
}) => {
  const [tab, setTab] = useState<"footage" | "raw" | "library" | "resources">(initialTab);

  // Tab 1: Curated Real NASA Mars Footage & Curiosity Mount Sharp Route Animation
  const [selectedFootage, setSelectedFootage] = useState<NasaFootageItem>(NASA_FOOTAGE_CATALOG[0]);

  // Tab 2: Live NASA Perseverance (1M+ photos) & Curiosity Raw Gallery
  const [rawRover, setRawRover] = useState<"perseverance" | "curiosity">("perseverance");
  const [rawSol, setRawSol] = useState("");
  const [rawCam, setRawCam] = useState("ALL");
  const [rawPage, setRawPage] = useState(0);
  const [rawLoading, setRawLoading] = useState(false);
  const [rawResult, setRawResult] = useState<{
    source: string;
    total?: number;
    images: LiveRoverRawImage[];
    live: boolean;
  } | null>(null);
  const [lightboxImg, setLightboxImg] = useState<LiveRoverRawImage | null>(null);

  // Tab 3: Live NASA Image & Video Library Search (images-api.nasa.gov)
  const [libQuery, setLibQuery] = useState("Mars Perseverance Jezero");
  const [libType, setLibType] = useState<"video" | "image">("video");
  const [libLoading, setLibLoading] = useState(false);
  const [libItems, setLibItems] = useState<NasaLibraryItem[]>([]);
  const [libErr, setLibErr] = useState<string | null>(null);
  const [activeLibVideo, setActiveLibVideo] = useState<{ item: NasaLibraryItem; mp4: string } | null>(null);
  const [resolvingVideoId, setResolvingVideoId] = useState<string | null>(null);

  const loadRaw = async (pageOverride?: number) => {
    setRawLoading(true);
    try {
      const res = await fetchLiveRoverRawImages({
        rover: rawRover,
        sol: rawSol,
        camera: rawCam,
        page: pageOverride ?? rawPage,
        num: 20,
      });
      setRawResult(res);
    } finally {
      setRawLoading(false);
    }
  };

  useEffect(() => {
    if (tab === "raw" && !rawResult) {
      loadRaw(0);
    }
  }, [tab]);

  useEffect(() => {
    if (tab === "raw") {
      setRawPage(0);
      loadRaw(0);
    }
  }, [rawRover, rawCam]);

  const runLibSearch = async (q = libQuery, t = libType) => {
    setLibLoading(true);
    setLibErr(null);
    try {
      const items = await searchNasaMediaLibrary(q, t, 15);
      setLibItems(items);
    } catch (e) {
      setLibErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLibLoading(false);
    }
  };

  useEffect(() => {
    if (tab === "library" && libItems.length === 0) {
      runLibSearch();
    }
  }, [tab]);

  const openLibraryVideo = async (item: NasaLibraryItem) => {
    setResolvingVideoId(item.nasaId);
    try {
      const mp4 = await resolveNasaVideoUrl(item.assetManifestUrl);
      if (mp4) {
        setActiveLibVideo({ item, mp4 });
      }
    } finally {
      setResolvingVideoId(null);
    }
  };

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 86,
        background: "rgba(4, 6, 12, 0.94)",
        display: "flex",
        flexDirection: "column",
        padding: 16,
        gap: 10,
      }}
    >
      {/* Modal Header */}
      <div className="glass" style={{ padding: "10px 14px", borderRadius: 12, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <Film size={17} color="#e46f3b" />
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontWeight: 700, fontSize: 15 }}>NASA Real Mars Footage, Raw Rover Gallery &amp; Geologic Maps</div>
          <div className="small muted">
            Live direct streams from NASA JPL Mars Trek, NASA SVS, Science.NASA.gov, USGS Astrogeology, and Mars 2020 Raw Images
          </div>
        </div>
        <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
          <button className={`btn btn-sm ${tab === "footage" ? "btn-primary" : ""}`} onClick={() => setTab("footage")}>
            <Play size={12} /> NASA Footage &amp; Route Maps
          </button>
          <button className={`btn btn-sm ${tab === "raw" ? "btn-primary" : ""}`} onClick={() => setTab("raw")}>
            <Camera size={12} /> Live Raw Rover Images (1M+)
          </button>
          <button className={`btn btn-sm ${tab === "library" ? "btn-primary" : ""}`} onClick={() => setTab("library")}>
            <Search size={12} /> NASA Media Library
          </button>
          <button className={`btn btn-sm ${tab === "resources" ? "btn-primary" : ""}`} onClick={() => setTab("resources")}>
            <Layers size={12} /> USGS Geology &amp; Worldview
          </button>
          <button className="btn btn-sm" onClick={onClose}>
            <X size={14} />
          </button>
        </div>
      </div>

      {/* TAB 1: REAL NASA VIDEO FOOTAGE & CURIOSITY ROUTE ANIMATION */}
      {tab === "footage" && (
        <div style={{ flex: 1, display: "flex", gap: 12, minHeight: 0 }}>
          {/* Main Cinema Player */}
          <div className="glass" style={{ flex: 1, borderRadius: 12, padding: 14, display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
            <div
              style={{
                flex: 1,
                background: "#04060b",
                borderRadius: 10,
                border: "1px solid var(--border)",
                overflow: "hidden",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                position: "relative",
                minHeight: 280,
              }}
            >
              {selectedFootage.mediaType === "animated-image" ? (
                <img
                  key={selectedFootage.id}
                  src={selectedFootage.imageUrl}
                  alt={selectedFootage.title}
                  style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain" }}
                />
              ) : (
                <video
                  key={selectedFootage.id}
                  controls
                  autoPlay
                  playsInline
                  poster={selectedFootage.posterUrl}
                  style={{ width: "100%", height: "100%", maxHeight: "100%", objectFit: "contain", background: "#000" }}
                >
                  {selectedFootage.webmUrl && <source src={selectedFootage.webmUrl} type="video/webm" />}
                  {selectedFootage.mp4Url && <source src={selectedFootage.mp4Url} type="video/mp4" />}
                  Your browser could not stream this NASA video directly. Open the official NASA source link below.
                </video>
              )}
              <span
                className="pill"
                style={{
                  position: "absolute",
                  top: 10,
                  left: 10,
                  background: "rgba(6,10,20,0.82)",
                  borderColor: "rgba(228,111,59,0.55)",
                  color: "#fed7aa",
                }}
              >
                {selectedFootage.durationNote}
              </span>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 260 }}>
                <div style={{ fontWeight: 700, fontSize: 15 }}>{selectedFootage.title}</div>
                <div className="small muted" style={{ marginTop: 3 }}>
                  {selectedFootage.mission} · {selectedFootage.locationName}
                </div>
                <div className="small" style={{ marginTop: 6, lineHeight: 1.45, color: "#cbd5e1" }}>
                  {selectedFootage.description}
                </div>
                <div className="small muted" style={{ marginTop: 4 }}>
                  Credit: {selectedFootage.credit}
                </div>
              </div>
              <div style={{ display: "flex", gap: 8, flexShrink: 0, flexWrap: "wrap" }}>
                <button
                  className="btn btn-primary btn-sm"
                  onClick={() => {
                    onFlyTo(selectedFootage.lat, selectedFootage.lon, 450);
                    onClose();
                  }}
                >
                  <Compass size={13} /> Fly Globe Here
                </button>
                <a
                  className="btn btn-sm"
                  href={selectedFootage.sourcePage}
                  target="_blank"
                  rel="noreferrer"
                  style={{ textDecoration: "none" }}
                >
                  <ExternalLink size={13} /> Official NASA Page
                </a>
              </div>
            </div>
          </div>

          {/* Playlist Sidebar */}
          <div className="glass" style={{ width: 340, borderRadius: 12, padding: 10, overflowY: "auto", display: "flex", flexDirection: "column", gap: 7 }}>
            <div className="section-title">Official NASA Mars Footage &amp; Route Maps ({NASA_FOOTAGE_CATALOG.length})</div>
            {NASA_FOOTAGE_CATALOG.map((item) => {
              const active = item.id === selectedFootage.id;
              return (
                <div
                  key={item.id}
                  onClick={() => setSelectedFootage(item)}
                  style={{
                    display: "flex",
                    gap: 9,
                    padding: 8,
                    borderRadius: 9,
                    cursor: "pointer",
                    border: active ? "1px solid var(--accent)" : "1px solid var(--border)",
                    background: active ? "rgba(228,111,59,0.16)" : "rgba(255,255,255,0.025)",
                  }}
                >
                  <div style={{ width: 84, height: 54, borderRadius: 6, overflow: "hidden", position: "relative", flexShrink: 0, background: "#0b0f1a" }}>
                    <img
                      src={item.posterUrl}
                      alt={item.title}
                      style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
                    />
                    <div
                      style={{
                        position: "absolute",
                        inset: 0,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        background: "rgba(0,0,0,0.28)",
                      }}
                    >
                      <Play size={16} color="#fff" />
                    </div>
                  </div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontWeight: 600, fontSize: 12, lineHeight: 1.25 }}>{item.title}</div>
                    <div className="small muted" style={{ marginTop: 2 }}>{item.locationName}</div>
                    <div className="small" style={{ color: "#7dd3fc", fontSize: 10, marginTop: 2 }}>{item.durationNote}</div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* TAB 2: LIVE NASA PERSEVERANCE (1M+ PHOTOS) & CURIOSITY RAW GALLERY */}
      {tab === "raw" && (
        <div className="glass" style={{ flex: 1, borderRadius: 12, padding: 14, display: "flex", flexDirection: "column", gap: 10, minHeight: 0 }}>
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            <button
              className={`btn btn-sm ${rawRover === "perseverance" ? "btn-primary" : ""}`}
              onClick={() => setRawRover("perseverance")}
            >
              Perseverance + Ingenuity (Jezero)
            </button>
            <button
              className={`btn btn-sm ${rawRover === "curiosity" ? "btn-primary" : ""}`}
              onClick={() => setRawRover("curiosity")}
            >
              Curiosity MSL (Gale / Mt. Sharp)
            </button>
            <input
              className="input"
              style={{ width: 115 }}
              placeholder="Sol # (optional)"
              value={rawSol}
              onChange={(e) => setRawSol(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && loadRaw(0)}
            />
            {rawRover === "perseverance" && (
              <select className="select" style={{ width: 170 }} value={rawCam} onChange={(e) => setRawCam(e.target.value)}>
                {PERSEVERANCE_CAMERAS.map((c) => (
                  <option key={c.id} value={c.id}>{c.label}</option>
                ))}
              </select>
            )}
            <button className="btn btn-sm btn-primary" onClick={() => loadRaw(0)} disabled={rawLoading}>
              <RefreshCw size={12} /> {rawLoading ? "Fetching NASA…" : "Fetch Live NASA Raw"}
            </button>
            <a
              className="btn btn-sm"
              href={
                rawRover === "perseverance"
                  ? "https://mars.nasa.gov/mars2020/multimedia/raw-images/"
                  : "https://mars.nasa.gov/msl/multimedia/raw-images/"
              }
              target="_blank"
              rel="noreferrer"
              style={{ textDecoration: "none", marginLeft: "auto" }}
            >
              <ExternalLink size={12} /> Official Raw Gallery
            </a>
          </div>

          {rawResult && (
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: 12 }}>
              <span style={{ color: rawResult.live ? "#86efac" : "#fcd34d" }}>
                ● {rawResult.source}
                {rawResult.total ? ` · ${rawResult.total.toLocaleString()} images available` : ""}
              </span>
              <div style={{ display: "flex", gap: 6 }}>
                <button
                  className="btn btn-sm"
                  disabled={rawPage <= 0 || rawLoading}
                  onClick={() => {
                    const p = Math.max(0, rawPage - 1);
                    setRawPage(p);
                    loadRaw(p);
                  }}
                >
                  Prev Page
                </button>
                <span className="mono small muted" style={{ alignSelf: "center" }}>Page {rawPage + 1}</span>
                <button
                  className="btn btn-sm"
                  disabled={rawLoading}
                  onClick={() => {
                    const p = rawPage + 1;
                    setRawPage(p);
                    loadRaw(p);
                  }}
                >
                  Next Page
                </button>
              </div>
            </div>
          )}

          <div
            style={{
              flex: 1,
              overflowY: "auto",
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))",
              gap: 10,
              alignContent: "start",
            }}
          >
            {(rawResult?.images || []).map((img) => (
              <div
                key={img.id}
                onClick={() => setLightboxImg(img)}
                style={{
                  borderRadius: 9,
                  border: "1px solid var(--border)",
                  background: "rgba(255,255,255,0.03)",
                  overflow: "hidden",
                  cursor: "pointer",
                  display: "flex",
                  flexDirection: "column",
                }}
              >
                <img
                  src={img.thumbUrl}
                  alt={img.title}
                  loading="lazy"
                  style={{ width: "100%", height: 148, objectFit: "cover", display: "block", background: "#090d16" }}
                />
                <div style={{ padding: 8 }}>
                  <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, fontWeight: 700 }}>
                    <span style={{ color: "#e46f3b" }}>Sol {img.sol}</span>
                    <span className="mono muted">{img.camera}</span>
                  </div>
                  <div className="small" style={{ marginTop: 3, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {img.title}
                  </div>
                  <div className="small muted" style={{ fontSize: 10, marginTop: 2 }}>{img.earthDate}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Full-Res Photo Lightbox */}
          {lightboxImg && (
            <div
              onClick={() => setLightboxImg(null)}
              style={{
                position: "fixed",
                inset: 0,
                zIndex: 95,
                background: "rgba(2,4,10,0.92)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                padding: 24,
              }}
            >
              <div
                className="glass"
                onClick={(e) => e.stopPropagation()}
                style={{ maxWidth: 960, maxHeight: "90vh", borderRadius: 12, padding: 14, display: "flex", flexDirection: "column", gap: 10 }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
                  <div>
                    <div style={{ fontWeight: 700 }}>{lightboxImg.rover} · Sol {lightboxImg.sol} · {lightboxImg.camera}</div>
                    <div className="small muted">{lightboxImg.earthDate} · {lightboxImg.credit}</div>
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      className="btn btn-sm btn-primary"
                      onClick={() => {
                        onFlyTo(lightboxImg.rover === "Perseverance" ? 18.4447 : -4.5895, lightboxImg.rover === "Perseverance" ? 77.4508 : 137.4417, 250);
                        onClose();
                      }}
                    >
                      <Compass size={12} /> Fly to Rover Site
                    </button>
                    <a className="btn btn-sm" href={lightboxImg.fullUrl} target="_blank" rel="noreferrer" style={{ textDecoration: "none" }}>
                      <ExternalLink size={12} /> Full Res
                    </a>
                    <button className="btn btn-sm" onClick={() => setLightboxImg(null)}><X size={13} /></button>
                  </div>
                </div>
                <img
                  src={lightboxImg.fullUrl}
                  alt={lightboxImg.title}
                  style={{ maxWidth: "100%", maxHeight: "68vh", objectFit: "contain", borderRadius: 8, background: "#000" }}
                />
                {lightboxImg.caption && <div className="small muted">{lightboxImg.caption}</div>}
              </div>
            </div>
          )}
        </div>
      )}

      {/* TAB 3: LIVE NASA IMAGE & VIDEO LIBRARY SEARCH */}
      {tab === "library" && (
        <div className="glass" style={{ flex: 1, borderRadius: 12, padding: 14, display: "flex", flexDirection: "column", gap: 10, minHeight: 0 }}>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
            <input
              className="input"
              style={{ flex: 1, minWidth: 220 }}
              value={libQuery}
              onChange={(e) => setLibQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && runLibSearch()}
              placeholder="Search NASA's official Mars image & video archive…"
            />
            <button
              className={`btn btn-sm ${libType === "video" ? "btn-primary" : ""}`}
              onClick={() => {
                setLibType("video");
                runLibSearch(libQuery, "video");
              }}
            >
              <Film size={12} /> Videos
            </button>
            <button
              className={`btn btn-sm ${libType === "image" ? "btn-primary" : ""}`}
              onClick={() => {
                setLibType("image");
                runLibSearch(libQuery, "image");
              }}
            >
              <ImageIcon size={12} /> Images
            </button>
            <button className="btn btn-sm btn-primary" onClick={() => runLibSearch()} disabled={libLoading}>
              <Search size={12} /> {libLoading ? "Searching…" : "Search NASA API"}
            </button>
          </div>
          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
            {["Perseverance Jezero", "Curiosity Mount Sharp", "Ingenuity Helicopter", "HiRISE Mars", "Valles Marineris", "Mars Dust Storm"].map((preset) => (
              <button
                key={preset}
                className="btn btn-sm"
                onClick={() => {
                  setLibQuery(preset);
                  runLibSearch(preset, libType);
                }}
              >
                {preset}
              </button>
            ))}
          </div>

          {libErr && <div className="small" style={{ color: "#f87171" }}>NASA Library error: {libErr}</div>}

          {activeLibVideo && (
            <div style={{ borderRadius: 10, border: "1px solid var(--accent)", background: "#04060b", padding: 10, display: "flex", flexDirection: "column", gap: 6 }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div style={{ fontWeight: 700, fontSize: 13 }}>{activeLibVideo.item.title} ({activeLibVideo.item.nasaId})</div>
                <button className="btn btn-sm" onClick={() => setActiveLibVideo(null)}><X size={12} /> Close Player</button>
              </div>
              <video controls autoPlay playsInline style={{ width: "100%", maxHeight: 310, background: "#000", borderRadius: 8 }}>
                <source src={activeLibVideo.mp4} type="video/mp4" />
              </video>
            </div>
          )}

          <div
            style={{
              flex: 1,
              overflowY: "auto",
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(230px, 1fr))",
              gap: 10,
              alignContent: "start",
            }}
          >
            {libItems.map((it) => (
              <div
                key={it.nasaId}
                style={{
                  borderRadius: 9,
                  border: "1px solid var(--border)",
                  background: "rgba(255,255,255,0.03)",
                  overflow: "hidden",
                  display: "flex",
                  flexDirection: "column",
                }}
              >
                <img src={it.thumbUrl} alt={it.title} loading="lazy" style={{ width: "100%", height: 136, objectFit: "cover", display: "block" }} />
                <div style={{ padding: 8, flex: 1, display: "flex", flexDirection: "column", gap: 4 }}>
                  <div style={{ fontWeight: 600, fontSize: 12, lineHeight: 1.25 }}>{it.title}</div>
                  <div className="small muted">{it.center} · {it.dateCreated.slice(0, 10)}</div>
                  <div style={{ marginTop: "auto", display: "flex", gap: 6, paddingTop: 6 }}>
                    {it.mediaType === "video" ? (
                      <button
                        className="btn btn-sm btn-primary"
                        style={{ flex: 1 }}
                        disabled={resolvingVideoId === it.nasaId}
                        onClick={() => openLibraryVideo(it)}
                      >
                        <Play size={11} /> {resolvingVideoId === it.nasaId ? "Loading MP4…" : "Play NASA Video"}
                      </button>
                    ) : (
                      <a
                        className="btn btn-sm btn-primary"
                        style={{ flex: 1, textDecoration: "none" }}
                        href={`https://images.nasa.gov/details/${encodeURIComponent(it.nasaId)}`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <ExternalLink size={11} /> Open Full NASA Image
                      </a>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 4: USGS SIM 3292 GEOLOGIC MAP & OFFICIAL NASA RESOURCES HUB */}
      {tab === "resources" && (
        <div style={{ flex: 1, display: "flex", gap: 12, minHeight: 0 }}>
          {/* High-Res USGS SIM 3292 Global Geologic Map Viewer */}
          <div className="glass" style={{ flex: 1.15, borderRadius: 12, padding: 14, display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14 }}>USGS SIM 3292 — Global Geologic Map of Mars (Tanaka et al., 2014)</div>
                <div className="small muted">Standardized 1:20,000,000 planetary geologic stratigraphy from the USGS-NASA Geologic Mapping Program</div>
              </div>
              <button
                className="btn btn-sm btn-primary"
                onClick={() => {
                  onActivateBasemap("usgs-sim3292");
                  onClose();
                }}
              >
                <Globe size={13} /> Drape on 3D Mars Globe
              </button>
            </div>
            <div style={{ flex: 1, background: "#03050a", borderRadius: 10, border: "1px solid var(--border)", overflow: "auto", display: "flex", alignItems: "center", justifyContent: "center", padding: 8 }}>
              <img
                src="/nasa/usgs_sim3292_geology.png"
                alt="USGS SIM 3292 Geologic Map of Mars"
                style={{ maxWidth: "100%", maxHeight: "100%", objectFit: "contain", borderRadius: 6 }}
              />
            </div>
          </div>

          {/* All 5 Official NASA Data & Resource Portals + Mandatory Disclaimer */}
          <div className="glass" style={{ flex: 0.85, borderRadius: 12, padding: 14, overflowY: "auto", display: "flex", flexDirection: "column", gap: 9 }}>
            <div className="section-title">Integrated NASA &amp; USGS Planetary Data Portals</div>
            {NASA_OFFICIAL_RESOURCES.map((res) => (
              <div
                key={res.id}
                style={{
                  padding: 10,
                  borderRadius: 9,
                  border: "1px solid var(--border)",
                  background: "rgba(255,255,255,0.03)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                  <div style={{ fontWeight: 700, fontSize: 13 }}>{res.name}</div>
                  <a
                    className="btn btn-sm"
                    href={res.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ textDecoration: "none", flexShrink: 0 }}
                  >
                    <ExternalLink size={11} /> Open
                  </a>
                </div>
                <div className="small" style={{ color: "#86efac", marginTop: 4 }}>● {res.integration}</div>
                <div className="small muted" style={{ marginTop: 3 }}>{res.description}</div>
              </div>
            ))}

            <div
              style={{
                marginTop: "auto",
                padding: 10,
                borderRadius: 9,
                border: "1px solid rgba(250, 204, 21, 0.3)",
                background: "rgba(250, 204, 21, 0.06)",
                fontSize: 11,
                lineHeight: 1.45,
                color: "#cbd5e1",
              }}
            >
              <strong style={{ color: "#fde047" }}>NASA Non-Endorsement Notice:</strong> {NASA_NON_ENDORSEMENT_DISCLAIMER}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

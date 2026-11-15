import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { Camera, Compass, Footprints, Navigation, X } from "lucide-react";
import { api } from "../lib/api";
import { formatCoords, normLon } from "../lib/marsMath";
import { buildWalkViewOrbitalCanvas, resolvePanoramaPhoto } from "../lib/nasaImagery";
import type { Panorama } from "../types/nam";

interface WalkViewModalProps {
  initialLat: number;
  initialLon: number;
  onOpenPanorama: (p: Panorama) => void;
  onClose: () => void;
}

export const WalkViewModal: React.FC<WalkViewModalProps> = ({
  initialLat,
  initialLon,
  onOpenPanorama,
  onClose,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [lat, setLat] = useState(initialLat);
  const [lon, setLon] = useState(initialLon);
  const [eyeHeightM, setEyeHeightM] = useState(2.0);
  const [fov, setFov] = useState(72);
  const [vertScale, setVertScale] = useState(2.2);
  const [headingDeg, setHeadingDeg] = useState(0);
  const [loading, setLoading] = useState(true);
  const [imagerySource, setImagerySource] = useState("NASA Viking MDIM 2.1 Orbital Imagery");
  const [povs, setPovs] = useState<Array<Record<string, unknown>>>([]);
  const [matchedPhotos, setMatchedPhotos] = useState<Array<Panorama & { heading_diff_deg?: number }>>([]);
  const [cellSizeM, setCellSizeM] = useState<number | null>(null);

  const playerRef = useRef({ x: 0, z: 0, yaw: 0, pitch: -0.05, keys: new Set<string>() });
  const patchRef = useRef<{ n: number; radiusM: number; heights: number[] } | null>(null);
  const stateRef = useRef({ eyeHeightM, fov, vertScale });
  stateRef.current = { eyeHeightM, fov, vertScale };

  useEffect(() => {
    api
      .walkviewPovs()
      .then((r) => setPovs(r.povs || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const t = setTimeout(() => {
      api
        .walkviewPhotos(lat, lon, headingDeg)
        .then((r) => setMatchedPhotos(r.matched_photographs || []))
        .catch(() => {});
    }, 300);
    return () => clearTimeout(t);
  }, [lat, lon, Math.round(headingDeg / 15)]);

  // Load 3D Walk View terrain mesh patch + drape REAL NASA Mars Trek / HiRISE / CTX / Viking orbital texture!
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let alive = true;
    setLoading(true);

    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0xc88d68);
    scene.fog = new THREE.FogExp2(0xc88d68, 0.00055);

    const camera = new THREE.PerspectiveCamera(stateRef.current.fov, 16 / 9, 0.3, 6000);
    scene.add(new THREE.HemisphereLight(0xf3cbb0, 0x452214, 0.85));
    const sun = new THREE.DirectionalLight(0xfff1dc, 1.85);
    sun.position.set(800, 520, 450);
    scene.add(sun);

    let terrainMesh: THREE.Mesh | null = null;
    let orbitalTex: THREE.CanvasTexture | null = null;
    let raf = 0;

    const resize = () => {
      const w = canvas.clientWidth || 960;
      const h = canvas.clientHeight || 520;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };
    resize();

    const sampleGroundY = (x: number, z: number): number => {
      const pr = patchRef.current;
      if (!pr) return 0;
      const { n, radiusM, heights } = pr;
      const u = ((x + radiusM) / (2 * radiusM)) * (n - 1);
      const v = ((z + radiusM) / (2 * radiusM)) * (n - 1);
      const ix = Math.max(0, Math.min(n - 2, Math.floor(u)));
      const iz = Math.max(0, Math.min(n - 2, Math.floor(v)));
      const fx = u - ix;
      const fz = v - iz;
      const h00 = heights[iz * n + ix] || 0;
      const h10 = heights[iz * n + ix + 1] || 0;
      const h01 = heights[(iz + 1) * n + ix] || 0;
      const h11 = heights[(iz + 1) * n + ix + 1] || 0;
      return (h00 * (1 - fx) * (1 - fz) + h10 * fx * (1 - fz) + h01 * (1 - fx) * fz + h11 * fx * fz) * stateRef.current.vertScale;
    };

    const radiusKm = 2.5;
    // Build real NASA orbital imagery canvas (upgrades live to Jezero HiRISE 25cm or CTX 5m!)
    const orbCanvas = buildWalkViewOrbitalCanvas(lat, lon, radiusKm, (_cv, label) => {
      if (!alive) return;
      setImagerySource(label);
      if (orbitalTex) orbitalTex.needsUpdate = true;
    });
    orbitalTex = new THREE.CanvasTexture(orbCanvas);
    orbitalTex.colorSpace = THREE.SRGBColorSpace;
    orbitalTex.anisotropy = 8;

    api
      .walkviewPatch(lat, lon, radiusKm, 56)
      .then((patch) => {
        if (!alive) return;
        setCellSizeM(patch.cell_size_m);
        const n = patch.n;
        const radiusM = patch.radius_km * 1000;
        const positions = new Float32Array(patch.vertices_local_m.length * 3);
        const uvs = new Float32Array(patch.vertices_local_m.length * 2);
        const heights: number[] = new Array(patch.vertices_local_m.length);

        for (let i = 0; i < patch.vertices_local_m.length; i++) {
          const [vx, vy, vz] = patch.vertices_local_m[i];
          positions[i * 3] = vx;
          positions[i * 3 + 1] = vz * stateRef.current.vertScale;
          positions[i * 3 + 2] = vy;
          heights[i] = vz;
          uvs[i * 2] = (vx + radiusM) / (2 * radiusM);
          uvs[i * 2 + 1] = 1 - (vy + radiusM) / (2 * radiusM);
        }

        patchRef.current = { n, radiusM, heights };
        playerRef.current.x = 0;
        playerRef.current.z = 0;

        const geo = new THREE.BufferGeometry();
        geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
        geo.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
        geo.setIndex(patch.indices);
        geo.computeVertexNormals();

        const mat = new THREE.MeshStandardMaterial({
          map: orbitalTex,
          roughness: 0.94,
          metalness: 0.02,
        });
        terrainMesh = new THREE.Mesh(geo, mat);
        scene.add(terrainMesh);
        setLoading(false);
      })
      .catch(() => setLoading(false));

    const onKeyDown = (e: KeyboardEvent) => {
      const k = e.key.toLowerCase();
      if (["w", "a", "s", "d", "arrowup", "arrowdown", "arrowleft", "arrowright", "shift"].includes(k)) {
        playerRef.current.keys.add(k);
      }
    };
    const onKeyUp = (e: KeyboardEvent) => {
      playerRef.current.keys.delete(e.key.toLowerCase());
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);

    let lastT = performance.now();
    let lastHeadingReport = 0;
    const animate = (now: number) => {
      if (!alive) return;
      raf = requestAnimationFrame(animate);
      const dt = Math.min(0.05, (now - lastT) / 1000);
      lastT = now;

      const pl = playerRef.current;
      const speed = (pl.keys.has("shift") ? 140 : 42) * dt;
      const fwdX = Math.sin(pl.yaw);
      const fwdZ = -Math.cos(pl.yaw);
      const rightX = Math.cos(pl.yaw);
      const rightZ = Math.sin(pl.yaw);

      if (pl.keys.has("w") || pl.keys.has("arrowup")) {
        pl.x += fwdX * speed;
        pl.z += fwdZ * speed;
      }
      if (pl.keys.has("s") || pl.keys.has("arrowdown")) {
        pl.x -= fwdX * speed;
        pl.z -= fwdZ * speed;
      }
      if (pl.keys.has("d")) {
        pl.x += rightX * speed;
        pl.z += rightZ * speed;
      }
      if (pl.keys.has("a")) {
        pl.x -= rightX * speed;
        pl.z -= rightZ * speed;
      }
      if (pl.keys.has("arrowleft")) pl.yaw -= 1.4 * dt;
      if (pl.keys.has("arrowright")) pl.yaw += 1.4 * dt;

      if (patchRef.current) {
        const lim = patchRef.current.radiusM * 0.85;
        pl.x = Math.max(-lim, Math.min(lim, pl.x));
        pl.z = Math.max(-lim, Math.min(lim, pl.z));
      }

      if (Math.abs(camera.fov - stateRef.current.fov) > 0.1) {
        camera.fov = stateRef.current.fov;
        camera.updateProjectionMatrix();
      }

      const groundY = sampleGroundY(pl.x, pl.z);
      camera.position.set(pl.x, groundY + stateRef.current.eyeHeightM, pl.z);
      const lookDir = new THREE.Vector3(
        Math.sin(pl.yaw) * Math.cos(pl.pitch),
        Math.sin(pl.pitch),
        -Math.cos(pl.yaw) * Math.cos(pl.pitch)
      );
      camera.lookAt(camera.position.clone().add(lookDir));

      if (now - lastHeadingReport > 180) {
        lastHeadingReport = now;
        setHeadingDeg(Math.round(normLon((pl.yaw * 180) / Math.PI)));
      }

      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(animate);

    return () => {
      alive = false;
      cancelAnimationFrame(raf);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
      if (terrainMesh) {
        terrainMesh.geometry.dispose();
        (terrainMesh.material as THREE.Material).dispose();
      }
      orbitalTex?.dispose();
      renderer.dispose();
    };
  }, [lat, lon, vertScale]);

  const dragRef = useRef({ active: false, lastX: 0, lastY: 0 });

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 82,
        background: "rgba(4,6,12,0.94)",
        display: "flex",
        flexDirection: "column",
        padding: 16,
        gap: 10,
      }}
    >
      {/* Header */}
      <div className="glass" style={{ padding: "10px 14px", borderRadius: 12, display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <Footprints size={16} color="#e46f3b" />
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14 }}>First-Person Walk View — NASA Orbital Terrain Mesh</div>
          <div className="small muted">
            {formatCoords(lat, lon)} · Eye {eyeHeightM.toFixed(1)}m · {cellSizeM ? `${cellSizeM.toFixed(0)}m DEM` : "loading"} ·{" "}
            <strong style={{ color: "#86efac" }}>{imagerySource}</strong>
          </div>
        </div>
        <span className="pill" style={{ background: "rgba(56,189,248,0.14)", borderColor: "rgba(56,189,248,0.4)", color: "#7dd3fc" }}>
          WASD / Arrows + Drag Look
        </span>
        <button className="btn btn-sm" onClick={onClose}>
          <X size={14} /> Exit Walk View
        </button>
      </div>

      {/* Main 3D FPS canvas + POV sidebar */}
      <div style={{ flex: 1, display: "flex", gap: 10, minHeight: 0 }}>
        <div
          style={{
            flex: 1,
            position: "relative",
            borderRadius: 12,
            overflow: "hidden",
            border: "1px solid var(--border)",
            cursor: "crosshair",
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
            playerRef.current.yaw -= dx * 0.004;
            playerRef.current.pitch = Math.max(-0.9, Math.min(0.8, playerRef.current.pitch - dy * 0.004));
          }}
          onPointerUp={() => {
            dragRef.current.active = false;
          }}
        >
          <canvas ref={canvasRef} style={{ width: "100%", height: "100%", display: "block" }} />
          {loading && (
            <div className="glass" style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%,-50%)", padding: "10px 16px", borderRadius: 10 }}>
              Loading NASA Orbital Terrain Mesh…
            </div>
          )}

          {/* Heading HUD */}
          <div className="glass" style={{ position: "absolute", top: 12, left: 12, padding: "5px 10px", borderRadius: 8, display: "flex", gap: 10, alignItems: "center", fontSize: 12 }}>
            <Compass size={14} color="#38bdf8" />
            <span className="mono">HDG {headingDeg}°</span>
            <span className="muted">Shift = Sprint</span>
          </div>

          {/* Sliders */}
          <div className="glass" style={{ position: "absolute", left: 12, bottom: 12, padding: 10, borderRadius: 10, display: "flex", gap: 14, flexWrap: "wrap", fontSize: 11 }}>
            <label>
              Eye Height: <strong className="mono">{eyeHeightM.toFixed(1)}m</strong>
              <input type="range" min={1.2} max={18} step={0.5} value={eyeHeightM} onChange={(e) => setEyeHeightM(Number(e.target.value))} style={{ display: "block", width: 95 }} />
            </label>
            <label>
              FOV: <strong className="mono">{fov}°</strong>
              <input type="range" min={50} max={95} step={1} value={fov} onChange={(e) => setFov(Number(e.target.value))} style={{ display: "block", width: 95 }} />
            </label>
            <label>
              Relief: <strong className="mono">{vertScale.toFixed(1)}×</strong>
              <input type="range" min={1} max={6} step={0.2} value={vertScale} onChange={(e) => setVertScale(Number(e.target.value))} style={{ display: "block", width: 95 }} />
            </label>
          </div>
        </div>

        {/* Right sidebar: Curated POVs + Real NASA Matched Rover Photographs */}
        <div className="glass" style={{ width: 295, borderRadius: 12, padding: 12, display: "flex", flexDirection: "column", gap: 10, overflowY: "auto" }}>
          <div>
            <div className="section-title">Curated Mars POV Presets</div>
            <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
              {povs.map((p, idx) => (
                <button
                  key={String(p.id || idx)}
                  className="btn btn-sm"
                  style={{ justifyContent: "space-between", textAlign: "left" }}
                  onClick={() => {
                    setLat(Number(p.lat));
                    setLon(Number(p.lon));
                  }}
                >
                  <span style={{ display: "flex", alignItems: "center", gap: 5 }}>
                    <Navigation size={11} color="#e46f3b" />
                    {String(p.name)}
                  </span>
                  <span className="mono muted" style={{ fontSize: 10 }}>{String(p.region || "")}</span>
                </button>
              ))}
            </div>
          </div>

          <div style={{ borderTop: "1px solid var(--border)", paddingTop: 10 }}>
            <div className="section-title">
              Real NASA Rover Photos (Heading {headingDeg}°)
            </div>
            {matchedPhotos.length === 0 ? (
              <div className="small muted">Walk or jump to Jezero / Gale / Gusev for matched rover photos.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {matchedPhotos.slice(0, 4).map((m) => {
                  const photo = resolvePanoramaPhoto(m);
                  return (
                    <div
                      key={m.id}
                      onClick={() => onOpenPanorama(m)}
                      style={{
                        borderRadius: 8,
                        border: "1px solid var(--border)",
                        background: "rgba(255,255,255,0.03)",
                        overflow: "hidden",
                        cursor: "pointer",
                      }}
                    >
                      <img
                        src={photo.localUrl}
                        alt={m.title}
                        style={{ width: "100%", height: 74, objectFit: "cover", display: "block" }}
                      />
                      <div style={{ padding: 7 }}>
                        <div style={{ fontWeight: 600, fontSize: 11, display: "flex", alignItems: "center", gap: 4 }}>
                          <Camera size={11} color="#38bdf8" /> {m.rover} {m.sol ? `Sol ${m.sol}` : ""}
                        </div>
                        <div className="small muted">{m.title}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

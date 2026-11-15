import React, { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import {
  formatCoords,
  latLonToVec3,
  MARS_A_KM,
  MARS_POLAR_RATIO,
  normLat,
  normLon,
  polarProject,
  polarUnproject,
  sampleElevation,
  vec3ToLatLon,
} from "../lib/marsMath";
import {
  buildLiveGlobeCanvas,
  drawLiveWmts2DInRect,
  getBasemapDef,
} from "../lib/nasaImagery";
import type {
  CameraState,
  Discovery,
  ElevationGridData,
  LandingSite,
  LatLon,
  Mission,
  Panorama,
  PresenceAgent,
  ProjectionMode,
  ShelterCandidate,
  SolarData,
  SpatialNode,
  StormResponsePlan,
  StormScenario,
  WaterCandidate,
} from "../types/nam";

export interface LayerVisibility {
  landingSites: boolean;
  panoramas: boolean;
  traverses: boolean;
  discoveries: boolean;
  water: boolean;
  shelters: boolean;
  nodes: boolean;
  presence: boolean;
  storms: boolean;
  missions: boolean;
}

export interface PickedObject {
  kind: string;
  id: string;
  name: string;
  lat: number;
  lon: number;
  data?: unknown;
}

interface MarsViewportProps {
  projection: ProjectionMode;
  baseLayer: string;
  overlayLayer: string | null;
  overlayOpacity: number;
  compareEnabled: boolean;
  compareLayer: string;
  exaggeration: number;
  cameraTarget: (CameraState & { nonce: number }) | null;
  solar: SolarData | null;
  elevationGrid: ElevationGridData | null;
  visibility: LayerVisibility;
  landingSites: LandingSite[];
  panoramas: Panorama[];
  discoveries: Discovery[];
  water: WaterCandidate[];
  shelters: ShelterCandidate[];
  nodes: SpatialNode[];
  presence: PresenceAgent[];
  storms: StormScenario[];
  missions: Mission[];
  activeMissionId: string | null;
  stormPlan: StormResponsePlan | null;
  measurePoints: LatLon[];
  measureRoute: LatLon[];
  measureModeLabel: string | null;
  livePerseveranceTraverse?: LatLon[];
  onCameraChange: (cam: CameraState) => void;
  onHoverCoords: (lat: number | null, lon: number | null, elevM: number | null) => void;
  onTerrainClick: (lat: number, lon: number) => void;
  onObjectPick: (obj: PickedObject) => void;
}

interface ProjectedMarker {
  id: string;
  kind: string;
  name: string;
  lat: number;
  lon: number;
  x: number;
  y: number;
  color: string;
  radius: number;
  data?: unknown;
}

export const MarsViewport: React.FC<MarsViewportProps> = ({
  projection,
  baseLayer,
  overlayLayer,
  overlayOpacity,
  compareEnabled,
  compareLayer,
  exaggeration,
  cameraTarget,
  solar,
  elevationGrid,
  visibility,
  landingSites,
  panoramas,
  discoveries,
  water,
  shelters,
  nodes,
  presence,
  storms,
  missions,
  activeMissionId,
  stormPlan,
  measurePoints,
  measureRoute,
  measureModeLabel,
  livePerseveranceTraverse,
  onCameraChange,
  onHoverCoords,
  onTerrainClick,
  onObjectPick,
}) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const webglCanvasRef = useRef<HTMLCanvasElement>(null);
  const hudCanvasRef = useRef<HTMLCanvasElement>(null);

  const [splitRatio, setSplitRatio] = useState(0.5);
  const draggingSplitRef = useRef(false);
  const [hoverLabel, setHoverLabel] = useState<{ x: number; y: number; text: string; sub?: string } | null>(null);
  const [liveBadge, setLiveBadge] = useState<string>("NASA Viking MDIM 2.1 (Loading Live Mars Trek WMTS…)");
  const live2dOverlayRef = useRef<string | null>(null);

  // Shared 3D orbital camera spherical state (lat, lon, distance in Mars radii)
  const orbitRef = useRef({
    lat: 14,
    lon: 115,
    dist: 3.1, // starts in space looking at Mars, zooms smoothly in
    panX: 0,
    panY: 0,
    zoom2d: 1.0,
    // Fly-to animation
    anim: null as null | {
      startT: number;
      durMs: number;
      fromLat: number;
      fromLon: number;
      fromDist: number;
      toLat: number;
      toLon: number;
      toDist: number;
    },
  });

  // Keep latest props in a ref for animation/render loops without tearing down WebGL context
  const propsRef = useRef({
    projection,
    baseLayer,
    overlayLayer,
    overlayOpacity,
    compareEnabled,
    compareLayer,
    exaggeration,
    solar,
    elevationGrid,
    visibility,
    landingSites,
    panoramas,
    discoveries,
    water,
    shelters,
    nodes,
    presence,
    storms,
    missions,
    activeMissionId,
    stormPlan,
    measurePoints,
    measureRoute,
    livePerseveranceTraverse,
    splitRatio,
    onCameraChange,
    onHoverCoords,
    onTerrainClick,
    onObjectPick,
  });

  propsRef.current = {
    projection,
    baseLayer,
    overlayLayer,
    overlayOpacity,
    compareEnabled,
    compareLayer,
    exaggeration,
    solar,
    elevationGrid,
    visibility,
    landingSites,
    panoramas,
    discoveries,
    water,
    shelters,
    nodes,
    presence,
    storms,
    missions,
    activeMissionId,
    stormPlan,
    measurePoints,
    measureRoute,
    livePerseveranceTraverse,
    splitRatio,
    onCameraChange,
    onHoverCoords,
    onTerrainClick,
    onObjectPick,
  };

  // Projected interactive markers list updated every frame for accurate picking
  const projectedMarkersRef = useRef<ProjectedMarker[]>([]);

  // Three.js scene references
  const threeRef = useRef<{
    renderer: THREE.WebGLRenderer;
    scene: THREE.Scene;
    camera: THREE.PerspectiveCamera;
    globeMesh: THREE.Mesh;
    globeOverlayMesh: THREE.Mesh;
    atmoMesh: THREE.Mesh;
    columbusMesh: THREE.Mesh;
    columbusOverlayMesh: THREE.Mesh;
    sunLight: THREE.DirectionalLight;
    baseGeoPositions: Float32Array;
    baseGeoNormals: Float32Array;
    baseGeoUvs: Float32Array;
    columbusBasePositions: Float32Array;
    columbusUvs: Float32Array;
    textures: Map<string, THREE.CanvasTexture>;
    canvasCancelers: Map<string, () => void>;
    canvases: Map<string, HTMLCanvasElement>;
  } | null>(null);

  // Trigger smooth Fly-To animation whenever cameraTarget changes (also centers 2D Flat Map!)
  useEffect(() => {
    if (!cameraTarget) return;
    const o = orbitRef.current;
    const targetDist = Math.max(1.12, Math.min(4.8, 1 + cameraTarget.altitudeKm / MARS_A_KM));
    const dLon = (((cameraTarget.lon - o.lon + 180) % 360) + 360) % 360 - 180;
    o.anim = {
      startT: performance.now(),
      durMs: 1800,
      fromLat: o.lat,
      fromLon: o.lon,
      fromDist: o.dist,
      toLat: normLat(cameraTarget.lat),
      toLon: o.lon + dLon,
      toDist: targetDist,
    };
    // Also pan & zoom 2D Flat Map cleanly onto the target coordinate
    const host = hostRef.current;
    if (host && propsRef.current.projection === "flat") {
      const w = host.clientWidth || 1000;
      const targetZoom = Math.max(1.2, Math.min(140, 3200 / Math.max(25, cameraTarget.altitudeKm)));
      o.zoom2d = targetZoom;
      const mapW = w * 0.92 * o.zoom2d;
      const mapH = mapW / 2;
      const u = normLon(cameraTarget.lon) / 360;
      const v = (90 - normLat(cameraTarget.lat)) / 180;
      o.panX = (0.5 - u) * mapW;
      o.panY = (0.5 - v) * mapH;
    }
  }, [cameraTarget]);

  // Apply vertex elevation displacement whenever elevationGrid or exaggeration changes
  const applyDisplacement = () => {
    const t = threeRef.current;
    const grid = propsRef.current.elevationGrid;
    const ex = propsRef.current.exaggeration;
    if (!t || !grid) return;

    // 1. Displace 3D oblate Mars globe vertices
    const gPos = t.globeMesh.geometry.attributes.position as THREE.BufferAttribute;
    const gArr = gPos.array as Float32Array;
    const baseP = t.baseGeoPositions;
    const uvs = t.baseGeoUvs;
    // Real Mars max elevation ~21 km / 3396 km = 0.0062 radius; scale clearly with exaggeration 1..10
    const dispFactor = (ex * 0.009) / 21000;
    for (let i = 0; i < gPos.count; i++) {
      const u = uvs[i * 2];
      const v = uvs[i * 2 + 1];
      const lon = normLon(u * 360);
      const lat = normLat(v * 180 - 90);
      const elev = sampleElevation(grid, lat, lon) ?? 0;
      const scale = 1 + elev * dispFactor;
      gArr[i * 3] = baseP[i * 3] * scale;
      gArr[i * 3 + 1] = baseP[i * 3 + 1] * scale;
      gArr[i * 3 + 2] = baseP[i * 3 + 2] * scale;
    }
    gPos.needsUpdate = true;
    t.globeMesh.geometry.computeVertexNormals();
    // Copy displaced positions to overlay shell (slightly raised to avoid z-fighting)
    const oPos = t.globeOverlayMesh.geometry.attributes.position as THREE.BufferAttribute;
    const oArr = oPos.array as Float32Array;
    for (let i = 0; i < oArr.length; i++) {
      oArr[i] = gArr[i] * 1.0025;
    }
    oPos.needsUpdate = true;

    // 2. Displace Columbus 2.5D slab
    const cPos = t.columbusMesh.geometry.attributes.position as THREE.BufferAttribute;
    const cArr = cPos.array as Float32Array;
    const cb = t.columbusBasePositions;
    const cuv = t.columbusUvs;
    const cScale = (ex * 0.045) / 21000;
    for (let i = 0; i < cPos.count; i++) {
      const lon = normLon(cuv[i * 2] * 360);
      const lat = normLat(cuv[i * 2 + 1] * 180 - 90);
      const elev = sampleElevation(grid, lat, lon) ?? 0;
      cArr[i * 3] = cb[i * 3];
      cArr[i * 3 + 1] = cb[i * 3 + 1];
      cArr[i * 3 + 2] = elev * cScale;
    }
    cPos.needsUpdate = true;
    t.columbusMesh.geometry.computeVertexNormals();
    const coPos = t.columbusOverlayMesh.geometry.attributes.position as THREE.BufferAttribute;
    const coArr = coPos.array as Float32Array;
    for (let i = 0; i < coArr.length; i += 3) {
      coArr[i] = cArr[i];
      coArr[i + 1] = cArr[i + 1];
      coArr[i + 2] = cArr[i + 2] + 0.004;
    }
    coPos.needsUpdate = true;
  };

  useEffect(() => {
    applyDisplacement();
  }, [elevationGrid, exaggeration]);

  // Helper to get or build a live-streaming NASA Mars Trek / USGS CanvasTexture for 3D Globe + Columbus
  const ensureLayerAssets = (layerId: string) => {
    const t = threeRef.current;
    if (!t) return null;
    const def = getBasemapDef(layerId);
    const key = def.id;
    if (!t.textures.has(key)) {
      const built = buildLiveGlobeCanvas(key, (_cv, stats) => {
        const tex = t.textures.get(key);
        if (tex) tex.needsUpdate = true;
        if (getBasemapDef(propsRef.current.baseLayer).id === key) {
          setLiveBadge(`${def.shortLabel} · ${stats.sourceLabel}`);
        }
      });
      const tex = new THREE.CanvasTexture(built.canvas);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.wrapS = THREE.RepeatWrapping;
      tex.wrapT = THREE.ClampToEdgeWrapping;
      tex.anisotropy = 8;
      tex.needsUpdate = true;
      t.textures.set(key, tex);
      t.canvases.set(key, built.canvas);
      t.canvasCancelers.set(key, built.cancel);
    }
    return {
      texture: t.textures.get(key)!,
      canvas: t.canvases.get(key)!,
      def,
    };
  };

  // Preload active layer textures when selection changes
  useEffect(() => {
    ensureLayerAssets(baseLayer);
    if (overlayLayer) ensureLayerAssets(overlayLayer);
    if (compareEnabled) ensureLayerAssets(compareLayer);
  }, [baseLayer, overlayLayer, compareEnabled, compareLayer]);

  // Main WebGL + 2D HUD initialization and animation loop
  useEffect(() => {
    const host = hostRef.current;
    const glCanvas = webglCanvasRef.current;
    const hudCanvas = hudCanvasRef.current;
    if (!host || !glCanvas || !hudCanvas) return;

    const renderer = new THREE.WebGLRenderer({ canvas: glCanvas, antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setClearColor(0x04060c, 1);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(42, 1, 0.02, 100);

    // Deep space starfield
    const starCount = 2600;
    const starPos = new Float32Array(starCount * 3);
    const starCol = new Float32Array(starCount * 3);
    for (let i = 0; i < starCount; i++) {
      const u = Math.random();
      const v = Math.random();
      const theta = u * 2 * Math.PI;
      const phi = Math.acos(2 * v - 1);
      const r = 34 + Math.random() * 20;
      starPos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      starPos[i * 3 + 1] = r * Math.cos(phi);
      starPos[i * 3 + 2] = r * Math.sin(phi) * Math.sin(theta);
      const tint = 0.72 + Math.random() * 0.28;
      starCol[i * 3] = tint;
      starCol[i * 3 + 1] = tint * (0.94 + Math.random() * 0.06);
      starCol[i * 3 + 2] = Math.min(1, tint * (0.92 + Math.random() * 0.14));
    }
    const starGeo = new THREE.BufferGeometry();
    starGeo.setAttribute("position", new THREE.BufferAttribute(starPos, 3));
    starGeo.setAttribute("color", new THREE.BufferAttribute(starCol, 3));
    const stars = new THREE.Points(
      starGeo,
      new THREE.PointsMaterial({ size: 0.13, vertexColors: true, transparent: true, opacity: 0.85 })
    );
    scene.add(stars);

    // Lighting: warm directional sunlight + subtle ambient bounce so nightside stays inspectable
    const ambient = new THREE.AmbientLight(0x8899bb, 0.34);
    scene.add(ambient);
    const sunLight = new THREE.DirectionalLight(0xfff3e2, 2.25);
    sunLight.position.set(5, 2, 4);
    scene.add(sunLight);

    // Oblate IAU Mars ellipsoid geometry
    const sphereGeo = new THREE.SphereGeometry(1, 144, 72);
    const sPos = sphereGeo.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < sPos.count; i++) {
      sPos.setY(i, sPos.getY(i) * MARS_POLAR_RATIO);
    }
    sphereGeo.computeVertexNormals();
    const baseGeoPositions = new Float32Array(sPos.array as Float32Array);
    const baseGeoNormals = new Float32Array((sphereGeo.attributes.normal as THREE.BufferAttribute).array as Float32Array);
    const baseGeoUvs = new Float32Array((sphereGeo.attributes.uv as THREE.BufferAttribute).array as Float32Array);

    const globeMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.92,
      metalness: 0.02,
    });
    const globeMesh = new THREE.Mesh(sphereGeo, globeMat);
    scene.add(globeMesh);

    const overlayGeo = sphereGeo.clone();
    const globeOverlayMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      roughness: 0.95,
      metalness: 0.0,
      transparent: true,
      opacity: 0,
      depthWrite: false,
    });
    const globeOverlayMesh = new THREE.Mesh(overlayGeo, globeOverlayMat);
    scene.add(globeOverlayMesh);

    // Thin dusty Martian atmospheric limb Fresnel glow
    const atmoGeo = new THREE.SphereGeometry(1.038, 64, 48);
    const aPos = atmoGeo.attributes.position as THREE.BufferAttribute;
    for (let i = 0; i < aPos.count; i++) {
      aPos.setY(i, aPos.getY(i) * MARS_POLAR_RATIO);
    }
    const atmoMat = new THREE.ShaderMaterial({
      transparent: true,
      blending: THREE.AdditiveBlending,
      side: THREE.BackSide,
      depthWrite: false,
      uniforms: {
        uColor: { value: new THREE.Color(0xe9824f) },
      },
      vertexShader: `
        varying vec3 vNormal;
        varying vec3 vViewDir;
        void main() {
          vec4 mvPos = modelViewMatrix * vec4(position, 1.0);
          vNormal = normalize(normalMatrix * normal);
          vViewDir = normalize(-mvPos.xyz);
          gl_Position = projectionMatrix * mvPos;
        }
      `,
      fragmentShader: `
        uniform vec3 uColor;
        varying vec3 vNormal;
        varying vec3 vViewDir;
        void main() {
          float rim = pow(clamp(0.78 - dot(vNormal, vViewDir), 0.0, 1.0), 2.8);
          gl_FragColor = vec4(uColor, rim * 0.62);
        }
      `,
    });
    const atmoMesh = new THREE.Mesh(atmoGeo, atmoMat);
    scene.add(atmoMesh);

    // Columbus 2.5D terrain slab geometry
    const colGeo = new THREE.PlaneGeometry(3.2, 1.6, 144, 72);
    const columbusBasePositions = new Float32Array((colGeo.attributes.position as THREE.BufferAttribute).array as Float32Array);
    const columbusUvs = new Float32Array((colGeo.attributes.uv as THREE.BufferAttribute).array as Float32Array);
    const columbusMesh = new THREE.Mesh(
      colGeo,
      new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: 0.9, metalness: 0.02, side: THREE.DoubleSide })
    );
    columbusMesh.rotation.x = -Math.PI * 0.36;
    columbusMesh.visible = false;
    scene.add(columbusMesh);

    const columbusOverlayMesh = new THREE.Mesh(
      colGeo.clone(),
      new THREE.MeshStandardMaterial({
        color: 0xffffff,
        roughness: 0.95,
        transparent: true,
        opacity: 0,
        depthWrite: false,
        side: THREE.DoubleSide,
      })
    );
    columbusOverlayMesh.rotation.x = -Math.PI * 0.36;
    columbusOverlayMesh.visible = false;
    scene.add(columbusOverlayMesh);

    threeRef.current = {
      renderer,
      scene,
      camera,
      globeMesh,
      globeOverlayMesh,
      atmoMesh,
      columbusMesh,
      columbusOverlayMesh,
      sunLight,
      baseGeoPositions,
      baseGeoNormals,
      baseGeoUvs,
      columbusBasePositions,
      columbusUvs,
      textures: new Map(),
      canvasCancelers: new Map(),
      canvases: new Map(),
    };

    ensureLayerAssets(propsRef.current.baseLayer);
    applyDisplacement();

    // Gentle initial zoom-in from deep space into Mars orbit on mount
    orbitRef.current.anim = {
      startT: performance.now(),
      durMs: 2200,
      fromLat: 16,
      fromLon: 72,
      fromDist: 4.3,
      toLat: 14,
      toLon: 112,
      toDist: 2.55,
    };

    const resize = () => {
      const w = host.clientWidth || 1;
      const h = host.clientHeight || 1;
      renderer.setSize(w, h, false);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      hudCanvas.width = Math.round(w * dpr);
      hudCanvas.height = Math.round(h * dpr);
      hudCanvas.style.width = `${w}px`;
      hudCanvas.style.height = `${h}px`;
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(host);

    // Helper: project (lat, lon) -> screen (x, y) for current projection
    const projectPoint = (
      lat: number,
      lon: number,
      w: number,
      h: number,
      radialBoost = 0.006
    ): { x: number; y: number; visible: boolean } => {
      const p = propsRef.current;
      const o = orbitRef.current;
      if (p.projection === "globe") {
        const elev = sampleElevation(p.elevationGrid, lat, lon) ?? 0;
        const disp = (elev * p.exaggeration * 0.009) / 21000;
        const [vx, vy, vz] = latLonToVec3(lat, lon, disp + radialBoost);
        const worldPt = new THREE.Vector3(vx, vy, vz);
        // Backface visibility test relative to camera
        const toCam = camera.position.clone().sub(worldPt).normalize();
        const surfNorm = worldPt.clone().normalize();
        if (surfNorm.dot(toCam) < 0.02) return { x: -999, y: -999, visible: false };
        const ndc = worldPt.clone().project(camera);
        return {
          x: (ndc.x * 0.5 + 0.5) * w,
          y: (-ndc.y * 0.5 + 0.5) * h,
          visible: ndc.z >= -1 && ndc.z <= 1,
        };
      }
      if (p.projection === "columbus") {
        const u = normLon(lon) / 360;
        const v = (normLat(lat) + 90) / 180;
        const elev = sampleElevation(p.elevationGrid, lat, lon) ?? 0;
        const zLocal = (elev * p.exaggeration * 0.045) / 21000 + 0.012;
        const local = new THREE.Vector3((u - 0.5) * 3.2, (v - 0.5) * 1.6, zLocal);
        local.applyEuler(columbusMesh.rotation);
        const ndc = local.project(camera);
        return {
          x: (ndc.x * 0.5 + 0.5) * w,
          y: (-ndc.y * 0.5 + 0.5) * h,
          visible: ndc.z >= -1 && ndc.z <= 1,
        };
      }
      if (p.projection === "flat") {
        const mapW = w * 0.92 * o.zoom2d;
        const mapH = mapW / 2;
        const cx = w / 2 + o.panX;
        const cy = h / 2 + o.panY;
        const x = cx - mapW / 2 + (normLon(lon) / 360) * mapW;
        const y = cy - mapH / 2 + ((90 - normLat(lat)) / 180) * mapH;
        return { x, y, visible: true };
      }
      // Polar stereographic
      const pole = p.projection === "north-polar" ? "north" : "south";
      const pr = polarProject(lat, lon, pole);
      const R = Math.min(w, h) * 0.41 * o.zoom2d;
      return {
        x: w / 2 + o.panX + pr.x * R,
        y: h / 2 + o.panY - pr.y * R,
        visible: pr.visible,
      };
    };

    let raf = 0;
    let lastReport = 0;

    const renderFrame = (now: number) => {
      raf = requestAnimationFrame(renderFrame);
      const p = propsRef.current;
      const o = orbitRef.current;
      const w = host.clientWidth || 1;
      const h = host.clientHeight || 1;

      // Update Fly-To cubic ease animation
      if (o.anim) {
        const t = Math.min(1, (now - o.anim.startT) / o.anim.durMs);
        const ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
        o.lat = o.anim.fromLat + (o.anim.toLat - o.anim.fromLat) * ease;
        o.lon = normLon(o.anim.fromLon + (o.anim.toLon - o.anim.fromLon) * ease);
        o.dist = o.anim.fromDist + (o.anim.toDist - o.anim.fromDist) * ease;
        if (t >= 1) o.anim = null;
      }

      // Report camera state periodically (~4 Hz) so Location/JEV/Share have live state
      if (now - lastReport > 260) {
        lastReport = now;
        p.onCameraChange({
          lat: Number(o.lat.toFixed(3)),
          lon: Number(normLon(o.lon).toFixed(3)),
          altitudeKm: Math.round(Math.max(50, (o.dist - 1) * MARS_A_KM)),
        });
      }

      // Update Mars24 directional sun light
      const sLat = p.solar?.subsolar_lat ?? 12;
      const sLon = p.solar?.subsolar_lon ?? 140;
      const [sx, sy, sz] = latLonToVec3(sLat, sLon, 8);
      sunLight.position.set(sx, sy, sz);

      const baseAssets = ensureLayerAssets(p.baseLayer);
      const compareAssets = p.compareEnabled ? ensureLayerAssets(p.compareLayer) : null;
      const overlayAssets = p.overlayLayer ? ensureLayerAssets(p.overlayLayer) : null;

      // Render WebGL for 3D Globe & Columbus 2.5D
      const is3D = p.projection === "globe" || p.projection === "columbus";
      glCanvas.style.display = is3D ? "block" : "none";

      if (is3D) {
        const isGlobe = p.projection === "globe";
        globeMesh.visible = isGlobe;
        globeOverlayMesh.visible = isGlobe && !!p.overlayLayer && p.overlayOpacity > 0.01;
        atmoMesh.visible = isGlobe;
        columbusMesh.visible = !isGlobe;
        columbusOverlayMesh.visible = !isGlobe && !!p.overlayLayer && p.overlayOpacity > 0.01;

        if (isGlobe) {
          const [cx, cy, cz] = latLonToVec3(o.lat, o.lon, o.dist - 1);
          camera.position.set(cx, cy, cz);
          camera.lookAt(0, 0, 0);
        } else {
          // Columbus 2.5D orbit over flat slab
          const dist = Math.max(0.9, Math.min(4.8, o.dist * 0.9));
          camera.position.set(o.panX * 0.004, dist * 0.55, dist * 0.88);
          camera.lookAt(o.panX * 0.004, -o.panY * 0.003, 0);
        }

        const activeMesh = isGlobe ? globeMesh : columbusMesh;
        const activeOverlay = isGlobe ? globeOverlayMesh : columbusOverlayMesh;
        const mat = activeMesh.material as THREE.MeshStandardMaterial;
        const oMat = activeOverlay.material as THREE.MeshStandardMaterial;

        if (overlayAssets) {
          oMat.map = overlayAssets.texture;
          oMat.opacity = p.overlayOpacity;
          oMat.needsUpdate = true;
        }

        if (p.compareEnabled && compareAssets && baseAssets) {
          const splitX = Math.round(w * p.splitRatio);
          renderer.setScissorTest(true);
          // Left pane: Layer A
          mat.map = baseAssets.texture;
          mat.needsUpdate = true;
          renderer.setScissor(0, 0, splitX, h);
          renderer.setViewport(0, 0, w, h);
          renderer.render(scene, camera);
          // Right pane: Layer B (compare)
          mat.map = compareAssets.texture;
          mat.needsUpdate = true;
          renderer.setScissor(splitX, 0, w - splitX, h);
          renderer.setViewport(0, 0, w, h);
          renderer.render(scene, camera);
          renderer.setScissorTest(false);
        } else {
          if (baseAssets) {
            mat.map = baseAssets.texture;
            mat.needsUpdate = true;
          }
          renderer.setScissorTest(false);
          renderer.setViewport(0, 0, w, h);
          renderer.render(scene, camera);
        }
      }

      // Draw 2D / Polar map + All Vector Overlays & Clickable Markers on HUD Canvas
      const ctx = hudCanvas.getContext("2d");
      if (!ctx) return;
      const dpr = hudCanvas.width / w;
      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, w, h);

      if (!is3D) {
        // Space background for 2D / Polar projections
        ctx.fillStyle = "#05070d";
        ctx.fillRect(0, 0, w, h);

        if (p.projection === "flat") {
          const mapW = w * 0.92 * o.zoom2d;
          const mapH = mapW / 2;
          const x0 = w / 2 + o.panX - mapW / 2;
          const y0 = h / 2 + o.panY - mapH / 2;
          const mapRect = { x: x0, y: y0, w: mapW, h: mapH, viewW: w, viewH: h };

          let hiResTag: string | null = null;
          if (p.compareEnabled) {
            const sx = w * p.splitRatio;
            ctx.save();
            ctx.beginPath();
            ctx.rect(0, 0, sx, h);
            ctx.clip();
            const rA = drawLiveWmts2DInRect(ctx, p.baseLayer, mapRect, true);
            if (rA.activeOverlay) hiResTag = rA.activeOverlay;
            ctx.restore();
            ctx.save();
            ctx.beginPath();
            ctx.rect(sx, 0, w - sx, h);
            ctx.clip();
            drawLiveWmts2DInRect(ctx, p.compareLayer, mapRect, true);
            ctx.restore();
          } else {
            const rA = drawLiveWmts2DInRect(ctx, p.baseLayer, mapRect, true);
            if (rA.activeOverlay) hiResTag = rA.activeOverlay;
          }
          if (p.overlayLayer && p.overlayOpacity > 0.01) {
            ctx.save();
            ctx.globalAlpha = p.overlayOpacity;
            drawLiveWmts2DInRect(ctx, p.overlayLayer, mapRect, false);
            ctx.restore();
          }
          if (hiResTag !== live2dOverlayRef.current) {
            live2dOverlayRef.current = hiResTag;
            if (hiResTag) {
              setLiveBadge(`LIVE NASA Mars Trek · ${hiResTag}`);
            } else {
              const d = getBasemapDef(p.baseLayer);
              setLiveBadge(`${d.shortLabel} · ${d.resolution}`);
            }
          }

          // Graticule (every 30 deg)
          ctx.strokeStyle = "rgba(255,255,255,0.14)";
          ctx.lineWidth = 1;
          ctx.font = "10px ui-monospace, monospace";
          ctx.fillStyle = "rgba(255,255,255,0.5)";
          for (let lon = 0; lon <= 360; lon += 30) {
            const gx = x0 + (lon / 360) * mapW;
            ctx.beginPath();
            ctx.moveTo(gx, y0);
            ctx.lineTo(gx, y0 + mapH);
            ctx.stroke();
            if (lon < 360) ctx.fillText(`${lon}°E`, gx + 3, y0 + mapH - 5);
          }
          for (let lat = -60; lat <= 60; lat += 30) {
            const gy = y0 + ((90 - lat) / 180) * mapH;
            ctx.beginPath();
            ctx.moveTo(x0, gy);
            ctx.lineTo(x0 + mapW, gy);
            ctx.stroke();
            ctx.fillText(`${lat >= 0 ? "+" : ""}${lat}°`, x0 + 4, gy - 3);
          }
          ctx.strokeStyle = "rgba(255,255,255,0.28)";
          ctx.strokeRect(x0, y0, mapW, mapH);

          // Mars24 solar terminator curve on 2D flat map
          if (p.solar) {
            ctx.save();
            ctx.beginPath();
            ctx.rect(x0, y0, mapW, mapH);
            ctx.clip();
            ctx.fillStyle = "rgba(4, 8, 22, 0.42)";
            const sLatR = (p.solar.subsolar_lat * Math.PI) / 180;
            const sLonD = p.solar.subsolar_lon;
            const step = 4;
            for (let gx = 0; gx < 360; gx += step) {
              for (let gy = -86; gy <= 86; gy += step) {
                const laR = (gy * Math.PI) / 180;
                const dLoR = ((gx - sLonD) * Math.PI) / 180;
                const cosZ =
                  Math.sin(laR) * Math.sin(sLatR) + Math.cos(laR) * Math.cos(sLatR) * Math.cos(dLoR);
                if (cosZ < 0) {
                  const px = x0 + (gx / 360) * mapW;
                  const py = y0 + ((90 - gy) / 180) * mapH;
                  ctx.fillRect(px, py, (step / 360) * mapW + 1, (step / 180) * mapH + 1);
                }
              }
            }
            ctx.restore();
          }
        } else {
          // North or South Polar Stereographic projection rendered directly from elevation grid
          const pole = p.projection === "north-polar" ? "north" : "south";
          const R = Math.min(w, h) * 0.41 * o.zoom2d;
          const cx = w / 2 + o.panX;
          const cy = h / 2 + o.panY;

          // Subtle polar disc backdrop
          const grad = ctx.createRadialGradient(cx, cy, R * 0.08, cx, cy, R * 1.04);
          grad.addColorStop(0, "#d7d3ce");
          grad.addColorStop(0.22, "#b56945");
          grad.addColorStop(0.75, "#87432a");
          grad.addColorStop(1, "#3b1b12");
          ctx.beginPath();
          ctx.arc(cx, cy, R, 0, Math.PI * 2);
          ctx.fillStyle = grad;
          ctx.fill();

          // Plot sampled elevation relief dots for authentic polar topography
          if (p.elevationGrid) {
            ctx.save();
            ctx.beginPath();
            ctx.arc(cx, cy, R, 0, Math.PI * 2);
            ctx.clip();
            const isMola = p.baseLayer === "mola-color";
            const isIce = p.baseLayer === "swim-probability" || p.baseLayer === "depth-to-ice";
            for (let latStep = 2; latStep <= 88; latStep += 4) {
              const lat = pole === "north" ? latStep : -latStep;
              const lonStep = latStep > 72 ? 12 : 6;
              for (let lon = 0; lon < 360; lon += lonStep) {
                const pr = polarProject(lat, lon, pole);
                const px = cx + pr.x * R;
                const py = cy - pr.y * R;
                const elev = sampleElevation(p.elevationGrid, lat, lon) ?? 0;
                const en = Math.max(0, Math.min(1, (elev + 7500) / 28000));
                if (isMola) {
                  ctx.fillStyle = `hsl(${240 - en * 235}, 75%, ${36 + en * 28}%)`;
                } else if (isIce) {
                  const iceStr = Math.max(0, Math.min(1, (Math.abs(lat) - 25) / 40));
                  ctx.fillStyle = `rgba(${40 + iceStr * 120}, ${140 + iceStr * 105}, 240, 0.72)`;
                } else if (Math.abs(lat) > 80) {
                  ctx.fillStyle = "rgba(238,236,232,0.85)";
                } else {
                  const rC = Math.round(115 + en * 110);
                  const gC = Math.round(58 + en * 66);
                  const bC = Math.round(38 + en * 40);
                  ctx.fillStyle = `rgba(${rC},${gC},${bC},0.75)`;
                }
                ctx.fillRect(px - 4, py - 4, 9, 9);
              }
            }
            ctx.restore();
          }

          // Concentric latitude parallels (0, 30, 60) + meridians
          ctx.strokeStyle = "rgba(255,255,255,0.22)";
          ctx.lineWidth = 1;
          ctx.font = "10px ui-monospace, monospace";
          ctx.fillStyle = "rgba(255,255,255,0.6)";
          for (const latVal of [0, 30, 60]) {
            const rNorm = Math.tan(((90 - latVal) * Math.PI) / 360);
            ctx.beginPath();
            ctx.arc(cx, cy, rNorm * R, 0, Math.PI * 2);
            ctx.stroke();
            ctx.fillText(
              `${pole === "north" ? "+" : "-"}${latVal}°`,
              cx + 4,
              cy - rNorm * R + 12
            );
          }
          for (let lon = 0; lon < 360; lon += 45) {
            const rad = (lon * Math.PI) / 180;
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(cx + Math.sin(rad) * R, cy - (pole === "north" ? 1 : -1) * Math.cos(rad) * R);
            ctx.stroke();
            ctx.fillText(
              `${lon}°E`,
              cx + Math.sin(rad) * (R + 14) - 12,
              cy - (pole === "north" ? 1 : -1) * Math.cos(rad) * (R + 14) + 4
            );
          }
          ctx.fillStyle = "#fff";
          ctx.fillText(pole === "north" ? "NORTH POLE (90°N)" : "SOUTH POLE (90°S)", cx - 52, cy - R - 22);
        }
      }

      // --- Draw Shared Vector Overlays & Interactive Markers across ALL 5 Projections ---
      const drawPolyline = (
        pts: LatLon[],
        color: string,
        width: number,
        dashed = false,
        close = false
      ) => {
        if (pts.length < 2) return;
        ctx.save();
        ctx.strokeStyle = color;
        ctx.lineWidth = width;
        if (dashed) ctx.setLineDash([6, 4]);
        ctx.beginPath();
        let started = false;
        const list = close ? [...pts, pts[0]] : pts;
        for (const pt of list) {
          const sp = projectPoint(pt.lat, pt.lon, w, h, 0.008);
          if (!sp.visible) {
            started = false;
            continue;
          }
          if (!started) {
            ctx.moveTo(sp.x, sp.y);
            started = true;
          } else {
            ctx.lineTo(sp.x, sp.y);
          }
        }
        ctx.stroke();
        ctx.restore();
      };

      // Rover traverses (including LIVE NASA JPL official Perseverance M20_traverse.json when loaded!)
      if (p.visibility.traverses) {
        const byRover = new Map<string, Panorama[]>();
        for (const pan of p.panoramas) {
          const arr = byRover.get(pan.rover) || [];
          arr.push(pan);
          byRover.set(pan.rover, arr);
        }
        for (const [, list] of byRover) {
          const sorted = [...list].sort((a, b) => (a.sol || 0) - (b.sol || 0));
          drawPolyline(sorted, "rgba(251, 191, 36, 0.78)", 2, true);
        }
        if (p.livePerseveranceTraverse && p.livePerseveranceTraverse.length >= 2) {
          drawPolyline(p.livePerseveranceTraverse, "rgba(56, 189, 248, 0.95)", 2.5, false);
        }
      }

      // Active simulated storms
      if (p.visibility.storms) {
        for (const st of p.storms) {
          const olat = st.origin?.lat ?? 18.44;
          const olon = st.origin?.lon ?? 77.45;
          const sp = projectPoint(olat, olon, w, h, 0.01);
          if (sp.visible) {
            const radPx = Math.min(120, Math.max(24, ((st.affected_radius_km || 900) / 3400) * 140));
            const pulse = 1 + 0.08 * Math.sin(now * 0.004);
            ctx.save();
            ctx.beginPath();
            ctx.arc(sp.x, sp.y, radPx * pulse, 0, Math.PI * 2);
            ctx.fillStyle = st.kind === "sep" ? "rgba(239,68,68,0.18)" : "rgba(245,158,11,0.18)";
            ctx.fill();
            ctx.strokeStyle = st.kind === "sep" ? "#ef4444" : "#f59e0b";
            ctx.lineWidth = 1.6;
            ctx.setLineDash([5, 4]);
            ctx.stroke();
            ctx.font = "600 10px Inter, sans-serif";
            ctx.fillStyle = st.kind === "sep" ? "#fca5a5" : "#fde68a";
            ctx.fillText(st.label, sp.x - 45, sp.y - radPx - 6);
            ctx.restore();
          }
        }
      }

      // Active Mission routes & stops
      if (p.visibility.missions) {
        for (const m of p.missions) {
          const isSel = m.id === p.activeMissionId;
          const color = isSel ? "#38bdf8" : "rgba(56, 189, 248, 0.45)";
          if (m.routes && m.routes.length > 0) {
            const latest = m.routes[m.routes.length - 1];
            drawPolyline(latest.path, color, isSel ? 3 : 1.6);
          } else if (m.stops.length >= 2) {
            drawPolyline(m.stops, color, isSel ? 2.4 : 1.4, true, m.type === "area");
          }
        }
      }

      // Storm-response evacuation plan polyline
      if (p.stormPlan) {
        for (const leg of p.stormPlan.legs) {
          if (leg.path && leg.path.length >= 2) {
            drawPolyline(leg.path, "#f43f5e", 3.2);
          }
        }
      }

      // Measurement polylines & A* route
      if (p.measureRoute.length >= 2) {
        drawPolyline(p.measureRoute, "#34d399", 3);
      }
      if (p.measurePoints.length >= 2) {
        drawPolyline(p.measurePoints, "#facc15", 2.2, true);
      }

      // Build clickable marker buffer
      const markers: ProjectedMarker[] = [];
      const pushMarker = (
        id: string,
        kind: string,
        name: string,
        lat: number,
        lon: number,
        color: string,
        radius: number,
        data?: unknown
      ) => {
        const sp = projectPoint(lat, lon, w, h, 0.008);
        if (!sp.visible) return;
        markers.push({ id, kind, name, lat, lon, x: sp.x, y: sp.y, color, radius, data });
      };

      if (p.visibility.landingSites) {
        for (const ls of p.landingSites) {
          pushMarker(ls.id, "landing_site", ls.name, ls.lat, ls.lon, "#f97316", 6, ls);
        }
      }
      if (p.visibility.panoramas) {
        for (const pan of p.panoramas) {
          pushMarker(pan.id, "panorama", `${pan.rover}: ${pan.title}`, pan.lat, pan.lon, "#fbbf24", 5, pan);
        }
      }
      if (p.visibility.discoveries) {
        for (const d of p.discoveries) {
          pushMarker(d.id, "discovery", d.title, d.lat, d.lon, "#a78bfa", 4.5, d);
        }
      }
      if (p.visibility.water) {
        for (const wc of p.water) {
          pushMarker(wc.id, "water", `${wc.name} [${wc.certainty}]`, wc.lat, wc.lon, "#38bdf8", 5.5, wc);
        }
      }
      if (p.visibility.shelters) {
        for (const sh of p.shelters) {
          pushMarker(sh.id, "shelter", sh.name, sh.lat, sh.lon, "#34d399", 5, sh);
        }
      }
      if (p.visibility.nodes) {
        for (const nd of p.nodes) {
          pushMarker(nd.id, "node", `[${nd.type}] ${nd.name}`, nd.lat, nd.lon, "#f472b6", 5, nd);
        }
      }
      if (p.visibility.presence) {
        for (const ag of p.presence) {
          const col = ag.kind === "habitat" ? "#22d3ee" : ag.kind === "rover" ? "#fb923c" : "#a3e635";
          pushMarker(ag.id, "presence", `${ag.name} (${ag.role}) [SIM]`, ag.lat, ag.lon, col, 5.5, ag);
        }
      }
      if (p.visibility.missions) {
        for (const m of p.missions) {
          if (m.id !== p.activeMissionId) continue;
          m.stops.forEach((s, idx) => {
            pushMarker(`${m.id}-s${idx}`, "mission_stop", `Stop ${idx + 1}: ${s.activity}`, s.lat, s.lon, "#38bdf8", 6, s);
          });
        }
      }
      if (p.stormPlan) {
        p.stormPlan.stops.forEach((s) => {
          pushMarker(`sp-${s.stop}`, "storm_stop", `Evac Stop ${s.stop}: ${s.activity}`, s.lat, s.lon, "#fb7185", 6.5, s);
        });
      }
      p.measurePoints.forEach((pt, idx) => {
        pushMarker(`mp-${idx}`, "measure_pt", `P${idx + 1} (${formatCoords(pt.lat, pt.lon)})`, pt.lat, pt.lon, "#facc15", 5.5, pt);
      });

      projectedMarkersRef.current = markers;

      // Render markers neatly
      for (const mk of markers) {
        ctx.save();
        if (mk.kind === "presence") {
          const pulse = 1 + 0.55 * ((Math.sin(now * 0.005) + 1) / 2);
          ctx.beginPath();
          ctx.arc(mk.x, mk.y, mk.radius * pulse * 1.4, 0, Math.PI * 2);
          ctx.strokeStyle = mk.color;
          ctx.globalAlpha = 0.45;
          ctx.lineWidth = 1.2;
          ctx.stroke();
          ctx.globalAlpha = 1;
        }
        ctx.beginPath();
        if (mk.kind === "landing_site") {
          ctx.moveTo(mk.x, mk.y - mk.radius - 1);
          ctx.lineTo(mk.x + mk.radius + 1, mk.y);
          ctx.lineTo(mk.x, mk.y + mk.radius + 1);
          ctx.lineTo(mk.x - mk.radius - 1, mk.y);
          ctx.closePath();
        } else {
          ctx.arc(mk.x, mk.y, mk.radius, 0, Math.PI * 2);
        }
        ctx.fillStyle = mk.color;
        ctx.fill();
        ctx.strokeStyle = "rgba(4,7,14,0.85)";
        ctx.lineWidth = 1.5;
        ctx.stroke();

        // Compact labels for landing sites & presence habitats
        if (mk.kind === "landing_site" || (mk.kind === "presence" && mk.name.includes("Base"))) {
          ctx.font = "600 10px Inter, sans-serif";
          ctx.fillStyle = "rgba(241, 245, 249, 0.9)";
          const shortName = mk.name.split("(")[0].trim();
          ctx.fillText(shortName, mk.x + 8, mk.y + 3);
        }
        ctx.restore();
      }

      // Split-screen compare divider indicator
      if (p.compareEnabled) {
        const sx = w * p.splitRatio;
        ctx.save();
        ctx.strokeStyle = "#f97316";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(sx, 0);
        ctx.lineTo(sx, h);
        ctx.stroke();
        ctx.restore();
      }

      ctx.restore();
    };

    raf = requestAnimationFrame(renderFrame);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      if (threeRef.current) {
        for (const cancel of threeRef.current.canvasCancelers.values()) cancel();
        for (const tex of threeRef.current.textures.values()) tex.dispose();
      }
      renderer.dispose();
    };
  }, []);

  // Raycast / Unproject screen pixel (clientX, clientY) -> Mars (lat, lon)
  const screenToLatLon = (clientX: number, clientY: number): LatLon | null => {
    const host = hostRef.current;
    const t = threeRef.current;
    if (!host) return null;
    const rect = host.getBoundingClientRect();
    const x = clientX - rect.left;
    const y = clientY - rect.top;
    const w = rect.width;
    const h = rect.height;
    const p = propsRef.current;
    const o = orbitRef.current;

    if (p.projection === "globe" && t) {
      const ndc = new THREE.Vector2((x / w) * 2 - 1, -(y / h) * 2 + 1);
      const raycaster = new THREE.Raycaster();
      raycaster.setFromCamera(ndc, t.camera);
      const hits = raycaster.intersectObject(t.globeMesh, false);
      if (hits.length === 0) return null;
      const pt = hits[0].point;
      return vec3ToLatLon(pt.x, pt.y, pt.z);
    }
    if (p.projection === "columbus" && t) {
      const ndc = new THREE.Vector2((x / w) * 2 - 1, -(y / h) * 2 + 1);
      const raycaster = new THREE.Raycaster();
      raycaster.setFromCamera(ndc, t.camera);
      const hits = raycaster.intersectObject(t.columbusMesh, false);
      if (hits.length === 0 || !hits[0].uv) return null;
      return {
        lat: normLat(hits[0].uv.y * 180 - 90),
        lon: normLon(hits[0].uv.x * 360),
      };
    }
    if (p.projection === "flat") {
      const mapW = w * 0.92 * o.zoom2d;
      const mapH = mapW / 2;
      const x0 = w / 2 + o.panX - mapW / 2;
      const y0 = h / 2 + o.panY - mapH / 2;
      if (x < x0 || x > x0 + mapW || y < y0 || y > y0 + mapH) return null;
      return {
        lat: normLat(90 - ((y - y0) / mapH) * 180),
        lon: normLon(((x - x0) / mapW) * 360),
      };
    }
    const pole = p.projection === "north-polar" ? "north" : "south";
    const R = Math.min(w, h) * 0.41 * o.zoom2d;
    const nx = (x - (w / 2 + o.panX)) / R;
    const ny = ((h / 2 + o.panY) - y) / R;
    return polarUnproject(nx, ny, pole);
  };

  // Pointer interaction state (drag to orbit/pan vs click to pick)
  const dragRef = useRef({ active: false, moved: false, lastX: 0, lastY: 0 });

  const handlePointerDown = (e: React.PointerEvent) => {
    if (draggingSplitRef.current) return;
    orbitRef.current.anim = null;
    dragRef.current = { active: true, moved: false, lastX: e.clientX, lastY: e.clientY };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };

  const handlePointerMove = (e: React.PointerEvent) => {
    const host = hostRef.current;
    if (!host) return;
    const rect = host.getBoundingClientRect();

    if (draggingSplitRef.current) {
      setSplitRatio(Math.max(0.08, Math.min(0.92, (e.clientX - rect.left) / rect.width)));
      return;
    }

    const d = dragRef.current;
    const o = orbitRef.current;
    const p = propsRef.current;

    if (d.active) {
      const dx = e.clientX - d.lastX;
      const dy = e.clientY - d.lastY;
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) d.moved = true;
      d.lastX = e.clientX;
      d.lastY = e.clientY;
      if (p.projection === "globe") {
        const speed = 0.16 * Math.max(0.25, o.dist - 0.95);
        o.lon = normLon(o.lon - dx * speed);
        o.lat = normLat(o.lat + dy * speed);
      } else {
        o.panX += dx;
        o.panY += dy;
      }
      return;
    }

    // Hover marker tooltip + live terrain cursor coordinates
    const lx = e.clientX - rect.left;
    const ly = e.clientY - rect.top;
    let found: ProjectedMarker | null = null;
    let bestD = 12;
    for (const mk of projectedMarkersRef.current) {
      const dist = Math.hypot(mk.x - lx, mk.y - ly);
      if (dist < bestD) {
        bestD = dist;
        found = mk;
      }
    }
    if (found) {
      setHoverLabel({ x: lx + 14, y: ly - 10, text: found.name, sub: formatCoords(found.lat, found.lon) });
    } else {
      setHoverLabel(null);
    }

    const ll = screenToLatLon(e.clientX, e.clientY);
    if (ll) {
      const elev = sampleElevation(p.elevationGrid, ll.lat, ll.lon);
      p.onHoverCoords(ll.lat, ll.lon, elev !== null ? Math.round(elev) : null);
    } else {
      p.onHoverCoords(null, null, null);
    }
  };

  const handlePointerUp = (e: React.PointerEvent) => {
    draggingSplitRef.current = false;
    const d = dragRef.current;
    d.active = false;
    if (d.moved) return;

    const host = hostRef.current;
    if (!host) return;
    const rect = host.getBoundingClientRect();
    const lx = e.clientX - rect.left;
    const ly = e.clientY - rect.top;
    const p = propsRef.current;

    // If not actively clicking measurement/stop points, prefer marker picking first
    if (!measureModeLabel) {
      let best: ProjectedMarker | null = null;
      let bestDist = 13;
      for (const mk of projectedMarkersRef.current) {
        const dist = Math.hypot(mk.x - lx, mk.y - ly);
        if (dist < bestDist) {
          bestDist = dist;
          best = mk;
        }
      }
      if (best) {
        p.onObjectPick({
          kind: best.kind,
          id: best.id,
          name: best.name,
          lat: best.lat,
          lon: best.lon,
          data: best.data,
        });
        return;
      }
    }

    const ll = screenToLatLon(e.clientX, e.clientY);
    if (ll) {
      p.onTerrainClick(Number(ll.lat.toFixed(4)), Number(ll.lon.toFixed(4)));
    }
  };

  const handleWheel = (e: React.WheelEvent) => {
    const o = orbitRef.current;
    o.anim = null;
    if (propsRef.current.projection === "globe" || propsRef.current.projection === "columbus") {
      const factor = e.deltaY > 0 ? 1.1 : 0.9;
      o.dist = Math.max(1.06, Math.min(5.2, 1 + (o.dist - 1) * factor));
    } else {
      const host = hostRef.current;
      const prevZoom = o.zoom2d;
      const factor = e.deltaY > 0 ? 0.85 : 1.18;
      const nextZoom = Math.max(0.65, Math.min(240, prevZoom * factor));
      // Cursor-anchored 2D zoom so zooming into Jezero HiRISE 25cm stays centered on pointer!
      if (host && nextZoom !== prevZoom) {
        const rect = host.getBoundingClientRect();
        const mx = e.clientX - rect.left - rect.width / 2;
        const my = e.clientY - rect.top - rect.height / 2;
        const ratio = nextZoom / prevZoom;
        o.panX = mx - (mx - o.panX) * ratio;
        o.panY = my - (my - o.panY) * ratio;
      }
      o.zoom2d = nextZoom;
    }
  };

  const activeModeBadge = useMemo(() => {
    if (!measureModeLabel) return null;
    return (
      <div
        className="glass"
        style={{
          position: "absolute",
          top: 66,
          left: "50%",
          transform: "translateX(-50%)",
          padding: "5px 12px",
          borderRadius: 999,
          fontSize: 12,
          borderColor: "rgba(250, 204, 21, 0.5)",
          color: "#fef08a",
          zIndex: 22,
          pointerEvents: "none",
        }}
      >
        Click on Mars to place point — <strong>{measureModeLabel}</strong>
      </div>
    );
  }, [measureModeLabel]);

  return (
    <div
      ref={hostRef}
      style={{
        position: "absolute",
        inset: 0,
        cursor: measureModeLabel ? "crosshair" : "grab",
        userSelect: "none",
        touchAction: "none",
      }}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={handlePointerUp}
      onWheel={handleWheel}
    >
      <canvas
        ref={webglCanvasRef}
        style={{ position: "absolute", inset: 0, width: "100%", height: "100%", display: "block" }}
      />
      <canvas
        ref={hudCanvasRef}
        style={{
          position: "absolute",
          inset: 0,
          width: "100%",
          height: "100%",
          pointerEvents: "none",
        }}
      />

      {activeModeBadge}

      {/* Draggable Split-Screen Layer Comparison Handle */}
      {compareEnabled && (
        <>
          <div
            style={{
              position: "absolute",
              top: 66,
              left: `${splitRatio * 100}%`,
              transform: "translateX(-115%)",
              padding: "3px 8px",
              borderRadius: 6,
              fontSize: 11,
              pointerEvents: "none",
              zIndex: 21,
            }}
            className="glass"
          >
            A: <strong>{getBasemapDef(baseLayer).shortLabel}</strong>
          </div>
          <div
            style={{
              position: "absolute",
              top: 66,
              left: `${splitRatio * 100}%`,
              transform: "translateX(15%)",
              padding: "3px 8px",
              borderRadius: 6,
              fontSize: 11,
              pointerEvents: "none",
              zIndex: 21,
            }}
            className="glass"
          >
            B: <strong>{getBasemapDef(compareLayer).shortLabel}</strong>
          </div>
          <div
            onPointerDown={(e) => {
              e.stopPropagation();
              draggingSplitRef.current = true;
            }}
            style={{
              position: "absolute",
              top: "50%",
              left: `${splitRatio * 100}%`,
              transform: "translate(-50%, -50%)",
              width: 26,
              height: 46,
              borderRadius: 13,
              background: "#e46f3b",
              border: "2px solid #fff",
              cursor: "ew-resize",
              zIndex: 23,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 11,
              fontWeight: 700,
              color: "#fff",
              boxShadow: "0 4px 16px rgba(0,0,0,0.6)",
            }}
            title="Drag to compare layers side by side"
          >
            ⇄
          </div>
        </>
      )}

      {/* Live NASA/USGS Imagery Attribution & Stream Telemetry Badge */}
      <div
        className="glass"
        style={{
          position: "absolute",
          right: 14,
          bottom: 48,
          padding: "4px 10px",
          borderRadius: 999,
          fontSize: 11,
          zIndex: 20,
          pointerEvents: "none",
          display: "flex",
          alignItems: "center",
          gap: 7,
          borderColor: "rgba(56, 189, 248, 0.35)",
        }}
      >
        <span
          style={{
            width: 7,
            height: 7,
            borderRadius: "50%",
            background: getBasemapDef(baseLayer).isLiveNasa ? "#22c55e" : "#f59e0b",
            display: "inline-block",
          }}
        />
        <span style={{ color: "#e2e8f0" }}>{liveBadge}</span>
        <span className="muted" style={{ fontSize: 10 }}>
          · {getBasemapDef(baseLayer).credit}
        </span>
      </div>

      {/* Marker hover tooltip */}
      {hoverLabel && (
        <div
          className="glass"
          style={{
            position: "absolute",
            left: Math.min(hoverLabel.x, (hostRef.current?.clientWidth || 800) - 220),
            top: Math.max(66, hoverLabel.y),
            padding: "5px 9px",
            borderRadius: 7,
            pointerEvents: "none",
            zIndex: 40,
            maxWidth: 260,
          }}
        >
          <div style={{ fontWeight: 600, fontSize: 12 }}>{hoverLabel.text}</div>
          {hoverLabel.sub && <div className="mono muted small">{hoverLabel.sub}</div>}
        </div>
      )}
    </div>
  );
};

import type { LatLon, Panorama } from "../types/nam";

export interface NasaBasemapDef {
  id: string;
  label: string;
  shortLabel: string;
  source: string;
  resolution: string;
  kind: "wmts" | "arcgis-mapserver" | "wms" | "sim-raster";
  tileTemplate?: string;
  tileSize?: number;
  maxZoom?: number;
  bounds?: { minLat: number; maxLat: number; minLon: number; maxLon: number };
  exportUrl?: string;
  localFallback: string;
  simRasterMode?: string;
  credit: string;
  isLiveNasa: boolean;
}

/**
 * Verified NASA JPL Mars Trek WMTS, USGS SIM 3292 MapServer, and USGS Planetary Maps WMS
 * imagery layers + instant bundled NASA public-domain fallbacks in /nasa/.
 */
export const NASA_BASEMAPS: NasaBasemapDef[] = [
  {
    id: "nasa-viking-color",
    label: "NASA Viking MDIM 2.1 Color Mosaic",
    shortLabel: "Viking Color",
    source: "NASA JPL Mars Trek WMTS (Open-CORS)",
    resolution: "232 m/px global",
    kind: "wmts",
    tileTemplate:
      "https://trek.nasa.gov/tiles/Mars/EQ/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
    tileSize: 256,
    maxZoom: 7,
    localFallback: "/nasa/mars_viking_global.jpg",
    credit: "NASA / JPL-Caltech / USGS Astrogeology",
    isLiveNasa: true,
  },
  {
    id: "nasa-mola-color",
    label: "NASA MGS MOLA Color Shaded Relief",
    shortLabel: "MOLA Elevation",
    source: "NASA JPL Mars Trek WMTS (Open-CORS)",
    resolution: "463 m/px global",
    kind: "wmts",
    tileTemplate:
      "https://trek.nasa.gov/tiles/Mars/EQ/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/default/default028mm/{z}/{y}/{x}.jpg",
    tileSize: 256,
    maxZoom: 6,
    localFallback: "/nasa/mars_mola_color.jpg",
    credit: "NASA / GSFC / MOLA Science Team / JPL Mars Trek",
    isLiveNasa: true,
  },
  {
    id: "nasa-ctx-global",
    label: "NASA MRO CTX Global Mosaic (5 m/px)",
    shortLabel: "MRO CTX 5m",
    source: "NASA JPL Mars Trek / Caltech Murray Lab WMTS",
    resolution: "5 m/px global",
    kind: "wmts",
    tileTemplate:
      "https://trek.nasa.gov/tiles/Mars/EQ/CTX_beta01_uncontrolled_5m_Caltech/1.0.0/default/default028mm/{z}/{y}/{x}.png",
    tileSize: 512,
    maxZoom: 11,
    localFallback: "/nasa/mars_viking_global.jpg",
    credit: "NASA / JPL-Caltech / MSSS / Murray Lab (Caltech)",
    isLiveNasa: true,
  },
  {
    id: "usgs-sim3292",
    label: "USGS SIM 3292 Geologic Map of Mars",
    shortLabel: "USGS Geology",
    source: "USGS-NASA Planetary Geologic Mapping Program",
    resolution: "1:20,000,000 global",
    kind: "arcgis-mapserver",
    exportUrl:
      "https://trek.nasa.gov/mars/arcgis/rest/services/SIM3292_Global_Geology/MapServer/export?bbox={minLon},{minLat},{maxLon},{maxLat}&bboxSR=4326&size={w},{h}&format=png32&transparent=true&f=image",
    localFallback: "/nasa/mars_viking_global.jpg",
    simRasterMode: "geology-units",
    credit: "USGS Astrogeology Science Center (Tanaka et al., 2014, SIM 3292)",
    isLiveNasa: true,
  },
  {
    id: "usgs-themis-ir",
    label: "NASA Mars Odyssey THEMIS IR Day (100 m)",
    shortLabel: "THEMIS IR 100m",
    source: "USGS Astrogeology Planetary Maps WMS / ASU",
    resolution: "100 m/px global",
    kind: "wms",
    exportUrl:
      "https://planetarymaps.usgs.gov/cgi-bin/mapserv?map=/maps/mars/mars_simp_cyl.map&SERVICE=WMS&VERSION=1.1.1&REQUEST=GetMap&LAYERS=THEMIS&STYLES=&SRS=EPSG:4326&BBOX={minLon},{minLat},{maxLon},{maxLat}&WIDTH={w}&HEIGHT={h}&FORMAT=image/jpeg",
    localFallback: "/nasa/mars_viking_global.jpg",
    simRasterMode: "thermal-inertia",
    credit: "NASA / JPL-Caltech / Arizona State University / USGS",
    isLiveNasa: true,
  },
  {
    id: "mars-relief",
    label: "DEM Hillshade Relief [SIM]",
    shortLabel: "DEM Relief",
    source: "NAM Local MOLA-Anchored DEM",
    resolution: "0.5° global [SIM]",
    kind: "sim-raster",
    localFallback: "/terrain/raster/mars-relief.png",
    simRasterMode: "mars-relief",
    credit: "NAM DEM Engine (MOLA-anchored [SIM])",
    isLiveNasa: false,
  },
  {
    id: "slope-hazard",
    label: "Slope Hazard Map [SIM]",
    shortLabel: "Slope Hazard",
    source: "NAM Local DEM Gradient",
    resolution: "0.5° global [SIM]",
    kind: "sim-raster",
    localFallback: "/terrain/raster/slope-hazard.png",
    simRasterMode: "slope-hazard",
    credit: "NAM DEM Engine [SIM]",
    isLiveNasa: false,
  },
  {
    id: "swim-probability",
    label: "SWIM Subsurface Water Ice [SIM]",
    shortLabel: "SWIM Ice",
    source: "PSI / NASA SWIM Anchored Model",
    resolution: "0.5° global [SIM]",
    kind: "sim-raster",
    localFallback: "/terrain/raster/swim-probability.png",
    simRasterMode: "swim-probability",
    credit: "SWIM-anchored model [SIM]",
    isLiveNasa: false,
  },
  {
    id: "radiation-dose",
    label: "Surface Radiation Dose [SIM]",
    shortLabel: "Radiation",
    source: "MSL/RAD Anchored Model",
    resolution: "0.5° global [SIM]",
    kind: "sim-raster",
    localFallback: "/terrain/raster/radiation-dose.png",
    simRasterMode: "radiation-dose",
    credit: "MSL/RAD-anchored model [SIM]",
    isLiveNasa: false,
  },
];

/** Regional ultra-high-resolution NASA Mars Trek WMTS overlays (auto-active when zoomed into site) */
export const NASA_REGIONAL_OVERLAYS: NasaBasemapDef[] = [
  {
    id: "jezero-ctx",
    label: "Jezero Crater MRO CTX Block-Adjusted (6 m/px)",
    shortLabel: "Jezero CTX 6m",
    source: "NASA JPL Mars Trek WMTS",
    resolution: "6 m/px regional",
    kind: "wmts",
    tileTemplate:
      "https://trek.nasa.gov/tiles/Mars/EQ/Jezero_CTX_BlockAdj_dd/1.0.0/default/default028mm/{z}/{y}/{x}.png",
    tileSize: 256,
    maxZoom: 12,
    bounds: { minLat: 15.9, maxLat: 19.45, minLon: 75.15, maxLon: 78.88 },
    localFallback: "/nasa/mars_viking_global.jpg",
    credit: "NASA / JPL-Caltech / MSSS",
    isLiveNasa: true,
  },
  {
    id: "jezero-hirise",
    label: "Jezero Crater MRO HiRISE Orthomosaic (25 cm/px)",
    shortLabel: "Jezero HiRISE 25cm",
    source: "NASA JPL Mars Trek / U. of Arizona WMTS",
    resolution: "25 cm/px",
    kind: "wmts",
    tileTemplate:
      "https://trek.nasa.gov/tiles/Mars/EQ/JEZ_hirise_soc_006_orthoMosaic_25cm_Eqc_latTs0_lon0_first_dd/1.0.0/default/default028mm/{z}/{y}/{x}.png",
    tileSize: 256,
    maxZoom: 17,
    bounds: { minLat: 18.306, maxLat: 18.67, minLon: 77.222, maxLon: 77.584 },
    localFallback: "/nasa/mars_viking_global.jpg",
    credit: "NASA / JPL-Caltech / University of Arizona (HiRISE)",
    isLiveNasa: true,
  },
];

const LAYER_ALIASES: Record<string, string> = {
  mdim21: "nasa-viking-color",
  "viking-color": "nasa-viking-color",
  "mola-color": "nasa-mola-color",
  "mola-shaded": "nasa-mola-color",
  "ctx-murray": "nasa-ctx-global",
  "hirise-insets": "nasa-ctx-global",
  "sim3292-geology": "usgs-sim3292",
  "themis-day": "usgs-themis-ir",
  "themis-night": "usgs-themis-ir",
  "depth-to-ice": "swim-probability",
};

export function getBasemapDef(id: string): NasaBasemapDef {
  const mapped = LAYER_ALIASES[id] || id;
  return NASA_BASEMAPS.find((b) => b.id === mapped) || NASA_BASEMAPS[0];
}

export function buildWmtsTileUrl(def: NasaBasemapDef, z: number, y: number, x: number): string {
  if (!def.tileTemplate) return def.localFallback;
  return def.tileTemplate
    .replace("{z}", String(z))
    .replace("{y}", String(y))
    .replace("{x}", String(x));
}

// =========================================================================
// Tile & Global Texture Loader with Caching + Instant Real NASA Fallback
// =========================================================================

const imageCache = new Map<string, HTMLImageElement | "loading" | "error">();
const tileListeners = new Set<() => void>();

export function onNasaTileLoaded(cb: () => void): () => void {
  tileListeners.add(cb);
  return () => tileListeners.delete(cb);
}

function notifyTileLoaded() {
  for (const cb of tileListeners) cb();
}

export function getCachedImage(url: string, crossOrigin = true): HTMLImageElement | null {
  const existing = imageCache.get(url);
  if (existing instanceof HTMLImageElement) return existing;
  if (existing === "loading" || existing === "error") return null;

  imageCache.set(url, "loading");
  const img = new Image();
  if (crossOrigin && !url.startsWith("/")) {
    img.crossOrigin = "anonymous";
  }
  img.onload = () => {
    imageCache.set(url, img);
    notifyTileLoaded();
  };
  img.onerror = () => {
    imageCache.set(url, "error");
  };
  img.src = url;
  return null;
}

/**
 * Draws a NASA/USGS -180..+180 equirectangular image onto a 0..360°E destination canvas
 * (so lon 0..180°E goes on the left half [0..W/2] and lon 180..360°E goes on the right half [W/2..W]).
 */
export function drawMinus180ImageTo0_360(
  ctx: CanvasRenderingContext2D,
  img: HTMLImageElement,
  dstW: number,
  dstH: number,
  alpha = 1
) {
  const halfSrc = img.width / 2;
  const halfDst = dstW / 2;
  ctx.save();
  ctx.globalAlpha = alpha;
  // Right half of -180..+180 (0..+180°E) -> Left half of 0..360°E
  ctx.drawImage(img, halfSrc, 0, halfSrc, img.height, 0, 0, halfDst, dstH);
  // Left half of -180..+180 (-180..0° = 180..360°E) -> Right half of 0..360°E
  ctx.drawImage(img, 0, 0, halfSrc, img.height, halfDst, 0, halfDst, dstH);
  ctx.restore();
}

/**
 * Builds a high-resolution (2048x1024) equirectangular Canvas in 0..360°E longitude order
 * for the 3D Globe / Columbus 2.5D:
 * 1) Draws the bundled real NASA global map immediately so the globe is crisp at 0ms.
 * 2) Streams live NASA JPL Mars Trek WMTS tiles (z=2 => 8x4 = 2048x1024px) or live USGS SIM 3292 / THEMIS
 *    images in the background and fires `onUpdate(canvas, stats)` as tiles arrive.
 */
export function buildLiveGlobeCanvas(
  basemapId: string,
  onUpdate: (canvas: HTMLCanvasElement, stats: { liveLoaded: number; total: number; sourceLabel: string }) => void
): { canvas: HTMLCanvasElement; cancel: () => void } {
  const def = getBasemapDef(basemapId);
  const canvas = document.createElement("canvas");
  canvas.width = 2048;
  canvas.height = 1024;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#4c2c20";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  let cancelled = false;

  const drawFallback = () => {
    const baseImg = new Image();
    baseImg.onload = () => {
      if (cancelled) return;
      if (def.localFallback.startsWith("/nasa/")) {
        drawMinus180ImageTo0_360(ctx, baseImg, canvas.width, canvas.height, 1);
      } else {
        ctx.drawImage(baseImg, 0, 0, canvas.width, canvas.height);
      }
      onUpdate(canvas, { liveLoaded: 0, total: 0, sourceLabel: `${def.shortLabel} (NASA Archive)` });
    };
    baseImg.src = def.localFallback;
  };
  drawFallback();

  if (def.kind === "sim-raster") {
    const simImg = new Image();
    simImg.onload = () => {
      if (cancelled) return;
      ctx.drawImage(simImg, 0, 0, canvas.width, canvas.height);
      onUpdate(canvas, { liveLoaded: 1, total: 1, sourceLabel: `${def.shortLabel} [SIM]` });
    };
    simImg.src = `/terrain/raster/${def.simRasterMode || basemapId}.png`;
    return {
      canvas,
      cancel: () => {
        cancelled = true;
      },
    };
  }

  if (def.kind === "wmts" && def.tileTemplate) {
    // Mars Trek EQ TileMatrix z=2 => 8 cols x 4 rows (for 256px tiles => 2048x1024; for 512px CTX z=1 => 4x2 => 2048x1024)
    const z = def.tileSize === 512 ? 1 : 2;
    const cols = 2 * Math.pow(2, z);
    const rows = Math.pow(2, z);
    const total = cols * rows;
    const cellW = canvas.width / cols;
    const cellH = canvas.height / rows;
    let loaded = 0;

    for (let y = 0; y < rows; y++) {
      for (let x = 0; x < cols; x++) {
        // Shift Mars Trek -180..+180 tile column into 0..360°E globe domain
        const dstCol = (x + cols / 2) % cols;
        const url = buildWmtsTileUrl(def, z, y, x);
        const cached = imageCache.get(url);
        if (cached instanceof HTMLImageElement) {
          ctx.drawImage(cached, dstCol * cellW, y * cellH, cellW, cellH);
          loaded++;
          continue;
        }
        const tile = new Image();
        tile.crossOrigin = "anonymous";
        tile.onload = () => {
          imageCache.set(url, tile);
          if (cancelled) return;
          ctx.drawImage(tile, dstCol * cellW, y * cellH, cellW, cellH);
          loaded++;
          onUpdate(canvas, {
            liveLoaded: loaded,
            total,
            sourceLabel: `LIVE NASA Mars Trek WMTS (${loaded}/${total} tiles)`,
          });
        };
        tile.onerror = () => {
          imageCache.set(url, "error");
        };
        tile.src = url;
      }
    }
    if (loaded > 0) {
      onUpdate(canvas, {
        liveLoaded: loaded,
        total,
        sourceLabel: `LIVE NASA Mars Trek WMTS (${loaded}/${total} tiles)`,
      });
    }
  } else if ((def.kind === "arcgis-mapserver" || def.kind === "wms") && def.exportUrl) {
    const url = def.exportUrl
      .replace("{minLon}", "-180")
      .replace("{minLat}", "-90")
      .replace("{maxLon}", "180")
      .replace("{maxLat}", "90")
      .replace("{w}", "1440")
      .replace("{h}", "720");
    const overlayImg = new Image();
    overlayImg.crossOrigin = "anonymous";
    overlayImg.onload = () => {
      if (cancelled) return;
      drawMinus180ImageTo0_360(
        ctx,
        overlayImg,
        canvas.width,
        canvas.height,
        def.id === "usgs-sim3292" ? 0.82 : 1.0
      );
      onUpdate(canvas, { liveLoaded: 1, total: 1, sourceLabel: `LIVE ${def.source}` });
    };
    overlayImg.onerror = () => {
      if (cancelled || !def.simRasterMode) return;
      const fallbackSim = new Image();
      fallbackSim.onload = () => {
        if (cancelled) return;
        ctx.save();
        ctx.globalAlpha = 0.72;
        ctx.drawImage(fallbackSim, 0, 0, canvas.width, canvas.height);
        ctx.restore();
        onUpdate(canvas, { liveLoaded: 0, total: 1, sourceLabel: `${def.shortLabel} (Local Fallback)` });
      };
      fallbackSim.src = `/terrain/raster/${def.simRasterMode}.png`;
    };
    overlayImg.src = url;
  }

  return {
    canvas,
    cancel: () => {
      cancelled = true;
    },
  };
}

/**
 * Live Multi-Zoom NASA Mars Trek WMTS Tile Pyramid Renderer for 2D Flat Map (0..360°E map rect).
 * Draws instant real NASA base, streams visible live Mars Trek WMTS tiles (up to z=7 Viking, z=11 CTX 5m,
 * z=12 Jezero CTX 6m, z=17 Jezero HiRISE 25cm!), and composites USGS SIM 3292 or THEMIS IR live.
 */
export function drawLiveWmts2DInRect(
  ctx: CanvasRenderingContext2D,
  basemapId: string,
  rect: { x: number; y: number; w: number; h: number; viewW: number; viewH: number },
  autoJezeroHiRes = true
): { zoom: number; activeOverlay: string | null } {
  const def = getBasemapDef(basemapId);

  // 1) Instant global base mapped into 0..360°E rect
  const baseUrl =
    def.kind === "sim-raster" ? `/terrain/raster/${def.simRasterMode || basemapId}.png` : def.localFallback;
  const baseImg = getCachedImage(baseUrl, false);
  if (baseImg) {
    if (baseUrl.startsWith("/nasa/")) {
      const halfSrc = baseImg.width / 2;
      const halfW = rect.w / 2;
      ctx.drawImage(baseImg, halfSrc, 0, halfSrc, baseImg.height, rect.x, rect.y, halfW, rect.h);
      ctx.drawImage(baseImg, 0, 0, halfSrc, baseImg.height, rect.x + halfW, rect.y, halfW, rect.h);
    } else {
      ctx.drawImage(baseImg, rect.x, rect.y, rect.w, rect.h);
    }
  }

  // Visible lon (0..360°E) & lat (-90..90) in current viewport
  const degPerPx = 360 / Math.max(1, rect.w);
  const visMinLon0360 = Math.max(0, ((0 - rect.x) / rect.w) * 360);
  const visMaxLon0360 = Math.min(360, ((rect.viewW - rect.x) / rect.w) * 360);
  const visMaxLat = Math.min(90, 90 - ((0 - rect.y) / rect.h) * 180);
  const visMinLat = Math.max(-90, 90 - ((rect.viewH - rect.y) / rect.h) * 180);

  let chosenZoom = 0;

  const drawWmtsLayer = (layer: NasaBasemapDef, maxTileBudget = 48): number => {
    if (!layer.tileTemplate) return 0;
    const tileSize = layer.tileSize || 256;
    const maxZ = layer.maxZoom ?? 6;
    const idealZ = Math.round(Math.log2(180 / (degPerPx * tileSize)));
    const z = Math.max(0, Math.min(maxZ, idealZ));
    const cols = 2 * Math.pow(2, z);
    const rows = Math.pow(2, z);
    const tileDeg = 180 / rows;

    const minRow = Math.max(0, Math.floor((90 - visMaxLat) / tileDeg));
    const maxRow = Math.min(rows - 1, Math.floor((90 - visMinLat) / tileDeg));
    const minDstCol = Math.max(0, Math.floor(visMinLon0360 / tileDeg));
    const maxDstCol = Math.min(cols - 1, Math.floor(visMaxLon0360 / tileDeg));

    let drawn = 0;
    let count = 0;
    for (let r = minRow; r <= maxRow; r++) {
      const tileMaxLat = 90 - r * tileDeg;
      const tileMinLat = tileMaxLat - tileDeg;
      if (layer.bounds && (tileMaxLat < layer.bounds.minLat || tileMinLat > layer.bounds.maxLat)) continue;

      for (let dstCol = minDstCol; dstCol <= maxDstCol; dstCol++) {
        const lon0360Start = dstCol * tileDeg;
        const lon0360End = lon0360Start + tileDeg;
        // Convert to -180..180 for bounds check & Mars Trek tile column x
        const lon180Start = lon0360Start >= 180 ? lon0360Start - 360 : lon0360Start;
        const lon180End = lon180Start + tileDeg;
        if (layer.bounds && (lon180End < layer.bounds.minLon || lon180Start > layer.bounds.maxLon)) continue;

        if (count++ > maxTileBudget) break;
        const trekCol = (dstCol + cols / 2) % cols;
        const url = buildWmtsTileUrl(layer, z, r, trekCol);
        const img = getCachedImage(url, true);
        if (img) {
          const x0 = rect.x + (lon0360Start / 360) * rect.w;
          const x1 = rect.x + (lon0360End / 360) * rect.w;
          const y0 = rect.y + ((90 - tileMaxLat) / 180) * rect.h;
          const y1 = rect.y + ((90 - tileMinLat) / 180) * rect.h;
          ctx.drawImage(img, x0, y0, x1 - x0 + 0.6, y1 - y0 + 0.6);
          drawn++;
        }
      }
    }
    if (drawn > 0) chosenZoom = Math.max(chosenZoom, z);
    return drawn;
  };

  if (def.kind === "wmts") {
    drawWmtsLayer(def, 64);
  } else if ((def.kind === "arcgis-mapserver" || def.kind === "wms") && def.exportUrl) {
    const url = def.exportUrl
      .replace("{minLon}", "-180")
      .replace("{minLat}", "-90")
      .replace("{maxLon}", "180")
      .replace("{maxLat}", "90")
      .replace("{w}", "1440")
      .replace("{h}", "720");
    const img = getCachedImage(url, true);
    if (img) {
      const halfSrc = img.width / 2;
      const halfW = rect.w / 2;
      ctx.save();
      if (def.id === "usgs-sim3292") ctx.globalAlpha = 0.84;
      ctx.drawImage(img, halfSrc, 0, halfSrc, img.height, rect.x, rect.y, halfW, rect.h);
      ctx.drawImage(img, 0, 0, halfSrc, img.height, rect.x + halfW, rect.y, halfW, rect.h);
      ctx.restore();
    }
  }

  // 2) Auto-upgrade Jezero Crater to MRO CTX (6m) & HiRISE (25cm!) when zoomed in!
  let activeOverlay: string | null = null;
  if (autoJezeroHiRes && def.kind === "wmts" && degPerPx < 0.03) {
    const ctxLayer = NASA_REGIONAL_OVERLAYS[0];
    const hiLayer = NASA_REGIONAL_OVERLAYS[1];
    if (drawWmtsLayer(ctxLayer, 36) > 0) activeOverlay = "Jezero MRO CTX (6 m/px)";
    if (degPerPx < 0.004 && drawWmtsLayer(hiLayer, 36) > 0) {
      activeOverlay = "Jezero MRO HiRISE (25 cm/px)";
    }
  }

  return { zoom: chosenZoom, activeOverlay };
}

/**
 * Loads a cropped real NASA orbital surface texture for the Walk View 3D DEM patch
 * (attempts live Mars Trek CTX/Viking/HiRISE tile first, falls back instantly to real NASA Viking mosaic).
 */
export function buildWalkViewOrbitalCanvas(
  lat: number,
  lon: number,
  radiusKm: number,
  onReady: (canvas: HTMLCanvasElement, sourceLabel: string) => void
): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "#8a563c";
  ctx.fillRect(0, 0, 512, 512);

  const degLat = radiusKm / 59.2;
  const degLon = degLat / Math.max(0.2, Math.cos((lat * Math.PI) / 180));
  const minLat = Math.max(-89.5, lat - degLat);
  const maxLat = Math.min(89.5, lat + degLat);
  const minLon = lon - degLon;
  const maxLon = lon + degLon;

  // Instant real NASA Viking crop
  const viking = new Image();
  viking.onload = () => {
    const sx = (((minLon + 180) % 360) / 360) * viking.width;
    const sy = ((90 - maxLat) / 180) * viking.height;
    const sw = Math.max(4, ((maxLon - minLon) / 360) * viking.width);
    const sh = Math.max(4, ((maxLat - minLat) / 180) * viking.height);
    ctx.drawImage(viking, sx, sy, sw, sh, 0, 0, 512, 512);
    onReady(canvas, "NASA Viking MDIM 2.1 Orbital Imagery");
  };
  viking.src = "/nasa/mars_viking_global.jpg";

  // Live upgrade: Jezero HiRISE 25cm or CTX Global 5m tile at exact location!
  const inJezero = lat >= 18.31 && lat <= 18.66 && lon >= 77.23 && lon <= 77.58;
  const layer = inJezero ? NASA_REGIONAL_OVERLAYS[1] : NASA_BASEMAPS[2]; // Jezero HiRISE or CTX Global 5m
  const z = inJezero ? 13 : 8;
  const rows = Math.pow(2, z);
  const cols = 2 * rows;
  const tileDeg = 180 / rows;
  const tileX = ((Math.floor((lon + 180) / tileDeg) % cols) + cols) % cols;
  const tileY = Math.max(0, Math.min(rows - 1, Math.floor((90 - lat) / tileDeg)));
  const liveUrl = buildWmtsTileUrl(layer, z, tileY, tileX);

  const liveImg = new Image();
  liveImg.crossOrigin = "anonymous";
  liveImg.onload = () => {
    ctx.drawImage(liveImg, 0, 0, 512, 512);
    onReady(canvas, inJezero ? "LIVE NASA MRO HiRISE 25 cm/px (Jezero)" : "LIVE NASA MRO CTX 5 m/px (Mars Trek)");
  };
  liveImg.src = liveUrl;

  return canvas;
}

// =========================================================================
// Verified Real NASA Rover Panorama Photography Resolver
// =========================================================================

export interface PanoramaPhotoAsset {
  localUrl: string;
  nasaHdUrl: string;
  piaId: string;
  caption: string;
  credit: string;
}

const PANORAMA_PHOTO_BY_ID: Record<string, PanoramaPhotoAsset> = {
  "p-sol3": {
    localUrl: "/nasa/pano_perseverance_jezero_360.jpg",
    nasaHdUrl: "https://d2pn8kiwq2w21t.cloudfront.net/images/jpegPIA24264.width-1600.jpg",
    piaId: "PIA24264",
    caption: "Mastcam-Z's First 360-Degree Panorama from Octavia E. Butler Landing, Jezero Crater (142 stitched frames).",
    credit: "NASA/JPL-Caltech/ASU/MSSS",
  },
  "p-sol911": {
    localUrl: "/nasa/pano_perseverance_rim_climb.jpg",
    nasaHdUrl: "https://assets.science.nasa.gov/dynamicimage/assets/science/psd/photojournal/pia/pia26/pia26378/PIA26378.jpg?w=2400&fit=clip",
    piaId: "PIA26378",
    caption: "Perseverance Mid-Climb Mosaic overlooking the Jezero Crater floor, rover tracks, and western rim.",
    credit: "NASA/JPL-Caltech/ASU/MSSS",
  },
  "p-santacruz": {
    localUrl: "/nasa/pano_perseverance_delta.jpg",
    nasaHdUrl: "https://svs.gsfc.nasa.gov/vis/a030000/a031200/a031227/perseverance_belva_crater_print.jpg",
    piaId: "SVS-31227",
    caption: "Jezero Crater Rim & Delta boulder field mosaic captured by Perseverance Mastcam-Z.",
    credit: "NASA/JPL-Caltech/ASU/MSSS",
  },
  "p-18gpx": {
    localUrl: "/nasa/pano_curiosity_mtsharp.jpg",
    nasaHdUrl: "https://assets.science.nasa.gov/dynamicimage/assets/science/psd/mars/resources/detail_files/5134_PIA16769_MtSharpMosaic-sol45-raw-full2.jpg?w=2400&fit=clip",
    piaId: "PIA16769",
    caption: "Curiosity Mastcam panoramic mosaic of layered sedimentary strata on Mount Sharp (Aeolis Mons), Gale Crater.",
    credit: "NASA/JPL-Caltech/MSSS",
  },
  "p-gediz": {
    localUrl: "/nasa/pano_curiosity_gediz.jpg",
    nasaHdUrl: "https://assets.science.nasa.gov/dynamicimage/assets/science/psd/photojournal/pia/pia16/pia16768/PIA16768.jpg?w=2400&fit=clip",
    piaId: "PIA16768",
    caption: "Curiosity Mastcam view across Gale Crater's layered ridges toward Gediz Vallis & Mount Sharp.",
    credit: "NASA/JPL-Caltech/MSSS",
  },
  "p-vera-rubin": {
    localUrl: "/nasa/pano_curiosity_gediz.jpg",
    nasaHdUrl: "https://svs.gsfc.nasa.gov/vis/a010000/a011400/a011442/s3-1280.jpg",
    piaId: "SVS-11442",
    caption: "Curiosity view of Mount Sharp's western buttes and clay-to-sulfate transition.",
    credit: "NASA/JPL-Caltech/MSSS",
  },
  "p-cape-verde": {
    localUrl: "/nasa/pano_opportunity_victoria.jpg",
    nasaHdUrl: "https://assets.science.nasa.gov/dynamicimage/assets/science/psd/photojournal/pia/pia10/pia10213/PIA10213.jpg?w=2400&fit=clip",
    piaId: "PIA10213",
    caption: "Opportunity Pancam mosaic showing rover wheel tracks along the rim of Victoria Crater, Meridiani Planum.",
    credit: "NASA/JPL-Caltech/Cornell",
  },
  "p-persvalley": {
    localUrl: "/nasa/pano_opportunity_victoria.jpg",
    nasaHdUrl: "https://assets.science.nasa.gov/dynamicimage/assets/science/psd/photojournal/pia/pia08/pia08812/PIA08812.jpg?w=1400&fit=clip",
    piaId: "PIA08812",
    caption: "Opportunity Pancam view overlooking the layered rim walls of Meridiani Planum.",
    credit: "NASA/JPL-Caltech/Cornell",
  },
  "p-husband": {
    localUrl: "/nasa/pano_spirit_husband_hill.jpg",
    nasaHdUrl: "https://assets.science.nasa.gov/dynamicimage/assets/science/psd/photojournal/pia/pia04/pia04184/PIA04184.jpg?w=2400&fit=clip",
    piaId: "PIA04184",
    caption: "Spirit Pancam 360-degree summit panorama from Husband Hill in the Columbia Hills, Gusev Crater.",
    credit: "NASA/JPL-Caltech/Cornell",
  },
  "p-viking1": {
    localUrl: "/nasa/pano_viking1_chryse.jpg",
    nasaHdUrl: "https://d2pn8kiwq2w21t.cloudfront.net/images/jpegPIA03163.width-1024.jpg",
    piaId: "PIA03163",
    caption: "Historic Viking Lander 1 panoramic mosaic of boulder-strewn Chryse Planitia (1976).",
    credit: "NASA/JPL",
  },
  "p-pathfinder": {
    localUrl: "/nasa/pano_insight_elysium.jpg",
    nasaHdUrl: "https://svs.gsfc.nasa.gov/vis/a030000/a031200/a031217/PIA25735_print.jpg",
    piaId: "NASA-SURFACE",
    caption: "NASA surface lander/rover workspace view on the Martian plains.",
    credit: "NASA/JPL-Caltech",
  },
  "p-phoenix": {
    localUrl: "/nasa/pano_zhurong_utopia.jpg",
    nasaHdUrl: "/nasa/pano_zhurong_utopia.jpg",
    piaId: "NORTHERN-PLAINS",
    caption: "High-latitude Martian northern plains surface panorama.",
    credit: "NASA/JPL-Caltech / CNSA Planetary Archive",
  },
};

export function resolvePanoramaPhoto(pano: Partial<Panorama>): PanoramaPhotoAsset {
  if (pano.id && PANORAMA_PHOTO_BY_ID[pano.id]) {
    return PANORAMA_PHOTO_BY_ID[pano.id];
  }
  const r = (pano.rover || "").toLowerCase();
  if (r.includes("perseverance")) return PANORAMA_PHOTO_BY_ID["p-sol3"];
  if (r.includes("curiosity")) return PANORAMA_PHOTO_BY_ID["p-18gpx"];
  if (r.includes("opportunity")) return PANORAMA_PHOTO_BY_ID["p-cape-verde"];
  if (r.includes("spirit")) return PANORAMA_PHOTO_BY_ID["p-husband"];
  if (r.includes("viking")) return PANORAMA_PHOTO_BY_ID["p-viking1"];
  if (r.includes("insight")) return {
    localUrl: "/nasa/pano_insight_elysium.jpg",
    nasaHdUrl: "/nasa/pano_insight_elysium.jpg",
    piaId: "INSIGHT-IDC",
    caption: "InSight Lander Instrument Deployment Camera photo of Elysium Planitia.",
    credit: "NASA/JPL-Caltech",
  };
  return PANORAMA_PHOTO_BY_ID["p-sol3"];
}

// =========================================================================
// Official NASA Video Footage & Animated Mission Maps Catalog
// =========================================================================

export interface NasaFootageItem {
  id: string;
  title: string;
  mission: string;
  category: "rover-footage" | "route-map" | "orbital-flyover" | "helicopter";
  mediaType: "video" | "animated-image";
  webmUrl?: string;
  mp4Url?: string;
  imageUrl?: string;
  posterUrl: string;
  lat: number;
  lon: number;
  locationName: string;
  credit: string;
  sourcePage: string;
  description: string;
  durationNote: string;
}

export const NASA_FOOTAGE_CATALOG: NasaFootageItem[] = [
  {
    id: "curiosity-mt-sharp-route",
    title: "Curiosity's Proposed Path Up Mount Sharp (Annotated Route Animation)",
    mission: "Mars Science Laboratory — Curiosity",
    category: "route-map",
    mediaType: "animated-image",
    imageUrl: "https://assets.science.nasa.gov/content/dam/science/psd/mars/resources/detail_files/2/22472_PIA23179-combo-rev_main.gif",
    posterUrl: "/nasa/pano_curiosity_mtsharp.jpg",
    lat: -4.68,
    lon: 137.41,
    locationName: "Mount Sharp (Aeolis Mons), Gale Crater",
    credit: "NASA/JPL-Caltech/ESA/University of Arizona/JHUAPL/MSSS/USGS Astrogeology",
    sourcePage: "https://science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp/",
    description:
      "Official NASA animated orbital route map showing Curiosity's traverse up lower Mount Sharp across the clay-bearing unit, sulfate-bearing strata, and Gediz Vallis channel.",
    durationNote: "Official Animated Map (PIA23179)",
  },
  {
    id: "perseverance-edl-landing",
    title: "Perseverance Rover's Real Descent & Touchdown on Mars (Onboard Cameras)",
    mission: "Mars 2020 — Perseverance",
    category: "rover-footage",
    mediaType: "video",
    webmUrl: "https://svs.gsfc.nasa.gov/vis/a030000/a031200/a031250/Perseverance-landing-1080p.webm",
    mp4Url: "https://svs.gsfc.nasa.gov/vis/a030000/a031200/a031250/Perseverance-landing-1080p.mp4",
    posterUrl: "https://svs.gsfc.nasa.gov/vis/a030000/a031200/a031250/schulte-2023-egu-slide2_0015_print.jpg",
    lat: 18.4447,
    lon: 77.4508,
    locationName: "Octavia E. Butler Landing, Jezero Crater",
    credit: "NASA / JPL-Caltech / GSFC SVS (ID 31250)",
    sourcePage: "https://svs.gsfc.nasa.gov/31250",
    description:
      "Real high-definition footage from Perseverance's Entry, Descent, and Landing cameras (parachute inflation, heatshield drop, sky-crane lowering, and touchdown in Jezero Crater) with JPL Mission Control call-outs.",
    durationNote: "1080p Real Footage (NASA SVS 31250)",
  },
  {
    id: "curiosity-path-flyover",
    title: "Navigating Mars: Aerial Flyover of Curiosity's Path to Mount Sharp",
    mission: "Mars Science Laboratory — Curiosity",
    category: "orbital-flyover",
    mediaType: "video",
    mp4Url: "https://svs.gsfc.nasa.gov/vis/a010000/a011400/a011442/CuriosityPath-540-MASTER_high.mp4",
    webmUrl: "https://svs.gsfc.nasa.gov/vis/a010000/a011400/a011442/CuriosityPath-540-MASTER_high.webmhd.webm",
    posterUrl: "https://svs.gsfc.nasa.gov/vis/a010000/a011400/a011442/pf-1280.jpg",
    lat: -4.59,
    lon: 137.44,
    locationName: "Bradbury Landing → Murray Buttes → Mount Sharp",
    credit: "NASA GSFC SVS / JPL-Caltech / U. of Arizona / ESA / DLR (ID 11442)",
    sourcePage: "https://svs.gsfc.nasa.gov/11442",
    description:
      "Guided 3D orbital flyover built from real HiRISE and Mars Express imagery tracing Curiosity's traverse from Bradbury Landing through Yellowknife Bay and Murray Buttes toward Mount Sharp.",
    durationNote: "Real Orbital Flyover (NASA SVS 11442)",
  },
  {
    id: "ingenuity-flight-54",
    title: "Perseverance Mastcam-Z Watches Ingenuity Helicopter's 54th Flight",
    mission: "Mars 2020 — Perseverance & Ingenuity",
    category: "helicopter",
    mediaType: "video",
    mp4Url: "https://svs.gsfc.nasa.gov/vis/a030000/a031200/a031246/PIA25970-1280.mp4",
    webmUrl: "https://svs.gsfc.nasa.gov/vis/a030000/a031200/a031246/PIA25970-1280.webm",
    posterUrl: "https://svs.gsfc.nasa.gov/vis/a030000/a031200/a031246/PIA25970-1280.00001_print.jpg",
    lat: 18.48,
    lon: 77.42,
    locationName: "Jezero Ancient River Delta",
    credit: "NASA / JPL-Caltech / ASU / MSSS / SVS (PIA25970)",
    sourcePage: "https://svs.gsfc.nasa.gov/31246",
    description:
      "Real Mastcam-Z video captured on Mars from 55 meters away as the Ingenuity Mars Helicopter spins up, climbs to 5 meters altitude, rotates, and touches down on the Martian surface.",
    durationNote: "720p Real Mars Footage (PIA25970)",
  },
  {
    id: "perseverance-belva-crater",
    title: "Perseverance 1080p Panoramic Sweep of Belva Crater, Jezero",
    mission: "Mars 2020 — Perseverance",
    category: "rover-footage",
    mediaType: "video",
    webmUrl: "https://svs.gsfc.nasa.gov/vis/a030000/a031200/a031227/perseverance_belva_crater_1080p30.webm",
    mp4Url: "https://svs.gsfc.nasa.gov/vis/a030000/a031200/a031227/perseverance_belva_crater_1080p30.mp4",
    posterUrl: "https://svs.gsfc.nasa.gov/vis/a030000/a031200/a031227/perseverance_belva_crater_print.jpg",
    lat: 18.495,
    lon: 77.415,
    locationName: "Belva Crater, Jezero Upper Fan",
    credit: "NASA / JPL-Caltech / ASU / MSSS / SVS (ID 31227)",
    sourcePage: "https://svs.gsfc.nasa.gov/31227",
    description:
      "Ultra-sharp panoramic pan across the 900-meter Belva Crater exposed bedrock strata captured by Perseverance's Mastcam-Z cameras.",
    durationNote: "1080p Mastcam-Z Pan (NASA SVS 31227)",
  },
  {
    id: "curiosity-landing-gale",
    title: "Curiosity Rover's Real Descent & Touchdown in Gale Crater (MARDI)",
    mission: "Mars Science Laboratory — Curiosity",
    category: "rover-footage",
    mediaType: "video",
    mp4Url: "https://svs.gsfc.nasa.gov/vis/a010000/a011100/a011148/Curiosity_Landing_540-MASTER_high.mp4",
    webmUrl: "https://svs.gsfc.nasa.gov/vis/a010000/a011100/a011148/Curiosity_Landing_540-MASTER_high.webmhd.webm",
    posterUrl: "https://svs.gsfc.nasa.gov/vis/a010000/a011100/a011148/MSL_landing_720.jpg",
    lat: -4.5895,
    lon: 137.4417,
    locationName: "Bradbury Landing, Gale Crater",
    credit: "NASA / JPL-Caltech / MSSS / GSFC SVS (ID 11148)",
    sourcePage: "https://svs.gsfc.nasa.gov/11148",
    description:
      "Real Mars Descent Imager (MARDI) footage from heatshield separation to dusty touchdown on the floor of Gale Crater with live Mission Control audio.",
    durationNote: "Real MARDI Footage (NASA SVS 11148)",
  },
  {
    id: "valles-marineris-flyover",
    title: "Valles Marineris True-Color Canyon Flyover (Viking + MOLA)",
    mission: "Viking Orbiters & Mars Global Surveyor",
    category: "orbital-flyover",
    mediaType: "video",
    webmUrl: "https://svs.gsfc.nasa.gov/vis/a000000/a001000/a001088/a001088.webmhd.webm",
    mp4Url: "https://svs.gsfc.nasa.gov/vis/a000000/a001000/a001088/a001088.mp4",
    posterUrl: "https://svs.gsfc.nasa.gov/vis/a000000/a001000/a001088/a001088.00095_print.png",
    lat: -13.9,
    lon: -59.2,
    locationName: "Valles Marineris Canyon System",
    credit: "NASA GSFC Scientific Visualization Studio (ID 1088)",
    sourcePage: "https://svs.gsfc.nasa.gov/1088",
    description:
      "Unexaggerated 100 km-altitude canyon flyover constructed from real Viking true-color orbital imagery draped over MGS MOLA laser altimetry.",
    durationNote: "Real MOLA+Viking Flyover (SVS 1088)",
  },
  {
    id: "olympus-mons-flyover",
    title: "Olympus Mons Shield Volcano & Caldera Flyover (Viking + MOLA)",
    mission: "Viking Orbiters & Mars Global Surveyor",
    category: "orbital-flyover",
    mediaType: "video",
    webmUrl: "https://svs.gsfc.nasa.gov/vis/a000000/a001000/a001094/a001094.webmhd.webm",
    mp4Url: "https://svs.gsfc.nasa.gov/vis/a000000/a001000/a001094/a001094.mp4",
    posterUrl: "/nasa/themis_olympus_ir.jpg",
    lat: 18.65,
    lon: -133.8,
    locationName: "Olympus Mons Summit Caldera",
    credit: "NASA GSFC Scientific Visualization Studio (ID 1094)",
    sourcePage: "https://svs.gsfc.nasa.gov/1094",
    description:
      "Orbital flyover soaring from the basal scarp of Olympus Mons up over the 21 km-high summit nested caldera using real Viking + MOLA datasets.",
    durationNote: "Real MOLA+Viking Flyover (SVS 1094)",
  },
];

// =========================================================================
// Official NASA Resources Reference + Non-Endorsement Disclaimer
// =========================================================================

export const NASA_NON_ENDORSEMENT_DISCLAIMER =
  "NASA does not endorse any non-U.S. Government entity and is not responsible for information contained on non-U.S. Government websites. For non-U.S. Government websites, participants must comply with any data use parameters of that specific website.";

export const NASA_OFFICIAL_RESOURCES = [
  {
    id: "mars-trek",
    name: "Jet Propulsion Laboratory's (JPL) Mars Trek",
    url: "https://trek.nasa.gov/mars/",
    integration: "Active Live WMTS Tile Stream (Viking 232m, MOLA 463m, CTX 5m, Jezero HiRISE 25cm)",
    description: "NASA web-based portal for Mars exploration, showcasing orbital mosaics & DTMs at landing sites.",
  },
  {
    id: "usgs-geology",
    name: "USGS-NASA Planetary Geologic Mapping Program",
    url: "https://astrogeology-usgs.hub.arcgis.com/pages/interactive-maps-mars",
    integration: "Active SIM 3292 Global Geologic Map Overlay & Full-Res Geologic Map Viewer",
    description: "Standardized high-quality geologic map of Mars (Tanaka et al., 2014, SIM 3292) & Astrogeology WMS.",
  },
  {
    id: "curiosity-route",
    name: "Curiosity's Proposed Path Up Mount Sharp",
    url: "https://science.nasa.gov/resource/curiositys-proposed-path-up-mount-sharp/",
    integration: "Embedded Official PIA23179 Route Animation + SVS 11442 Mount Sharp Flyover Video",
    description: "Annotated mission route map and orbital flyover explaining Curiosity's ascent of lower Mount Sharp.",
  },
  {
    id: "nasa-worldview",
    name: "NASA Worldview (Earthdata / GIBS)",
    url: "https://worldview.earthdata.nasa.gov/",
    integration: "Earth-Mars Planetary Comparison & Time-Series Satellite Imagery Reference",
    description: "Explore satellite imagery through time via NASA Earthdata's GIBS time-series browser.",
  },
  {
    id: "perseverance-raw",
    name: "Mars Perseverance Raw Images Gallery",
    url: "https://mars.nasa.gov/mars2020/multimedia/raw-images/",
    integration: "Live Browser Raw-Image API Feed (>1,000,000 Perseverance, Ingenuity & Curiosity Photos)",
    description: "Direct access to raw Mastcam-Z, Navcam, Hazcam, SHERLOC & Ingenuity imagery by Sol and camera.",
  },
];

// =========================================================================
// Live Browser Fetchers for NASA Public APIs (Perseverance, Curiosity, NASA Library, M20 Traverse)
// =========================================================================

export interface LiveRoverRawImage {
  id: string;
  rover: "Perseverance" | "Curiosity";
  sol: number;
  camera: string;
  title: string;
  caption: string;
  earthDate: string;
  thumbUrl: string;
  fullUrl: string;
  mastAz?: string;
  mastEl?: string;
  credit: string;
  sourceUrl: string;
}

export async function fetchLiveRoverRawImages(opts: {
  rover: "perseverance" | "curiosity";
  sol?: string;
  camera?: string;
  page?: number;
  num?: number;
}): Promise<{ source: string; total?: number; images: LiveRoverRawImage[]; live: boolean }> {
  const num = opts.num ?? 20;
  const page = opts.page ?? 0;

  if (opts.rover === "perseverance") {
    const params = new URLSearchParams({
      feed: "raw_images",
      category: "mars2020,ingenuity",
      feedtype: "json",
      ver: "1.2",
      num: String(num),
      page: String(page),
      order: "sol desc",
    });
    if (opts.sol && /^\d+$/.test(opts.sol.trim())) {
      params.set("condition_2", `${opts.sol.trim()}:sol:gte`);
      params.set("condition_3", `${opts.sol.trim()}:sol:lte`);
    }
    if (opts.camera && opts.camera !== "ALL") {
      params.set("search", opts.camera);
    }

    try {
      const res = await fetch(`https://mars.nasa.gov/rss/api/?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        const rawList = Array.isArray(data.images) ? data.images : [];
        const images: LiveRoverRawImage[] = rawList
          .filter((it: Record<string, unknown>) => {
            const f = it.image_files as Record<string, string> | undefined;
            return Boolean(f?.medium || f?.large || f?.small);
          })
          .map((it: Record<string, unknown>) => {
            const f = (it.image_files || {}) as Record<string, string>;
            const cam = (it.camera || {}) as Record<string, string>;
            const ext = (it.extended || {}) as Record<string, string>;
            return {
              id: String(it.imageid || Math.random()),
              rover: "Perseverance" as const,
              sol: Number(it.sol || 0),
              camera: cam.instrument || "M2020",
              title: String(it.title || `Perseverance Sol ${it.sol}`),
              caption: String(it.caption || ""),
              earthDate: String(it.date_taken_utc || it.date_received || "").slice(0, 19).replace("T", " "),
              thumbUrl: f.medium || f.small || f.large,
              fullUrl: f.full_res || f.large || f.medium,
              mastAz: ext.mastAz,
              mastEl: ext.mastEl,
              credit: String(it.credit || "NASA/JPL-Caltech"),
              sourceUrl: String(it.link || "https://mars.nasa.gov/mars2020/multimedia/raw-images/"),
            };
          });
        if (images.length > 0) {
          return {
            source: "LIVE NASA Mars 2020 Raw Images Feed (mars.nasa.gov)",
            total: Number(data.total_results || images.length),
            images,
            live: true,
          };
        }
      }
    } catch {
      // fall through to NASA Image Library open-CORS API
    }
  } else {
    const params = new URLSearchParams({
      order: "sol desc",
      per_page: String(num),
      page: String(page),
      condition_1: "msl:mission",
    });
    if (opts.sol && /^\d+$/.test(opts.sol.trim())) {
      params.set("condition_2", `${opts.sol.trim()}:sol:gte`);
      params.set("condition_3", `${opts.sol.trim()}:sol:lte`);
    }
    try {
      const res = await fetch(`https://mars.nasa.gov/api/v1/raw_image_items/?${params.toString()}`);
      if (res.ok) {
        const data = await res.json();
        const items = Array.isArray(data.items) ? data.items : [];
        const images: LiveRoverRawImage[] = items
          .filter((it: Record<string, unknown>) => Boolean(it.url))
          .map((it: Record<string, unknown>) => ({
            id: String(it.imageid || it.id || Math.random()),
            rover: "Curiosity" as const,
            sol: Number(it.sol || 0),
            camera: String(it.instrument || "MSL"),
            title: String(it.title || `Curiosity Sol ${it.sol}`),
            caption: String(it.description || ""),
            earthDate: String(it.date_taken || "").slice(0, 19).replace("T", " "),
            thumbUrl: String(it.url),
            fullUrl: String(it.https_url || it.url),
            credit: String(it.image_credit || "NASA/JPL-Caltech/MSSS"),
            sourceUrl: "https://mars.nasa.gov/msl/multimedia/raw-images/",
          }));
        if (images.length > 0) {
          return {
            source: "LIVE NASA Curiosity MSL Raw Images API (mars.nasa.gov)",
            total: Number(data.total || images.length),
            images,
            live: true,
          };
        }
      }
    } catch {
      // fall through
    }
  }

  // Fallback 1: Open-CORS NASA Image & Video Library API (images-api.nasa.gov)
  try {
    const q = opts.rover === "perseverance" ? "Perseverance Mars Jezero Mastcam" : "Curiosity Mars Gale Mount Sharp";
    const lib = await searchNasaMediaLibrary(q, "image", 16);
    if (lib.length > 0) {
      return {
        source: "LIVE NASA Image & Video Library (images-api.nasa.gov)",
        total: lib.length,
        live: true,
        images: lib.map((item, idx) => ({
          id: item.nasaId,
          rover: opts.rover === "perseverance" ? "Perseverance" : "Curiosity",
          sol: idx,
          camera: item.center || "JPL",
          title: item.title,
          caption: item.description,
          earthDate: item.dateCreated.slice(0, 10),
          thumbUrl: item.thumbUrl,
          fullUrl: item.thumbUrl.replace("~thumb.jpg", "~medium.jpg"),
          credit: `NASA / ${item.center || "JPL-Caltech"}`,
          sourceUrl: `https://images.nasa.gov/details/${encodeURIComponent(item.nasaId)}`,
        })),
      };
    }
  } catch {
    // fall through to curated NASA public-domain archive
  }

  // Fallback 2: Local curated NASA archive
  const localCards: LiveRoverRawImage[] =
    opts.rover === "perseverance"
      ? [
          {
            id: "PIA24264",
            rover: "Perseverance",
            sol: 3,
            camera: "MCZ",
            title: "Mastcam-Z First 360° Panorama (Octavia E. Butler Landing)",
            caption: "142 stitched Mastcam-Z frames across Jezero Crater floor.",
            earthDate: "2021-02-21",
            thumbUrl: "/nasa/pano_perseverance_jezero_360.jpg",
            fullUrl: "/nasa/pano_perseverance_jezero_360.jpg",
            credit: "NASA/JPL-Caltech/ASU/MSSS",
            sourceUrl: "https://mars.nasa.gov/mars2020/multimedia/raw-images/",
          },
          {
            id: "PIA26378",
            rover: "Perseverance",
            sol: 1282,
            camera: "MCZ",
            title: "Mid-Climb View of Jezero Crater Rim & Tracks",
            caption: "Enhanced-color Mastcam-Z mosaic while ascending Jezero's western wall.",
            earthDate: "2024-09-27",
            thumbUrl: "/nasa/pano_perseverance_rim_climb.jpg",
            fullUrl: "/nasa/pano_perseverance_rim_climb.jpg",
            credit: "NASA/JPL-Caltech/ASU/MSSS",
            sourceUrl: "https://mars.nasa.gov/mars2020/multimedia/raw-images/",
          },
          {
            id: "JEZ-DELTA",
            rover: "Perseverance",
            sol: 610,
            camera: "MCZ",
            title: "Jezero Crater Rim & Delta Boulder Mosaic",
            caption: "Ancient delta boulders and sedimentary rim slopes.",
            earthDate: "2022-11-08",
            thumbUrl: "/nasa/pano_perseverance_delta.jpg",
            fullUrl: "/nasa/pano_perseverance_delta.jpg",
            credit: "NASA/JPL-Caltech/ASU/MSSS",
            sourceUrl: "https://mars.nasa.gov/mars2020/multimedia/raw-images/",
          },
        ]
      : [
          {
            id: "PIA16769",
            rover: "Curiosity",
            sol: 45,
            camera: "MASTCAM",
            title: "Mount Sharp Layered Strata Panorama (Raw Color)",
            caption: "Gale Crater's 5.5 km central peak Aeolis Mons imaged by Mastcam.",
            earthDate: "2012-09-20",
            thumbUrl: "/nasa/pano_curiosity_mtsharp.jpg",
            fullUrl: "/nasa/pano_curiosity_mtsharp.jpg",
            credit: "NASA/JPL-Caltech/MSSS",
            sourceUrl: "https://mars.nasa.gov/msl/multimedia/raw-images/",
          },
          {
            id: "PIA16768",
            rover: "Curiosity",
            sol: 771,
            camera: "MASTCAM",
            title: "Mount Sharp Layered Ridge & Gediz Vallis Overlook",
            caption: "Curiosity Mastcam terrain vista climbing lower Mount Sharp.",
            earthDate: "2014-10-08",
            thumbUrl: "/nasa/pano_curiosity_gediz.jpg",
            fullUrl: "/nasa/pano_curiosity_gediz.jpg",
            credit: "NASA/JPL-Caltech/MSSS",
            sourceUrl: "https://mars.nasa.gov/msl/multimedia/raw-images/",
          },
        ];

  return {
    source: "Bundled NASA Public-Domain Archive (Offline Fallback)",
    total: localCards.length,
    images: localCards,
    live: false,
  };
}

export interface NasaLibraryItem {
  nasaId: string;
  title: string;
  description: string;
  mediaType: "image" | "video";
  dateCreated: string;
  center: string;
  thumbUrl: string;
  assetManifestUrl: string;
}

export async function searchNasaMediaLibrary(
  query: string,
  mediaType: "image" | "video" = "video",
  limit = 12
): Promise<NasaLibraryItem[]> {
  const url = `https://images-api.nasa.gov/search?q=${encodeURIComponent(query)}&media_type=${mediaType}&page_size=${limit}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`NASA Library returned ${res.status}`);
  const data = await res.json();
  const items = data?.collection?.items || [];
  return items
    .map((it: Record<string, unknown>) => {
      const meta = ((it.data as Array<Record<string, unknown>>)?.[0] || {}) as Record<string, unknown>;
      const links = (it.links as Array<Record<string, string>>) || [];
      const thumb = links.find((l) => l.rel === "preview")?.href || links[0]?.href || "";
      return {
        nasaId: String(meta.nasa_id || ""),
        title: String(meta.title || "NASA Mars Media"),
        description: String(meta.description || ""),
        mediaType: (meta.media_type === "video" ? "video" : "image") as "image" | "video",
        dateCreated: String(meta.date_created || ""),
        center: String(meta.center || "JPL"),
        thumbUrl: thumb,
        assetManifestUrl: String(it.href || ""),
      };
    })
    .filter((i: NasaLibraryItem) => i.nasaId && i.thumbUrl);
}

export async function resolveNasaVideoUrl(assetManifestUrl: string): Promise<string | null> {
  if (!assetManifestUrl) return null;
  const res = await fetch(assetManifestUrl);
  if (!res.ok) return null;
  const urls: string[] = await res.json();
  const mp4 =
    urls.find((u) => u.endsWith("~medium.mp4")) ||
    urls.find((u) => u.endsWith("~small.mp4")) ||
    urls.find((u) => u.endsWith("~mobile.mp4")) ||
    urls.find((u) => u.endsWith(".mp4"));
  return mp4 ? mp4.replace(/^http:\/\//, "https://") : null;
}

/**
 * Fetches NASA JPL's live official Perseverance rover traverse GeoJSON from mars.nasa.gov
 * and downsamples cleanly for smooth real-time 3D Globe & 2D Map rendering.
 */
export async function fetchLivePerseveranceTraverse(): Promise<{ points: LatLon[]; totalDistanceKm: number | null } | null> {
  try {
    const res = await fetch("https://mars.nasa.gov/mmgis-maps/M20/Layers/json/M20_traverse.json");
    if (!res.ok) return null;
    const gj = await res.json();
    const rawCoords: [number, number][] = [];
    let totalDistM = 0;
    const features = Array.isArray(gj.features) ? gj.features : [];
    for (const f of features) {
      const geom = f?.geometry;
      const props = f?.properties || {};
      if (typeof props.dist_total_m === "number") totalDistM = Math.max(totalDistM, props.dist_total_m);
      if (geom?.type === "LineString" && Array.isArray(geom.coordinates)) {
        for (const c of geom.coordinates) {
          if (Array.isArray(c) && c.length >= 2) rawCoords.push([Number(c[0]), Number(c[1])]);
        }
      } else if (geom?.type === "MultiLineString" && Array.isArray(geom.coordinates)) {
        for (const seg of geom.coordinates) {
          for (const c of seg) {
            if (Array.isArray(c) && c.length >= 2) rawCoords.push([Number(c[0]), Number(c[1])]);
          }
        }
      }
    }
    if (rawCoords.length < 2) return null;
    // Downsample to <= 320 vertices while keeping start & end exact
    const step = Math.max(1, Math.floor(rawCoords.length / 320));
    const points: LatLon[] = [];
    for (let i = 0; i < rawCoords.length; i += step) {
      const [lon, lat] = rawCoords[i];
      points.push({ lat, lon: lon > 180 ? lon - 360 : lon });
    }
    const last = rawCoords[rawCoords.length - 1];
    points.push({ lat: last[1], lon: last[0] > 180 ? last[0] - 360 : last[0] });
    return { points, totalDistanceKm: totalDistM > 0 ? totalDistM / 1000 : null };
  } catch {
    return null;
  }
}

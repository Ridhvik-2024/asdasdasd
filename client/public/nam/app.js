/* NAM — Navigation Assistance for Mars · planetary field atlas.
   Map imagery is curated from the NASA/JPL Mars Trek resource map
   (https://trek.nasa.gov/mars/) and served by its Mars EQ WMTS services.
   The default view is the Viking MDIM 2.1 global colour mosaic; MOLA and
   other products are optional. Route distance is a spherical Mars
   surface-distance estimate only. */

(() => {
  "use strict";

  const MARS_A = 3396190;
  const MARS_B = 3376200;
  const MARS_RADIUS_KM = 3389.5;
  const TILE_ROOT = "https://trek.nasa.gov/tiles/Mars/EQ";
  const CAPABILITIES_ROOT = TILE_ROOT;
  const MIN_ZOOM_METERS = 250;
  const $ = (id) => document.getElementById(id);

  const BASE_LAYERS = [
    {
      id: "viking",
      name: "Viking colour mosaic",
      shortName: "Viking colour",
      description: "Global visible-image mosaic · 231 m/px at the equator",
      tileId: "Mars_Viking_MDIM21_ClrMosaic_global_232m",
      maxLevel: 7,
      format: "jpg",
      // Offline / blocked-network fallback: the same bundled Viking MDIM 2.1
      // global mosaic the homepage planet is textured with, so the atlas
      // still shows the same Mars (the ArcGIS mirror of this service uses a
      // square MarsEC0 cache scheme that does not match the geographic grid).
      localFallback: "/nam/assets/mars-surface-texture.jpg",
      swatch: "viking",
      attribution: "NASA / JPL / USGS",
      sourceUrl: "https://astrogeology.usgs.gov/search/map/Mars/Viking/MDIM21/Mars_Viking_MDIM21_ClrMosaic_global_232m",
      sourceLabel: "USGS product page"
    },
    {
      id: "ctx-global",
      name: "CTX high-resolution mosaic",
      shortName: "CTX · 5 m/px",
      description: "MRO context camera · beta mosaic · ~5 m/px · requires network; gaps possible",
      tileId: "CTX_beta01_uncontrolled_5m_Caltech",
      maxLevel: 11, tileSize: 512, format: "png", swatch: "atlas",
      attribution: "NASA / JPL / MSSS / Caltech Murray Lab",
      sourceUrl: "https://murray-lab.caltech.edu/CTX/beta01.html",
      sourceLabel: "Murray Lab beta mosaic"
    },
    {
      id: "mola-colour",
      name: "MOLA colour hillshade",
      shortName: "MOLA colour relief",
      description: "Elevation and shaded relief · global mosaic",
      tileId: "Mars_MGS_MOLA_ClrShade_merge_global_463m",
      maxLevel: 7,
      format: "jpg",
      swatch: "mola",
      attribution: "NASA / JPL · MGS MOLA",
      sourceUrl: "https://pds-geosciences.wustl.edu/missions/mgs/megdr.html",
      sourceLabel: "MOLA PDS archive"
    }
  ];

  // These products are listed by Mars Trek under its equirectangular services.
  // They share the Mars 2000 geographic/equirectangular grid used by the globe.
  const OVERLAY_LAYERS = [
    {
      id: "mola-roughness",
      name: "MOLA surface roughness",
      group: "Terrain",
      description: "Global surface roughness observations",
      tileId: "mola_roughness",
      maxLevel: 1,
      format: "png",
      swatch: "roughness",
      sourceUrl: "https://pds-geosciences.wustl.edu/missions/mgs/megdr.html",
      sourceLabel: "MOLA PDS archive"
    },
    {
      id: "moc-atlas",
      name: "MGS MOC atlas mosaic",
      group: "Surface imagery",
      description: "Mars Orbiter Camera global colour mosaic",
      tileId: "msss_atlas_simp_clon",
      maxLevel: 6,
      format: "png",
      swatch: "atlas",
      sourceUrl: "https://pds-imaging.jpl.nasa.gov/",
      sourceLabel: "PDS Imaging Node"
    },
    {
      id: "hrsc-colour",
      name: "MOLA + HRSC colour blend",
      group: "Terrain",
      description: "Global colour hillshade blend · MOLA / Mars Express HRSC",
      tileId: "Mars_MOLA_blend200ppx_HRSC_ClrShade_clon0dd_200mpp_lzw",
      maxLevel: 8,
      format: "jpg",
      swatch: "hillshade",
      sourceUrl: "https://www.cosmos.esa.int/web/psa/mars-express",
      sourceLabel: "ESA Mars Express archive"
    },
    {
      id: "hrsc-shade",
      name: "MOLA + HRSC hillshade",
      group: "Terrain",
      description: "Global shaded-relief blend · MOLA / Mars Express HRSC",
      tileId: "Mars_MOLA_blend200ppx_HRSC_Shade_clon0dd_200mpp_lzw",
      maxLevel: 8,
      format: "jpg",
      swatch: "hillshade",
      sourceUrl: "https://www.cosmos.esa.int/web/psa/mars-express",
      sourceLabel: "ESA Mars Express archive"
    }
    ,{ id: "themis-day", name: "THEMIS daytime infrared", group: "Thermal imagery", description: "100 m/px · ~65° S to 65° N · data gaps possible", tileId: "THEMIS_DayIR_ControlledMosaics_100m_v2_oct2018", maxLevel: 9, format: "png", swatch: "hillshade", attribution: "NASA / JPL / ASU / USGS", sourceUrl: "https://themis.asu.edu/", sourceLabel: "THEMIS project" },
    { id: "themis-night", name: "THEMIS nighttime infrared", group: "Thermal imagery", description: "100 m/px · ~65° S to 65° N · data gaps possible", tileId: "THEMIS_NightIR_ControlledMosaics_100m_v2_oct2018", maxLevel: 9, format: "png", swatch: "hillshade", attribution: "NASA / JPL / ASU / USGS", sourceUrl: "https://themis.asu.edu/", sourceLabel: "THEMIS project" },
    { id: "tes-dust", name: "TES atmospheric dust", group: "Atmosphere", description: "Global dust product · coarse resolution", tileId: "TES_Dust", maxLevel: 1, format: "png", swatch: "viking", attribution: "NASA / JPL / MGS TES", sourceUrl: "https://pds-geosciences.wustl.edu/missions/mgs/tes.html", sourceLabel: "MGS TES archive" },
    { id: "tes-inertia", name: "TES thermal inertia", group: "Surface properties", description: "Global thermal inertia · coarse resolution", tileId: "TES_Thermal_Inertia", maxLevel: 1, format: "png", swatch: "roughness", attribution: "NASA / JPL / MGS TES", sourceUrl: "https://pds-geosciences.wustl.edu/missions/mgs/tes.html", sourceLabel: "MGS TES archive" },
    { id: "tes-albedo", name: "TES surface albedo", group: "Surface properties", description: "Global reflectivity · coarse resolution", tileId: "Mars_MGS_TES_Albedo_mosaic_global_7410m", maxLevel: 1, format: "png", swatch: "atlas", attribution: "NASA / JPL / MGS TES", sourceUrl: "https://pds-geosciences.wustl.edu/missions/mgs/tes.html", sourceLabel: "MGS TES archive" }
  ];

  const DATA_SOURCES = [
    {
      title: "Mars Trek map services",
      description: "NASA/JPL's browsable resource map for Mars, including the interactive atlas, WMTS layer capabilities, service metadata and previews.",
      links: [
        { label: "Interactive Mars Trek resource map", url: "https://trek.nasa.gov/mars/" },
        { label: "Browse Mars layers", url: "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars" },
        { label: "Viking WMTS capabilities", url: `${CAPABILITIES_ROOT}/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/WMTSCapabilities.xml` },
        { label: "MOLA WMTS capabilities", url: `${CAPABILITIES_ROOT}/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/WMTSCapabilities.xml` }
      ]
    },
    {
      title: "Viking MDIM 2.1 global colour mosaic",
      description: "231 m/pixel global mosaic assembled from Viking colour imagery and the USGS MDIM 2.1 basemap.",
      links: [
        { label: "USGS product page", url: "https://astrogeology.usgs.gov/search/map/Mars/Viking/MDIM21/Mars_Viking_MDIM21_ClrMosaic_global_232m" },
        { label: "ArcGIS map service", url: "https://tiles.arcgis.com/tiles/lqRTrQp2HrfnJt8U/arcgis/rest/services/mars_viking_mosaic/MapServer" },
        { label: "NASA/JPL tile service", url: `${TILE_ROOT}/Mars_Viking_MDIM21_ClrMosaic_global_232m/1.0.0/default/default028mm/0/0/0.jpg` }
      ]
    },
    {
      title: "MOLA elevation data",
      description: "Mars Orbiter Laser Altimeter gridded elevation data. Source products are archived separately from the map tiles.",
      links: [
        { label: "PDS MOLA archive", url: "https://pds-geosciences.wustl.edu/missions/mgs/megdr.html" },
        { label: "MOLA tile capabilities", url: `${CAPABILITIES_ROOT}/Mars_MGS_MOLA_ClrShade_merge_global_463m/1.0.0/WMTSCapabilities.xml` }
      ]
    },
    {
      title: "USGS global geologic map",
      description: "Standardized global geological map of Mars. The source map is a separate GIS product, not an imagery overlay in this build.",
      links: [
        { label: "USGS map and downloads", url: "https://www.usgs.gov/maps/geologic-map-mars" },
        { label: "USGS Astrogeology", url: "https://astrogeology.usgs.gov/" }
      ]
    },
    {
      title: "THEMIS infrared observations",
      description: "Thermal Emission Imaging System observations. Several products use polar or regional map projections and are not forced onto the equirectangular globe as if they were compatible.",
      links: [
        { label: "THEMIS data portal", url: "https://themis.asu.edu/" },
        { label: "Mars Trek service catalogue", url: "https://trek.nasa.gov/tiles/apidoc/trekAPI.html?body=mars" }
      ]
    },
    {
      title: "HiRISE and rover imagery",
      description: "High-resolution regional images and rover raw images, with their own footprint and location metadata.",
      links: [
        { label: "HiRISE image archive", url: "https://hirise.lpl.arizona.edu/" },
        { label: "Perseverance raw images", url: "https://mars.nasa.gov/mars2020/multimedia/raw-images/" },
        { label: "Curiosity raw images", url: "https://mars.nasa.gov/msl/multimedia/raw/" }
      ]
    }
  ];

  const places = {
    gale: { name: "Gale Crater", lat: -5.4, lon: 137.8, detail: "Curiosity exploration region", note: "Gale Crater is the exploration region of NASA's Curiosity rover. This marker is a regional reference, not a live rover position.", height: 780000 },
    jezero: { name: "Jezero Crater", lat: 18.4, lon: 77.7, detail: "Perseverance exploration region", note: "Jezero Crater is the exploration region of NASA's Perseverance rover. This marker is a regional reference, not a live rover position.", height: 470000 },
    olympus: { name: "Olympus Mons", lat: 18.7, lon: -133.8, detail: "Shield volcano", note: "Olympus Mons is a major Martian shield volcano. The marker indicates the named feature's approximate location.", height: 850000 },
    valles: { name: "Valles Marineris", lat: -13.9, lon: -59.2, detail: "Canyon system", note: "Valles Marineris is an extensive canyon system near the Martian equator.", height: 1100000 },
    eberswalde: { name: "Eberswalde Crater", lat: -23.9753, lon: 326.7029, detail: "Ancient delta deposit", note: "Eberswalde contains a well-preserved ancient delta deposit. Longitude is normalized to east-positive values.", height: 600000 }
  };

  let CesiumLib = null;
  let MARS = null;
  let viewer = null;
  let baseLayer = null;
  let baseLayerId = "viking";
  let overlays = new Map();
  let customLayers = [];
  let clickHandler = null;
  let selectedPoint = null;
  let selectionEntity = null;
  let routePoints = [];
  let routeEntities = [];
  let plannedRouteEntities = [];
  let siteEntities = [];
  let routeModeActive = false;
  let sitesVisible = true;
  let baseTileErrors = 0;
  let usingFallbackBasemap = false;
  let atlasGlobeReady = false;

  const ui = {
    loading: $("map-loading"), error: $("map-error"), errorTitle: $("map-error-title"), errorMessage: $("map-error-message"), errorDetail: $("map-error-detail"),
    connectionDot: $("connection-dot"), connectionLabel: $("connection-label"), region: $("region-label"), coordinate: $("coordinate-readout"),
    inspector: $("inspector-panel"), inspectorTitle: $("inspector-title"), inspectorNote: $("inspector-note"), selectedCoordinates: $("selected-coordinates"), selectedLat: $("selected-lat"), selectedLon: $("selected-lon"),
    routePanel: $("route-panel"), routeMode: $("route-mode"), routeInstruction: $("route-instruction"), routeDistance: $("route-distance"), routePoints: $("route-points"), waypointList: $("waypoint-list"), exportRoute: $("export-route")
  };

  function setConnectionState(state, message) {
    ui.connectionDot.classList.remove("live", "error");
    if (state === "live") {
      ui.connectionDot.classList.add("live");
      ui.connectionLabel.textContent = message || "NASA / JPL imagery connected";
    } else if (state === "error") {
      ui.connectionDot.classList.add("error");
      ui.connectionLabel.textContent = message || "Map service unavailable";
    } else {
      ui.connectionLabel.textContent = message || "Connecting to Mars Trek";
    }
  }

  function showMapError(title, message, detail = "") {
    ui.loading.classList.add("hidden");
    ui.errorTitle.textContent = title;
    ui.errorMessage.textContent = message;
    ui.errorDetail.textContent = detail;
    ui.errorDetail.classList.toggle("hidden", !detail);
    ui.error.classList.remove("hidden");
    setConnectionState("error", "Map unavailable");
  }

  function hideMapError() { ui.error.classList.add("hidden"); }

  function seededRandom(seed) {
    let value = seed >>> 0;
    return () => {
      value = (value * 1664525 + 1013904223) >>> 0;
      return value / 4294967296;
    };
  }

  // Generate a small, local six-face star cube. A shared 3D point distribution
  // is projected onto the six faces, so the sky is present in every direction.
  function createStarSkyBox(C) {
    const size = 768;
    const faces = {
      positiveX: document.createElement("canvas"), negativeX: document.createElement("canvas"),
      positiveY: document.createElement("canvas"), negativeY: document.createElement("canvas"),
      positiveZ: document.createElement("canvas"), negativeZ: document.createElement("canvas")
    };
    const contexts = {};
    Object.entries(faces).forEach(([name, canvas]) => {
      canvas.width = size;
      canvas.height = size;
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#03070b";
      ctx.fillRect(0, 0, size, size);
      contexts[name] = ctx;
    });

    const rand = seededRandom(739102);
    const count = 7200;
    for (let i = 0; i < count; i += 1) {
      const z = rand() * 2 - 1;
      const theta = rand() * Math.PI * 2;
      const radius = Math.sqrt(1 - z * z);
      const x = radius * Math.cos(theta);
      const y = radius * Math.sin(theta);
      const ax = Math.abs(x), ay = Math.abs(y), az = Math.abs(z);
      let face, u, v, dominant;
      if (ax >= ay && ax >= az) {
        dominant = ax;
        if (x > 0) { face = "positiveX"; u = -z / dominant; v = -y / dominant; }
        else { face = "negativeX"; u = z / dominant; v = -y / dominant; }
      } else if (ay >= ax && ay >= az) {
        dominant = ay;
        if (y > 0) { face = "positiveY"; u = x / dominant; v = z / dominant; }
        else { face = "negativeY"; u = x / dominant; v = -z / dominant; }
      } else {
        dominant = az;
        if (z > 0) { face = "positiveZ"; u = x / dominant; v = -y / dominant; }
        else { face = "negativeZ"; u = -x / dominant; v = -y / dominant; }
      }
      const px = (u + 1) * .5 * size;
      const py = (v + 1) * .5 * size;
      const magnitude = rand();
      const r = magnitude > .994 ? 1.75 : magnitude > .95 ? 1.15 : .55 + rand() * .45;
      const alpha = magnitude > .994 ? .95 : magnitude > .95 ? .7 : .22 + rand() * .25;
      const tint = rand();
      const color = tint > .93 ? `rgba(194,211,238,${alpha})` : tint < .04 ? `rgba(241,211,178,${alpha})` : `rgba(235,239,242,${alpha})`;
      const ctx = contexts[face];
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(px, py, r, 0, Math.PI * 2);
      ctx.fill();
      if (r > 1.5) {
        ctx.strokeStyle = `rgba(235,239,242,${alpha * .28})`;
        ctx.lineWidth = .45;
        ctx.beginPath();
        ctx.moveTo(px - 3.8, py); ctx.lineTo(px + 3.8, py);
        ctx.moveTo(px, py - 3.8); ctx.lineTo(px, py + 3.8);
        ctx.stroke();
      }
    }

    const sources = {};
    Object.entries(faces).forEach(([name, canvas]) => { sources[name] = canvas.toDataURL("image/png"); });
    return new C.SkyBox({ sources });
  }

  function getTileUrl(layer, useFallback = false) {
    if (useFallback && layer.fallbackUrl) return layer.fallbackUrl;
    if (layer.customUrl) return layer.customUrl;
    return `${TILE_ROOT}/${layer.tileId}/1.0.0/default/default028mm/{z}/{y}/{x}.${layer.format || "jpg"}`;
  }

  function createMarsProvider(layer, useFallback = false) {
    if (useFallback && layer.localFallback) {
      // Blocked or offline network: serve the bundled global mosaic as one
      // local, same-origin image — the same Mars the homepage planet uses.
      return new CesiumLib.SingleTileImageryProvider({
        url: layer.localFallback,
        rectangle: CesiumLib.Rectangle.fromDegrees(-180, -90, 180, 90),
        ellipsoid: MARS,
        credit: new CesiumLib.Credit(`${layer.name} · bundled global mosaic · ${layer.attribution}`),
        tileWidth: 4096,
        tileHeight: 2048
      });
    }
    const tilingScheme = new CesiumLib.GeographicTilingScheme({ ellipsoid: MARS });
    return new CesiumLib.UrlTemplateImageryProvider({
      url: getTileUrl(layer, false),
      tilingScheme,
      minimumLevel: 0,
      maximumLevel: Number(layer.maxLevel || 8),
      rectangle: CesiumLib.Rectangle.fromDegrees(-180, -89.999, 180, 89.999),
      credit: new CesiumLib.Credit(layer.attribution || `NASA / JPL · ${layer.name}`),
      tileWidth: layer.tileSize || 256,
      tileHeight: layer.tileSize || 256
    });
  }

  function createMarsViewer() {
    MARS = new CesiumLib.Ellipsoid(MARS_A, MARS_A, MARS_B);
    viewer = new CesiumLib.Viewer("cesiumContainer", {
      animation: false,
      timeline: false,
      baseLayerPicker: false,
      geocoder: false,
      homeButton: false,
      sceneModePicker: false,
      navigationHelpButton: false,
      fullscreenButton: false,
      infoBox: false,
      selectionIndicator: false,
      shouldAnimate: false,
      skyBox: false,
      skyAtmosphere: false,
      baseLayer: false,
      scene3DOnly: true,
      requestRenderMode: false,
      contextOptions: { webgl: { alpha: false, antialias: true, powerPreference: "high-performance", preserveDrawingBuffer: true } },
      globe: new CesiumLib.Globe(MARS),
      mapProjection: new CesiumLib.GeographicProjection(MARS)
    });

    const scene = viewer.scene;
    scene.logarithmicDepthBuffer = true;
    scene.backgroundColor = CesiumLib.Color.fromCssColorString("#02060b");
    scene.skyBox = createStarSkyBox(CesiumLib);
    scene.skyBox.show = true;
    scene.globe.baseColor = CesiumLib.Color.fromCssColorString("#9a7b60");
    scene.globe.enableLighting = true;
    scene.globe.showGroundAtmosphere = true;
    scene.globe.showWaterEffect = false;
    scene.globe.depthTestAgainstTerrain = false;

scene.globe.maximumScreenSpaceError = 3.0;

scene.skyAtmosphere = new CesiumLib.SkyAtmosphere(MARS);
scene.skyAtmosphere.hueShift = 0.0;
scene.skyAtmosphere.saturationShift = 0.0;
scene.skyAtmosphere.brightnessShift = 0.0;

if (scene.sun) scene.sun.show = false;
if (scene.moon) scene.moon.show = false;

scene.fog.enabled = false;


const controls = scene.screenSpaceCameraController;

// Native camera controls
controls.enableZoom = true;
controls.enableRotate = true;
controls.enableTilt = true;
controls.enableTranslate = true;

// Use Cesium's built-in wheel and pinch support
controls.zoomEventTypes = [
    CesiumLib.CameraEventType.WHEEL,
    CesiumLib.CameraEventType.PINCH
];

// Moderate zoom speed
controls.zoomFactor = 5.0;

// Reduce excessive camera momentum
controls.inertiaZoom = 0.65;
controls.inertiaSpin = 0.84;
controls.inertiaTranslate = 0.84;

// Enable collision protection
controls.enableCollisionDetection = true;

// Prevent extreme close-ups for now
controls.minimumZoomDistance = MIN_ZOOM_METERS;
controls.maximumZoomDistance = 50000000;

// Keep camera movement controlled
controls.maximumMovementRatio = 0.05;

// Do not let camera tilt underneath the globe
controls.maximumTiltAngle = Math.PI / 2;

// Improve planetary depth precision
scene.logarithmicDepthBuffer = true;

scene.globe.maximumScreenSpaceError = 2.0;

viewer.resolutionScale = 1.0;

    // Start with the bundled mosaic so an unreachable remote service cannot
    // keep the atlas on "Finding Mars". Upgrade to live tiles in the background.
    addBaseLayer("viking", true);
    addMissionSites();
    installMapInteractions();
    viewer.camera.moveEnd.addEventListener(updateCoordinateHint);
    // The globe starts a little wider than the canonical overview so the
    // homepage hand-off can fly the camera in as the hero zooms through.
    viewer.camera.setView({
      destination: CesiumLib.Cartesian3.fromDegrees(18, 14, 11200000, MARS),
      orientation: { heading: CesiumLib.Math.toRadians(-12), pitch: CesiumLib.Math.toRadians(-82), roll: 0 }
    });
    document.addEventListener("nam:enter-atlas", () => {
      const params = new URLSearchParams(location.search);
      const lat = Number(params.get("lat")), lon = Number(params.get("lon"));
      if (params.has("lat") && params.has("lon") && Number.isFinite(lat) && Math.abs(lat) <= 90 && Number.isFinite(lon)) flyToCoordinates(lat, lon);
      else enterAtlasFlight();
    });
    installTrackpadPinchZoom();
    updateCoordinateHint();
    probeBaseLayer(true, true);
  }

  /* Cinematic hand-off from the homepage: while the hero planet zooms through,
     the globe glides from the wide establishing shot to the canonical overview. */
  let atlasArrived = false;
  function enterAtlasFlight() {
    if (!viewer || atlasArrived) return;
    atlasArrived = true;
    viewer.camera.flyTo({
      destination: CesiumLib.Cartesian3.fromDegrees(18, 14, 7400000, MARS),
      orientation: { heading: CesiumLib.Math.toRadians(-12), pitch: CesiumLib.Math.toRadians(-82), roll: 0 },
      duration: 2.4,
      easingFunction: CesiumLib.EasingFunction.QUADRATIC_IN_OUT
    });
  }
// Laptop trackpad pinch-to-zoom
function installTrackpadPinchZoom() {
    const canvas = viewer.canvas;

    let queuedDeltaY = 0;
    let frameRequested = false;

    function applyZoom() {
        frameRequested = false;

        if (!viewer || viewer.isDestroyed()) {
            queuedDeltaY = 0;
            return;
        }

        const deltaY = queuedDeltaY;
        queuedDeltaY = 0;

        if (Math.abs(deltaY) < 0.01) return;

        const camera = viewer.camera;
        const currentHeight = camera.positionCartographic.height;

        // Controls how much each pinch movement zooms.
        const scale = Math.exp(deltaY * 0.0024);

        const nextHeight = CesiumLib.Math.clamp(
            currentHeight * scale,
            MIN_ZOOM_METERS,
            50000000
        );

        const distance = Math.abs(nextHeight - currentHeight);

        if (distance < 0.5) return;

        if (nextHeight < currentHeight) {
            camera.zoomIn(distance);
        } else {
            camera.zoomOut(distance);
        }
    }

    window.addEventListener("wheel", (event) => {

        // Only intercept trackpad-style pinch zoom.
        if (event.target !== canvas) return;

        if (!event.ctrlKey && !event.metaKey) return;

        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();

        const unit =
            event.deltaMode === 1 ? 16 :
            event.deltaMode === 2 ? window.innerHeight : 1;

        queuedDeltaY += event.deltaY * unit;

        if (!frameRequested) {
            frameRequested = true;
            window.requestAnimationFrame(applyZoom);
        }

    }, {
        capture: true,
        passive: false
    });
}
  let baseProbeGeneration = 0;
  function probeBaseLayer(useFallback = usingFallbackBasemap, upgradeWhenReady = false) {
    const layer = BASE_LAYERS.find((item) => item.id === baseLayerId);
    if (!layer) return;
    const generation = ++baseProbeGeneration;
    const image = new Image();
    let settled = false;
    const isCurrent = () => !settled && generation === baseProbeGeneration && baseLayerId === layer.id;
    const fail = (reason) => {
      if (!isCurrent()) return;
      settled = true;
      window.clearTimeout(timer);
      if (!useFallback && layer.localFallback) {
        try {
          addBaseLayer(layer.id, true);
          setConnectionState("loading", "Switching to the bundled Viking mosaic");
          probeBaseLayer(true);
        } catch (error) {
          showMapError("Mars imagery unavailable", "The bundled map could not be initialized. Try reloading the atlas.", error.message || String(error));
        }
      } else if (useFallback) {
        showMapError("Mars imagery unavailable", "The bundled Mars mosaic could not be loaded. Check the connection to this site and retry.", reason);
      } else {
        // A failed remote basemap must not leave the globe blank.
        addBaseLayer("viking", true);
        ui.loading.classList.add("hidden");
        setConnectionState("error", `${layer.shortName} unavailable · showing bundled Viking`);
        ui.coordinate.textContent = "Remote map unavailable · showing bundled Viking";
      }
    };
    const timer = window.setTimeout(() => fail("Image request timed out."), useFallback ? 15000 : 3200);
    image.onload = () => {
      if (!isCurrent()) return;
      settled = true;
      window.clearTimeout(timer);
      atlasGlobeReady = true;
      window.__NAM_GLOBE_READY = true;
      ui.loading.classList.add("hidden");
      hideMapError();
      setConnectionState("live", useFallback ? "Viking mosaic · bundled imagery" : "NASA / JPL imagery connected");
      document.dispatchEvent(new CustomEvent("nam:atlas-globe-ready"));
      if (useFallback && upgradeWhenReady) tryLiveViking(generation);
    };
    image.onerror = () => fail("Image request failed.");
    image.src = useFallback ? layer.localFallback : `${TILE_ROOT}/${layer.tileId}/1.0.0/default/default028mm/0/0/0.${layer.format}`;
  }

  function tryLiveViking(generation) {
    const layer = BASE_LAYERS.find((item) => item.id === "viking");
    const image = new Image();
    let expired = false;
    const timer = window.setTimeout(() => { expired = true; }, 3200);
    image.onload = () => {
      window.clearTimeout(timer);
      if (expired || generation !== baseProbeGeneration || baseLayerId !== "viking" || !usingFallbackBasemap) return;
      try {
        baseTileErrors = 0;
        addBaseLayer("viking");
        setConnectionState("live", "NASA / JPL imagery connected");
      } catch (error) {
        console.warn("Could not switch to live Mars Trek imagery:", error);
      }
    };
    image.onerror = () => { expired = true; window.clearTimeout(timer); };
    image.src = `${TILE_ROOT}/${layer.tileId}/1.0.0/default/default028mm/0/0/0.${layer.format}`;
  }

  function addBaseLayer(id, useFallback = false) {
    const layer = BASE_LAYERS.find((item) => item.id === id);
    if (!layer || !viewer) return;
    const provider = createMarsProvider(layer, useFallback);
    baseTileErrors = 0;
    if (baseLayer) viewer.imageryLayers.remove(baseLayer, true);
    baseLayer = viewer.imageryLayers.addImageryProvider(provider, 0);
    baseLayer.alpha = 1;
    baseLayerId = id;
    usingFallbackBasemap = useFallback;
    const credit = $("map-credit");
    credit.textContent = useFallback ? `${layer.name} · bundled global mosaic` : `${layer.name} · ${layer.attribution}`;
    $("active-base-label").textContent = layer.shortName;
    renderLayerCatalogue();
    provider.errorEvent.addEventListener((error) => {
      if (!baseLayer || baseLayer.imageryProvider !== provider) return;
      baseTileErrors += 1;
      console.warn(`NAM base layer ${layer.name} tile error:`, error);
      if (baseTileErrors >= 4 && !usingFallbackBasemap && layer.localFallback) {
        console.warn("Primary NASA Viking tile service is failing; switching to the bundled global mosaic (the same Mars the homepage shows).");
        baseTileErrors = 0;
        addBaseLayer(id, true);
        setConnectionState("loading", "Switching to the bundled Viking mosaic");
        probeBaseLayer(true);
      } else if (baseTileErrors >= 4) {
        setConnectionState("error", "Some base map tiles failed");
      }
    });
  }

  function addOverlayLayer(id) {
    const layer = [...OVERLAY_LAYERS, ...customLayers].find((item) => item.id === id);
    if (!layer || !viewer || overlays.has(id)) return;
    const provider = createMarsProvider(layer);
    const imagery = viewer.imageryLayers.addImageryProvider(provider);
    imagery.alpha = .68;
    overlays.set(id, { layer, imagery });
    let errors = 0;
    provider.errorEvent.addEventListener((error) => {
      console.warn(`NAM overlay ${layer.name} tile error:`, error);
      if (++errors === 3 && overlays.has(id)) {
        setConnectionState("error", `${layer.name}: some tiles unavailable · check connection or coverage`);
      }
    });
    renderLayerCatalogue();
  }

  function removeOverlayLayer(id) {
    const item = overlays.get(id);
    if (!item || !viewer) return;
    viewer.imageryLayers.remove(item.imagery, true);
    overlays.delete(id);
    renderLayerCatalogue();
  }

  function layerCapabilitiesUrl(layer) {
    if (!layer.tileId) return null;
    return `${CAPABILITIES_ROOT}/${layer.tileId}/1.0.0/WMTSCapabilities.xml`;
  }

  function renderLayerCatalogue(filter = $("layer-filter").value) {
    const query = filter.trim().toLowerCase();
    const baseList = $("base-layer-list");
    const overlayList = $("overlay-layer-list");
    baseList.replaceChildren();
    overlayList.replaceChildren();

    BASE_LAYERS.forEach((layer) => {
      const card = document.createElement("div");
      card.className = `base-layer-card${baseLayerId === layer.id ? " is-active" : ""}`;
      const swatch = document.createElement("span");
      swatch.className = `layer-swatch ${layer.swatch}`;
      const copy = document.createElement("span");
      copy.className = "layer-copy";
      const name = document.createElement("strong"); name.textContent = layer.name;
      const desc = document.createElement("small"); desc.textContent = layer.description;
      copy.append(name, desc);
      const sourceLink = document.createElement("a");
      sourceLink.className = "layer-source-link";
      sourceLink.href = layerCapabilitiesUrl(layer) || layer.sourceUrl;
      sourceLink.target = "_blank"; sourceLink.rel = "noreferrer";
      sourceLink.textContent = "WMTS service ↗";
      copy.append(sourceLink);
      if (layer.sourceUrl) {
        const productLink = document.createElement("a");
        productLink.className = "layer-source-link";
        productLink.href = layer.sourceUrl; productLink.target = "_blank"; productLink.rel = "noreferrer";
        productLink.textContent = `${layer.sourceLabel || "Source product"} ↗`;
        copy.append(productLink);
      }
      const action = document.createElement("button");
      action.className = "layer-select";
      action.type = "button";
      action.textContent = baseLayerId === layer.id ? "Selected" : "Use map";
      action.setAttribute("aria-label", `${baseLayerId === layer.id ? "Selected map" : "Use map"}: ${layer.name}`);
      action.setAttribute("aria-pressed", String(baseLayerId === layer.id));
      action.addEventListener("click", () => {
        baseTileErrors = 0;
        addBaseLayer(layer.id);
        setConnectionState("loading", "Loading " + layer.shortName);
        probeBaseLayer(false);
      });
      card.append(swatch, copy, action);
      baseList.append(card);
    });

    const candidates = [...OVERLAY_LAYERS, ...customLayers].filter((layer) => {
      const text = `${layer.name} ${layer.group || ""} ${layer.description}`.toLowerCase();
      return text.includes(query);
    });
    if (!candidates.length) {
      const empty = document.createElement("p");
      empty.className = "layer-empty";
      empty.textContent = "No layers match that search.";
      overlayList.append(empty);
    }

    candidates.forEach((layer) => {
      const active = overlays.has(layer.id);
      const card = document.createElement("div");
      card.className = "overlay-layer-card";
      const swatch = document.createElement("span"); swatch.className = `layer-swatch ${layer.swatch || "mola"}`;
      const copy = document.createElement("span"); copy.className = "layer-copy";
      const name = document.createElement("strong"); name.textContent = layer.name;
      const desc = document.createElement("small"); desc.textContent = `${layer.group || "Custom service"} · ${layer.description}`;
      copy.append(name, desc);
      if (layerCapabilitiesUrl(layer)) {
        const sourceLink = document.createElement("a");
        sourceLink.className = "layer-source-link";
        sourceLink.href = layerCapabilitiesUrl(layer);
        sourceLink.target = "_blank"; sourceLink.rel = "noreferrer";
        sourceLink.textContent = "WMTS service ↗";
        copy.append(sourceLink);
      }
      if (layer.sourceUrl) {
        const productLink = document.createElement("a");
        productLink.className = "layer-source-link";
        productLink.href = layer.sourceUrl; productLink.target = "_blank"; productLink.rel = "noreferrer";
        productLink.textContent = `${layer.sourceLabel || "Source product"} ↗`;
        copy.append(productLink);
      }
      const action = document.createElement("button");
      action.type = "button";
      action.className = "layer-add";
      action.textContent = active ? "Remove" : "Add";
      action.setAttribute("aria-pressed", String(active));
      action.setAttribute("aria-label", `${active ? "Remove" : "Add"} ${layer.name}`);
      action.addEventListener("click", () => active ? removeOverlayLayer(layer.id) : addOverlayLayer(layer.id));
      card.append(swatch, copy, action);
      overlayList.append(card);

      if (active) {
        const opacity = document.createElement("label");
        opacity.className = "layer-opacity";
        opacity.innerHTML = `<span>Opacity</span>`;
        const range = document.createElement("input");
        range.type = "range"; range.min = "0"; range.max = "100"; range.value = String(Math.round(overlays.get(layer.id).imagery.alpha * 100));
        range.setAttribute("aria-label", `${layer.name} opacity`);
        range.addEventListener("input", () => { const activeLayer = overlays.get(layer.id); if (activeLayer) activeLayer.imagery.alpha = Number(range.value) / 100; });
        opacity.append(range);
        overlayList.append(opacity);
      }
    });
    $("overlay-count").textContent = `${overlays.size} active`;
  }

  function renderDataSources() {
    const container = $("data-source-list");
    container.replaceChildren();
    DATA_SOURCES.forEach((source) => {
      const card = document.createElement("section"); card.className = "data-source-card";
      const title = document.createElement("h3"); title.textContent = source.title;
      const desc = document.createElement("p"); desc.textContent = source.description;
      const links = document.createElement("div"); links.className = "data-source-links";
      source.links.forEach((item) => {
        const link = document.createElement("a"); link.href = item.url; link.target = "_blank"; link.rel = "noreferrer"; link.textContent = item.label + " ↗";
        links.append(link);
      });
      card.append(title, desc, links);
      container.append(card);
    });
    const note = document.createElement("p");
    note.className = "data-note";
    note.textContent = "Map tiles are streamed for visualisation. A WMTS capabilities document describes the service; it is not the same as downloading the original raster product. Use the archive or product links for source data downloads.";
    container.append(note);
  }

  function renderPlaces() {
    const list = $("place-list");
    list.replaceChildren();
    Object.entries(places).forEach(([id, place]) => {
      const button = document.createElement("button");
      button.type = "button"; button.className = "place-row";
      const marker = document.createElement("span"); marker.className = `place-marker${id === "olympus" ? " volcano" : ""}`;
      const copy = document.createElement("span");
      const name = document.createElement("strong"); name.textContent = place.name;
      const detail = document.createElement("small"); detail.textContent = place.detail;
      copy.append(name, detail);
      const arrow = document.createElement("span"); arrow.className = "place-arrow"; arrow.textContent = "↗";
      button.append(marker, copy, arrow);
      button.addEventListener("click", () => flyToPlace(id));
      list.append(button);
    });
  }

  function addMissionSites() {
    siteEntities = Object.entries(places).map(([id, place]) => viewer.entities.add({
      id: `site-${id}`,
      name: place.name,
      position: CesiumLib.Cartesian3.fromDegrees(normalizeLongitude(place.lon), place.lat, 0, MARS),
      point: {
        pixelSize: 7,
        color: CesiumLib.Color.fromCssColorString("#d29a78"),
        outlineColor: CesiumLib.Color.fromCssColorString("#302c26"),
        outlineWidth: 1.3,
        heightReference: CesiumLib.HeightReference.NONE,
        disableDepthTestDistance: 350000
      },
      label: {
        text: place.name,
        font: "11px Inter, Arial, sans-serif",
        fillColor: CesiumLib.Color.fromCssColorString("#f1eee5"),
        outlineColor: CesiumLib.Color.fromCssColorString("#151817"),
        outlineWidth: 3,
        style: CesiumLib.LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new CesiumLib.Cartesian2(9, -9),
        distanceDisplayCondition: new CesiumLib.DistanceDisplayCondition(0, 5400000),
        disableDepthTestDistance: 350000
      },
      properties: { placeId: id }
    }));
  }

  function installMapInteractions() {
    clickHandler = new CesiumLib.ScreenSpaceEventHandler(viewer.scene.canvas);
    clickHandler.setInputAction((movement) => {
      const cartesian = viewer.camera.pickEllipsoid(movement.endPosition, MARS);
      if (!cartesian) return;
      const point = CesiumLib.Cartographic.fromCartesian(cartesian, MARS);
      ui.coordinate.textContent = `${formatLatitude(CesiumLib.Math.toDegrees(point.latitude))}  ·  ${formatLongitude(CesiumLib.Math.toDegrees(point.longitude))}`;
    }, CesiumLib.ScreenSpaceEventType.MOUSE_MOVE);

    clickHandler.setInputAction((movement) => {
      const cartesian = viewer.camera.pickEllipsoid(movement.position, MARS);
      if (!cartesian) return;
      const point = CesiumLib.Cartographic.fromCartesian(cartesian, MARS);
      const lat = CesiumLib.Math.toDegrees(point.latitude);
      const lon = normalizeLongitude(CesiumLib.Math.toDegrees(point.longitude));
      const picked = viewer.scene.pick(movement.position);
      const siteId = picked && picked.id && picked.id.properties && picked.id.properties.placeId ? picked.id.properties.placeId.getValue() : null;
      if (routeModeActive) addRoutePoint(lat, lon);
      else selectLocation(lat, lon, siteId);
    }, CesiumLib.ScreenSpaceEventType.LEFT_CLICK);

    clickHandler.setInputAction(() => { if (routeModeActive) toggleRouteMode(false); }, CesiumLib.ScreenSpaceEventType.RIGHT_CLICK);
  }

  function selectLocation(lat, lon, siteId = null, result = null) {
    selectedPoint = { lat, lon };
    const place = siteId ? places[siteId] : null;
    const title = result?.name || place?.name || "Selected location";
    if (selectionEntity) viewer.entities.remove(selectionEntity);
    selectionEntity = viewer.entities.add({
      id: "nam-selection", name: title,
      position: CesiumLib.Cartesian3.fromDegrees(lon, lat, 100, MARS),
      point: { pixelSize: 14, color: CesiumLib.Color.fromCssColorString("#ffe4a1"),
        outlineColor: CesiumLib.Color.fromCssColorString("#a34828"), outlineWidth: 4,
        disableDepthTestDistance: 0 },
      label: { text: title, font: "bold 14px sans-serif", fillColor: CesiumLib.Color.WHITE,
        outlineColor: CesiumLib.Color.BLACK, outlineWidth: 4, style: CesiumLib.LabelStyle.FILL_AND_OUTLINE,
        pixelOffset: new CesiumLib.Cartesian2(0, -25),
        disableDepthTestDistance: 0 }
    });
    ui.inspectorTitle.textContent = title;
    ui.selectedCoordinates.textContent = `${formatLatitude(lat)}  ·  ${formatLongitude(lon)}`;
    ui.selectedLat.textContent = formatLatitude(lat);
    ui.selectedLon.textContent = formatLongitude(lon);
    ui.inspectorNote.textContent = result ? `${result.type || result.kind || "Location"} · catalogue center, not a mapped boundary${Number.isFinite(result.diameter_km) && result.diameter_km > 0 ? ` · reported diameter ${result.diameter_km.toFixed(1)} km` : ""}. ${result.src || "Selected coordinates"}.` : place ? `${place.note} Marker shows an approximate center, not a feature boundary.` : "Marker shows the selected coordinates, not a feature boundary. No elevation or hazard values are inferred from the image.";
    ui.inspector.classList.remove("hidden");
    $("bookmark-status").textContent = "";
    $("backend-terrain").textContent = "Loading terrain data…";
    const point = selectedPoint;
    fetch(`/location/card?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`)
      .then(response => { if (!response.ok) throw new Error(`HTTP ${response.status}`); return response.json(); })
      .then(data => {
        if (selectedPoint !== point) return;
        $("backend-terrain").textContent = `Elevation ${data.terrain.elevation_m.toLocaleString()} m · slope ${data.terrain.slope_deg}° — synthetic demo terrain [SIM], not a safety assessment.`;
      }).catch(() => { if (selectedPoint === point) $("backend-terrain").textContent = "Terrain service unavailable; imagery remains available independently."; });
  }

  function clearSelection() { selectedPoint = null; if (selectionEntity && viewer) viewer.entities.remove(selectionEntity); selectionEntity = null; ui.inspector.classList.add("hidden"); }

  function addRoutePoint(lat, lon) {
    routePoints.push({ lat, lon });
    redrawRoute();
    renderRouteStats();
    ui.routeInstruction.textContent = routePoints.length < 2 ? "Add another point to extend the traverse. Right-click to finish." : "Add more points or right-click to finish.";
  }

  function clearPlannedRoute() {
    if (!viewer) return;
    plannedRouteEntities.forEach(entity => viewer.entities.remove(entity));
    plannedRouteEntities = [];
  }

  function showPlannedRoute(points, stops) {
    if (!viewer || !Array.isArray(points) || points.length < 2) return;
    clearPlannedRoute();
    const coordinates = points.flatMap(p => [p.lon, p.lat, 300]);
    plannedRouteEntities.push(viewer.entities.add({ polyline: {
      positions: CesiumLib.Cartesian3.fromDegreesArrayHeights(coordinates, MARS), width: 3,
      material: new CesiumLib.ColorMaterialProperty(CesiumLib.Color.fromCssColorString("#f2ad76")),
      arcType: CesiumLib.ArcType.GEODESIC, clampToGround: false
    }}));
    for (const stop of stops) {
      plannedRouteEntities.push(viewer.entities.add({
        position: CesiumLib.Cartesian3.fromDegrees(stop.lon, stop.lat, 400, MARS),
        point: { pixelSize: 9, color: CesiumLib.Color.fromCssColorString(stop.kind === "water" ? "#8ad7f1" : stop.kind === "shelter" ? "#b9d79f" : "#f2ad76"), outlineColor: CesiumLib.Color.BLACK, outlineWidth: 1 },
        label: { text: stop.name, font: "12px sans-serif", fillColor: CesiumLib.Color.WHITE, showBackground: true, pixelOffset: new CesiumLib.Cartesian2(0, -18) }
      }));
    }
  }

  function redrawRoute() {
    routeEntities.forEach((entity) => viewer.entities.remove(entity));
    routeEntities = [];
    if (!routePoints.length) return;
    routePoints.forEach((point, index) => {
      routeEntities.push(viewer.entities.add({
        position: CesiumLib.Cartesian3.fromDegrees(point.lon, point.lat, 100, MARS),
        point: { pixelSize: index === 0 ? 9 : 7, color: index === 0 ? CesiumLib.Color.fromCssColorString("#e1b38e") : CesiumLib.Color.fromCssColorString("#a8c0a9"), outlineColor: CesiumLib.Color.fromCssColorString("#151a17"), outlineWidth: 1.5, disableDepthTestDistance: 350000 },
        label: { text: String(index + 1), font: "10px Inter, Arial, sans-serif", fillColor: CesiumLib.Color.WHITE, outlineColor: CesiumLib.Color.fromCssColorString("#172019"), outlineWidth: 3, style: CesiumLib.LabelStyle.FILL_AND_OUTLINE, pixelOffset: new CesiumLib.Cartesian2(0, -13), disableDepthTestDistance: 350000 }
      }));
    });
    if (routePoints.length > 1) {
      const coordinates = routePoints.flatMap((point) => [point.lon, point.lat, 100]);
      routeEntities.push(viewer.entities.add({ polyline: { positions: CesiumLib.Cartesian3.fromDegreesArrayHeights(coordinates, MARS), width: 2.5, material: new CesiumLib.ColorMaterialProperty(CesiumLib.Color.fromCssColorString("#c3d5bb")), arcType: CesiumLib.ArcType.GEODESIC, clampToGround: false } }));
    }
  }

  function renderRouteStats() {
    const distance = routePoints.slice(1).reduce((sum, point, index) => sum + haversineKm(routePoints[index], point), 0);
    ui.routeDistance.innerHTML = `${distance.toFixed(1)} <small>km</small>`;
    ui.routePoints.textContent = String(routePoints.length);
    ui.exportRoute.disabled = routePoints.length < 2;
    if (!routePoints.length) {
      ui.waypointList.innerHTML = '<span class="empty-waypoints">No waypoints yet</span>';
      return;
    }
    ui.waypointList.replaceChildren();
    routePoints.forEach((point, index) => {
      const row = document.createElement("div"); row.className = "waypoint-item";
      const label = document.createElement("span"); label.textContent = `${index + 1}. ${formatLatitude(point.lat)}, ${formatLongitude(point.lon)}`;
      const remove = document.createElement("button"); remove.type = "button"; remove.textContent = "×"; remove.setAttribute("aria-label", `Remove waypoint ${index + 1}`);
      remove.addEventListener("click", () => { routePoints.splice(index, 1); redrawRoute(); renderRouteStats(); });
      row.append(label, remove); ui.waypointList.append(row);
    });
  }

  function haversineKm(a, b) {
    const radians = Math.PI / 180;
    const lat1 = a.lat * radians, lat2 = b.lat * radians;
    const dLat = (b.lat - a.lat) * radians, dLon = (b.lon - a.lon) * radians;
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
    return 2 * MARS_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(h)));
  }

  function toggleRouteMode(force) {
    routeModeActive = typeof force === "boolean" ? force : !routeModeActive;
    ui.routeMode.setAttribute("aria-pressed", String(routeModeActive));
    ui.routePanel.classList.remove("hidden");
    ui.routeInstruction.textContent = routeModeActive ? "Click the surface to add waypoints. Right-click to finish." : (routePoints.length ? "Traverse saved in this session. Continue editing or export it." : "No waypoints yet.");
    if (!routeModeActive && !routePoints.length) ui.routePanel.classList.add("hidden");
  }

  function clearRoute() {
    routePoints = []; redrawRoute(); renderRouteStats(); toggleRouteMode(false); ui.routePanel.classList.add("hidden");
  }

  function exportRouteGeoJSON() {
    if (routePoints.length < 2) return;
    const distance = routePoints.slice(1).reduce((sum, point, index) => sum + haversineKm(routePoints[index], point), 0);
    const feature = { type: "Feature", properties: { name: "NAM proposed traverse", body: "Mars", coordinateReference: "Mars 2000 / geodetic latitude, east-positive longitude", distanceKm: Number(distance.toFixed(3)), distanceNote: "Spherical surface-distance estimate; does not account for terrain, slope or obstacles." }, geometry: { type: "LineString", coordinates: routePoints.map((point) => [point.lon, point.lat]) } };
    downloadBlob(new Blob([JSON.stringify(feature, null, 2)], { type: "application/geo+json" }), "nam-traverse.geojson");
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a"); anchor.href = url; anchor.download = filename; document.body.append(anchor); anchor.click(); anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 1500);
  }

  function saveMapImage() {
    if (!viewer) return;
    try {
      viewer.render();
      viewer.scene.canvas.toBlob((blob) => {
        if (!blob) { window.alert("The browser could not capture the map. Try again after the globe finishes rendering."); return; }
        downloadBlob(blob, "nam-map-view.png");
      }, "image/png");
    } catch (error) {
      console.warn("Map image export failed:", error);
      window.alert("The map image could not be exported in this browser.");
    }
  }

  function flyToPlace(id) {
    const place = places[id];
    if (!place || !viewer) return;
    ui.coordinate.textContent = place.name;
    closePanel("places-panel");
    selectLocation(place.lat, normalizeLongitude(place.lon), id);
    viewer.camera.flyTo({ destination: CesiumLib.Cartesian3.fromDegrees(normalizeLongitude(place.lon), place.lat, place.height, MARS), orientation: { heading: 0, pitch: CesiumLib.Math.toRadians(-90), roll: 0 }, duration: 2.0 });
  }

  function flyHome() {
    if (!viewer) return;
    closeAllPanels(); clearSelection();
    viewer.camera.flyTo({ destination: CesiumLib.Cartesian3.fromDegrees(18, 14, 7400000, MARS), orientation: { heading: CesiumLib.Math.toRadians(-12), pitch: CesiumLib.Math.toRadians(-82), roll: 0 }, duration: 1.8 });
  }

  function normalizeLongitude(lon) { return ((lon + 180) % 360 + 360) % 360 - 180; }
  function formatLatitude(lat) { return `${Math.abs(lat).toFixed(3)}° ${lat >= 0 ? "N" : "S"}`; }
  function formatLongitude(lon) { return `${Math.abs(lon).toFixed(3)}° ${lon >= 0 ? "E" : "W"}`; }

  function updateCoordinateHint() {
    if (!viewer || selectedPoint) return;
    ui.coordinate.textContent = "Mars  ·  move over the surface for coordinates";
  }

  function flyToCoordinates(lat, lon, title, result = null) {
    if (!viewer || !Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90) return;
    lon = normalizeLongitude(lon);
    const info = result || (title ? { name: title } : null);
    selectLocation(lat, lon, null, info);
    // Frame large features broadly and small features more closely. The marker
    // represents the gazetteer's center, not a claimed geometry or boundary.
    const diameter = Number(result?.diameter_km);
    const height = Number.isFinite(diameter) && diameter > 0 ? Math.max(30000, Math.min(1600000, diameter * 1800)) : 250000;
    viewer.camera.flyTo({ destination: CesiumLib.Cartesian3.fromDegrees(lon, lat, height, MARS), orientation: { heading: 0, pitch: CesiumLib.Math.toRadians(-90), roll: 0 }, duration: 1.7 });
  }

  let searchRequest = 0;
  let searchTimer = null;
  async function searchLocation(query) {
    const normalized = query.trim();
    if (!normalized || !viewer) return;
    const request = ++searchRequest;
    const coordinates = normalized.match(/^\s*(-?\d+(?:\.\d+)?)\s*[, ]\s*(-?\d+(?:\.\d+)?)\s*$/);
    if (coordinates) {
      const lat = Number(coordinates[1]), lon = Number(coordinates[2]);
      if (Math.abs(lat) <= 90) {
        closePanel("search-panel"); closePanel("search-results"); flyToCoordinates(lat, lon);
      } else ui.coordinate.textContent = "Latitude must be between -90 and 90 degrees";
      return;
    }
    const list = $("search-results-list");
    list.textContent = "Searching the gazetteer…";
    $("search-results").classList.remove("hidden");
    try {
      const response = await fetch(`/search?q=${encodeURIComponent(normalized)}&limit=12`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      if (request !== searchRequest) return;
      list.replaceChildren();
      if (!data.results.length) { list.textContent = "No catalogue matches. Try a different name or latitude, longitude. Not every Mars feature is in the bundled catalogue."; return; }
      for (const hit of data.results) {
        const button = document.createElement("button");
        button.type = "button"; button.className = "backend-search-result";
        const name = document.createElement("strong"); name.textContent = hit.name;
        const detail = document.createElement("span"); detail.textContent = `${hit.kind === "landing_site" ? "Landing site" : hit.type || "Named feature"} · ${formatLatitude(hit.lat)} · ${formatLongitude(normalizeLongitude(hit.lon))}`;
        button.append(name, detail);
        button.addEventListener("click", () => { searchRequest++; closePanel("search-results"); closePanel("search-panel"); flyToCoordinates(hit.lat, hit.lon, hit.name, hit); });
        list.append(button);
      }
    } catch (_) { if (request === searchRequest) list.textContent = "Gazetteer unavailable. Check the backend connection and try again."; }
  }

  function openPanel(id) {
    closeAllPanels(id);
    const panel = $(id);
    panel.classList.remove("hidden");
    const buttonId = { "layers-panel": "layers-toggle", "data-panel": "data-toggle", "places-panel": "places-toggle", "search-panel": "search-toggle", "operations-panel": "operations-toggle" }[id];
    if (buttonId) $(buttonId).setAttribute("aria-expanded", "true");
    if (id === "search-panel") window.setTimeout(() => $("location-search").focus(), 30);
  }

  function closePanel(id) {
    const panel = $(id); if (!panel) return;
    panel.classList.add("hidden");
    const buttonId = { "layers-panel": "layers-toggle", "data-panel": "data-toggle", "places-panel": "places-toggle", "search-panel": "search-toggle", "operations-panel": "operations-toggle" }[id];
    if (buttonId) $(buttonId).setAttribute("aria-expanded", "false");
  }

  function closeAllPanels(except = null) {
    ["layers-panel", "data-panel", "places-panel", "search-panel", "operations-panel", "service-panel", "search-results"].forEach((id) => { if (id !== except) closePanel(id); });
  }

  function togglePanel(id) {
    if ($(id).classList.contains("hidden")) openPanel(id); else closePanel(id);
  }

  function addCustomLayer(event) {
    event.preventDefault();
    const name = $("custom-layer-name").value.trim();
    let url = $("custom-layer-url").value.trim();
    if (!name || !url) return;
    if (url.includes("{TileMatrix}")) url = url.replaceAll("{TileMatrix}", "{z}").replaceAll("{TileRow}", "{y}").replaceAll("{TileCol}", "{x}");
    if (!url.includes("{z}") || !url.includes("{y}") || !url.includes("{x}")) {
      window.alert("Use a tile URL template containing {z}, {y} and {x} (or WMTS {TileMatrix}, {TileRow} and {TileCol})."); return;
    }
    try {
      const parsed = new URL(url.replaceAll("{z}", "0").replaceAll("{y}", "0").replaceAll("{x}", "0"));
      if (parsed.protocol !== "https:") throw new Error("Use an HTTPS tile URL.");
    } catch (error) { window.alert(error.message || "That tile URL is not valid."); return; }
    const id = `custom-${Date.now()}`;
    customLayers.push({ id, name, group: "Custom service", description: "User-added XYZ tile service", customUrl: url, maxLevel: 8, attribution: name, swatch: "mola" });
    $("custom-layer-form").reset();
    addOverlayLayer(id);
    renderLayerCatalogue($("layer-filter").value);
  }

  function wireEvents() {
    $("operations-toggle").addEventListener("click", () => togglePanel("operations-panel"));
    const tools = window.NAMBackendTools({
      getPoint: () => selectedPoint,
      getRoute: () => routePoints.map(point => ({ ...point })),
      showPlan: showPlannedRoute,
      clearPlan: clearPlannedRoute,
      flyTo: (lat, lon, name) => flyToCoordinates(lat, lon, name),
      showRoute: (points) => { routePoints = points.map(p => ({ lat: p.lat, lon: p.lon })); redrawRoute(); renderRouteStats(); ui.routePanel.classList.remove("hidden"); },
      open: () => openPanel("service-panel"),
      activateLayer: (id) => { const mapped = {"mdim21":"viking", "mola-color":"mola-colour", "mola-shaded":"mola-colour"}[id]; if (mapped) addBaseLayer(mapped); return !!mapped; }
    });
    document.querySelectorAll("[data-service]").forEach(button => button.addEventListener("click", () => tools.show(button.dataset.service)));
    $("inspect-science").addEventListener("click", () => tools.show("science"));
    $("close-results").addEventListener("click", () => { searchRequest++; closePanel("search-results"); });
    $("bookmark-point").addEventListener("click", async () => {
      if (!selectedPoint) return;
      const status = $("bookmark-status"); status.textContent = "Saving…";
      try {
        const response = await fetch("/bookmarks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ name: ui.inspectorTitle.textContent, ...selectedPoint, camera: {} }) });
        if (!response.ok) throw new Error(response.status === 401 ? "API key required; use an authorized API client." : `HTTP ${response.status}`);
        status.textContent = "Bookmark saved. Find it in Field tools.";
      } catch (error) { status.textContent = `Could not save bookmark: ${error.message}`; }
    });
    $("search-toggle").addEventListener("click", () => togglePanel("search-panel"));
    $("layers-toggle").addEventListener("click", () => togglePanel("layers-panel"));
    $("data-toggle").addEventListener("click", () => togglePanel("data-panel"));
    $("places-toggle").addEventListener("click", () => togglePanel("places-panel"));
    $("home-view").addEventListener("click", flyHome);
    $("zoom-in").addEventListener("click", () => { if (viewer) { const h = viewer.camera.positionCartographic.height; viewer.camera.zoomIn(Math.max(0, Math.min(h * .22, h - MIN_ZOOM_METERS))); } });
    $("zoom-out").addEventListener("click", () => { if (viewer) viewer.camera.zoomOut(Math.max(viewer.camera.positionCartographic.height * .22, .30)); });
    $("download-view").addEventListener("click", saveMapImage);
    $("about-toggle").addEventListener("click", () => $("notice-dialog").showModal());
    ui.routeMode.addEventListener("click", () => { toggleRouteMode(); openPanel("route-panel"); });
    $("close-route").addEventListener("click", () => {
      toggleRouteMode(false);
      if (routePoints.length) ui.routePanel.classList.add("hidden");
    });
    $("clear-route").addEventListener("click", clearRoute);
    ui.exportRoute.addEventListener("click", exportRouteGeoJSON);
    $("clear-selection").addEventListener("click", clearSelection);
    $("add-waypoint").addEventListener("click", () => { if (!selectedPoint) return; addRoutePoint(selectedPoint.lat, selectedPoint.lon); openPanel("route-panel"); toggleRouteMode(false); });
    $("retry-map").addEventListener("click", () => window.location.reload());
    $("search-panel").addEventListener("submit", (event) => { event.preventDefault(); window.clearTimeout(searchTimer); searchLocation($("location-search").value); });
    $("location-search").addEventListener("input", (event) => {
      window.clearTimeout(searchTimer);
      searchRequest++;
      const query = event.target.value.trim();
      if (query.length < 2) { closePanel("search-results"); return; }
      // Coordinates should only navigate on explicit submit.
      if (/^[-+\d.,;\s]+$/.test(query)) { closePanel("search-results"); return; }
      searchTimer = window.setTimeout(() => {
        if (!$("search-panel").classList.contains("hidden")) searchLocation(query);
      }, 300);
    });
    $("layer-filter").addEventListener("input", () => renderLayerCatalogue($("layer-filter").value));
    $("custom-layer-form").addEventListener("submit", addCustomLayer);
    document.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => closePanel(button.dataset.close)));
    const notice = $("notice-dialog");
    $("close-notice").addEventListener("click", () => notice.close());
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") { window.clearTimeout(searchTimer); searchRequest++; closeAllPanels(); }
      if (event.key === "/" && !event.ctrlKey && !event.metaKey && !event.altKey && !/^(INPUT|TEXTAREA|SELECT)$/.test(event.target.tagName)) { event.preventDefault(); openPanel("search-panel"); }
    });
    document.addEventListener("pointerdown", (event) => {
      if (event.target.closest(".floating-panel, .floating-search, .top-tools, .tool-rail, .zoom-tools")) return;
      closeAllPanels();
    });
  }

  function init() {
    wireEvents();
    renderDataSources();
    renderPlaces();
    renderLayerCatalogue();
    if (!window.Cesium) {
      showMapError("The globe library did not load", "The local Cesium library could not be loaded. Check the connection to this site and retry.", "/cesium/Cesium.js");
      return;
    }
    CesiumLib = window.Cesium;
    try {
      createMarsViewer();
    } catch (error) {
      console.error("NAM globe initialization failed:", error);
      showMapError("Mars could not be displayed", "The 3D globe did not initialize. The technical detail is shown below.", `${error.name || "Error"}: ${error.message || String(error)}`);
    }
  }

  document.addEventListener("DOMContentLoaded", init, { once: true });
})();

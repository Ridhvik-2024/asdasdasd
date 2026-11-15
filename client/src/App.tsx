import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Bookmark as BookmarkIcon,
  Camera,
  CloudLightning,
  Flag,
  FlaskConical,
  Layers,
  Ruler,
  X,
} from "lucide-react";
import { api, wsUrl } from "./lib/api";
import { normLon } from "./lib/marsMath";
import { fetchLivePerseveranceTraverse } from "./lib/nasaImagery";
import type {
  Bookmark,
  CameraState,
  Discovery,
  ElevationGridData,
  Flyover,
  GazetteerHit,
  LandingSite,
  LatLon,
  MeasureTool,
  Mission,
  PanelTab,
  Panorama,
  PresenceAgent,
  ProjectionMode,
  ScienceLayer,
  ShelterCandidate,
  SolarData,
  SpatialNode,
  StormResponsePlan,
  StormScenario,
  WaterCandidate,
  WsEventItem,
} from "./types/nam";
import { BookmarksPanel } from "./components/BookmarksPanel";
import { BottomBar } from "./components/BottomBar";
import { EnvironmentPanel } from "./components/EnvironmentPanel";
import { FlyoverBar } from "./components/FlyoverBar";
import { JevDrawer } from "./components/JevDrawer";
import { LayersPanel } from "./components/LayersPanel";
import { LocationCard } from "./components/LocationCard";
import { type LayerVisibility, MarsViewport, type PickedObject } from "./components/MarsViewport";
import { MeasurePanel } from "./components/MeasurePanel";
import { MissionsPanel } from "./components/MissionsPanel";
import { NasaMediaModal } from "./components/NasaMediaModal";
import { SciencePanel } from "./components/SciencePanel";
import { StreetViewModal } from "./components/StreetViewModal";
import { StreetViewPanel } from "./components/StreetViewPanel";
import { TopBar } from "./components/TopBar";
import { WalkViewModal } from "./components/WalkViewModal";

const RAIL_ITEMS: Array<{ id: PanelTab; label: string; icon: React.ReactNode }> = [
  { id: "layers", label: "Layers", icon: <Layers size={18} /> },
  { id: "measure", label: "Measure (12)", icon: <Ruler size={18} /> },
  { id: "streetview", label: "Street View", icon: <Camera size={18} /> },
  { id: "science", label: "Science", icon: <FlaskConical size={18} /> },
  { id: "missions", label: "Missions", icon: <Flag size={18} /> },
  { id: "environment", label: "Env & Ops", icon: <CloudLightning size={18} /> },
  { id: "bookmarks", label: "Bookmarks", icon: <BookmarkIcon size={18} /> },
];

export const App: React.FC = () => {
  // Navigation, projection & imagery state (defaults to LIVE NASA Viking Color + USGS SIM 3292 compare!)
  const [projection, setProjection] = useState<ProjectionMode>("globe");
  const [baseLayer, setBaseLayer] = useState("nasa-viking-color");
  const [overlayLayer, setOverlayLayer] = useState<string | null>(null);
  const [overlayOpacity, setOverlayOpacity] = useState(0.55);
  const [compareEnabled, setCompareEnabled] = useState(false);
  const [compareLayer, setCompareLayer] = useState("usgs-sim3292");
  const [exaggeration, setExaggeration] = useState(3.0);
  const [livePerseveranceTraverse, setLivePerseveranceTraverse] = useState<LatLon[]>([]);
  const [nasaModalTab, setNasaModalTab] = useState<"footage" | "raw" | "library" | "resources" | null>(null);

  // Camera & telemetry
  const [camera, setCamera] = useState<CameraState>({ lat: 14, lon: 112, altitudeKm: 5200 });
  const [cameraTarget, setCameraTarget] = useState<(CameraState & { nonce: number }) | null>(null);
  const [hoverTelemetry, setHoverTelemetry] = useState<{ lat: number | null; lon: number | null; elev: number | null }>({
    lat: null,
    lon: null,
    elev: null,
  });

  // Solar / Mars24 state
  const [solar, setSolar] = useState<SolarData | null>(null);
  const [solPlaying, setSolPlaying] = useState(false);

  // Panels, modals & contextual cards
  const [activeTab, setActiveTab] = useState<PanelTab | null>("layers");
  const [jevOpen, setJevOpen] = useState(false);
  const [locationFocus, setLocationFocus] = useState<{ lat: number; lon: number; title?: string } | null>(null);
  const [pickedObject, setPickedObject] = useState<PickedObject | null>(null);
  const [activeFlyover, setActiveFlyover] = useState<Flyover | null>(null);
  const [streetViewPano, setStreetViewPano] = useState<Panorama | null>(null);
  const [walkViewTarget, setWalkViewTarget] = useState<LatLon | null>(null);

  // Overlays visibility (shared across all 5 views)
  const [visibility, setVisibility] = useState<LayerVisibility>({
    landingSites: true,
    panoramas: true,
    traverses: true,
    discoveries: false,
    water: true,
    shelters: false,
    nodes: true,
    presence: true,
    storms: true,
    missions: true,
  });

  // Planetary datasets hydrated from backend
  const [elevationGrid, setElevationGrid] = useState<ElevationGridData | null>(null);
  const [layers, setLayers] = useState<ScienceLayer[]>([]);
  const [landingSites, setLandingSites] = useState<LandingSite[]>([]);
  const [panoramas, setPanoramas] = useState<Panorama[]>([]);
  const [discoveries, setDiscoveries] = useState<Discovery[]>([]);
  const [water, setWater] = useState<WaterCandidate[]>([]);
  const [shelters, setShelters] = useState<ShelterCandidate[]>([]);
  const [nodes, setNodes] = useState<SpatialNode[]>([]);
  const [presence, setPresence] = useState<PresenceAgent[]>([]);
  const [storms, setStorms] = useState<StormScenario[]>([]);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  const [flyovers, setFlyovers] = useState<Flyover[]>([]);

  // Interactive tool states
  const [measureTool, setMeasureTool] = useState<MeasureTool>("inspect");
  const [measurePoints, setMeasurePoints] = useState<LatLon[]>([]);
  const [measureRoute, setMeasureRoute] = useState<LatLon[]>([]);
  const [activeMissionId, setActiveMissionId] = useState<string | null>(null);
  const [placingStop, setPlacingStop] = useState(false);
  const [stormPlan, setStormPlan] = useState<StormResponsePlan | null>(null);

  // Realtime WS state & toast alerts
  const [wsConnected, setWsConnected] = useState(false);
  const [wsEvents, setWsEvents] = useState<WsEventItem[]>([]);
  const [toasts, setToasts] = useState<Array<{ id: number; text: string; kind?: "danger" | "info" }>>([]);

  const notify = useCallback((text: string, kind: "danger" | "info" = "info") => {
    const id = Date.now() + Math.random();
    setToasts((prev) => [...prev.slice(-3), { id, text, kind }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4500);
  }, []);

  const flyTo = useCallback((lat: number, lon: number, altitudeKm = 900) => {
    setCameraTarget({ lat, lon: normLon(lon), altitudeKm, nonce: Date.now() + Math.random() });
  }, []);

  // Refresh helpers
  const refreshMissions = useCallback(async () => {
    const r = await api.missions();
    setMissions(r.missions || []);
  }, []);

  const refreshStorms = useCallback(async () => {
    const r = await api.activeStorms();
    setStorms(r.active_simulations || []);
  }, []);

  const refreshNodes = useCallback(async () => {
    const r = await api.nodes();
    setNodes(r.nodes || []);
  }, []);

  const refreshPresence = useCallback(async () => {
    const r = await api.presence();
    setPresence(r.agents || []);
  }, []);

  const refreshBookmarks = useCallback(async () => {
    const r = await api.bookmarks();
    setBookmarks(r.bookmarks || []);
  }, []);

  // Hydrate all initial catalogs + restore ?share= link if present
  useEffect(() => {
    Promise.allSettled([
      api.elevationGrid(2).then(setElevationGrid),
      api.layers().then((r) => setLayers(r.layers || [])),
      api.sites().then((r) => setLandingSites(r.sites || [])),
      api.panoramas().then((r) => setPanoramas(r.panoramas || [])),
      api.discoveries().then((r) => setDiscoveries(r.discoveries || [])),
      api.water().then((r) => setWater(r.candidates || [])),
      api.shelters().then((r) => setShelters(r.shelters || [])),
      api.nodes().then((r) => setNodes(r.nodes || [])),
      api.presence().then((r) => setPresence(r.agents || [])),
      api.activeStorms().then((r) => setStorms(r.active_simulations || [])),
      api.missions().then((r) => setMissions(r.missions || [])),
      api.bookmarks().then((r) => setBookmarks(r.bookmarks || [])),
      api.flyovers().then((r) => setFlyovers(r.flyovers || [])),
      api.measureSolar(18.44, 77.45).then(setSolar),
      fetchLivePerseveranceTraverse().then((tr) => {
        if (tr && tr.points.length >= 2) {
          setLivePerseveranceTraverse(tr.points);
          notify(
            `Live NASA Perseverance traverse loaded${
              tr.totalDistanceKm ? ` (${tr.totalDistanceKm.toFixed(1)} km)` : ""
            } — mars.nasa.gov`
          );
        }
      }),
    ]);

    const params = new URLSearchParams(window.location.search);
    const sid = params.get("share");
    if (sid) {
      api
        .getShare(sid)
        .then((payload) => {
          const cam = payload.camera as Record<string, number> | undefined;
          if (cam && typeof cam.lat === "number" && typeof cam.lon === "number") {
            flyTo(cam.lat, cam.lon, cam.altitude_km || cam.altitudeKm || 1200);
          }
          if (typeof payload.mission_id === "string") {
            setActiveMissionId(payload.mission_id);
            setActiveTab("missions");
          }
          notify(`Restored shared Mars view: ${String(payload.name || sid)}`);
        })
        .catch(() => {});
    }
  }, [flyTo, notify]);

  // Sol Time-Lapse Animation loop (rotates subsolar longitude across Mars)
  useEffect(() => {
    if (!solPlaying) return;
    const id = window.setInterval(() => {
      setSolar((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          subsolar_lon: normLon(prev.subsolar_lon - 2.8),
          mtc_hours: (prev.mtc_hours + 0.186) % 24,
        };
      });
    }, 100);
    return () => window.clearInterval(id);
  }, [solPlaying]);

  // Real-Time WebSockets: /ws/events & /ws/presence
  const lastEventIdRef = useRef<number | null>(null);
  useEffect(() => {
    let closed = false;
    let evWs: WebSocket | null = null;
    let prWs: WebSocket | null = null;
    let retryTimer: number | null = null;

    const connect = () => {
      if (closed) return;
      const evPath = lastEventIdRef.current ? `/ws/events?since_id=${lastEventIdRef.current}` : "/ws/events";
      evWs = new WebSocket(wsUrl(evPath));
      evWs.onopen = () => setWsConnected(true);
      evWs.onclose = () => {
        setWsConnected(false);
        if (!closed) retryTimer = window.setTimeout(connect, 3500);
      };
      evWs.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data) as WsEventItem;
          if (typeof msg.id === "number") lastEventIdRef.current = msg.id;
          if (msg.type === "heartbeat" || msg.type === "welcome") return;
          setWsEvents((prev) => [msg, ...prev].slice(0, 60));
          if (msg.type === "storm_alert") {
            notify(`STORM ALERT: ${msg.scenario?.label || "Simulated Mars Storm [SIM]"}`, "danger");
            refreshStorms().catch(() => {});
          } else if (msg.type === "plan_change") {
            refreshMissions().catch(() => {});
          }
        } catch {
          // ignore
        }
      };

      prWs = new WebSocket(wsUrl("/ws/presence"));
      prWs.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "presence_update" && Array.isArray(msg.agents)) {
            setPresence(msg.agents);
          }
        } catch {
          // ignore
        }
      };
    };

    connect();
    return () => {
      closed = true;
      if (retryTimer) window.clearTimeout(retryTimer);
      evWs?.close();
      prWs?.close();
    };
  }, [notify, refreshMissions, refreshStorms]);

  // Execute JEV AI Globe Control Intents (fly_to, activate_layer)
  const executeJevIntent = useCallback(
    (intent: Record<string, unknown>) => {
      const action = String(intent.action || intent.type || "");
      if (action === "fly_to" && typeof intent.lat === "number" && typeof intent.lon === "number") {
        flyTo(intent.lat, intent.lon, Number(intent.altitude_km || 850));
        setLocationFocus({ lat: intent.lat, lon: intent.lon, title: String(intent.label || "") || undefined });
      } else if (action === "activate_layer" && typeof intent.layer_id === "string") {
        const lid = intent.layer_id;
        if (["mars-relief", "mdim21", "ctx-murray", "mola-color", "mola-shaded", "themis-day", "themis-night", "sim3292-geology", "swim-probability", "depth-to-ice"].includes(lid)) {
          setBaseLayer(lid);
        }
        if (lid === "water-candidates" || lid === "swim-probability") {
          setVisibility((v) => ({ ...v, water: true }));
        } else if (lid === "shelters") {
          setVisibility((v) => ({ ...v, shelters: true }));
        }
        notify(`JEV activated layer: ${lid}`);
      }
    },
    [flyTo, notify]
  );

  // One-click SEP Storm Drill (simulate X-class SEP + compute evacuation route + display on globe)
  const triggerSepDrill = async () => {
    try {
      const sc = await api.simulateStorm("sep", "X", camera.lat, camera.lon);
      await refreshStorms();
      const plan = await api.stormResponse(camera.lat, camera.lon, "X");
      setStormPlan(plan);
      setActiveTab("environment");
      setVisibility((v) => ({ ...v, water: true, shelters: true, storms: true }));
      flyTo(camera.lat, camera.lon, 1800);
      notify(`SEP DRILL ACTIVE: ${sc.label} · ${plan.stops.length}-stop evacuation plotted`, "danger");
    } catch (e) {
      notify(`SEP drill error: ${String(e)}`, "danger");
    }
  };

  // Terrain Click Handler (routes to measurement, mission stop placement, or location card)
  const handleTerrainClick = async (lat: number, lon: number) => {
    if (placingStop && activeMissionId) {
      try {
        await api.addMissionStop(activeMissionId, {
          lat,
          lon,
          activity: "waypoint",
          reason: "placed interactively on Mars globe",
        });
        await refreshMissions();
        notify(`Added stop at ${lat.toFixed(2)}°, ${lon.toFixed(2)}°E`);
      } catch (e) {
        notify(`Failed adding stop: ${String(e)}`, "danger");
      }
      return;
    }

    if (activeTab === "measure" && !["inspect", "dem", "stl"].includes(measureTool)) {
      setMeasurePoints((prev) => [...prev, { lat, lon }]);
      return;
    }

    setPickedObject(null);
    setLocationFocus({ lat, lon });
  };

  const handleObjectPick = (obj: PickedObject) => {
    setPickedObject(obj);
    if (obj.kind === "panorama" && obj.data) {
      setStreetViewPano(obj.data as Panorama);
      return;
    }
    setLocationFocus({ lat: obj.lat, lon: obj.lon, title: obj.name });
  };

  const handleSelectSearchHit = (hit: GazetteerHit) => {
    flyTo(hit.lat, hit.lon, hit.diameter_km ? Math.max(380, hit.diameter_km * 3) : 650);
    setLocationFocus({ lat: hit.lat, lon: hit.lon, title: hit.name });
  };

  const handleShareCamera = async (): Promise<string | null> => {
    try {
      const res = await api.createShare(locationFocus?.title || "NAM Mars View", {
        lat: camera.lat,
        lon: camera.lon,
        altitudeKm: camera.altitudeKm,
        projection,
        baseLayer,
      });
      const full = `${window.location.origin}/?share=${res.share_id}`;
      navigator.clipboard?.writeText(full).catch(() => {});
      notify(`Camera link copied: ?share=${res.share_id}`);
      return full;
    } catch {
      return null;
    }
  };

  const handleSavePlanAsMission = async (plan: StormResponsePlan) => {
    const m = await api.createMission({
      type: "evacuation",
      name: `SEP Evac (${plan.plan_id.slice(-4)})`,
      objective: "Emergency storm-response evacuation via water cache & shelter [SIM]",
      stops: plan.stops.map((s) => ({
        lat: s.lat,
        lon: s.lon,
        activity: s.activity,
        reason: s.reason,
      })),
    });
    if (plan.stops.length >= 2) {
      const first = plan.origin;
      const last = plan.destination;
      await api.attachMissionRoute(m.id, first.lat, first.lon, last.lat, last.lon, "speed");
    }
    await refreshMissions();
    setActiveMissionId(m.id);
    setActiveTab("missions");
    notify(`Saved evacuation plan as mission "${m.name}"`);
  };

  // Mode banner for viewport cursor guidance
  const measureModeLabel = placingStop
    ? "Mission Stop Placement"
    : activeTab === "measure" && !["inspect", "dem", "stl"].includes(measureTool)
    ? `Measure: ${measureTool}`
    : null;

  const visibleLayerIds = [
    baseLayer,
    ...(overlayLayer ? [overlayLayer] : []),
    ...Object.entries(visibility)
      .filter(([, on]) => on)
      .map(([k]) => k),
  ];

  return (
    <div className="app-shell">
      {/* Interactive 5-Projection Mars Globe / Map Canvas */}
      <MarsViewport
        projection={projection}
        baseLayer={baseLayer}
        overlayLayer={overlayLayer}
        overlayOpacity={overlayOpacity}
        compareEnabled={compareEnabled}
        compareLayer={compareLayer}
        exaggeration={exaggeration}
        cameraTarget={cameraTarget}
        solar={solar}
        elevationGrid={elevationGrid}
        visibility={visibility}
        landingSites={landingSites}
        panoramas={panoramas}
        discoveries={discoveries}
        water={water}
        shelters={shelters}
        nodes={nodes}
        presence={presence}
        storms={storms}
        missions={missions}
        activeMissionId={activeMissionId}
        stormPlan={stormPlan}
        measurePoints={measurePoints}
        measureRoute={measureRoute}
        measureModeLabel={measureModeLabel}
        livePerseveranceTraverse={livePerseveranceTraverse}
        onCameraChange={setCamera}
        onHoverCoords={(lat, lon, elev) => setHoverTelemetry({ lat, lon, elev })}
        onTerrainClick={handleTerrainClick}
        onObjectPick={handleObjectPick}
      />

      {/* Top Navigation & Global Search Bar */}
      <TopBar
        projection={projection}
        onProjectionChange={setProjection}
        onSelectHit={handleSelectSearchHit}
        flyovers={flyovers}
        onStartFlyover={(f) => {
          setProjection("globe");
          setActiveFlyover(f);
        }}
        onOpenStreetView={() => {
          if (panoramas[0]) setStreetViewPano(panoramas[0]);
          else setActiveTab("streetview");
        }}
        onOpenWalkView={() => setWalkViewTarget({ lat: camera.lat, lon: camera.lon })}
        onOpenNasaHub={(t) => setNasaModalTab(t || "footage")}
        jevOpen={jevOpen}
        onToggleJev={() => setJevOpen((v) => !v)}
        onTriggerSepDrill={triggerSepDrill}
        onShareCamera={handleShareCamera}
        wsConnected={wsConnected}
        activeStormCount={storms.length}
      />

      {/* Live Toast Notifications */}
      {toasts.length > 0 && (
        <div className="toast-stack">
          {toasts.map((t) => (
            <div
              key={t.id}
              className="toast glass"
              style={{
                borderColor: t.kind === "danger" ? "rgba(239,68,68,0.65)" : "rgba(56,189,248,0.45)",
                color: t.kind === "danger" ? "#fecaca" : "#e0f2fe",
              }}
            >
              {t.text}
            </div>
          ))}
        </div>
      )}

      {/* Left Tool Rail */}
      <nav className="left-rail glass" aria-label="Workspace Tools">
        {RAIL_ITEMS.map((item) => (
          <button
            key={item.id}
            className={`rail-btn ${activeTab === item.id ? "active" : ""}`}
            title={item.label}
            onClick={() => {
              setPlacingStop(false);
              setActiveTab((cur) => (cur === item.id ? null : item.id));
            }}
          >
            {item.icon}
          </button>
        ))}
      </nav>

      {/* Left Expandable Workspace Drawer */}
      {activeTab && (
        <section className="left-drawer glass">
          <div className="drawer-head">
            <span>{RAIL_ITEMS.find((r) => r.id === activeTab)?.label}</span>
            <button
              className="btn btn-xs btn-ghost"
              onClick={() => {
                setPlacingStop(false);
                setActiveTab(null);
              }}
              aria-label="Close drawer"
            >
              <X size={14} />
            </button>
          </div>

          <div className="drawer-body">
            {activeTab === "layers" && (
              <LayersPanel
                layers={layers}
                baseLayer={baseLayer}
                onBaseLayerChange={setBaseLayer}
                overlayLayer={overlayLayer}
                onOverlayLayerChange={setOverlayLayer}
                overlayOpacity={overlayOpacity}
                onOverlayOpacityChange={setOverlayOpacity}
                compareEnabled={compareEnabled}
                onCompareEnabledChange={setCompareEnabled}
                compareLayer={compareLayer}
                onCompareLayerChange={setCompareLayer}
                visibility={visibility}
                onVisibilityChange={(patch) => setVisibility((v) => ({ ...v, ...patch }))}
                onZoomJezeroHiRes={() => {
                  setBaseLayer("nasa-viking-color");
                  setProjection("flat");
                  setTimeout(() => flyTo(18.4447, 77.4508, 25), 50);
                  notify("Zooming into Jezero Crater — streaming live NASA MRO CTX (6m) & HiRISE (25cm) tiles");
                }}
                onOpenNasaHub={(t) => setNasaModalTab(t)}
              />
            )}

            {activeTab === "measure" && (
              <MeasurePanel
                activeTool={measureTool}
                onToolChange={(t) => {
                  setMeasureTool(t);
                  setMeasurePoints([]);
                  setMeasureRoute([]);
                }}
                points={measurePoints}
                onClearPoints={() => {
                  setMeasurePoints([]);
                  setMeasureRoute([]);
                }}
                onSetRouteLine={setMeasureRoute}
                camera={camera}
                solar={solar}
                onRefreshSolar={(la, lo) => {
                  api.measureSolar(la, lo).then(setSolar).catch(() => {});
                }}
              />
            )}

            {activeTab === "streetview" && (
              <StreetViewPanel
                panoramas={panoramas}
                camera={camera}
                onOpenPanorama={(p) => setStreetViewPano(p)}
                onOpenWalkView={(la, lo) => setWalkViewTarget({ lat: la, lon: lo })}
                onFlyTo={flyTo}
                onOpenNasaHub={(t) => setNasaModalTab(t)}
              />
            )}

            {activeTab === "science" && (
              <SciencePanel
                discoveries={discoveries}
                landingSites={landingSites}
                onFlyTo={(la, lo, alt) => {
                  flyTo(la, lo, alt);
                  setLocationFocus({ lat: la, lon: lo });
                }}
              />
            )}

            {activeTab === "missions" && (
              <MissionsPanel
                missions={missions}
                activeMissionId={activeMissionId}
                placingStop={placingStop}
                onTogglePlacingStop={() => setPlacingStop((v) => !v)}
                onSelectMission={(id) => {
                  setPlacingStop(false);
                  setActiveMissionId(id);
                }}
                onRefresh={refreshMissions}
                onFlyTo={flyTo}
                onNotify={notify}
              />
            )}

            {activeTab === "environment" && (
              <EnvironmentPanel
                camera={camera}
                water={water}
                shelters={shelters}
                nodes={nodes}
                presence={presence}
                storms={storms}
                stormPlan={stormPlan}
                wsEvents={wsEvents}
                onRefreshStorms={refreshStorms}
                onRefreshNodes={refreshNodes}
                onRefreshPresence={refreshPresence}
                onSetStormPlan={setStormPlan}
                onSavePlanAsMission={handleSavePlanAsMission}
                onFlyTo={flyTo}
                onNotify={notify}
              />
            )}

            {activeTab === "bookmarks" && (
              <BookmarksPanel
                bookmarks={bookmarks}
                camera={camera}
                onAdd={async (name, lat, lon, note) => {
                  await api.addBookmark(name, lat, lon, note, {
                    altitudeKm: camera.altitudeKm,
                    projection,
                    baseLayer,
                  });
                  await refreshBookmarks();
                  notify(`Saved bookmark "${name}"`);
                }}
                onDelete={async (id) => {
                  await api.deleteBookmark(id);
                  await refreshBookmarks();
                }}
                onFlyTo={flyTo}
                onShareCamera={handleShareCamera}
              />
            )}
          </div>
        </section>
      )}

      {/* Contextual Location Card (shown when JEV drawer is closed) */}
      {locationFocus && !jevOpen && (
        <LocationCard
          lat={locationFocus.lat}
          lon={locationFocus.lon}
          title={locationFocus.title}
          onClose={() => setLocationFocus(null)}
          onEnterStreetView={(pid) => {
            const p = panoramas.find((x) => x.id === pid) || panoramas[0];
            if (p) setStreetViewPano(p);
          }}
          onEnterWalkView={(la, lo) => setWalkViewTarget({ lat: la, lon: lo })}
          onBookmark={async (name, la, lo) => {
            await api.addBookmark(name, la, lo, "", { altitudeKm: camera.altitudeKm });
            await refreshBookmarks();
            notify(`Bookmarked "${name}"`);
          }}
          onFlyTo={flyTo}
        />
      )}

      {/* JEV AI Planetary Assistant Drawer */}
      {jevOpen && (
        <JevDrawer
          camera={camera}
          visibleLayers={visibleLayerIds}
          pickedObject={pickedObject}
          onExecuteIntent={executeJevIntent}
          onClose={() => setJevOpen(false)}
        />
      )}

      {/* Active Landmark Flyover Tour HUD */}
      {activeFlyover && (
        <FlyoverBar
          flyover={activeFlyover}
          onMoveTo={(la, lo, alt) => flyTo(la, lo, alt)}
          onClose={() => setActiveFlyover(null)}
        />
      )}

      {/* Bottom Telemetry & Exaggeration Bar */}
      <BottomBar
        hoverLat={hoverTelemetry.lat}
        hoverLon={hoverTelemetry.lon}
        hoverElevM={hoverTelemetry.elev}
        exaggeration={exaggeration}
        onExaggerationChange={setExaggeration}
        solar={solar}
        solPlaying={solPlaying}
        onToggleSolPlay={() => setSolPlaying((p) => !p)}
        baseLayer={baseLayer}
      />

      {/* Full-Screen Mars Street View 360° Modal */}
      {streetViewPano && (
        <StreetViewModal
          panorama={streetViewPano}
          allPanoramas={panoramas}
          onSelectPanorama={setStreetViewPano}
          onReturnToOrbit={(la, lo) => {
            setStreetViewPano(null);
            setProjection("globe");
            flyTo(la, lo, 320);
            setLocationFocus({ lat: la, lon: lo });
          }}
          onClose={() => setStreetViewPano(null)}
        />
      )}

      {/* Full-Screen First-Person 3D Walk View Modal */}
      {walkViewTarget && (
        <WalkViewModal
          initialLat={walkViewTarget.lat}
          initialLon={walkViewTarget.lon}
          onOpenPanorama={(p) => {
            setWalkViewTarget(null);
            setStreetViewPano(p);
          }}
          onClose={() => setWalkViewTarget(null)}
        />
      )}

      {/* Full-Screen NASA Mars Footage, Live 1M+ Raw Rover Gallery & USGS Geologic Map Modal */}
      {nasaModalTab && (
        <NasaMediaModal
          initialTab={nasaModalTab}
          onFlyTo={(la, lo, alt) => {
            flyTo(la, lo, alt ?? 450);
            setLocationFocus({ lat: la, lon: lo });
          }}
          onActivateBasemap={(bid) => {
            setBaseLayer(bid);
            notify(`Activated live orbital layer: ${bid}`);
          }}
          onClose={() => setNasaModalTab(null)}
        />
      )}
    </div>
  );
};

import type {
  Bookmark,
  Discovery,
  ElevationGridData,
  Flyover,
  GazetteerHit,
  JevToolTrace,
  LandingSite,
  LatLon,
  Mission,
  Panorama,
  PresenceAgent,
  ScienceLayer,
  ShelterCandidate,
  SolarData,
  SpatialNode,
  StormResponsePlan,
  StormScenario,
  WaterCandidate,
} from "../types/nam";

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
    } catch {
      // ignore non-json error body
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

const jsonPost = <T>(url: string, body: unknown) =>
  req<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

const jsonPut = <T>(url: string, body: unknown) =>
  req<T>(url, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const api = {
  // Health & connectors
  health: () => req<Record<string, unknown>>("/health"),
  connectors: () => req<{ connectors: Array<Record<string, unknown>> }>("/connectors/status"),
  imageryLadder: () => req<{ rungs: Array<Record<string, unknown>> }>("/imagery/ladder"),

  // Gazetteer, Location Card, Bookmarks, Share
  search: (q: string, limit = 14) =>
    req<{ query: string; latency_ms: number; count: number; results: GazetteerHit[] }>(
      `/search?q=${encodeURIComponent(q)}&limit=${limit}`
    ),
  locationCard: (lat: number, lon: number) =>
    req<Record<string, unknown>>(`/location/card?lat=${lat}&lon=${lon}`),
  bookmarks: async (): Promise<{ count: number; bookmarks: Bookmark[] }> => {
    const raw = await req<Bookmark[] | { bookmarks: Bookmark[] }>("/bookmarks");
    const list = Array.isArray(raw) ? raw : raw.bookmarks || [];
    return { count: list.length, bookmarks: list };
  },
  addBookmark: (name: string, lat: number, lon: number, note = "", camera: Record<string, unknown> = {}) =>
    jsonPost<Bookmark>("/bookmarks", { name, lat, lon, camera: { ...camera, note } }),
  deleteBookmark: (bid: string | number) =>
    req<{ deleted: boolean }>(`/bookmarks/${encodeURIComponent(String(bid))}`, { method: "DELETE" }),
  createShare: (name: string, camera: Record<string, unknown>) =>
    jsonPost<{ share_id: string; url: string }>("/share", { name, camera }),
  getShare: (sid: string) => req<Record<string, unknown>>(`/share/${encodeURIComponent(sid)}`),

  // Terrain & Flyovers
  elevation: (lat: number, lon: number) =>
    req<{ elevation_m: number; slope_deg: number; aspect_deg: number; provenance: Record<string, unknown> }>(
      `/elevation?lat=${lat}&lon=${lon}`
    ),
  elevationGrid: (step = 2) => req<ElevationGridData>(`/terrain/elevation_grid?step=${step}`),
  elevationProfile: (points: LatLon[], samples = 140) =>
    jsonPost<{
      total_km: number;
      points: Array<{ dist_km: number; lat: number; lon: number; elev_m: number }>;
      elevation_gain_m: number;
      elevation_loss_m: number;
      min_elev_m: number;
      max_elev_m: number;
      provenance: Record<string, unknown>;
    }>("/elevation/profile", { points, samples }),
  terrainHazard: (min_lat: number, min_lon: number, max_lat: number, max_lon: number) =>
    req<Record<string, unknown>>(
      `/terrain/hazard?min_lat=${min_lat}&min_lon=${min_lon}&max_lat=${max_lat}&max_lon=${max_lon}`
    ),
  flyovers: () => req<{ count: number; flyovers: Flyover[] }>("/terrain/flyovers"),

  // Measurements (12-tool Mars Trek parity)
  measureStraight: (from_lat: number, from_lon: number, to_lat: number, to_lon: number) =>
    jsonPost<Record<string, unknown>>("/measure/distance", {
      points: [
        { lat: from_lat, lon: from_lon },
        { lat: to_lat, lon: to_lon },
      ],
    }),
  measurePath: (points: LatLon[]) => jsonPost<Record<string, unknown>>("/measure/path_distance", { points }),
  measureRoute: (from_lat: number, from_lon: number, to_lat: number, to_lon: number, preset = "balanced") =>
    jsonPost<{
      path_preview?: LatLon[];
      path?: LatLon[];
      length_km?: number;
      max_slope_deg?: number;
      provenance: Record<string, unknown>;
    }>("/measure/route_distance", { from_lat, from_lon, to_lat, to_lon, preset }),
  measureCrater: (rim_a_lat: number, rim_a_lon: number, rim_b_lat: number, rim_b_lon: number) =>
    jsonPost<Record<string, unknown>>("/measure/crater", {
      rim_a: { lat: rim_a_lat, lon: rim_a_lon },
      rim_b: { lat: rim_b_lat, lon: rim_b_lon },
    }),
  measureArea: (polygon: LatLon[]) => jsonPost<Record<string, unknown>>("/measure/area", { polygon }),
  measureElevDiff: (from_lat: number, from_lon: number, to_lat: number, to_lon: number) =>
    jsonPost<Record<string, unknown>>("/measure/elevation_difference", {
      a: { lat: from_lat, lon: from_lon },
      b: { lat: to_lat, lon: to_lon },
    }),
  measureSolar: async (lat: number, lon: number, timestamp_utc?: string): Promise<SolarData> => {
    const raw = await jsonPost<{
      subsolar: { lat: number; lon: number; ls_deg: number; msd: number; mtc_hours: number };
      sun_elevation_deg: number;
      sun_azimuth_deg: number;
      provenance: Record<string, unknown>;
    }>("/measure/solar", {
      lat,
      lon,
      iso_time: timestamp_utc || new Date().toISOString(),
    });
    return {
      mars_sol_date: raw.subsolar.msd,
      ls_deg: raw.subsolar.ls_deg,
      mtc_hours: raw.subsolar.mtc_hours,
      subsolar_lat: raw.subsolar.lat,
      subsolar_lon: raw.subsolar.lon,
      solar_elevation_deg: raw.sun_elevation_deg,
      solar_azimuth_deg: raw.sun_azimuth_deg,
      daylight: raw.sun_elevation_deg > 0,
      provenance: raw.provenance,
    };
  },
  downloadDemUrl: (min_lat: number, min_lon: number, max_lat: number, max_lon: number, fmt: string) =>
    `/measure/terrain_download?min_lat=${min_lat}&min_lon=${min_lon}&max_lat=${max_lat}&max_lon=${max_lon}&format=${fmt}`,
  downloadStlBlob: async (lat: number, lon: number, radius_km: number, vertical_scale: number, n = 72) => {
    const res = await fetch("/measure/stl", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lat, lon, radius_km, vertical_scale, n }),
    });
    if (!res.ok) throw new Error(`STL export failed (${res.status})`);
    return res.blob();
  },

  // Science Explorer & Catalogs
  layers: () => req<{ count: number; layers: ScienceLayer[] }>("/layers"),
  discoveries: (params?: { q?: string; instrument?: string; lat?: number; lon?: number; radius_km?: number }) => {
    const sp = new URLSearchParams();
    if (params?.q) sp.set("q", params.q);
    if (params?.instrument) sp.set("instrument", params.instrument);
    if (params?.lat !== undefined && params?.lon !== undefined) {
      sp.set("lat", String(params.lat));
      sp.set("lon", String(params.lon));
      if (params.radius_km) sp.set("radius_km", String(params.radius_km));
    }
    return req<{ count: number; discoveries: Discovery[] }>(`/discoveries?${sp.toString()}`);
  },
  sites: () => req<{ sites: LandingSite[] }>("/sites"),
  compareSites: (ids: string[]) =>
    req<{ comparison: Array<Record<string, unknown>>; provenance: Record<string, unknown> }>(
      `/sites/compare?ids=${encodeURIComponent(ids.join(","))}`
    ),
  datasets: (q?: string) =>
    req<{ count: number; datasets: Array<Record<string, unknown>> }>(
      `/datasets${q ? `?q=${encodeURIComponent(q)}` : ""}`
    ),
  orbiters: () => req<{ count: number; orbiters: Array<Record<string, unknown>> }>("/science/orbiters"),
  instruments: () => req<{ count: number; instruments: Array<Record<string, unknown>> }>("/science/instruments"),
  spectralTargets: () =>
    req<{ count: number; spectral_targets: Array<Record<string, unknown>> }>("/science/spectral_targets"),
  unavailableSources: () =>
    req<{ count: number; unavailable_sources: Array<Record<string, unknown>> }>("/science/unavailable_sources"),

  // Street View & Walk View
  panoramas: (rover?: string) =>
    req<{ count: number; panoramas: Panorama[] }>(
      `/panoramas${rover ? `?rover=${encodeURIComponent(rover)}` : ""}`
    ),
  panoramaDetail: (pid: string) =>
    req<{
      panorama: Panorama;
      adjacent_observation_points: Array<{ id: string; title: string; bearing_deg: number; distance_km: number }>;
    }>(`/panoramas/${encodeURIComponent(pid)}`),
  traverses: () => req<{ rovers: Array<{ rover: string; points: number }> }>("/traverses"),
  traverse: (rover: string) => req<{ rover: string; points: Panorama[] }>(`/traverses/${encodeURIComponent(rover)}`),
  imageryLinkage: (lat: number, lon: number) =>
    req<Record<string, unknown>>(`/imagery/linkage?lat=${lat}&lon=${lon}`),
  compareRoverHistory: (rover: string, a?: string, b?: string) => {
    const sp = new URLSearchParams();
    if (a) sp.set("a", a);
    if (b) sp.set("b", b);
    return req<{
      rover: string;
      earlier: Panorama;
      later: Panorama;
      delta: { sol_delta: number | null; separation_km: number; bearing_deg: number; heading_delta_deg: number };
    }>(`/sites/${encodeURIComponent(rover)}/compare?${sp.toString()}`);
  },
  rawImages: (rover = "perseverance", limit = 12) =>
    req<Record<string, unknown>>(`/panoramas/raw?rover=${encodeURIComponent(rover)}&limit=${limit}`),
  walkviewPovs: () => req<{ count: number; povs: Array<Record<string, unknown>> }>("/walkview/pov/library"),
  walkviewNearestPov: (lat: number, lon: number) =>
    req<{ nearest_pov: Record<string, unknown> }>(`/walkview/pov?lat=${lat}&lon=${lon}`),
  walkviewPatch: (lat: number, lon: number, radius_km = 2.0, n = 48) =>
    req<{
      center: LatLon;
      radius_km: number;
      n: number;
      cell_size_m: number;
      vertices_local_m: [number, number, number][];
      indices: number[];
      base_elev_m: number;
      provenance: Record<string, unknown>;
    }>(`/walkview/patch?lat=${lat}&lon=${lon}&radius_km=${radius_km}&n=${n}`),
  walkviewPhotos: async (lat: number, lon: number, heading_deg = 0) => {
    const r = await req<{ imagery?: Array<Panorama & { heading_diff_deg?: number }>; matched_photographs?: Array<Panorama & { heading_diff_deg?: number }> }>(
      `/walkview/imagery?lat=${lat}&lon=${lon}&heading_deg=${heading_deg}`
    );
    return {
      heading_deg,
      matched_photographs: r.imagery || r.matched_photographs || [],
    };
  },

  // Missions
  missions: () => req<{ count: number; missions: Mission[] }>("/missions"),
  createMission: (payload: { type: string; name: string; objective: string; stops: Array<Record<string, unknown>> }) =>
    jsonPost<Mission>("/missions", payload),
  addMissionStop: (mid: string, stop: { lat: number; lon: number; activity: string; reason: string }) =>
    jsonPost<Mission>(`/missions/${encodeURIComponent(mid)}/stops`, stop),
  attachMissionRoute: (
    mid: string,
    from_lat: number,
    from_lon: number,
    to_lat: number,
    to_lon: number,
    preset = "balanced"
  ) =>
    jsonPost<Record<string, unknown>>(`/missions/${encodeURIComponent(mid)}/route`, {
      from_lat,
      from_lon,
      to_lat,
      to_lon,
      preset,
    }),
  optimizeMission: (mid: string, preset = "balanced") =>
    jsonPost<Mission>(`/missions/${encodeURIComponent(mid)}/optimize`, { preset }),
  missionProfile: (mid: string, speed_km_sol = 12, shielding = "rover") =>
    req<{
      mission_id: string;
      profile: {
        total_km: number;
        points: Array<{ dist_km: number; lat: number; lon: number; elev_m: number }>;
        elevation_gain_m: number;
        elevation_loss_m: number;
      };
      slope_summary: { mean_slope_deg: number; max_slope_deg: number };
      radiation: { total_msv: number; gcr_total_msv: number; sep_total_msv: number; total_duration_sols: number };
    }>(`/missions/${encodeURIComponent(mid)}/profile?speed_km_sol=${speed_km_sol}&shielding=${shielding}`),
  shareMission: (mid: string) =>
    jsonPost<{ share_id: string; url: string }>(`/missions/${encodeURIComponent(mid)}/share`, {}),
  updateMissionNotes: (mid: string, note: string) =>
    jsonPut<Mission>(`/missions/${encodeURIComponent(mid)}/notes`, { note }),
  deleteMission: (mid: string) =>
    req<{ deleted: boolean }>(`/missions/${encodeURIComponent(mid)}`, { method: "DELETE" }),

  // Environment, Resources, Nodes, Presence
  radiation: (lat: number, lon: number, duration_sols = 1, shielding = "suit", storm_id?: string) =>
    req<Record<string, unknown>>(
      `/environment/radiation?lat=${lat}&lon=${lon}&duration_sols=${duration_sols}&shielding=${shielding}${
        storm_id ? `&storm_id=${encodeURIComponent(storm_id)}` : ""
      }`
    ),
  radiationPath: (points: LatLon[], speed_km_sol = 12, shielding = "suit", storm_id?: string) =>
    jsonPost<Record<string, unknown>>("/environment/radiation/path", {
      points,
      speed_km_sol,
      shielding,
      storm_id: storm_id || null,
    }),
  stormCatalog: () => req<{ catalog: Array<Record<string, unknown>> }>("/environment/storms"),
  activeStorms: () => req<{ active_simulations: StormScenario[] }>("/environment/storms/active"),
  simulateStorm: (kind: "dust" | "sep", scale_or_class: string, lat?: number, lon?: number) =>
    jsonPost<StormScenario>("/environment/storms/simulate", {
      kind,
      scale_or_class,
      lat: lat ?? null,
      lon: lon ?? null,
      broadcast: true,
    }),
  deleteStorm: (sid: string) =>
    req<{ deleted: string }>(`/environment/storms/${encodeURIComponent(sid)}`, { method: "DELETE" }),
  stormResponse: (lat: number, lon: number, severity = "X", destination?: LatLon) =>
    jsonPost<StormResponsePlan>("/environment/storm_response", {
      lat,
      lon,
      severity,
      destination: destination ?? null,
    }),
  water: (certainty?: string) =>
    req<{ count: number; candidates: WaterCandidate[] }>(
      `/water${certainty ? `?certainty=${certainty}` : ""}`
    ),
  shelters: () => req<{ count: number; shelters: ShelterCandidate[] }>("/shelters"),
  nodes: () => req<{ count: number; nodes: SpatialNode[] }>("/nodes"),
  createNode: (payload: { type: string; name: string; lat: number; lon: number; props?: Record<string, unknown> }) =>
    jsonPost<SpatialNode>("/nodes", payload),
  deleteNode: (nid: string) => req<{ deleted: boolean }>(`/nodes/${encodeURIComponent(nid)}`, { method: "DELETE" }),
  presence: () => req<{ agents: PresenceAgent[] }>("/presence/agents"),
  tickPresence: (step_sols = 0.25) =>
    jsonPost<{ agents: PresenceAgent[] }>(`/presence/tick?step_sols=${step_sols}`, {}),

  // JEV AI Engine
  jevTools: () => req<{ count: number; tools: Array<Record<string, unknown>> }>("/jev/tools"),
  jevExamples: () => req<{ commands: string[] }>("/jev/examples"),
  jevExplain: (camera: { lat: number; lon: number; altitude_km?: number }, visible_layers: string[], picked?: Record<string, unknown> | null) =>
    jsonPost<Record<string, unknown>>("/jev/explain", {
      map_context: {
        center: { lat: camera.lat, lon: camera.lon },
        altitude_km: camera.altitude_km,
        active_layers: visible_layers,
        picked: picked ?? null,
      },
    }),

  /** Stream JEV SSE chat response (parses `data: {"type": ...}` protocol) */
  async jevChatStream(
    message: string,
    context: { camera: { lat: number; lon: number; altitudeKm?: number }; visible_layers: string[]; picked?: Record<string, unknown> | null },
    callbacks: {
      onToolStart?: (trace: JevToolTrace) => void;
      onToolEnd?: (trace: JevToolTrace) => void;
      onToken?: (chunk: string) => void;
      onIntent?: (intent: Record<string, unknown>) => void;
      onDone?: (payload: Record<string, unknown>) => void;
    }
  ): Promise<void> {
    const res = await fetch("/jev/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        map_context: {
          center: { lat: context.camera.lat, lon: context.camera.lon },
          altitude_km: context.camera.altitudeKm,
          active_layers: context.visible_layers,
          picked: context.picked ?? null,
        },
      }),
    });
    if (!res.ok || !res.body) {
      throw new Error(`JEV chat failed (${res.status})`);
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    const handlePayload = (dataStr: string) => {
      if (!dataStr) return;
      try {
        const data = JSON.parse(dataStr);
        const t = data.type;
        if (t === "tool_start") {
          callbacks.onToolStart?.({ id: data.id || `${data.tool}-${Date.now()}`, tool: data.tool, args: data.args || {} });
        } else if (t === "tool_result" || t === "tool_end") {
          callbacks.onToolEnd?.({
            id: data.id,
            tool: data.tool,
            args: {},
            ok: data.ok,
            error: data.error ? String(data.error) : undefined,
          });
        } else if (t === "delta" || t === "token") {
          callbacks.onToken?.(data.text || "");
        } else if (t === "done") {
          if (Array.isArray(data.intents)) {
            for (const intent of data.intents) {
              callbacks.onIntent?.(intent);
            }
          }
          callbacks.onDone?.(data);
        }
      } catch {
        // ignore malformed chunk
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop() || "";
      for (const raw of lines) {
        const line = raw.trimEnd();
        if (line.startsWith("data:")) {
          handlePayload(line.slice(5).trim());
        }
      }
    }
  },
};

export function wsUrl(path: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${path}`;
}

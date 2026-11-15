export type ProjectionMode = "globe" | "flat" | "north-polar" | "south-polar" | "columbus";

export type PanelTab =
  | "layers"
  | "measure"
  | "streetview"
  | "science"
  | "missions"
  | "environment"
  | "bookmarks";

export type MeasureTool =
  | "inspect"
  | "straight"
  | "path"
  | "route"
  | "profile"
  | "crater"
  | "area"
  | "slope"
  | "elev_diff"
  | "solar"
  | "dem"
  | "stl";

export interface LatLon {
  lat: number;
  lon: number;
}

export interface CameraState {
  lat: number;
  lon: number;
  altitudeKm: number;
  headingDeg?: number;
  pitchDeg?: number;
}

export interface Provenance {
  source?: string;
  mission?: string;
  instrument?: string;
  resolution?: string;
  date?: string;
  url?: string;
  attribution?: string;
  note?: string;
  sim?: boolean;
}

export interface GazetteerHit {
  id?: string;
  name?: string;
  type?: string;
  kind?: string;
  mission?: string;
  lat: number;
  lon: number;
  diameter_km?: number | null;
  note?: string;
  src?: string;
  score?: number;
  distance_km?: number;
  date?: string;
}

export interface ScienceLayer {
  id: string;
  title: string;
  category: string;
  res_m: number | null;
  source: string;
  attribution: string;
  url?: string;
  legend: string;
}

export interface LandingSite {
  id: string;
  name: string;
  mission: string;
  kind: string;
  lat: number;
  lon: number;
  date: string;
  traverse_km?: number;
  src: string;
}

export interface Panorama {
  id: string;
  rover: string;
  sol: number | null;
  title: string;
  lat: number;
  lon: number;
  heading_deg: number;
  credit: string;
  source_url: string;
  pose_confidence: string;
  resolution_note: string;
  date: string;
  distance_km?: number;
}

export interface Discovery {
  id: string;
  title: string;
  lat: number;
  lon: number;
  mission: string;
  instrument: string;
  summary: string;
  evidence: { citation: string; url: string | null };
  tags: string[];
  distance_km?: number;
}

export interface WaterCandidate {
  id: string;
  name: string;
  lat: number;
  lon: number;
  certainty: "A" | "B" | "C";
  depth_to_ice_m: [number, number];
  stability?: string;
  note: string;
  src: string;
  distance_km?: number;
}

export interface ShelterCandidate {
  id: string;
  name: string;
  kind: string;
  lat: number;
  lon: number;
  shielding: number;
  thermal: number;
  access: number;
  composite_index: number;
  note: string;
  src: string;
  distance_km?: number;
}

export interface SpatialNode {
  id: string;
  type: string;
  name: string;
  lat: number;
  lon: number;
  props: Record<string, unknown>;
}

export interface PresenceAgent {
  id: string;
  name: string;
  kind: "crew" | "rover" | "habitat";
  role: string;
  lat: number;
  lon: number;
  speed_km_sol: number;
  sim?: boolean;
}

export interface StormScenario {
  scenario_id: string;
  kind: "dust" | "sep";
  label: string;
  scale?: string;
  severity?: string;
  severity_class?: string;
  tau_peak?: number;
  affected_radius_km?: number;
  duration_sols?: number;
  peak_dose_rate_msv_per_sol?: number;
  origin?: { lat: number | null; lon: number | null };
  effects?: string[];
  sim?: boolean;
}

export interface StormResponsePlan {
  plan_id: string;
  type: string;
  origin: LatLon;
  destination: LatLon;
  stops: Array<{
    stop: number;
    kind: string;
    lat: number;
    lon: number;
    activity: string;
    reason: string;
  }>;
  legs: Array<{
    from: LatLon | null;
    to: LatLon | null;
    path?: LatLon[];
    stats?: { length_km?: number; max_slope_deg?: number; cost?: number };
  }>;
  total_length_km: number;
  radiation_estimate: Record<string, unknown>;
  advisory: boolean;
}

export interface MissionStop {
  lat: number;
  lon: number;
  activity: string;
  reason: string;
}

export interface MissionRoute {
  preset: string;
  path: LatLon[];
  stats: { length_km: number; max_slope_deg: number; mean_slope_deg?: number; cost?: number };
}

export interface Mission {
  id: string;
  type: "route" | "area" | "evacuation" | "survey";
  name: string;
  objective: string;
  stops: MissionStop[];
  routes?: MissionRoute[];
  notes?: string;
  advisory?: boolean;
  created_at?: string;
}

export interface Bookmark {
  id: string;
  name: string;
  lat: number;
  lon: number;
  note?: string;
  camera?: Record<string, unknown>;
}

export interface FlyoverKeyframe {
  lat: number;
  lon: number;
  altitude_km: number;
  heading_deg: number;
  pitch_deg: number;
  dwell_s: number;
  caption: string;
}

export interface Flyover {
  id: string;
  name: string;
  region: string;
  summary: string;
  keyframes: FlyoverKeyframe[];
  src: string;
}

export interface ElevationGridData {
  rows: number;
  cols: number;
  step_deg: number;
  min_m: number;
  max_m: number;
  lats: number[];
  lons: number[];
  grid_m: number[][];
  provenance: Provenance;
}

export interface SolarData {
  mars_sol_date: number;
  ls_deg: number;
  mtc_hours: number;
  subsolar_lat: number;
  subsolar_lon: number;
  solar_elevation_deg: number;
  solar_azimuth_deg: number;
  daylight: boolean;
  provenance: Provenance;
}

export interface JevToolTrace {
  id: string;
  tool: string;
  args: Record<string, unknown>;
  ok?: boolean;
  error?: string;
}

export interface JevMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  traces?: JevToolTrace[];
  citations?: string[];
  intents?: Array<Record<string, unknown>>;
  sim?: boolean;
  abstained?: boolean;
}

export interface WsEventItem {
  id?: number;
  type: string;
  t?: number;
  payload?: Record<string, unknown>;
  scenario?: StormScenario;
  mission_id?: string;
  action?: string;
  name?: string;
  sim?: boolean;
}

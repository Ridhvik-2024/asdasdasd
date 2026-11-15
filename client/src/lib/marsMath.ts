import type { ElevationGridData, LatLon } from "../types/nam";

/** IAU Mars 2000 reference ellipsoid constants (km) */
export const MARS_A_KM = 3396.19; // Equatorial radius
export const MARS_B_KM = 3376.2; // Polar radius
export const MARS_MEAN_R_KM = 3389.5;
export const MARS_FLATTENING = (MARS_A_KM - MARS_B_KM) / MARS_A_KM;
export const MARS_POLAR_RATIO = MARS_B_KM / MARS_A_KM; // ~0.994114

export function normLon(lon: number): number {
  return ((lon % 360) + 360) % 360;
}

export function normLat(lat: number): number {
  return Math.max(-90, Math.min(90, lat));
}

export function formatCoords(lat: number, lon: number): string {
  const ns = lat >= 0 ? "N" : "S";
  return `${Math.abs(lat).toFixed(2)}°${ns}, ${normLon(lon).toFixed(2)}°E`;
}

export function haversineKm(a: LatLon, b: LatLon): number {
  const toRad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * toRad;
  const dLon = ((((b.lon - a.lon) + 180) % 360 + 360) % 360 - 180) * toRad;
  const s1 = Math.sin(dLat / 2);
  const s2 = Math.sin(dLon / 2);
  const h = s1 * s1 + Math.cos(a.lat * toRad) * Math.cos(b.lat * toRad) * s2 * s2;
  return 2 * MARS_MEAN_R_KM * Math.asin(Math.min(1, Math.sqrt(h)));
}

/**
 * Convert Mars planetocentric (lat, lon East 0-360) + elevation (km) to 3D
 * Cartesian coordinates on the normalized oblate IAU Mars ellipsoid (unit eq radius = 1).
 *
 * Three.js SphereGeometry UV mapping:
 *   u = lon / 360 in [0, 1] -> phi = u * 2*PI
 *   v = (lat + 90) / 180    -> theta = (1 - v) * PI = (90 - lat) * PI/180
 *   x = -R * cos(phi) * sin(theta)
 *   y =  R * polarRatio * cos(theta)
 *   z =  R * sin(phi) * sin(theta)
 */
export function latLonToVec3(
  latDeg: number,
  lonDeg: number,
  radialOffset = 0
): [number, number, number] {
  const phi = (normLon(lonDeg) * Math.PI) / 180;
  const theta = ((90 - normLat(latDeg)) * Math.PI) / 180;
  const r = 1 + radialOffset;
  const sinT = Math.sin(theta);
  const cosT = Math.cos(theta);
  const x = -r * Math.cos(phi) * sinT;
  const y = r * MARS_POLAR_RATIO * cosT;
  const z = r * Math.sin(phi) * sinT;
  return [x, y, z];
}

/** Inverse of latLonToVec3 from a point on/near the Mars ellipsoid */
export function vec3ToLatLon(x: number, y: number, z: number): LatLon {
  const yn = y / MARS_POLAR_RATIO;
  const r = Math.sqrt(x * x + yn * yn + z * z) || 1;
  const lat = (Math.asin(Math.max(-1, Math.min(1, yn / r))) * 180) / Math.PI;
  const phi = Math.atan2(z, -x);
  const lon = normLon((phi * 180) / Math.PI);
  return { lat, lon };
}

/** Bilinear elevation lookup (meters) on the cached global grid */
export function sampleElevation(grid: ElevationGridData | null, lat: number, lon: number): number | null {
  if (!grid || !grid.grid_m.length) return null;
  const rows = grid.rows;
  const cols = grid.cols;
  const lClamped = normLat(lat);
  const lo = normLon(lon);
  // grid rows are ordered North (+90) -> South (-90)
  const fy = ((90 - lClamped) / 180) * (rows - 1);
  const y0 = Math.max(0, Math.min(rows - 2, Math.floor(fy)));
  const y1 = y0 + 1;
  const wy = Math.max(0, Math.min(1, fy - y0));

  const fx = (lo / 360) * cols;
  const x0 = ((Math.floor(fx) % cols) + cols) % cols;
  const x1 = (x0 + 1) % cols;
  const wx = fx - Math.floor(fx);

  const r0 = grid.grid_m[y0][x0] * (1 - wx) + grid.grid_m[y0][x1] * wx;
  const r1 = grid.grid_m[y1][x0] * (1 - wx) + grid.grid_m[y1][x1] * wx;
  return r0 * (1 - wy) + r1 * wy;
}

/** North/South polar stereographic projection (hemisphere radius = 1 at equator) */
export function polarProject(lat: number, lon: number, pole: "north" | "south"): { x: number; y: number; visible: boolean } {
  const isNorth = pole === "north";
  const signedLat = isNorth ? lat : -lat;
  const visible = signedLat >= -5;
  const colat = ((90 - Math.max(-5, signedLat)) * Math.PI) / 180;
  const r = Math.tan(colat / 2); // 0 at pole, 1 at equator
  const az = (normLon(lon) * Math.PI) / 180;
  const x = r * Math.sin(az);
  const y = isNorth ? r * Math.cos(az) : -r * Math.cos(az);
  return { x, y, visible };
}

export function polarUnproject(x: number, y: number, pole: "north" | "south"): LatLon | null {
  const r = Math.sqrt(x * x + y * y);
  if (r > 1.08) return null;
  const isNorth = pole === "north";
  const colat = 2 * Math.atan(r);
  const latSigned = 90 - (colat * 180) / Math.PI;
  const lat = normLat(isNorth ? latSigned : -latSigned);
  const az = Math.atan2(x, isNorth ? y : -y);
  const lon = normLon((az * 180) / Math.PI);
  return { lat, lon };
}

import React from "react";
import { Pause, Play, Sun } from "lucide-react";
import { formatCoords } from "../lib/marsMath";
import type { SolarData } from "../types/nam";

interface BottomBarProps {
  hoverLat: number | null;
  hoverLon: number | null;
  hoverElevM: number | null;
  exaggeration: number;
  onExaggerationChange: (v: number) => void;
  solar: SolarData | null;
  solPlaying: boolean;
  onToggleSolPlay: () => void;
  baseLayer: string;
}

export const BottomBar: React.FC<BottomBarProps> = ({
  hoverLat,
  hoverLon,
  hoverElevM,
  exaggeration,
  onExaggerationChange,
  solar,
  solPlaying,
  onToggleSolPlay,
  baseLayer,
}) => {
  return (
    <footer className="bottom-bar glass">
      {/* Live cursor telemetry */}
      <div className="row" style={{ gap: 12 }}>
        <span className="mono" style={{ minWidth: 165 }}>
          {hoverLat !== null && hoverLon !== null
            ? formatCoords(hoverLat, hoverLon)
            : "Move pointer over Mars"}
        </span>
        <span className="mono muted" style={{ minWidth: 96 }}>
          {hoverElevM !== null ? `Elev: ${hoverElevM > 0 ? "+" : ""}${hoverElevM} m` : "Elev: —"}
        </span>
        <span className="badge badge-sim" title="IAU:49900 Mars 2000 east-positive 0-360°">
          IAU Mars · 0–360°E
        </span>
      </div>

      {/* Terrain Vertical Exaggeration (1x-10x) */}
      <div className="row" style={{ gap: 6 }}>
        <span className="small muted">Terrain Relief</span>
        <input
          type="range"
          min={1}
          max={10}
          step={0.5}
          value={exaggeration}
          onChange={(e) => onExaggerationChange(parseFloat(e.target.value))}
          style={{ width: 88 }}
        />
        <span className="mono" style={{ width: 32 }}>
          {exaggeration.toFixed(1)}×
        </span>
      </div>

      {/* Mars24 Sun & Sol Time-Lapse */}
      <div className="row" style={{ gap: 8 }}>
        <Sun size={13} color="#f59e0b" />
        <span className="mono small">
          {solar
            ? `Ls ${solar.ls_deg.toFixed(1)}° · MTC ${solar.mtc_hours.toFixed(1)}h · Subsolar ${solar.subsolar_lat.toFixed(1)}°, ${solar.subsolar_lon.toFixed(0)}°E`
            : "Mars24 loading…"}
        </span>
        <button
          className={`btn btn-xs ${solPlaying ? "btn-active" : ""}`}
          onClick={onToggleSolPlay}
          title="Animate Mars sun & day/night terminator across a sol"
        >
          {solPlaying ? <Pause size={11} /> : <Play size={11} />}
          {solPlaying ? "Sol Anim" : "Play Sol"}
        </button>
      </div>

      {/* Provenance integrity status */}
      <div className="row" style={{ gap: 6 }}>
        <span className="small muted">Layer: {baseLayer}</span>
        <span className="badge badge-sim" title="Synthetic demo topography raster [SIM]; swap to MOLA MEGDR / Murray Lab CTX upstream when online">
          [SIM] Demo Grid
        </span>
      </div>
    </footer>
  );
};

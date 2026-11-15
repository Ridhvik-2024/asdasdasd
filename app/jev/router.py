"""Deterministic intent router - the JEV fallback planner (always available).

Maps natural-language commands to tool plans and globe-control intents.
The LLM adapter (when present) produces the same plan structure; the router
guarantees honest behaviour without any model.
"""
import re

from .. import environment, seeds
from ..integrity import SIM, prov
from . import retrieval, tools as jt

MOUNTAINS_RANK = ["Olympus Mons", "Ascraeus Mons", "Arsia Mons", "Pavonis Mons",
                  "Elysium Mons", "Alba Mons", "Tharsis Tholus", "Ceraunius Tholus"]

PUBLISHED_MOUNTAIN_HEIGHTS_KM = {
    "Olympus Mons": 21.9,
    "Ascraeus Mons": 18.2,
    "Arsia Mons": 17.7,
    "Pavonis Mons": 14.3,
    "Elysium Mons": 14.3,
    "Alba Mons": 6.8,
    "Tharsis Tholus": 3.0,
    "Ceraunius Tholus": 3.0,
}

ROVER_NAMES = ("perseverance", "curiosity", "opportunity", "spirit", "zhurong")
_ROVER_ALT = "|".join(ROVER_NAMES)
ROVER_ROUTE_RE = re.compile(
    r"\b(?:(%s)\b.*?\b(?:routes?|traverses?|paths?)\b"
    r"|(?:routes?|traverses?|paths?)\b.*?\b(%s))\b" % (_ROVER_ALT, _ROVER_ALT),
    re.IGNORECASE,
)


def extract_rover_name(message):
    """Extract canonical rover name from a rover-route query, or None."""
    m = ROVER_ROUTE_RE.search((message or "").strip())
    if not m:
        return None
    raw = m.group(1) or m.group(2)
    return raw.capitalize() if raw else None


def _loc(name):
    cleaned = re.sub(r"^\s*the\s+", "", (name or "").strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"[?.!,;]+$", "", cleaned).strip()
    res = seeds.search(cleaned, limit=1)
    return res[0] if res else None


class Plan:
    def __init__(self):
        self.steps = []       # [{"tool": name, "args": {...}, "id": "<tool>#<n>"}]
        self.intents = []     # globe-control directives for the client
        self.citations = []
        self._counts = {}     # per-tool invocation counters -> stable step ids

    def add(self, tool, **args):
        """Add a tool call. Every invocation gets a unique id (<tool>#<n>,
        numbered per tool), so plans that call the same tool twice (e.g. a
        geological comparison) can address each result separately."""
        self._counts[tool] = self._counts.get(tool, 0) + 1
        self.steps.append({"tool": tool, "args": args,
                           "id": "%s#%d" % (tool, self._counts[tool])})

    def fly_to(self, lat, lon, label):
        self.intents.append({"action": "fly_to", "lat": lat, "lon": lon, "label": label})


def is_resource_route_request(message):
    text = (message or "").lower()
    return bool(re.search(r"\b(route|travel|navigate|journey|drive|traverse|plan|get|go)\b", text)
                and re.search(r"\bfrom\b.+\bto\b", text))


def _route_preference(message):
    text = message.lower()
    water = bool(re.search(r"\bwater\b|\bice\b", text))
    shelter = bool(re.search(r"\bshelters?\b", text))
    excluded_water = bool(re.search(r"\b(?:without|no|avoid|avoiding)\s+(?:any\s+)?(?:water|ice)\b", text))
    excluded_shelter = bool(re.search(r"\b(?:without|no|avoid|avoiding)\s+(?:any\s+)?shelters?\b", text))
    if re.search(r"\b(?:without|no|avoid|avoiding)\s+(?:any\s+)?(?:water|ice)\s+(?:and|or)\s+shelters?\b", text):
        excluded_water = excluded_shelter = True
    if re.search(r"\b(?:without|no|avoid|avoiding)\s+(?:any\s+)?shelters?\s+(?:and|or)\s+(?:water|ice)\b", text):
        excluded_water = excluded_shelter = True
    if not water and not shelter:
        return "both"
    wanted_water, wanted_shelter = water and not excluded_water, shelter and not excluded_shelter
    if wanted_water and wanted_shelter: return "both"
    if wanted_water: return "water"
    if wanted_shelter: return "shelter"
    return "none"


def summarize_resource_route(route):
    if route.get("error"):
        return "Could not plan the route: " + str(route.get("detail") or route["error"])
    if route.get("status") != "ok":
        return "No complete terrain route could be calculated [SIM]. " + " ".join(route.get("warnings", []))
    stops = " → ".join(f"{s['name']} ({s['kind']})" for s in route["stops"])
    screen = route["resource_screen"]
    return (f"Advisory route [SIM]: {stops}. Distance {route['total_km']} km; "
            f"estimated {route['estimated_sols']} sols at {route['speed_km_sol']} km/sol; "
            f"estimated radiation {route['radiation']['total_msv']} mSv [SIM]. "
            f"Resource detour screening: {screen['estimated_extra_km']} km (limit {screen['limit_km']} km). "
            + " ".join(route.get("warnings", [])))


def plan_for(message, ctx=None):
    """Return (plan, composer_fn). Composer turns tool results into a cited reply."""
    msg = (message or "").lower().strip()
    p = Plan()

    # Route planning remains grounded even when a local model is configured:
    # the model extracts names inside this tool; the backend computes the route.
    if is_resource_route_request(message):
        p.add("plan_resource_route", message=message, preference=_route_preference(message))
        return p, lambda results: summarize_resource_route(results.get("plan_resource_route", {}))

    # 1. take me to X / fly to X / go to X
    m = re.search(r"(?:take me to|fly to|go to|navigate to|zoom to)\s+(.+)", msg)
    if m:
        target = re.sub(r"(crater|the|please)\s*$", "", m.group(1)).strip()
        loc = _loc(target)
        if loc:
            p.fly_to(loc["lat"], loc["lon"], loc["name"])
            p.add("search_planetary_location", q=loc["name"], limit=1)
            p.add("analyze_terrain", bbox=[loc["lat"] - 0.5, loc["lon"] - 0.5,
                                           loc["lat"] + 0.5, loc["lon"] + 0.5])
            def compose(res, loc=loc):
                terr = res.get("analyze_terrain", {})
                return ("Flying to %s (%.2f, %.2f). Local terrain: mean elevation %.0f m, "
                        "relief %.0f m, mean slope %.1f deg. %s"
                        % (loc["name"], loc["lat"], loc["lon"],
                           terr.get("mean_elev_m", 0), terr.get("relief_m", 0),
                           terr.get("mean_slope_deg", 0), _prov_footer(terr)))
            return p, compose

    # 2. landing sites
    if "landing site" in msg or ("landed" in msg and "site" in msg) or "all major landing" in msg:
        p.add("search_nasa_datasets", topic="landing")
        def compose(res):
            sites = seeds.landing_sites()
            lines = ["All successful Mars landing sites:"]
            lines += ["- %s: (%.2f, %.2f), landed %s" % (s["name"], s["lat"], s["lon"], s["date"])
                      for s in sites]
            lines.append("Source: " + sites[0]["src"] + " " + SIM)
            return "\n".join(lines)
        return p, compose

    # 3. compare A and B
    m = re.search(r"compare\s+(.+?)\s+(?:and|with|vs|versus)\s+(.+)", msg)
    if m:
        a = _loc(re.sub(r"\bcrater\b", "", m.group(1)).strip())
        b = _loc(re.sub(r"\bcrater\b", "", m.group(2)).strip())
        if a and b:
            p.add("analyze_terrain", bbox=[a["lat"] - 0.5, a["lon"] - 0.5, a["lat"] + 0.5, a["lon"] + 0.5])
            p.add("analyze_terrain", bbox=[b["lat"] - 0.5, b["lon"] - 0.5, b["lat"] + 0.5, b["lon"] + 0.5])

            def _terr_line(name, t):
                # each location reads its OWN invocation result: Plan.add ids
                # the two analyze_terrain calls separately and the executor
                # preserves them under those ids, so the second result can no
                # longer overwrite the first.
                if t is None:
                    return "%s: terrain data unavailable (tool did not run)." % name
                if isinstance(t, dict) and t.get("error"):
                    return "%s: terrain analysis failed (%s)." % (name, t.get("detail") or t["error"])
                return "%s - mean elev %.0f m, mean slope %.1f deg" % (
                    name, t.get("mean_elev_m", 0), t.get("mean_slope_deg", 0))

            def compose(res, a=a, b=b):
                ta = (res or {}).get("analyze_terrain#1")
                tb = (res or {}).get("analyze_terrain#2")
                return ("Comparison %s vs %s: %s; %s. Terrain stats from the demo grid [SIM]; "
                        "scientific detail via /sites/compare."
                        % (a["name"], b["name"],
                           _terr_line(a["name"], ta), _terr_line(b["name"], tb)))
            return p, compose

    # 4. ancient water evidence
    if "water" in msg and ("ancient" in msg or "evidence" in msg or "paleolake" in msg or "river" in msg):
        p.add("activate_map_layer", layer_id="paleolakes")
        p.add("activate_map_layer", layer_id="valley-networks")
        p.add("find_water", lat=45.0, lon=190.0, radius_km=9000)
        def compose(res):
            disc = seeds.observations(q="aqueous", limit=3) or seeds.observations(limit=3)
            lines = ["Ancient-water evidence regions:"]
            lines += ["- %s (%s): %s" % (d["title"], "%s/%s" % (d["mission"], d["instrument"]),
                                         d["evidence"]["citation"]) for d in disc]
            lines.append("Paleolake and valley-network layers activated on the globe. " + SIM)
            return "\n".join(lines)
        return p, compose

    # 5. rover routes
    rover = extract_rover_name(msg)
    if rover:
        p.add("activate_map_layer", layer_id="rover-traverses")
        def compose(res, rover=rover):
            pts = seeds.traverse(rover)
            if not pts:
                return "No traverse found for %s." % rover
            lines = ["%s traverse (Street View panorama sequence), ordered by sol:" % rover]
            lines += ["- Sol %s: %s (%s)" % (x.get("sol"), x["title"], x["credit"]) for x in pts]
            lines.append("Layer rover-traverses activated; open any point for the panorama. " + SIM)
            return "\n".join(lines)
        return p, compose

    # 6. explain what I am looking at
    if "explain" in msg or "what am i looking" in msg or "what is this" in msg or "current view" in msg:
        p.add("get_current_map_context")
        def compose(res):
            mc = res.get("get_current_map_context", {})
            st = mc.get("center_terrain", {})
            near = mc.get("nearest_features", [])
            bbox = st.get("bbox", [0, 0, 0, 0])
            lines = ["What you are looking at:"]
            lines.append("- Center (%.2f, %.2f): mean elev %.0f m, relief %.0f m, mean slope %.1f deg."
                         % (bbox[0] + 0.5, (bbox[1] + 0.5) % 360.0,
                            st.get("mean_elev_m", 0), st.get("relief_m", 0), st.get("mean_slope_deg", 0)))
            if near:
                lines.append("- Nearest named features: " + ", ".join(f["name"] for f in near[:4]) + ".")
            for o in mc.get("nearest_cited_observations", [])[:2]:
                lines.append("- Cited science here: %s (%s)" % (o["title"], o["citation"]))
            lines.append("Provenance: terrain from the demo grid [SIM]; features from the USGS gazetteer.")
            return "\n".join(lines)
        return p, compose

    # 7. interesting geological formations near this location
    if ("formation" in msg or "geolog" in msg) and ("near" in msg or "around" in msg or "here" in msg):
        center = (ctx or {}).get("map_context", {}).get("center") or {"lat": 18.44, "lon": 77.5}
        p.add("find_scientific_targets", lat=center["lat"], lon=center["lon"], radius_km=500)
        p.add("get_location_observations", lat=center["lat"], lon=center["lon"], radius_km=300)
        def compose(res):
            tg = res.get("find_scientific_targets", {}).get("targets", [])
            obs = res.get("get_location_observations", {}).get("observations", [])
            lines = ["Interesting geological targets near you:"]
            lines += ["- %s (cited: %s)" % (t["title"], t.get("citation", "NAM POV library")) for t in tg[:6]]
            for o in obs[:3]:
                lines.append("- %s (%s)" % (o["title"], o["evidence"]["citation"]))
            return "\n".join(lines)
        return p, compose

    # 8. highest mountains
    if "highest" in msg or "tallest" in msg or ("mountain" in msg and "show" in msg):
        from ..terrain import engine as _eng
        Te = _eng()
        p.add("analyze_terrain", bbox=[-15.0, 220.0, 45.0, 265.0])   # Tharsis rise
        rows = []
        for name in MOUNTAINS_RANK:
            loc = _loc(name)
            if loc:
                e = Te.elev(loc["lat"], loc["lon"])
                pub_km = PUBLISHED_MOUNTAIN_HEIGHTS_KM.get(
                    name, PUBLISHED_MOUNTAIN_HEIGHTS_KM.get(loc["name"])
                )
                rows.append((e, loc["name"], pub_km))
        rows.sort(key=lambda r: r[0], reverse=True)
        lines = ["Highest known volcanic mountains on Mars (elevation from demo grid [SIM], "
                 "published summit heights in the notes):"]
        for e, n, k in rows:
            if k is not None:
                lines.append("- %s: ~%.0f m on the demo grid (published ~%.1f km)" % (n, e, k))
            else:
                lines.append("- %s: ~%.0f m on the demo grid" % (n, e))
        lines.append("Provenance: USGS gazetteer feature positions; MOLA published summit heights.")
        return p, (lambda res: "\n".join(lines))

    # operational commands
    if "water" in msg and ("find" in msg or "where" in msg or "ice" in msg):
        center = (ctx or {}).get("map_context", {}).get("center") or {"lat": 45.0, "lon": 190.0}
        p.add("find_water", lat=center["lat"], lon=center["lon"], radius_km=2000)
        def compose(res):
            cands = res.get("find_water", {}).get("candidates", [])
            lines = ["Water-ice candidates (SWIM-derived):"]
            lines += ["- %s: certainty %s, %s, %s" % (c["name"], c["certainty"],
                                                      c["depth_to_ice_category"], c["stability"]) for c in cands[:6]]
            lines.append("Provenance: SWIM consensus maps (swim.psi.edu). " + SIM)
            return "\n".join(lines)
        return p, compose

    if "shelter" in msg:
        center = (ctx or {}).get("map_context", {}).get("center") or {"lat": 18.44, "lon": 77.5}
        p.add("find_shelter", lat=center["lat"], lon=center["lon"], radius_km=3000)
        def compose(res):
            sh = res.get("find_shelter", {}).get("shelters", [])
            lines = ["Shelter candidates ranked by composite index:"]
            lines += ["- %s (%s): composite %.1f - %s" % (s["name"], s["type"], s["composite_index"], s["note"])
                      for s in sh[:6]]
            lines.append(SIM + " - verify against HiRISE before any use.")
            return "\n".join(lines)
        return p, compose

    if "radiation" in msg or "dose" in msg:
        center = (ctx or {}).get("map_context", {}).get("center") or {"lat": 0.0, "lon": 0.0}
        p.add("assess_radiation", lat=center["lat"], lon=center["lon"], duration_sols=5, shielding="suit")
        def compose(res):
            r = res.get("assess_radiation", {})
            return ("Radiation estimate [SIM]: %.3f mSv/sol GCR at this site (%.0f m elevation, "
                    "%.0f Pa column), total %.3f mSv over 5 sols in a suit. Anchor: RAD at Gale "
                    "(Hassler et al. 2014); +/-30 percent band, advisory."
                    % (r.get("gcr_dose_equiv_msv_per_sol", 0), r.get("elevation_m", 0),
                       r.get("surface_pressure_pa", 0), r.get("gcr_total_msv", 0)))
        return p, compose

    if ("storm" in msg or "dust" in msg) and ("simulate" in msg or "model" in msg or "what if" in msg):
        sev = "my34" if "my34" in msg or "global" in msg or "planet-encircling" in msg else "regional"
        p.add("simulate_storm", kind="dust", scale_or_class=sev)
        def compose(res):
            s = res.get("simulate_storm", {})
            return ("Storm scenario [SIM]: %s - tau ~%.1f, radius ~%s km, ~%s sols. "
                    "Effects: %s. Documented analogs included. Advisory only."
                    % (s.get("label"), s.get("tau_peak", 0), s.get("affected_radius_km"),
                       s.get("duration_sols"), "; ".join(s.get("effects", []))))
        return p, compose

    if "evacuat" in msg or "storm response" in msg or ("plan" in msg and "storm" in msg):
        center = (ctx or {}).get("map_context", {}).get("center") or {"lat": 18.44, "lon": 77.5}
        p.add("plan_storm_response", lat=center["lat"], lon=center["lon"], severity="X")
        def compose(res):
            plan = res.get("plan_storm_response", {})
            stops = plan.get("stops", [])
            lines = ["Evacuation plan [SIM]:"]
            for s in stops:
                lines.append("- Stop %d (%s) at (%.2f, %.2f): %s - %s" % (
                    s["stop"], s["kind"], s["lat"], s["lon"], s["activity"], s["reason"]))
            rad = plan.get("radiation_estimate", {})
            lines.append("Route ~%.0f km; estimated dose %.2f mSv over 2 sols [SIM, advisory]."
                         % (plan.get("total_length_km", 0), rad.get("total_msv", 0)))
            return "\n".join(lines)
        return p, compose

    if msg.startswith("show layer") or "activate layer" in msg or "turn on layer" in msg:
        m2 = re.search(r"layer[s]?\s+(?:id\s+)?([a-z0-9\-]+)", msg)
        if m2:
            p.add("activate_map_layer", layer_id=m2.group(1))
            def compose(res, lid=m2.group(1)):
                r = res.get("activate_map_layer", {})
                if "layer" in r:
                    return "Layer %s activated: %s (%s)." % (lid, r["layer"]["title"], r["layer"]["source"])
                return "Unknown layer id %s - list via /layers." % lid
            return p, compose

    # retrieval fallback
    p.add("get_current_map_context")
    def compose_fallback(res):
        hits = retrieval.search(message, k=4)
        if not hits:
            return ("I don't have grounded information about that. I can search the gazetteer, "
                    "cited discoveries, water/shelter candidates and mission planning tools - "
                    "or try one of the example commands. (I abstain rather than invent.)")
        lines = ["Closest grounded matches (retrieval, with citations):"]
        for h in hits:
            lines.append("- %s [%s] %s" % (h["title"], h["kind"], h["citation"]))
        lines.append("Ask me to fly to any of these.")
        return "\n".join(lines)
    return p, compose_fallback


def _prov_footer(res):
    return "Provenance: %s" % ((res or {}).get("provenance", {}).get("source", "NAM services [SIM]"))


def explain_view(ctx):
    """Explain-what-I-am-looking-at as a first-class capability."""
    res = jt.run_tool("get_current_map_context", {}, {"map_context": (ctx or {}).get("map_context", {})})
    st = res.get("center_terrain", {})
    region = seeds.region_context(
        (ctx or {}).get("map_context", {}).get("center", {}).get("lat", 0),
        (ctx or {}).get("map_context", {}).get("center", {}).get("lon", 0))
    parts = []
    parts.append("Region: %s - %s" % (region["region"], region["description"]))
    parts.append("Center terrain: mean elev %.0f m, relief %.0f m, mean slope %.1f deg, hazard %.0f/100 [SIM demo grid]."
                 % (st.get("mean_elev_m", 0), st.get("relief_m", 0), st.get("mean_slope_deg", 0), st.get("hazard_score", 0)))
    near = res.get("nearest_features", [])
    if near:
        parts.append("Named features in view: " + ", ".join(f["name"] for f in near[:5]) + ".")
    for o in res.get("nearest_cited_observations", [])[:3]:
        parts.append("Cited science here: %s (%s)" % (o["title"], o["citation"]))
    if res.get("active_layers"):
        parts.append("Active layers: " + ", ".join(l["title"] for l in res["active_layers"]) + ".")
    parts.append("Every claim above is grounded: gazetteer (USGS), cited publications, demo-grid terrain [SIM].")
    return {"explanation": "\n".join(parts), "context": res,
            "provenance": prov(source="JEV explain-view (grounded tool outputs only)")}

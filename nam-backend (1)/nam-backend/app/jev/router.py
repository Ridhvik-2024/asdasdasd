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


def _err_msg(err):
    if isinstance(err, dict):
        code = err.get("code") or err.get("error") or "tool_error"
        detail = err.get("detail")
        if detail and detail != code:
            return "%s: %s" % (code, detail)
        return str(code)
    return str(err or "tool error")


def _unpack_invocation(inv):
    if not isinstance(inv, dict):
        return inv, None
    if "ok" in inv and ("result" in inv or "error" in inv):
        if not inv["ok"]:
            return None, inv.get("error") or inv.get("result") or "tool failed"
        raw = inv.get("result")
        if isinstance(raw, dict) and "error" in raw:
            return None, raw
        return raw if isinstance(raw, dict) else {"value": raw}, None
    if "error" in inv:
        return None, inv
    return inv, None


def _step_result(res, step_id=None, tool_name=None, index=0):
    """Resolve a specific tool invocation's (result_dict, error) from results."""
    if not isinstance(res, dict):
        return {}, None
    if step_id and dict.__contains__(res, step_id):
        return _unpack_invocation(dict.__getitem__(res, step_id))
    if hasattr(res, "for_tool") and tool_name:
        invs = res.for_tool(tool_name)
        if index < len(invs):
            return _unpack_invocation(invs[index])
        return {}, None
    if tool_name:
        matching = [
            v for v in res.values()
            if isinstance(v, dict) and v.get("tool") == tool_name and ("result" in v or "error" in v)
        ]
        if matching:
            if index < len(matching):
                return _unpack_invocation(matching[index])
            return {}, None
        direct = res.get(tool_name)
        if isinstance(direct, list):
            if index < len(direct):
                return _unpack_invocation(direct[index])
            return {}, None
        if isinstance(direct, dict):
            if index == 0:
                return _unpack_invocation(direct)
            return {}, None
    return {}, None


class Plan:
    def __init__(self):
        self.steps = []       # [{"id": "call_1", "tool": name, "args": {...}}]
        self.intents = []     # globe-control directives for the client
        self.citations = []

    def add(self, tool, **args):
        step_id = "call_%d" % (len(self.steps) + 1)
        self.steps.append({"id": step_id, "tool": tool, "args": args})
        return step_id

    def fly_to(self, lat, lon, label):
        self.intents.append({"action": "fly_to", "lat": lat, "lon": lon, "label": label})


def plan_for(message, ctx=None):
    """Return (plan, composer_fn). Composer turns tool results into a cited reply."""
    msg = (message or "").lower().strip()
    p = Plan()

    # 1. take me to X / fly to X / go to X
    m = re.search(r"(?:take me to|fly to|go to|navigate to|zoom to)\s+(.+)", msg)
    if m:
        target = re.sub(r"[?.!,;]+$", "", m.group(1)).strip()
        target = re.sub(r"\b(crater|the|please)\s*$", "", target).strip()
        loc = _loc(target)
        if loc:
            p.fly_to(loc["lat"], loc["lon"], loc["name"])
            id_loc = p.add("search_planetary_location", q=loc["name"], limit=1)
            id_terr = p.add("analyze_terrain", bbox=[loc["lat"] - 0.5, loc["lon"] - 0.5,
                                                     loc["lat"] + 0.5, loc["lon"] + 0.5])
            def compose(res, loc=loc, id_loc=id_loc, id_terr=id_terr):
                _, loc_err = _step_result(res, id_loc, "search_planetary_location", 0)
                terr, terr_err = _step_result(res, id_terr, "analyze_terrain", 0)
                if terr_err:
                    out = ("Flying to %s (%.2f, %.2f). Local terrain statistics are missing because "
                           "analyze_terrain failed (%s)."
                           % (loc["name"], loc["lat"], loc["lon"], _err_msg(terr_err)))
                else:
                    out = ("Flying to %s (%.2f, %.2f). Local terrain: mean elevation %.0f m, "
                           "relief %.0f m, mean slope %.1f deg. %s"
                           % (loc["name"], loc["lat"], loc["lon"],
                              terr.get("mean_elev_m", 0), terr.get("relief_m", 0),
                              terr.get("mean_slope_deg", 0), _prov_footer(terr)))
                if loc_err:
                    out += (" Note: Gazetteer verification via search_planetary_location failed (%s); "
                            "some location details are missing." % _err_msg(loc_err))
                return out
            return p, compose

    # 2. landing sites
    if "landing site" in msg or ("landed" in msg and "site" in msg) or "all major landing" in msg:
        id_ds = p.add("search_nasa_datasets", topic="landing")
        def compose(res, id_ds=id_ds):
            _, ds_err = _step_result(res, id_ds, "search_nasa_datasets", 0)
            sites = seeds.landing_sites()
            lines = ["All successful Mars landing sites:"]
            lines += ["- %s: (%.2f, %.2f), landed %s" % (s["name"], s["lat"], s["lon"], s["date"])
                      for s in sites]
            lines.append("Source: " + sites[0]["src"] + " " + SIM)
            if ds_err:
                lines.append("Note: Supporting NASA dataset catalog lookup (search_nasa_datasets) failed (%s); "
                             "catalog metadata is missing." % _err_msg(ds_err))
            return "\n".join(lines)
        return p, compose

    # 3. compare A and B
    m = re.search(r"compare\s+(.+?)\s+(?:and|with|vs\.?|versus)\s+(.+)", msg)
    if m:
        raw_a = re.sub(r"\b(?:crater|basin)\b", "", m.group(1)).strip()
        raw_b = re.sub(r"\b(?:crater|basin)\b", "", m.group(2)).strip()
        a = _loc(raw_a)
        b = _loc(raw_b)
        if a and b:
            id_a = p.add("analyze_terrain", bbox=[a["lat"] - 0.5, a["lon"] - 0.5, a["lat"] + 0.5, a["lon"] + 0.5])
            id_b = p.add("analyze_terrain", bbox=[b["lat"] - 0.5, b["lon"] - 0.5, b["lat"] + 0.5, b["lon"] + 0.5])
            def compose(res, a=a, b=b, id_a=id_a, id_b=id_b):
                ta, err_a = _step_result(res, id_a, "analyze_terrain", 0)
                tb, err_b = _step_result(res, id_b, "analyze_terrain", 1)
                if err_a and err_b:
                    return ("Comparison %s vs %s [SIM]: terrain statistics are unavailable because "
                            "analyze_terrain failed for both %s (%s) and %s (%s)."
                            % (a["name"], b["name"], a["name"], _err_msg(err_a), b["name"], _err_msg(err_b)))
                if err_a:
                    return ("Comparison %s vs %s [SIM]: %s - terrain statistics missing (analyze_terrain failed: %s); "
                            "%s - mean elev %.0f m, mean slope %.1f deg. "
                            "Note: comparison is incomplete due to missing terrain data for %s."
                            % (a["name"], b["name"], a["name"], _err_msg(err_a),
                               b["name"], tb.get("mean_elev_m", 0), tb.get("mean_slope_deg", 0), a["name"]))
                if err_b:
                    return ("Comparison %s vs %s [SIM]: %s - mean elev %.0f m, mean slope %.1f deg; "
                            "%s - terrain statistics missing (analyze_terrain failed: %s). "
                            "Note: comparison is incomplete due to missing terrain data for %s."
                            % (a["name"], b["name"], a["name"], ta.get("mean_elev_m", 0),
                               ta.get("mean_slope_deg", 0), b["name"], _err_msg(err_b), b["name"]))
                return ("Comparison %s vs %s [SIM]: %s - mean elev %.0f m, mean slope %.1f deg; "
                        "%s - mean elev %.0f m, mean slope %.1f deg. Terrain stats from the demo grid; "
                        "scientific detail via /sites/compare."
                        % (a["name"], b["name"],
                           a["name"], ta.get("mean_elev_m", 0), ta.get("mean_slope_deg", 0),
                           b["name"], tb.get("mean_elev_m", 0), tb.get("mean_slope_deg", 0)))
            return p, compose

    # 4. ancient water evidence
    if "water" in msg and ("ancient" in msg or "evidence" in msg or "paleolake" in msg or "river" in msg):
        id_l1 = p.add("activate_map_layer", layer_id="paleolakes")
        id_l2 = p.add("activate_map_layer", layer_id="valley-networks")
        id_w = p.add("find_water", lat=45.0, lon=190.0, radius_km=9000)
        def compose(res, id_l1=id_l1, id_l2=id_l2, id_w=id_w):
            _, err_l1 = _step_result(res, id_l1, "activate_map_layer", 0)
            _, err_l2 = _step_result(res, id_l2, "activate_map_layer", 1)
            _, err_w = _step_result(res, id_w, "find_water", 0)
            disc = seeds.observations(q="aqueous", limit=3) or seeds.observations(limit=3)
            lines = ["Ancient-water evidence regions:"]
            lines += ["- %s (%s): %s" % (d["title"], "%s/%s" % (d["mission"], d["instrument"]),
                                         d["evidence"]["citation"]) for d in disc]
            active_names = []
            if not err_l1:
                active_names.append("paleolakes")
            if not err_l2:
                active_names.append("valley-networks")
            if len(active_names) == 2:
                lines.append("Paleolake and valley-network layers activated on the globe. " + SIM)
            elif active_names:
                lines.append("Activated layer(s): %s. %s" % (", ".join(active_names), SIM))
            missing = []
            if err_l1:
                missing.append("activate_map_layer paleolakes (%s)" % _err_msg(err_l1))
            if err_l2:
                missing.append("activate_map_layer valley-networks (%s)" % _err_msg(err_l2))
            if err_w:
                missing.append("find_water (%s)" % _err_msg(err_w))
            if missing:
                lines.append("Note: Some tool outputs are missing because tool call(s) failed: %s."
                             % "; ".join(missing))
            return "\n".join(lines)
        return p, compose

    # 5. rover routes
    rover = extract_rover_name(msg)
    if rover:
        id_lay = p.add("activate_map_layer", layer_id="rover-traverses")
        def compose(res, rover=rover, id_lay=id_lay):
            _, lay_err = _step_result(res, id_lay, "activate_map_layer", 0)
            pts = seeds.traverse(rover)
            if not pts:
                out = "No traverse found for %s." % rover
                if lay_err:
                    out += " Note: activate_map_layer failed (%s); layer activation is unavailable." % _err_msg(lay_err)
                return out
            lines = ["%s traverse (Street View panorama sequence), ordered by sol:" % rover]
            lines += ["- Sol %s: %s (%s)" % (x.get("sol"), x["title"], x["credit"]) for x in pts]
            if lay_err:
                lines.append("Note: Layer rover-traverses could not be activated because activate_map_layer failed (%s). %s"
                             % (_err_msg(lay_err), SIM))
            else:
                lines.append("Layer rover-traverses activated; open any point for the panorama. " + SIM)
            return "\n".join(lines)
        return p, compose

    # 6. explain what I am looking at
    if "explain" in msg or "what am i looking" in msg or "what is this" in msg or "current view" in msg:
        id_mc = p.add("get_current_map_context")
        def compose(res, id_mc=id_mc):
            mc, mc_err = _step_result(res, id_mc, "get_current_map_context", 0)
            if mc_err:
                return ("Current view explanation is unavailable because get_current_map_context failed (%s). "
                        "Some map context and terrain information is missing." % _err_msg(mc_err))
            st = mc.get("center_terrain", {})
            near = mc.get("nearest_features", [])
            lines = ["What you are looking at:"]
            lines.append("- Center (%.2f, %.2f): mean elev %.0f m, relief %.0f m, mean slope %.1f deg."
                         % (st.get("bbox", [0, 0, 0, 0])[0] + 0.5, st.get("bbox", [0, 0, 0, 0])[1] + 0.5,
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
        id_tg = p.add("find_scientific_targets", lat=center["lat"], lon=center["lon"], radius_km=500)
        id_obs = p.add("get_location_observations", lat=center["lat"], lon=center["lon"], radius_km=300)
        def compose(res, id_tg=id_tg, id_obs=id_obs):
            tg_res, tg_err = _step_result(res, id_tg, "find_scientific_targets", 0)
            obs_res, obs_err = _step_result(res, id_obs, "get_location_observations", 0)
            if tg_err and obs_err:
                return ("Geological targets near this location are unavailable because both "
                        "find_scientific_targets (%s) and get_location_observations (%s) failed."
                        % (_err_msg(tg_err), _err_msg(obs_err)))
            tg = (tg_res or {}).get("targets", [])
            obs = (obs_res or {}).get("observations", [])
            lines = ["Interesting geological targets near you:"]
            lines += ["- %s (cited: %s)" % (t["title"], t.get("citation", "NAM POV library")) for t in tg[:6]]
            for o in obs[:3]:
                lines.append("- %s (%s)" % (o["title"], o["evidence"]["citation"]))
            if tg_err:
                lines.append("Note: Ranked target candidates are missing because find_scientific_targets failed (%s)."
                             % _err_msg(tg_err))
            if obs_err:
                lines.append("Note: Nearby cited observations are missing because get_location_observations failed (%s)."
                             % _err_msg(obs_err))
            return "\n".join(lines)
        return p, compose

    # 8. highest mountains
    if "highest" in msg or "tallest" in msg or ("mountain" in msg and "show" in msg):
        from ..terrain import engine as _eng
        Te = _eng()
        id_terr = p.add("analyze_terrain", bbox=[5.0, 230.0, 45.0, 260.0])   # Tharsis rise
        rows = []
        for name in MOUNTAINS_RANK:
            loc = _loc(name)
            if loc:
                e = Te.elev(loc["lat"], loc["lon"])
                rows.append((e, loc["name"]))
        rows.sort(reverse=True)
        base_lines = ["Highest known volcanic mountains on Mars (elevation from demo grid [SIM], "
                      "published summit heights in the notes):"]
        base_lines += ["- %s: ~%.0f m on the demo grid (published ~%.1f km)" % (n, e, k)
                       for (e, n), k in zip(rows, [21.9, 18.2, 17.7, 14.3, 14.3, 6.8, 3.0, 3.0])]
        base_lines.append("Provenance: USGS gazetteer feature positions; MOLA published summit heights.")
        def compose_mountains(res, id_terr=id_terr, base_lines=base_lines):
            _, terr_err = _step_result(res, id_terr, "analyze_terrain", 0)
            lines = list(base_lines)
            if terr_err:
                lines.append("Note: Regional Tharsis terrain summary is missing because analyze_terrain failed (%s)."
                             % _err_msg(terr_err))
            return "\n".join(lines)
        return p, compose_mountains

    # operational commands
    if "water" in msg and ("find" in msg or "where" in msg or "ice" in msg):
        center = (ctx or {}).get("map_context", {}).get("center") or {"lat": 45.0, "lon": 190.0}
        id_w = p.add("find_water", lat=center["lat"], lon=center["lon"], radius_km=2000)
        def compose(res, id_w=id_w):
            w_res, w_err = _step_result(res, id_w, "find_water", 0)
            if w_err:
                return "Water-ice candidate information is unavailable because find_water failed (%s)." % _err_msg(w_err)
            cands = w_res.get("candidates", [])
            lines = ["Water-ice candidates (SWIM-derived):"]
            lines += ["- %s: certainty %s, %s, %s" % (c["name"], c["certainty"],
                                                      c["depth_to_ice_category"], c["stability"]) for c in cands[:6]]
            lines.append("Provenance: SWIM consensus maps (swim.psi.edu). " + SIM)
            return "\n".join(lines)
        return p, compose

    if "shelter" in msg:
        center = (ctx or {}).get("map_context", {}).get("center") or {"lat": 18.44, "lon": 77.5}
        id_sh = p.add("find_shelter", lat=center["lat"], lon=center["lon"], radius_km=3000)
        def compose(res, id_sh=id_sh):
            sh_res, sh_err = _step_result(res, id_sh, "find_shelter", 0)
            if sh_err:
                return "Shelter candidate information is unavailable because find_shelter failed (%s)." % _err_msg(sh_err)
            sh = sh_res.get("shelters", [])
            lines = ["Shelter candidates ranked by composite index:"]
            lines += ["- %s (%s): composite %.1f - %s" % (s["name"], s["type"], s["composite_index"], s["note"])
                      for s in sh[:6]]
            lines.append(SIM + " - verify against HiRISE before any use.")
            return "\n".join(lines)
        return p, compose

    if "radiation" in msg or "dose" in msg:
        center = (ctx or {}).get("map_context", {}).get("center") or {"lat": 0.0, "lon": 0.0}
        id_rad = p.add("assess_radiation", lat=center["lat"], lon=center["lon"], duration_sols=5, shielding="suit")
        def compose(res, id_rad=id_rad):
            r, rad_err = _step_result(res, id_rad, "assess_radiation", 0)
            if rad_err:
                return "Radiation estimate is unavailable because assess_radiation failed (%s)." % _err_msg(rad_err)
            return ("Radiation estimate [SIM]: %.3f mSv/sol GCR at this site (%.0f m elevation, "
                    "%.0f Pa column), total %.3f mSv over 5 sols in a suit. Anchor: RAD at Gale "
                    "(Hassler et al. 2014); +/-30 percent band, advisory."
                    % (r.get("gcr_dose_equiv_msv_per_sol", 0), r.get("elevation_m", 0),
                       r.get("surface_pressure_pa", 0), r.get("gcr_total_msv", 0)))
        return p, compose

    if ("storm" in msg or "dust" in msg) and ("simulate" in msg or "model" in msg or "what if" in msg):
        sev = "my34" if "my34" in msg or "global" in msg or "planet-encircling" in msg else "regional"
        id_st = p.add("simulate_storm", kind="dust", scale_or_class=sev)
        def compose(res, id_st=id_st):
            s, st_err = _step_result(res, id_st, "simulate_storm", 0)
            if st_err:
                return "Storm simulation output is unavailable because simulate_storm failed (%s)." % _err_msg(st_err)
            return ("Storm scenario [SIM]: %s - tau ~%.1f, radius ~%s km, ~%s sols. "
                    "Effects: %s. Documented analogs included. Advisory only."
                    % (s.get("label"), s.get("tau_peak", 0), s.get("affected_radius_km"),
                       s.get("duration_sols"), "; ".join(s.get("effects", []))))
        return p, compose

    if "evacuat" in msg or "storm response" in msg or ("plan" in msg and "storm" in msg):
        center = (ctx or {}).get("map_context", {}).get("center") or {"lat": 18.44, "lon": 77.5}
        id_pl = p.add("plan_storm_response", lat=center["lat"], lon=center["lon"], severity="X")
        def compose(res, id_pl=id_pl):
            plan, pl_err = _step_result(res, id_pl, "plan_storm_response", 0)
            if pl_err:
                return "Evacuation plan is unavailable because plan_storm_response failed (%s)." % _err_msg(pl_err)
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
            id_lay = p.add("activate_map_layer", layer_id=m2.group(1))
            def compose(res, lid=m2.group(1), id_lay=id_lay):
                r, lay_err = _step_result(res, id_lay, "activate_map_layer", 0)
                if r and "layer" in r:
                    return "Layer %s activated: %s (%s)." % (lid, r["layer"]["title"], r["layer"]["source"])
                if lay_err:
                    return ("Unknown layer id %s (activate_map_layer failed: %s) - layer unavailable; "
                            "list valid layers via /layers." % (lid, _err_msg(lay_err)))
                return "Unknown layer id %s - list via /layers." % lid
            return p, compose

    # retrieval fallback
    id_mc = p.add("get_current_map_context")
    def compose_fallback(res, id_mc=id_mc):
        _, mc_err = _step_result(res, id_mc, "get_current_map_context", 0)
        hits = retrieval.search(message, k=4)
        if not hits:
            out = ("I don't have grounded information about that. I can search the gazetteer, "
                   "cited discoveries, water/shelter candidates and mission planning tools - "
                   "or try one of the example commands. (I abstain rather than invent.)")
        else:
            lines = ["Closest grounded matches (retrieval, with citations):"]
            for h in hits:
                lines.append("- %s [%s] %s" % (h["title"], h["kind"], h["citation"]))
            lines.append("Ask me to fly to any of these.")
            out = "\n".join(lines)
        if mc_err:
            out += ("\nNote: Map context lookup (get_current_map_context) failed (%s); "
                    "live view context is missing." % _err_msg(mc_err))
        return out
    return p, compose_fallback


def _prov_footer(res):
    return "Provenance: %s" % ((res or {}).get("provenance", {}).get("source", "NAM services [SIM]"))


def explain_view(ctx):
    """Explain-what-I-am-looking-at as a first-class capability."""
    res = jt.run_tool("get_current_map_context", {}, {"map_context": (ctx or {}).get("map_context", {})})
    region = seeds.region_context(
        (ctx or {}).get("map_context", {}).get("center", {}).get("lat", 0),
        (ctx or {}).get("map_context", {}).get("center", {}).get("lon", 0))
    parts = ["Region: %s - %s" % (region["region"], region["description"])]
    if isinstance(res, dict) and "error" in res:
        parts.append("Center terrain and nearby feature details are unavailable because "
                     "get_current_map_context failed (%s)." % _err_msg(res))
        return {"explanation": "\n".join(parts), "context": res,
                "provenance": prov(source="JEV explain-view (partial - map context failed)")}
    st = res.get("center_terrain", {})
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

"""Grounded resource-aware route planning over NAM's advisory demo data.

The model may extract *literal* place names, but never invent coordinates,
resource sites, routes, or scores. Candidate selection and all numbers below
are deterministic and traceable to the bundled backend services.
"""
import itertools
import math
import re

from .. import environment, resources, routing, seeds
from ..mars import hav_km, validate_coords
from . import llm

_COORDS = re.compile(r'^\s*([+-]?\d+(?:\.\d+)?)\s*,\s*([+-]?\d+(?:\.\d+)?)\s*$')


def _distance(a, b):
    return hav_km(a['lat'], a['lon'], b['lat'], b['lon'])


def _parse_request(message):
    # Conservative fallback: only accept a clear "from A [via B] to C".
    m = re.search(r'\bfrom\s+(.+?)\s+to\s+(.+?)(?=\s+(?:with|considering|including|using|avoiding|prioriti[sz]ing|and\s+(?:water|shelter))\b|[?!;]|$)', message, re.I)
    if not m:
        return None
    start, end = m.group(1).strip(), m.group(2).strip().rstrip('.')
    if re.search(r'\bvia\b', end, re.I):
        return None  # Ambiguous order; ask the user for explicit fields instead.
    places = [part.strip() for part in re.split(r'\s+via\s+', start, flags=re.I)] + [end]
    return places if 2 <= len(places) <= 5 and all(places) else None


def _resolve_place(value):
    if isinstance(value, dict):
        if not {'lat', 'lon'} <= value.keys():
            raise ValueError('Each coordinate needs lat and lon.')
        lat, lon = validate_coords(value['lat'], value['lon'])
        return {'name': str(value.get('name') or f'{lat:.3f}, {lon:.3f}')[:120], 'lat': lat, 'lon': lon, 'source': 'user-selected coordinate'}
    if not isinstance(value, str) or not value.strip() or len(value) > 120:
        raise ValueError('Place names must be non-empty strings of at most 120 characters.')
    name = value.strip()
    match = _COORDS.match(name)
    if match:
        lat, lon = validate_coords(float(match.group(1)), float(match.group(2)))
        return {'name': name, 'lat': lat, 'lon': lon, 'source': 'user-provided coordinate'}
    hits = seeds.search(name, limit=8)
    # The catalogue may store the feature as "Gale" instead of "Gale Crater".
    stripped = re.sub(r'\s+crater$', '', name, flags=re.I)
    if stripped != name:
        stripped_hits = seeds.search(stripped, limit=8)
        if stripped_hits and stripped_hits[0].get('name', '').casefold() == stripped.casefold():
            hits = stripped_hits
    if not hits or hits[0].get('score', 0) < 0.85:
        raise ValueError(f'Could not confidently resolve "{name}". Use a more specific name or latitude, longitude.')
    first = hits[0]
    for alternative in hits[1:]:
        if alternative.get('score', 0) < first['score'] - 0.02:
            break
        if _distance(first, alternative) > 25:
            raise ValueError(f'"{name}" is ambiguous in the gazetteer (different locations have similar names). Provide coordinates or a more specific name.')
    return {'id': first.get('id'), 'name': first['name'], 'lat': first['lat'],
            'lon': first['lon'] % 360, 'source': first.get('src', 'NAM gazetteer'),
            'match_score': first['score']}


def _waypoint_distance(points):
    return sum(_distance(a, b) for a, b in zip(points, points[1:]))


def _choose_resources(places, preference, max_detour_km):
    """Consider up to one water and one shelter stop across all legs.

    Enumerates both orders and positions; maximizes requested resource types,
    then minimizes great-circle extra distance with a modest quality penalty.
    The budget is a pre-screening estimate, NOT a terrain-route guarantee.
    """
    water = resources.find_water() if preference in ('water', 'both') else []
    shelters = resources.find_shelter() if preference in ('shelter', 'both') else []
    baseline = _waypoint_distance(places)
    nlegs = len(places) - 1
    w_options = [None] + [(i, 'water', item) for i in range(nlegs) for item in water]
    s_options = [None] + [(i, 'shelter', item) for i in range(nlegs) for item in shelters]
    best = None
    for w, shelter in itertools.product(w_options, s_options):
        selected = [x for x in (w, shelter) if x is not None]
        # Both same-leg orderings must be assessed, since their detours differ.
        orders = itertools.permutations(selected) if len(selected) == 2 else [tuple(selected)]
        for order in orders:
            stops = []
            for i in range(nlegs):
                stops.append({**places[i], 'kind': 'requested'})
                for leg, kind, item in order:
                    if leg == i:
                        stops.append({'id': item['id'], 'name': item['name'], 'lat': item['lat'],
                                      'lon': item['lon'] % 360, 'kind': kind,
                                      'certainty': item.get('certainty'),
                                      'shelter_score': item.get('composite_index'),
                                      'source': item.get('src') or item.get('provenance', {}).get('source'),
                                      'note': item.get('note', '')})
            stops.append({**places[-1], 'kind': 'requested'})
            detour = max(0.0, _waypoint_distance(stops) - baseline)
            if detour > max_detour_km + 1e-6:
                continue
            quality = sum(({'A': 0, 'B': 8, 'C': 20}.get(x[2].get('certainty'), 0) if x[1] == 'water'
                           else max(0, 100 - x[2].get('composite_index', 0)) * 0.15) for x in selected)
            rank = (-len(selected), detour + quality, detour)
            if best is None or rank < best[0]:
                best = (rank, stops, detour)
    return best[1], best[2], {'water': len(water), 'shelter': len(shelters)}


def plan(places=None, message='', preference='both', max_detour_km=250.0, speed_km_sol=0.12, preset='balanced', use_model=True):
    if preference not in ('none', 'water', 'shelter', 'both'):
        raise ValueError('resource_preference must be none, water, shelter or both.')
    if preset not in routing.PRESETS:
        raise ValueError('preset must be balanced, terrain or speed.')
    for value, label, low, high in ((max_detour_km, 'max_detour_km', 0, 5000), (speed_km_sol, 'speed_km_sol', 0.02, 100)):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{label} must be between {low} and {high}.')
    if len(message) > 2000:
        raise ValueError('Route request is too long (maximum 2000 characters).')
    engine = 'explicit-places'
    model_note = None
    if not places:
        if not message.strip():
            raise ValueError('Provide at least two places, or a request such as "from Jezero to Gale".')
        extracted = llm.extract_route_places(message) if use_model else None
        parsed = _parse_request(message)
        if extracted and parsed:
            # When an explicit from/via/to structure is available, do not let
            # the model silently omit a stop or select text from another part
            # of the request, even if all its proposed names are literal.
            if len(extracted) != len(parsed) or any(
                candidate.casefold() not in expected.casefold()
                for candidate, expected in zip(extracted, parsed)
            ):
                extracted = None
        if extracted:
            places, engine = extracted, 'configured-model-extraction'
        else:
            places, engine = parsed, 'deterministic-extraction'
            model_note = ('Configured model unavailable or could not extract literal place names consistently; '
                          'used the simple from/via/to parser.' if use_model else 'Model extraction disabled.')
        if not places:
            raise ValueError('Could not identify the places. Use "from Jezero to Gale", or provide explicit place names or coordinates.')
    if not isinstance(places, list) or not 2 <= len(places) <= 5:
        raise ValueError('Provide between 2 and 5 ordered places.')
    resolved = [_resolve_place(p) for p in places]
    if any(_distance(a, b) < 0.05 for a, b in zip(resolved, resolved[1:])):
        raise ValueError('Consecutive places must be at least 0.05 km apart.')
    stops, detour, candidates = _choose_resources(resolved, preference, max_detour_km)
    warnings = [
        'Advisory [SIM]: terrain is a synthetic coarse grid, not a validated mobility or safety assessment.',
        'Water candidates are possible ice deposits, not confirmed accessible drinking water. Shelter scores are simulated and sites are unverified.',
        'Detour limit screens great-circle waypoint distances only; it does not constrain the final terrain route.',
        'Weather, mobility, energy, communications, resource extraction and operational safety are not validated.',
    ]
    required = {'water', 'shelter'} if preference == 'both' else ({preference} if preference != 'none' else set())
    included = {stop['kind'] for stop in stops}
    for kind in sorted(required - included):
        warnings.append(f'No {kind} candidate fit the estimated detour limit; the route does not include one.')
    if model_note:
        warnings.append(model_note)
    legs = []
    path = []
    degraded = False
    for a, b in zip(stops, stops[1:]):
        if _distance(a, b) < 0.05:
            continue
        route = routing.plan_route(a['lat'], a['lon'], b['lat'], b['lon'], preset)
        ok = route.get('status') == 'ok' and route.get('stats', {}).get('length_km') is not None
        legs.append({'from': a['name'], 'to': b['name'], 'status': route.get('status'),
                     'stats': route.get('stats'), 'note': route.get('note'), 'provenance': route.get('provenance')})
        if not ok:
            degraded = True
            continue
        # The engine samples a grid; explicitly connect the user-selected endpoints.
        segment = [{'lat': a['lat'], 'lon': a['lon']}] + [{'lat': p['lat'], 'lon': p['lon']} for p in route['path']] + [{'lat': b['lat'], 'lon': b['lon']}]
        if path and _distance(path[-1], segment[0]) < 1e-6:
            segment = segment[1:]
        path.extend(segment)
    if degraded or len(path) < 2:
        warnings.append('At least one terrain leg failed; no continuous route or radiation estimate is presented.')
        return {'status': 'degraded', 'engine': engine, 'model': config_model(engine), 'places': resolved,
                'stops': stops, 'legs': legs, 'path': [], 'warnings': warnings, 'sim': True, 'advisory': True,
                'resource_screen': {'preference': preference, 'candidate_counts': candidates,
                                    'estimated_extra_km': round(detour, 2), 'limit_km': max_detour_km}}
    total = _waypoint_distance(path)
    # Limit integration samples while retaining endpoints. This is an approximation,
    # never a claim that every grid cell has been assessed for radiation.
    stride = max(1, math.ceil((len(path) - 1) / 200))
    samples = path[::stride]
    if samples[-1] != path[-1]:
        samples.append(path[-1])
    radiation = environment.radiation_path(samples, speed_km_sol=speed_km_sol, shielding='rover')
    return {'status': 'ok', 'engine': engine, 'model': config_model(engine), 'places': resolved,
            'stops': stops, 'legs': legs, 'path': path,
            'total_km': round(total, 2), 'estimated_sols': round(total / speed_km_sol, 2),
            'speed_km_sol': speed_km_sol, 'radiation': radiation,
            'resource_screen': {'preference': preference, 'candidate_counts': candidates,
                                'estimated_extra_km': round(detour, 2), 'limit_km': max_detour_km},
            'warnings': warnings, 'sim': True, 'advisory': True,
            'provenance': {'terrain': 'NAM synthetic DEM and A* [SIM]',
                           'water': 'SWIM-consistent curated candidate catalogue [SIM]',
                           'shelter': 'NAM curated shelter scoring [SIM]',
                           'radiation': radiation.get('provenance')}}


def config_model(engine):
    return llm.describe().get('model') if engine == 'configured-model-extraction' else None

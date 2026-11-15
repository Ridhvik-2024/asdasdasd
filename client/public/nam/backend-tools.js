/* Backend-powered tools in NAM's original atlas panels. */
window.NAMBackendTools = function (atlas) {
  'use strict';
  const title = document.getElementById('service-title');
  const content = document.getElementById('service-content');
  let generation = 0;

  function element(tag, text, className) {
    const el = document.createElement(tag);
    if (text != null) el.textContent = String(text);
    if (className) el.className = className;
    return el;
  }
  function note(text) { return element('p', text, 'inspector-note'); }
  function section(label) {
    const div = element('section', null, 'panel-section');
    if (label) div.append(element('h3', label, 'service-label'));
    content.append(div); return div;
  }
  function button(parent, label, fn) {
    const el = element('button', label, 'text-action'); el.type = 'button';
    el.addEventListener('click', async () => {
      el.disabled = true;
      try { await fn(); } catch (err) { status.textContent = `Unable to complete: ${err.message}`; }
      finally { el.disabled = false; }
    });
    parent.append(el); return el;
  }
  function input(parent, placeholder, value = '') {
    const el = element('input', null, 'service-input'); el.placeholder = placeholder; el.value = value;
    el.setAttribute('aria-label', placeholder); parent.append(el); return el;
  }
  function select(parent, options, label) {
    const el = element('select', null, 'service-input'); el.setAttribute('aria-label', label);
    for (const [value, name] of options) { const option = element('option', name); option.value = value; el.append(option); }
    parent.append(el); return el;
  }
  function link(parent, label, url) {
    if (!url) return;
    try {
      const parsed = new URL(url, window.location.origin);
      if (!['http:', 'https:'].includes(parsed.protocol)) return;
      const a = element('a', label, 'external-row'); a.href = parsed.href; a.target = '_blank'; a.rel = 'noopener noreferrer'; parent.append(a);
    } catch (_) { /* Ignore malformed source links. */ }
  }
  async function request(path, options) {
    const response = await fetch(path, options);
    if (!response.ok) {
      let message = `HTTP ${response.status}`;
      try { const body = await response.json(); if (body.detail) message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail); } catch (_) {}
      throw new Error(message);
    }
    return response.json();
  }
  function post(path, body) { return request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); }
  function point() {
    const p = atlas.getPoint();
    if (!p) throw new Error('Select a point on the globe first.');
    return p;
  }
  function waypoints(min = 2) {
    const points = atlas.getRoute();
    if (points.length < min) throw new Error(`Sketch at least ${min} waypoints with the traverse tool first.`);
    return points;
  }
  function query(p) { return `lat=${encodeURIComponent(p.lat)}&lon=${encodeURIComponent(p.lon)}`; }
  function output(parent, label, text) {
    const row = element('div', null, 'service-card');
    row.append(element('strong', label)); if (text) row.append(note(text)); parent.append(row); return row;
  }
  function located(parent, item, detail) {
    const card = output(parent, item.title || item.name || item.id, detail);
    if (Number.isFinite(item.lat) && Number.isFinite(item.lon)) button(card, 'Fly to location', () => atlas.flyTo(item.lat, item.lon, item.title || item.name));
    return card;
  }
  let status;
  function reset(name) {
    generation++; title.textContent = name; content.replaceChildren();
    status = element('p', '', 'small-note'); status.setAttribute('role', 'status'); content.append(status);
    atlas.open();
  }
  function actionOutput(target, label, value) {
    target.replaceChildren(outputElement(label, value));
  }
  function outputElement(label, value) {
    const node = element('div', null, 'service-card'); node.append(element('strong', label), note(value)); return node;
  }
  async function loadList(target, path, key, render) {
    target.textContent = 'Loading…'; const current = generation;
    try {
      const data = await request(path); if (current !== generation) return;
      target.replaceChildren(); const list = data[key] || [];
      if (!list.length) target.append(note('No results found.'));
      list.forEach(item => render(target, item));
    } catch (err) { if (current === generation) target.textContent = `Service unavailable: ${err.message}`; }
  }
  function measurements() {
    reset('Measurements');
    const s = section('Traverse analysis'); s.append(note('Sketch a traverse on the globe first. Terrain results use the synthetic DEM [SIM].'));
    const results = element('div'); s.append(results);
    button(s, 'Path distance', async () => { const d = await post('/measure/path_distance', {points: waypoints()}); actionOutput(results, 'Distance', `${d.distance_km} km · ${d.method}`); });
    button(s, 'Elevation profile [SIM]', async () => { const d = await post('/measure/profile', {points: waypoints()}); actionOutput(results, 'Elevation profile [SIM]', `${d.total_km} km · ${d.min_elev_m} to ${d.max_elev_m} m · gain ${d.elevation_gain_m} m`); });
    button(s, 'Crater diameter [SIM]', async () => { const p = waypoints(); const d = await post('/measure/crater', {rim_a: p[0], rim_b: p[p.length - 1]}); actionOutput(results, 'Crater diameter', `${d.diameter_km} km · depth model is an estimate [SIM].`); });
    button(s, 'Area', async () => { const d = await post('/measure/area', {polygon: waypoints(3)}); actionOutput(results, 'Surface area', `${d.area_km2} km²`); });
    button(s, 'Elevation difference [SIM]', async () => { const p = waypoints(); const d = await post('/measure/elevation_difference', {a:p[0], b:p[p.length-1]}); actionOutput(results, 'Elevation difference [SIM]', `${d.difference_m} m`); });
    button(s, 'Terrain route [SIM]', async () => { const p = waypoints(); const a=p[0], b=p[p.length-1]; const d=await post('/measure/route_distance',{from_lat:a.lat,from_lon:a.lon,to_lat:b.lat,to_lon:b.lon,preset:'balanced'}); if (d.status === 'degraded') { actionOutput(results, 'Route unavailable [SIM]', d.note || 'Routing degraded; no terrain route was produced.'); return; } actionOutput(results, 'Terrain route [SIM]', `${d.length_km} km · maximum slope ${d.max_slope_deg ?? 'unavailable'}°. Advisory only.`); if (d.path_preview?.length >= 2) atlas.showRoute(d.path_preview); });
    const t = section('Selected point'); t.append(note('Select a point on the globe for solar angles or a simulated terrain model.'));
    const res = element('div'); t.append(res);
    button(t, 'Solar angles', async () => { const d = await post('/measure/solar', {...point(), iso_time: new Date().toISOString()}); actionOutput(res, 'Solar illumination', `Elevation ${d.sun_elevation_deg}° · azimuth ${d.sun_azimuth_deg}°`); });
    button(t, 'Download STL [SIM]', async () => {
      const response = await fetch('/measure/stl', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({...point(), radius_km:20, vertical_scale:5, n:64})});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const url = URL.createObjectURL(await response.blob()); const a = document.createElement('a'); a.href = url; a.download = 'nam-terrain-sim.stl'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = 'Synthetic terrain STL downloaded [SIM].';
    });
  }
  function science() {
    reset('Science'); const s = section('Cited discoveries');
    const filter = input(s, 'Search discoveries'); const list = element('div');
    button(s, 'Search', () => loadList(list, `/discoveries?q=${encodeURIComponent(filter.value)}`, 'discoveries', (parent, d) => {
      const card = located(parent, d, `${d.summary} Citation: ${d.evidence?.citation || 'Not provided'}`); link(card, 'Source ↗', d.evidence?.url);
    })); s.append(list);
    loadList(list, '/discoveries', 'discoveries', (parent, d) => { const card = located(parent, d, `${d.summary} Citation: ${d.evidence?.citation || 'Not provided'}`); link(card, 'Source ↗', d.evidence?.url); });
    const c = section('Scientific catalogues'); const list2 = element('div');
    const catalogs = [['/layers','layers','Layers'], ['/datasets','datasets','Datasets'], ['/science/orbiters','orbiters','Orbiters'], ['/science/instruments','instruments','Instruments'], ['/science/spectral_targets','spectral_targets','Spectral targets']];
    for (const [path,key,label] of catalogs) button(c, label, () => loadList(list2, path, key, (parent, item) => { const card = output(parent, item.title || item.name || item.id, item.description || item.source || item.mission || ''); link(card, 'Source ↗', item.url); })); c.append(list2);
    const compare = section('Compare landing sites [SIM]'); const one = select(compare, [], 'First landing site'), two = select(compare, [], 'Second landing site'); const comparison = element('div');
    request('/sites').then(data => { for (const site of data.sites) { for (const menu of [one,two]) { const opt=element('option',site.name); opt.value=site.id; menu.append(opt); } } if (two.options.length > 1) two.selectedIndex=1; }).catch(err => { comparison.textContent = `Sites unavailable: ${err.message}`; });
    button(compare, 'Compare sites', async () => { if (!one.value || !two.value || one.value === two.value) throw new Error('Choose two different landing sites.'); const data=await request(`/sites/compare?ids=${encodeURIComponent(`${one.value},${two.value}`)}`); comparison.replaceChildren(); data.comparison.forEach(site => located(comparison, site, `Elevation ${site.elevation_m} m [SIM] · ${site.cited_discoveries} cited discoveries · ${site.panoramas_available} panoramas`)); }); compare.append(comparison);
  }
  function panoramas() {
    reset('Rover panoramas'); const s = section('NASA / JPL catalogue');
    s.append(note('Catalogue positions may be approximate. Source links open the original NASA galleries; images are not simulated panoramas.'));
    const list = element('div'); s.append(list);
    loadList(list, '/panoramas', 'panoramas', (parent, p) => { const card = located(parent, p, `${p.rover} · Sol ${p.sol ?? '—'} · ${p.credit} · pose: ${p.pose_confidence}`); link(card, 'Open source gallery ↗', p.source_url); });
  }
  function bookmarks() {
    reset('Bookmarks'); const s = section('Saved locations');
    const list = element('div'); s.append(list);
    async function render() {
      list.textContent = 'Loading…';
      try { const data = await request('/bookmarks'); list.replaceChildren(); if (!data.length) list.append(note('No saved bookmarks. Select a point and save it from the inspector.'));
        data.forEach(b => { const card = located(list, b, `${b.lat.toFixed(3)}°, ${b.lon.toFixed(3)}°`); button(card, 'Delete', async () => { await request(`/bookmarks/${encodeURIComponent(b.id)}`, {method:'DELETE'}); await render(); }); });
      } catch (err) { list.textContent = `Service unavailable: ${err.message}`; }
    }
    render();
  }
  function missions() {
    reset('Missions'); const s = section('Create mission [SIM]');
    s.append(note('The current sketch is saved as mission stops. Plans are advisory, not safety assessments.'));
    const name = input(s, 'Mission name'); const type = select(s, [['route','Route'],['survey','Survey'],['area','Area'],['evacuation','Evacuation']], 'Mission type');
    const listSection = section('Saved missions'); const list = element('div'); listSection.append(list);
    async function render() {
      list.textContent = 'Loading…';
      try { const data = await request('/missions'); const details = await Promise.all(data.missions.map(m => request(`/missions/${encodeURIComponent(m.id)}`))); list.replaceChildren();
        if (!details.length) list.append(note('No missions saved yet.'));
        details.forEach(m => {
          const card = output(list, m.name, `${m.type} · ${m.stops.length} stops · ${m.routes.length} routes · advisory [SIM]`);
          if (m.stops.length) button(card, 'Show stops', () => { atlas.showRoute(m.stops); atlas.flyTo(m.stops[0].lat, m.stops[0].lon, m.name); });
          if (m.routes.length && m.routes[m.routes.length-1].path?.length) button(card, 'Show planned route', () => atlas.showRoute(m.routes[m.routes.length-1].path));
          if (m.stops.length >= 2) button(card, 'Plan terrain route [SIM]', async () => {
            const a=m.stops[0], b=m.stops[m.stops.length-1];
            const result = await post(`/missions/${encodeURIComponent(m.id)}/route`, {from_lat:a.lat,from_lon:a.lon,to_lat:b.lat,to_lon:b.lon,preset:'balanced'});
            status.textContent = result.status === 'degraded' ? 'Route degraded; check mission details. [SIM]' : 'Route calculated [SIM].'; await render();
          });
          if (m.stops.length >= 2) button(card, 'Mission profile [SIM]', async () => { const d=await request(`/missions/${encodeURIComponent(m.id)}/profile`); status.textContent=`Mission profile [SIM]: ${d.profile.total_km} km · elevation gain ${d.profile.elevation_gain_m} m · radiation ${d.radiation.total_msv} mSv. Advisory only.`; });
          if (m.stops.length >= 3) button(card, 'Optimize stops [SIM]', async () => { await post(`/missions/${encodeURIComponent(m.id)}/optimize`, {preset:'balanced'}); await render(); });
          link(card, 'Export GeoJSON ↗', `/missions/${encodeURIComponent(m.id)}/geojson`); link(card, 'Export KML ↗', `/missions/${encodeURIComponent(m.id)}/kml`); link(card, 'Export CSV ↗', `/missions/${encodeURIComponent(m.id)}/csv`);
          button(card, 'Delete mission', async () => { await request(`/missions/${encodeURIComponent(m.id)}`, {method:'DELETE'}); await render(); });
        });
      } catch (err) { list.textContent = `Service unavailable: ${err.message}`; }
    }
    button(s, 'Save mission', async () => { const stops = atlas.getRoute().map(p => ({...p,activity:'observe',reason:'Atlas waypoint'})); await post('/missions', {name:name.value.trim() || 'Mars mission',type:type.value,objective:'Atlas mission',stops}); name.value = ''; status.textContent = 'Mission saved [SIM].'; await render(); });
    render();
  }
  function environment() {
    reset('Environment'); const s = section('Selected point [SIM]'); s.append(note('Estimates, resource scores, storm scenarios and presence are advisory simulations. Select a point to begin.'));
    const results = element('div'); s.append(results);
    button(s, 'Radiation estimate', async () => { const d=await request(`/environment/radiation?${query(point())}`); actionOutput(results,'Radiation [SIM]', `${d.total_msv} mSv per ${d.duration_sols} sol(s) · uncertainty ±${d.uncertainty_band_pct}%`); });
    button(s, 'Simulate MY34 dust storm', async () => { const d=await post('/environment/storms/simulate',{kind:'dust',scale_or_class:'my34',...point()}); actionOutput(results, 'Dust storm simulation [SIM]', d.label); });
    button(s, 'Simulate X-class SEP', async () => { const d=await post('/environment/storms/simulate',{kind:'sep',scale_or_class:'X',...point()}); actionOutput(results, 'Storm simulation [SIM]', d.label); });
    button(s, 'Storm response plan', async () => { const d=await post('/environment/storm_response',{...point(),severity:'X'}); actionOutput(results,'Storm response [SIM]', `${d.stops?.length || 0} stops · ${d.total_length_km ?? 'unavailable'} km. Advisory only.`); });
    const resources = section('Resources & presence'); const list = element('div');
    button(resources, 'Water candidates', () => loadList(list, '/water', 'candidates', (p,d) => located(p,d,`Certainty ${d.certainty} · ${d.stability || ''} · ${d.src || ''}`)));
    button(resources, 'Shelter candidates', () => loadList(list, '/shelters', 'shelters', (p,d) => located(p,d,`Score ${d.composite_index} [SIM] · ${d.note || ''}`)));
    button(resources, 'Presence [SIM]', () => loadList(list, '/presence/agents', 'agents', (p,d) => located(p,d,`${d.role} · ${d.status}`)));
    button(resources, 'Spatial nodes', () => loadList(list, '/nodes', 'nodes', (p,d) => located(p,d,`${d.type} · ${d.props?.name || d.id}`)));
    button(resources, 'Add waypoint node', async () => { await post('/nodes',{...point(),type:'waypoint',props:{name:'Atlas waypoint'}}); status.textContent = 'Waypoint node saved.'; });
    resources.append(list);
  }
  function aiRoute() {
    reset('JEV route planner');
    const s = section('Plan with resources [SIM]');
    s.append(note('Describe a journey such as “from Jezero to Gale”, or enter ordered places below. The model extracts names only; the backend calculates the route. Use the controls to set resource preferences and limits.'));
    const modelState = note('Checking local model…'); s.append(modelState);
    request('/jev/benchmark').then(d => {
      const model = d.adapter?.model || 'configured model';
      modelState.textContent = d.model_status === 'ready' ? `Configured model ready: ${model}.` :
        d.model_status === 'missing_model' ? `Model server is reachable, but ${model} is not installed. Using the simple parser.` :
        d.model_status === 'disabled' ? 'Local model disabled. Using the simple parser.' :
        'Local model unavailable. Using the simple from/via/to parser; see the README to set up Ollama.';
    }).catch(() => { modelState.textContent = 'Could not check local model status.'; });
    const message = input(s, 'Route request', '');
    const start = input(s, 'Start place or lat, lon', '');
    const end = input(s, 'Destination place or lat, lon', '');
    const preference = select(s, [['both','Consider water and shelter'],['water','Consider water'],['shelter','Consider shelter'],['none','No resource detours']], 'Resource preference');
    const detour = input(s, 'Maximum estimated detour (km)', '250'); detour.type = 'number'; detour.min = '0'; detour.max = '5000';
    const speed = input(s, 'Assumed travel speed (km per sol)', '0.12'); speed.type = 'number'; speed.min = '0.02'; speed.max = '100'; speed.step = '0.01';
    s.append(note('Detour is an approximate great-circle screening limit, not a guarantee for the terrain route. Candidate ice and shelters are unverified.'));
    const result = element('div'); s.append(result);
    async function run(places) {
      const maxDetour = Number(detour.value), travelSpeed = Number(speed.value);
      if (!detour.value || !speed.value || !Number.isFinite(maxDetour) || !Number.isFinite(travelSpeed)) throw new Error('Enter a valid detour and travel speed.');
      if (!places && (!!start.value.trim() !== !!end.value.trim())) throw new Error('Enter both start and destination, or neither.');
      const explicit = places || (start.value.trim() && end.value.trim() ? [start.value.trim(), end.value.trim()] : []);
      if (!explicit.length && !message.value.trim()) throw new Error('Describe the route or enter both places.');
      result.replaceChildren(note('Planning on the synthetic terrain grid; this may take a while…'));
      const d = await post('/jev/route-plan', { message: message.value.trim(), places: explicit, resource_preference: preference.value,
        max_detour_km: maxDetour, speed_km_sol: travelSpeed, preset: 'balanced', use_model: true });
      result.replaceChildren();
      const method = d.engine === 'configured-model-extraction' ? `Configured model: ${d.model}` : d.engine === 'explicit-places' ? 'Explicit places (no model needed)' : 'Simple parser (local model not used)';
      const summary = d.status === 'ok' ? `${d.total_km} km · ${d.estimated_sols} sols at ${d.speed_km_sol} km/sol · ${d.radiation.total_msv} mSv [SIM] · ${method}` : `Route degraded; no continuous path was calculated. ${method}`;
      const card = output(result, 'Route assessment [SIM]', summary);
      card.append(note(`Resource screening: ${d.resource_screen.preference}; estimated extra ${d.resource_screen.estimated_extra_km} km of ${d.resource_screen.limit_km} km budget.`));
      for (const stop of d.stops) {
        const detail = stop.kind === 'water' ? `Water candidate · certainty ${stop.certainty} · ${stop.source || 'catalogue'}` :
          stop.kind === 'shelter' ? `Shelter candidate · score ${stop.shelter_score} [SIM] · ${stop.source || 'catalogue'}` : `Requested location · ${stop.source || 'user input'}`;
        located(result, stop, detail);
      }
      if (d.status === 'ok' && d.path.length >= 2) {
        atlas.showPlan(d.path, d.stops);
        atlas.flyTo(d.path[0].lat, d.path[0].lon, d.stops[0].name);
        button(card, 'Show route on globe', () => atlas.showPlan(d.path, d.stops));
        button(card, 'Hide route', () => atlas.clearPlan());
        button(card, 'Export route GeoJSON', () => {
          const feature = {type:'Feature', properties:{name:'JEV resource-aware route [SIM]', advisory:true, total_km:d.total_km, resource_screen:d.resource_screen, stops:d.stops, warnings:d.warnings}, geometry:{type:'LineString', coordinates:d.path.map(p=>[p.lon,p.lat])}};
          const url = URL.createObjectURL(new Blob([JSON.stringify(feature,null,2)],{type:'application/geo+json'})); const a=document.createElement('a'); a.href=url; a.download='nam-jev-route-sim.geojson'; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
        });
      } else atlas.clearPlan();
      const cautions = output(result, 'Limitations & provenance', null);
      for (const warning of d.warnings) cautions.append(note(warning));
    }
    button(s, 'Plan route', () => run(null));
    button(s, 'Plan current traverse', () => { const points = waypoints(); if (points.length > 5) throw new Error('Use at most five traverse points.'); return run(points); });
  }
  function jev() {
    reset('JEV assistant'); const s = section('Ask about Mars');
    s.append(note('Answers use backend tools and may include simulated estimates. Select a point to provide map context.'));
    button(s, 'Open resource-aware route planner', aiRoute);
    const field = input(s, 'Ask JEV', ''); const reply = element('div'); s.append(reply);
    button(s, 'Send', async () => {
      const message=field.value.trim(); if (!message) throw new Error('Enter a question first.');
      reply.replaceChildren(note('Thinking…'));
      const p=atlas.getPoint(); const response=await fetch('/jev/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message,map_context:p ? {center:{lat:p.lat,lon:p.lon}} : {}})});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const raw=await response.text(); let done;
      for (const line of raw.split('\n')) if (line.startsWith('data: ')) { const event=JSON.parse(line.slice(6)); if (event.type === 'done') done=event; }
      if (!done) throw new Error('Incomplete JEV response.');
      reply.replaceChildren(); const card=output(reply,'JEV',done.reply);
      card.append(note(`Engine: ${done.engine === 'local-llm' || done.engine === 'configured-model-extraction' ? 'configured model with backend tools' : 'deterministic fallback (no local model used)'}`));
      if (done.citations?.length) card.append(note(`Sources: ${done.citations.join(' · ')}`));
      for (const intent of done.intents || []) {
        if (intent.action === 'show_route' && Array.isArray(intent.path) && intent.path.length >= 2 && Array.isArray(intent.stops)) { atlas.showPlan(intent.path,intent.stops); atlas.flyTo(intent.path[0].lat,intent.path[0].lon,intent.stops[0]?.name); button(card, 'Hide route', () => atlas.clearPlan()); }
        else if (intent.action === 'fly_to' && Number.isFinite(intent.lat) && Number.isFinite(intent.lon)) atlas.flyTo(intent.lat,intent.lon,intent.label);
        else if (intent.action === 'activate_layer' && !atlas.activateLayer(intent.layer_id)) card.append(note(`Layer ${intent.layer_id} is not available on this atlas.`));
      }
    });
  }
  const views = {measure:measurements, science, panoramas, missions, environment, bookmarks, 'ai-route':aiRoute, jev};
  return {show: (name) => { if (views[name]) views[name](); }};
};

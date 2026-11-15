/* NAM — Navigation Assistance for Mars · homepage hero.
   A real WebGL sphere rendered with a ray/sphere intersection shader using the
   locally bundled Viking MDIM 2.1 global colour mosaic — stitched from the
   very tile service the CesiumJS atlas streams, so the homepage planet and
   the atlas globe are the same Mars in the same OG colours. The planet is
   shown fully lit: soft depth shading, texture-driven relief (craters and
   canyons read from the real geology), polar frost and a thin dusty limb —
   no heavy dark vignette. A procedural starfield sits behind the hero;
   selecting the planet or the button recedes every other UI element and the
   live planet floats to the centre of the screen as a smaller globe before
   the atlas fades in around it.

   Movement is driven by the reference animation spec
   (marswalk_specs/01-animations/js-camera-motion.js, prototype 0.3):
   continuous 0.105 rad/s rotation in the shader, cursor tilt with release
   momentum (inertiaSpin 0.84 decay), controlled follow rate
   (maximumMovementRatio 0.05) and a requestAnimationFrame-batched exponential
   wheel / trackpad-pinch zoom (exp(deltaY × k) with inertiaZoom 0.65 momentum). */
(() => {
  "use strict";
  const home = document.getElementById("mars-home");
  const app = document.querySelector(".map-app");
  const planetButton = document.getElementById("planet-launch");
  const fallbackPlanet = document.getElementById("hero-planet");
  const canvas = document.getElementById("mars-webgl");
  const starCanvas = document.getElementById("home-stars");
  const enterButton = document.getElementById("enter-atlas");
  if (!home || !app || !planetButton || !fallbackPlanet || !canvas || !enterButton) return;

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const coordsBlock = document.querySelector(".home-coordinates");
  let entering = false;
  let gl = null;
  let animationFrame = 0;
  let program = null;
  let startTime = 0;
  let pointerX = 0;
  let pointerY = 0;
  let targetX = 0;
  let targetY = 0;
  let parallaxX = 0;
  let parallaxY = 0;
  let resizeObserver = null;
  let marsTexture = null;
  let textureReady = false;
  let zoomLevel = 1;
  let zoomTarget = 1;

  /* ---- Movement constants — from the reference animation spec ----------
     marswalk_specs/01-animations/js-camera-motion.js (prototype 0.3):
     SPIN_INERTIA 0.84  ← controls.inertiaSpin: tilt momentum decay
     ZOOM_INERTIA 0.65  ← controls.inertiaZoom: zoom momentum decay
     MOVE_RATIO  0.055  ← controls.maximumMovementRatio (0.05): the tilt
                          moves at most ~5% of the remaining distance/frame
     ZOOM_CURVE  0.0012 ← the atlas pinch curve exp(deltaY × 0.0024) scaled
                          to the hero's narrow zoom envelope; |ΔY| < 0.01
                          is ignored and deltas are rAF-batched, exactly
                          like installTrackpadPinchZoom
     The tilt input range [-1, 1] maps to ~±13° in the shader — always far
     inside the spec's maximumTiltAngle (π/2, never tilt under the horizon). */
  const SPIN_INERTIA = 0.84;
  const ZOOM_INERTIA = 0.65;
  const MOVE_RATIO = 0.055;
  const ZOOM_CURVE = 0.0012;
  const ZOOM_MIN = 0.92;
  const ZOOM_MAX = 1.42;
  let tiltVX = 0;
  let tiltVY = 0;
  let zoomVel = 0;
  let wheelQueue = 0;
  let wheelFrame = false;
  let pointerInside = false;
  let handoff = false;

  /* Focus hand-off from the homepage: the live planet itself drifts to the
     centre of the screen as a smaller globe while every other UI element
     recedes; only when the Mars is alone in focus does the atlas fade in
     around it. The homepage and atlas show the same Mars — the homepage
     texture is stitched from the very tile service the atlas streams. */
  function enterAtlas() {
    if (entering) return;
    entering = true;
    pointerInside = false;
    targetX = 0;
    targetY = 0;
    // Compute the morph target from the live layout: the button's current
    // (zoomed) box drifts so its centre lands on the viewport centre, scaled
    // to ~42% of the smaller viewport side.
    const rect = planetButton.getBoundingClientRect();
    const focusSize = Math.min(window.innerWidth, window.innerHeight) * 0.42;
    planetButton.style.setProperty("--fx", `${(window.innerWidth / 2 - rect.left - rect.width / 2).toFixed(1)}px`);
    planetButton.style.setProperty("--fy", `${(window.innerHeight / 2 - rect.top - rect.height / 2).toFixed(1)}px`);
    planetButton.style.setProperty("--fs", (focusSize / Math.max(rect.width, 1)).toFixed(4));
    home.classList.add("is-focusing");
    // The render loop keeps running during the morph — the same rotating
    // planet floats inward instead of being replaced by another Mars.
    const focusDelay = reducedMotion ? 420 : 1250;
    window.setTimeout(() => {
      app.classList.add("is-entered");
      // The atlas listens for this and flies the camera in behind the fade.
      document.dispatchEvent(new CustomEvent("nam:enter-atlas"));
      // Hold the focused Mars on screen until the atlas globe is actually
      // showing the same imagery, then crossfade the live planet into it.
      let faded = false;
      const fadeHome = () => {
        if (faded) return;
        faded = true;
        handoff = true;
        if (animationFrame) cancelAnimationFrame(animationFrame);
        animationFrame = 0;
        home.classList.add("is-entering");
        window.setTimeout(() => {
          home.hidden = true;
          stopStarfield();
          const globeCanvas = document.querySelector("#cesiumContainer canvas");
          if (globeCanvas) globeCanvas.focus?.();
        }, reducedMotion ? 120 : 950);
      };
      const startFade = () => window.setTimeout(fadeHome, reducedMotion ? 0 : 260);
      if (window.__NAM_GLOBE_READY) startFade();
      else {
        document.addEventListener("nam:atlas-globe-ready", startFade, { once: true });
        window.setTimeout(fadeHome, reducedMotion ? 1200 : 5200);
      }
    }, focusDelay);
  }
  if (new URLSearchParams(location.search).get("atlas") === "1") {
    // Return from the operations workspace directly to the atlas.
    window.addEventListener("DOMContentLoaded", enterAtlas, { once: true });
  }
  enterButton.addEventListener("click", enterAtlas);
  planetButton.addEventListener("click", enterAtlas);

  /* Interactive inspection zoom — the atlas's trackpad pinch handler applied
     to the homepage planet: wheel and ctrl/meta+wheel (trackpad pinch) both
     queue their deltas and one requestAnimationFrame applies
     exp(deltaY × ZOOM_CURVE) per batch, clamped to the zoom envelope.
     Applied through a CSS variable so hover/enter transforms keep working. */
  function applyWheelZoom() {
    wheelFrame = false;
    if (entering) { wheelQueue = 0; return; }
    const deltaY = wheelQueue;
    wheelQueue = 0;
    if (Math.abs(deltaY) < 0.01) return;
    // The atlas curve multiplies camera HEIGHT (exp(deltaY × k) < 1 ⇒ closer);
    // the hero multiplies CSS SIZE (bigger ⇒ closer), so the sign is flipped
    // to keep the natural direction: wheel up / pinch-out zooms in.
    const scale = Math.exp(-deltaY * ZOOM_CURVE);
    zoomTarget = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoomTarget * scale));
    if (reducedMotion) {
      zoomLevel = zoomTarget;
      planetButton.style.setProperty("--planet-scale", zoomLevel.toFixed(4));
    } else {
      // Inertial glide (inertiaZoom 0.65): a quick burst keeps easing for a
      // few frames after the wheel stops.
      zoomVel = Math.max(-0.02, Math.min(0.02, zoomVel + Math.log(scale) * 0.02));
    }
  }
  planetButton.addEventListener("wheel", (event) => {
    if (entering) return;
    event.preventDefault();
    // Delta-mode normalisation from the spec's pinch handler.
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? window.innerHeight : 1;
    wheelQueue += event.deltaY * unit;
    if (!wheelFrame) {
      wheelFrame = true;
      window.requestAnimationFrame(applyWheelZoom);
    }
  }, { passive: false });

  // A ray/sphere-intersection sphere. The albedo comes from the bundled real
  // Mars texture; relief, craters, frost and haze are computed on the GPU.
  const vertexSource = `
    attribute vec2 a_position;
    varying vec2 v_uv;
    void main() {
      v_uv = a_position * 0.5 + 0.5;
      gl_Position = vec4(a_position, 0.0, 1.0);
    }
  `;
  const fragmentSource = `
    precision highp float;
    varying vec2 v_uv;
    uniform vec2 u_resolution;
    uniform float u_time;
    uniform vec2 u_pointer;
    uniform float u_motion;
    uniform vec2 u_texel;
    uniform sampler2D u_marsTexture;

    float hash31(vec3 p) {
      p = fract(p * 0.1031);
      p += dot(p, p.yzx + 33.33);
      return fract((p.x + p.y) * p.z);
    }
    float noise3(vec3 x) {
      vec3 i = floor(x), f = fract(x);
      f = f * f * (3.0 - 2.0 * f);
      return mix(mix(mix(hash31(i), hash31(i+vec3(1.0,0.0,0.0)),f.x),
                      mix(hash31(i+vec3(0.0,1.0,0.0)),hash31(i+vec3(1.0,1.0,0.0)),f.x),f.y),
                 mix(mix(hash31(i+vec3(0.0,0.0,1.0)),hash31(i+vec3(1.0,0.0,1.0)),f.x),
                      mix(hash31(i+vec3(0.0,1.0,1.0)),hash31(i+vec3(1.0,1.0,1.0)),f.x),f.y),f.z);
    }
    float fbm(vec3 p) {
      float v = 0.0, a = 0.5;
      for (int i=0; i<5; i++) { v += a * noise3(p); p *= 2.03; a *= 0.5; }
      return v;
    }

    void main() {
      vec2 centered = (v_uv - 0.5) * 2.0;
      centered.x *= u_resolution.x / u_resolution.y;
      float r2 = dot(centered, centered);
      if (r2 > 1.0) discard;
      float z = sqrt(max(0.0, 1.0 - r2));
      vec3 n = normalize(vec3(centered.x, centered.y, z));

      float yaw = u_time * 0.105 + u_pointer.x * 0.22;
      float pitch = u_pointer.y * 0.12;
      mat3 ry = mat3(cos(yaw),0.0,-sin(yaw), 0.0,1.0,0.0, sin(yaw),0.0,cos(yaw));
      mat3 rx = mat3(1.0,0.0,0.0, 0.0,cos(pitch),sin(pitch), 0.0,-sin(pitch),cos(pitch));
      vec3 p = rx * ry * n;

      // Equirectangular Mars albedo: real global geology (Valles Marineris,
      // Olympus Mons, the great dark provinces) plus GPU-derived relief.
      vec2 marsUV = vec2(atan(p.z, p.x) / 6.2831853 + 0.5,
                         asin(clamp(p.y, -1.0, 1.0)) / 3.14159265 + 0.5);
      vec3 tex = texture2D(u_marsTexture, marsUV).rgb;
      float h  = dot(tex, vec3(0.299, 0.587, 0.114));
      float hx = dot(texture2D(u_marsTexture, marsUV + vec2(u_texel.x, 0.0)).rgb, vec3(0.299, 0.587, 0.114));
      float hy = dot(texture2D(u_marsTexture, marsUV + vec2(0.0, u_texel.y)).rgb, vec3(0.299, 0.587, 0.114));

      // Planet-space tangents: height gradients tilt the surface normal so the
      // real craters and canyon walls catch the light.
      vec3 east = vec3(-p.z, 0.0, p.x);
      float eastLen = max(length(east), 1e-4);
      east /= eastLen;
      vec3 north = vec3(-p.y * p.x / max(p.x * p.x + p.z * p.z, 1e-4), 1.0, -p.y * p.z / max(p.x * p.x + p.z * p.z, 1e-4));
      float northLen = max(length(north), 1e-4);
      north /= northLen;
      float reliefK = 2.8;
      vec3 bumped = normalize(p - east * (hx - h) * reliefK - north * (hy - h) * reliefK);

      // Procedural crater rings and fine regolith, subtle over the real albedo.
      float cr1 = fbm(p * 16.0 + vec3(5.2, 1.3, 7.7));
      float cr2 = fbm(p * 34.0 + vec3(2.2, 8.1, 3.3));
      float craterShade = (smoothstep(0.52, 0.62, cr1) - smoothstep(0.62, 0.72, cr1)) * 0.085
                        + (smoothstep(0.55, 0.60, cr2) - smoothstep(0.60, 0.68, cr2)) * 0.045;
      float fine = noise3(p * 125.0);
      float relief = (h - 0.42) * 0.10 + craterShade + (fine - 0.5) * 0.016;
      vec3 albedo = tex * (1.0 + relief);

      // Polar frost: the MDIM mosaic already carries the real polar caps, so
      // the procedural cap only gently brightens the frozen edges.
      float capEdge = smoothstep(0.855, 0.965, abs(p.y));
      float capNoise = 0.55 + 0.45 * fbm(p * 9.0 + vec3(3.1, 1.9, 0.7));
      float capMask = capEdge * capNoise * 0.30;
      albedo = mix(albedo, vec3(0.93, 0.90, 0.86), capMask);

      // Atlas-matched colour: the Viking MDIM 2.1 albedo renders nearly raw
      // — the same palette the Cesium globe shows — with only a soft depth
      // shade so the disc still reads as a sphere.
      vec3 lightView = normalize(vec3(-0.40, 0.26, 0.88));
      mat3 invRy = mat3(cos(yaw),0.0,sin(yaw), 0.0,1.0,0.0, -sin(yaw),0.0,cos(yaw));
      mat3 invRx = mat3(1.0,0.0,0.0, 0.0,cos(pitch),-sin(pitch), 0.0,sin(pitch),cos(pitch));
      vec3 lightPlanet = invRy * invRx * lightView;
      float diff = clamp((dot(bumped, lightPlanet) + 0.55) / 1.55, 0.0, 1.0);
      float shade = 0.58 + diff * 0.46;
      float limb = mix(1.0, 0.97, smoothstep(0.3, 1.0, r2));
      vec3 color = albedo * shade * limb;

      // Limb haze matching the atlas globe's OG ground-atmosphere glow.
      float rim = pow(1.0 - z, 3.0);
      color += vec3(0.70, 0.44, 0.30) * rim * 0.14;
      color = mix(color, vec3(0.93, 0.87, 0.82), rim * 0.16);
      gl_FragColor = vec4(color, 1.0);
    }
  `;

  function compileShader(type, source) {
    const shader = gl.createShader(type);
    gl.shaderSource(shader, source);
    gl.compileShader(shader);
    if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
      const message = gl.getShaderInfoLog(shader) || "Unknown shader compilation error";
      gl.deleteShader(shader);
      throw new Error(message);
    }
    return shader;
  }

  function initWebGL() {
    try {
      gl = canvas.getContext("webgl", { alpha: true, antialias: true, powerPreference: "high-performance" }) ||
           canvas.getContext("experimental-webgl", { alpha: true, antialias: true });
      if (!gl) throw new Error("WebGL is unavailable in this browser.");
      const vertex = compileShader(gl.VERTEX_SHADER, vertexSource);
      const fragment = compileShader(gl.FRAGMENT_SHADER, fragmentSource);
      program = gl.createProgram();
      gl.attachShader(program, vertex);
      gl.attachShader(program, fragment);
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program) || "WebGL program link failed.");
      gl.useProgram(program);
      // Load the locally bundled high-detail Mars albedo texture. It is served
      // with the site, so the hero does not depend on a third-party image host.
      marsTexture = gl.createTexture();
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, marsTexture);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 1, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE,
                    new Uint8Array([118, 55, 35, 255]));
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.uniform1i(gl.getUniformLocation(program, "u_marsTexture"), 0);
      gl.uniform2f(gl.getUniformLocation(program, "u_texel"), 1 / 4096, 1 / 2048);
      const surfaceImage = new Image();
      surfaceImage.onload = () => {
        if (!gl || !marsTexture) return;
        gl.bindTexture(gl.TEXTURE_2D, marsTexture);
        gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
        // WebGL 1 cannot mipmap/REPEAT a non-power-of-two texture (it samples
        // as solid black). Normalise the source to a power-of-two
        // equirectangular through a 2D canvas when needed.
        let source = surfaceImage;
        const isPOT = (n) => (n & (n - 1)) === 0;
        if (!isPOT(surfaceImage.width) || !isPOT(surfaceImage.height)) {
          const pot = document.createElement("canvas");
          pot.width = 2048;
          pot.height = 1024;
          pot.getContext("2d").drawImage(surfaceImage, 0, 0, 2048, 1024);
          source = pot;
        }
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
        gl.generateMipmap(gl.TEXTURE_2D);
        gl.uniform2f(gl.getUniformLocation(program, "u_texel"), 1 / source.width, 1 / source.height);
        textureReady = true;
      };
      // Primary texture: the Viking MDIM 2.1 global colour mosaic stitched
      // from the same tile service the atlas streams, so the homepage planet
      // and the atlas globe are the same Mars in the same OG colours. The
      // earlier homepage texture remains bundled as a graceful fallback.
      surfaceImage.onerror = () => {
        if (surfaceImage.dataset.stage === "mdim") {
          surfaceImage.dataset.stage = "legacy";
          surfaceImage.src = "/nam/assets/mars-surface-texture.png";
          return;
        }
        console.warn("NAM: bundled Mars texture could not be loaded; procedural fallback remains active.");
      };
      surfaceImage.dataset.stage = "mdim";
      surfaceImage.src = "/nam/assets/mars-surface-texture.jpg";
      const buffer = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, -1,1, 1,-1, 1,1]), gl.STATIC_DRAW);
      const position = gl.getAttribLocation(program, "a_position");
      gl.enableVertexAttribArray(position);
      gl.vertexAttribPointer(position, 2, gl.FLOAT, false, 0, 0);
      gl.uniform2f(gl.getUniformLocation(program, "u_pointer"), 0, 0);
      canvas.classList.add("is-webgl-ready");
      fallbackPlanet.hidden = true;
      resize();
      if ("ResizeObserver" in window) {
        resizeObserver = new ResizeObserver(resize);
        resizeObserver.observe(planetButton);
      } else window.addEventListener("resize", resize, { passive: true });
      canvas.addEventListener("webglcontextlost", (event) => {
        event.preventDefault();
        if (animationFrame) cancelAnimationFrame(animationFrame);
        canvas.classList.remove("is-webgl-ready");
        fallbackPlanet.hidden = false;
      });
      startTime = performance.now();
      if (!reducedMotion) animationFrame = requestAnimationFrame(draw);
      else draw(performance.now());
    } catch (error) {
      console.warn("NAM WebGL hero unavailable; using the static CSS fallback.", error);
      if (gl) gl = null;
      canvas.classList.remove("is-webgl-ready");
      fallbackPlanet.hidden = false;
    }
  }

  function resize() {
    if (!gl) return;
    const rect = planetButton.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const cssWidth = rect.width * 0.90;
    const cssHeight = rect.height * 0.90;
    const width = Math.max(1, Math.round(cssWidth * dpr));
    const height = Math.max(1, Math.round(cssHeight * dpr));
    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      canvas.style.width = `${cssWidth}px`;
      canvas.style.height = `${cssHeight}px`;
      gl.viewport(0, 0, width, height);
    }
    gl.uniform2f(gl.getUniformLocation(program, "u_resolution"), width, height);
  }

  function draw(now) {
    if (!gl || handoff) return;
    if (pointerInside) {
      // Controlled cursor follow (maximumMovementRatio 0.05): the tilt moves
      // at most ~5% of the remaining distance per frame. Velocity is tracked
      // so release momentum can carry the motion onward.
      const prevX = pointerX;
      const prevY = pointerY;
      pointerX += (targetX - pointerX) * MOVE_RATIO;
      pointerY += (targetY - pointerY) * MOVE_RATIO;
      tiltVX = pointerX - prevX;
      tiltVY = pointerY - prevY;
    } else {
      // Release momentum (inertiaSpin 0.84): the planet keeps swinging
      // briefly after the cursor leaves, then settles back to centre.
      pointerX += tiltVX;
      pointerY += tiltVY;
      tiltVX *= SPIN_INERTIA;
      tiltVY *= SPIN_INERTIA;
      pointerX -= pointerX * 0.02;
      pointerY -= pointerY * 0.02;
      targetX *= 0.94;
      targetY *= 0.94;
      if (Math.abs(tiltVX) < 0.0004) tiltVX = 0;
      if (Math.abs(tiltVY) < 0.0004) tiltVY = 0;
      if (!tiltVX && !tiltVY && Math.abs(pointerX) < 0.001 && Math.abs(pointerY) < 0.001) {
        pointerX = 0; pointerY = 0; targetX = 0; targetY = 0;
      }
    }
    if (!reducedMotion) {
      // Zoom momentum (inertiaZoom 0.65) feeding the smoothed scale follow.
      if (zoomVel !== 0) {
        zoomTarget = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, zoomTarget * (1 + zoomVel)));
        zoomVel *= ZOOM_INERTIA;
        if (Math.abs(zoomVel) < 0.0004) zoomVel = 0;
      }
      if (zoomLevel !== zoomTarget) {
        zoomLevel += (zoomTarget - zoomLevel) * 0.085;
        if (Math.abs(zoomTarget - zoomLevel) < 0.0006) zoomLevel = zoomTarget;
        planetButton.style.setProperty("--planet-scale", zoomLevel.toFixed(4));
      }
    }
    parallaxX += (targetX - parallaxX) * 0.03;
    parallaxY += (targetY - parallaxY) * 0.03;
    if (coordsBlock) coordsBlock.style.transform = `translate(${(parallaxX * 7).toFixed(2)}px, ${(parallaxY * 5).toFixed(2)}px)`;
    gl.useProgram(program);
    gl.uniform1f(gl.getUniformLocation(program, "u_time"), (now - startTime) / 1000);
    gl.uniform2f(gl.getUniformLocation(program, "u_pointer"), pointerX, pointerY);
    gl.uniform1f(gl.getUniformLocation(program, "u_motion"), reducedMotion ? 0 : 1);
    gl.drawArrays(gl.TRIANGLES, 0, 6);
    animationFrame = requestAnimationFrame(draw);
  }

  if (!reducedMotion) {
    planetButton.addEventListener("pointerenter", () => { pointerInside = true; });
    planetButton.addEventListener("pointermove", (event) => {
      pointerInside = true;
      const rect = planetButton.getBoundingClientRect();
      targetX = ((event.clientX - rect.left) / rect.width - 0.5) * 2;
      targetY = ((event.clientY - rect.top) / rect.height - 0.5) * 2;
      fallbackPlanet.style.setProperty("--ry", `${targetX * 13}deg`);
      fallbackPlanet.style.setProperty("--rx", `${-targetY * 11}deg`);
      fallbackPlanet.style.setProperty("--px", `${targetX * 7}px`);
      fallbackPlanet.style.setProperty("--py", `${targetY * 7}px`);
    });
    planetButton.addEventListener("pointerleave", () => {
      // Momentum phase: targets ease back through the draw loop with the
      // spec's spin inertia instead of snapping to centre.
      pointerInside = false;
      fallbackPlanet.style.setProperty("--ry", "0deg");
      fallbackPlanet.style.setProperty("--rx", "0deg");
      fallbackPlanet.style.setProperty("--px", "0px");
      fallbackPlanet.style.setProperty("--py", "0px");
    });
  }

  /* Procedural starfield behind the hero — the same generated-sky approach the
     atlas uses for its skybox, kept deliberately sparse and dim. */
  let starFrame = 0;
  let starCtx = null;
  let stars = [];
  let starWidth = 0;
  let starHeight = 0;

  function seedGenerator(seed) {
    let value = seed >>> 0;
    return () => {
      value = (value * 1664525 + 1013904223) >>> 0;
      return value / 4294967296;
    };
  }

  function buildStars() {
    const rect = starCanvas.getBoundingClientRect();
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    starWidth = Math.max(1, Math.round(rect.width * dpr));
    starHeight = Math.max(1, Math.round(rect.height * dpr));
    starCanvas.width = starWidth;
    starCanvas.height = starHeight;
    starCtx = starCanvas.getContext("2d");
    const rand = seedGenerator(910482);
    const count = Math.round(Math.min(430, Math.max(150, (rect.width * rect.height) / 6500)));
    stars = [];
    for (let i = 0; i < count; i += 1) {
      const magnitude = rand();
      stars.push({
        x: rand() * starWidth,
        y: rand() * starHeight,
        r: (magnitude > 0.965 ? 1.5 : magnitude > 0.8 ? 1.0 : 0.5 + rand() * 0.4) * dpr,
        alpha: (magnitude > 0.965 ? 0.5 : 0.10 + rand() * 0.26),
        tint: rand(),
        twinkle: rand() < 0.16 ? 0.5 + rand() * 1.4 : 0,
        phase: rand() * Math.PI * 2
      });
    }
    drawStars(0);
  }

  function drawStars(now) {
    if (!starCtx) return;
    starCtx.clearRect(0, 0, starWidth, starHeight);
    for (const star of stars) {
      let alpha = star.alpha;
      if (star.twinkle && now) alpha *= 0.72 + 0.28 * Math.sin(star.phase + (now / 1000) * star.twinkle);
      if (star.tint > 0.93) starCtx.fillStyle = `rgba(194,211,238,${alpha.toFixed(3)})`;
      else if (star.tint < 0.05) starCtx.fillStyle = `rgba(241,211,178,${alpha.toFixed(3)})`;
      else starCtx.fillStyle = `rgba(235,239,242,${alpha.toFixed(3)})`;
      starCtx.beginPath();
      starCtx.arc(star.x, star.y, star.r, 0, Math.PI * 2);
      starCtx.fill();
    }
    if (!reducedMotion && now) {
      // An almost imperceptible drift keeps the sky alive without competing
      // with the planet.
      for (const star of stars) {
        star.x += 0.006;
        if (star.x > starWidth) star.x -= starWidth;
      }
    }
  }

  function starLoop(now) {
    drawStars(now);
    starFrame = requestAnimationFrame(starLoop);
  }

  function stopStarfield() {
    if (starFrame) cancelAnimationFrame(starFrame);
    starFrame = 0;
  }

  function initStarfield() {
    if (!starCanvas) return;
    buildStars();
    if ("ResizeObserver" in window) new ResizeObserver(() => buildStars()).observe(starCanvas);
    else window.addEventListener("resize", buildStars, { passive: true });
    if (!reducedMotion) starFrame = requestAnimationFrame(starLoop);
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      if (animationFrame) cancelAnimationFrame(animationFrame);
      stopStarfield();
    } else {
      if (gl && !reducedMotion && !entering) animationFrame = requestAnimationFrame(draw);
      if (!reducedMotion && !entering && !starFrame) starFrame = requestAnimationFrame(starLoop);
    }
  });

  initStarfield();
  initWebGL();
})();

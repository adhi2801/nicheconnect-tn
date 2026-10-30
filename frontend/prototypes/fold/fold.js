// The fold: a folding phone, modelled from the iPhone Duo's published
// proportions (84.1 x 117.8 mm closed, 164.6 x 117.8 x 5.2 mm open, a
// book-style hinge), played by scroll. No maker's logo or name appears.
//
// The idea only this page has: the fold is the deal. The brand is one half
// of the inner display and the creator the other, the crease is where they
// meet, and the seal draws itself across the crease from both halves at
// once: a guilloche made from this deal's own fingerprint, so no two deals
// share one. At the end the phone closes on the sealed record.
//
// Scroll is the playhead, as in a film: forward plays, back rewinds. Six
// chapters, each held still long enough to read before the next forms.
// Rendered only on change and only while on screen; built only when the
// section is about to scroll into view, so the page paints without it. No
// WebGL, a weak device or reduce motion: the still, the same screens flat.
//
// Three.js r128 is the copy the page already loads for its temple, so this
// adds no download of its own.

(function () {
  "use strict";

  var section = document.getElementById("fold");
  var Screens = window.ColyvFoldScreens;
  if (!section || !Screens) return;

  var frame = section.querySelector(".fold-frame");
  var track = section.querySelector(".fold-track");
  var host = section.querySelector(".fold-gl");
  var items = [].slice.call(section.querySelectorAll(".fold-chapters li"));
  var N = items.length;
  var HOLD = 0.56; // the share of each chapter's scroll spent holding still
  var THREE_SRC = "https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js";

  // ---------- when not to run the film ----------

  function lowPower() {
    var n = navigator, c = n.connection || {};
    return Boolean(c.saveData) || (n.deviceMemory && n.deviceMemory < 4) ||
      (n.hardwareConcurrency && n.hardwareConcurrency < 4);
  }
  function webgl() {
    try { var c = document.createElement("canvas"); return Boolean(c.getContext("webgl")); }
    catch (e) { return false; }
  }
  function fontsReady() {
    if (!document.fonts) return Promise.resolve();
    return Promise.all([
      '700 20px "Plus Jakarta Sans"', '800 20px "Plus Jakarta Sans"',
      '500 20px "Fraunces"', '500 20px "JetBrains Mono"',
    ].map(function (f) { return document.fonts.load(f).catch(function () {}); }));
  }

  function still() {
    section.classList.remove("live");
    section.classList.add("still");
    if (host) host.innerHTML = "";
    var poster = section.querySelector(".fold-poster");
    if (!poster || poster.firstChild) return;
    var c = document.createElement("canvas");
    c.width = 1600;
    c.height = Math.round(1600 / SCREEN_RATIO);
    c.setAttribute("role", "img");
    c.setAttribute("aria-label", "The deal memo, accepted by both sides and sealed, on the brand's half and the creator's half of one screen.");
    poster.appendChild(c);
    fontsReady().then(function () { Screens.inner(c.getContext("2d"), c.width, c.height, 2, 2, 1); });
  }

  // ---------- the phone's dimensions, in units of 10 mm ----------

  var W = 8.23;   // one half's width
  var H = 11.78;  // height
  var T = 0.52;   // one half's thickness
  var G = 0.05;   // the gap between the halves when closed
  var R = 1.22;   // the outer corners
  var r = 0.1;    // the corners at the hinge
  var B = 0.24;   // the inner display's border
  var CB = 0.3;   // the cover display's border
  var Z0 = T / 2 + G / 2; // the hinge axis: the halves fold screen to screen
  var SCREEN_RATIO = (2 * (W - B)) / (H - 2 * B);

  var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || lowPower() || !webgl()) { still(); return; }
  section.classList.add("live");

  // ---------- the HUD: chapter, scrubber, jump to a chapter ----------

  var hud = section.querySelector(".fold-hud");
  var tc = hud.querySelector(".tc");
  var nameEl = hud.querySelector(".name");
  var scrub = hud.querySelector(".fold-scrub");
  var bars = items.map(function (li, i) {
    var b = document.createElement("button");
    b.type = "button";
    b.setAttribute("aria-label", "Chapter " + (i + 1) + ": " + li.querySelector("h3").textContent);
    b.appendChild(document.createElement("i"));
    b.addEventListener("click", function () {
      var total = track.offsetHeight - innerHeight;
      var top = track.getBoundingClientRect().top + scrollY;
      scrollTo({ top: top + ((i + 0.5) / N) * total, behavior: reduce ? "auto" : "smooth" });
    });
    scrub.appendChild(b);
    return b;
  });

  // ---------- scroll to scene ----------

  function clamp(x) { return x < 0 ? 0 : x > 1 ? 1 : x; }
  function ease(t) { return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2; }
  function lerp(a, b, t) { return a + (b - a) * t; }

  // Where the film is: x runs 0 to N-1 across the chapters' centres.
  function scrollState() {
    var rect = track.getBoundingClientRect();
    var total = Math.max(1, track.offsetHeight - innerHeight);
    var p = clamp(-rect.top / total);
    var enter = clamp(1 - rect.top / innerHeight); // the section arriving
    return { x: Math.min(0.99999, p) * N - 0.5, enter: enter };
  }

  // A scene position s (0..N-1, holding at whole numbers) and, while a
  // chapter holds, how far through its hold we are.
  function scene(x) {
    var c = Math.round(Math.min(N - 1, Math.max(0, x)));
    if (x <= c + HOLD / 2 && x >= c - HOLD / 2 || x < 0 || x > N - 1) {
      return { s: c, hold: c, h: clamp((x - c + HOLD / 2) / HOLD) };
    }
    var i = Math.floor(x), m = (x - i - HOLD / 2) / (1 - HOLD);
    return { s: i + ease(clamp(m)), hold: -1, h: 0, from: i, m: clamp(m) };
  }

  // The fold angle: closed (pi) on the first chapter, open (0) through the
  // deal, closed again on the last.
  function foldAngle(s) {
    if (s <= 1) return Math.PI * (1 - s);
    if (s >= N - 2) return Math.PI * (s - (N - 2));
    return 0;
  }

  // ---------- build ----------

  var THREE, renderer, scene3, camera, pose, phone, leftPivot, spine;
  var innerTex, coverTex, innerCanvas, coverCanvas, innerMats = [], coverMat;
  var shadow, visible = false, built = false;

  function loadThree() {
    return new Promise(function (resolve, reject) {
      if (window.THREE) return resolve(window.THREE);
      var s = document.querySelector('script[src="' + THREE_SRC + '"]');
      if (!s) {
        s = document.createElement("script");
        s.src = THREE_SRC;
        s.async = true;
        s.crossOrigin = "anonymous";
        document.head.appendChild(s);
      }
      s.addEventListener("load", function () { window.THREE ? resolve(window.THREE) : reject(); });
      s.addEventListener("error", reject);
    });
  }

  // A rectangle with each corner's own radius.
  function shape(x0, y0, x1, y1, bl, br, tr, tl) {
    var s = new THREE.Shape(), q = Math.PI / 2;
    bl = Math.max(bl, 1e-3); br = Math.max(br, 1e-3); tr = Math.max(tr, 1e-3); tl = Math.max(tl, 1e-3);
    s.moveTo(x0 + bl, y0);
    s.lineTo(x1 - br, y0); s.absarc(x1 - br, y0 + br, br, -q, 0, false);
    s.lineTo(x1, y1 - tr); s.absarc(x1 - tr, y1 - tr, tr, 0, q, false);
    s.lineTo(x0 + tl, y1); s.absarc(x0 + tl, y1 - tl, tl, q, 2 * q, false);
    s.lineTo(x0, y0 + bl); s.absarc(x0 + bl, y0 + bl, bl, 2 * q, 3 * q, false);
    return s;
  }
  // A flat face from a shape, with UVs spanning [u0,u1] x [v0,v1] in x, y.
  function face(sh, u0, u1, v0, v1) {
    var g = new THREE.ShapeGeometry(sh, 48);
    var p = g.attributes.position, uv = g.attributes.uv;
    for (var i = 0; i < p.count; i++) {
      uv.setXY(i, (p.getX(i) - u0) / (u1 - u0), (p.getY(i) - v0) / (v1 - v0));
    }
    return g;
  }

  function studio() {
    // The light the metal and glass reflect: one warm lamp from above left,
    // a cool rim behind right, a soft strip overhead, a dark room. Courtyard
    // dusk (TAMIL_DESIGN_ROOTS 8, 12.13), made as softboxes, not a photo.
    var env = new THREE.Scene();
    env.add(new THREE.Mesh(new THREE.SphereGeometry(60, 32, 16),
      new THREE.MeshBasicMaterial({ color: 0x06070b, side: THREE.BackSide })));
    function box(w, h, x, y, z, rgb) {
      var m = new THREE.MeshBasicMaterial({ side: THREE.DoubleSide });
      m.color.setRGB(rgb[0], rgb[1], rgb[2]);
      var b = new THREE.Mesh(new THREE.PlaneGeometry(w, h), m);
      b.position.set(x, y, z);
      b.lookAt(0, 0, 0);
      env.add(b);
    }
    box(26, 14, -16, 15, 14, [5.2, 4.4, 3.3]);   // the lamp
    box(6, 44, 22, 2, -10, [2.0, 2.5, 3.6]);    // the cool rim
    box(44, 4, 0, 24, -2, [2.6, 2.5, 2.4]);
    box(4, 40, -22, 0, 8, [1.3, 1.25, 1.2]);    // a soft side strip, for the edge     // overhead strip
    box(10, 30, -26, -2, -12, [0.5, 0.42, 0.36]); // a warm wall bounce
    box(60, 60, 0, -28, 0, [0.07, 0.06, 0.05]);  // the floor
    var pm = new THREE.PMREMGenerator(renderer);
    var tex = pm.fromScene(env, 0.035).texture;
    pm.dispose();
    return tex;
  }

  function build() {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
    var small = innerWidth < 768;
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, small ? 1.75 : 2));
    renderer.outputEncoding = THREE.sRGBEncoding;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    renderer.physicallyCorrectLights = true;
    renderer.setClearColor(0x000000, 0);
    host.appendChild(renderer.domElement);
    renderer.domElement.addEventListener("webglcontextlost", function (e) { e.preventDefault(); visible = false; still(); });

    scene3 = new THREE.Scene();
    scene3.environment = studio();
    camera = new THREE.PerspectiveCamera(26, 1, 0.5, 400);

    // Night Sky: mirror-polished titanium, a frosted glass back.
    var titanium = new THREE.MeshPhysicalMaterial({ color: 0x56617f, metalness: 1, roughness: 0.2, envMapIntensity: 1.4 });
    var blasted = new THREE.MeshPhysicalMaterial({ color: 0x56617f, metalness: 1, roughness: 0.42, side: THREE.DoubleSide });
    var back = new THREE.MeshPhysicalMaterial({ color: 0x243050, metalness: 0.15, roughness: 0.4, clearcoat: 1, clearcoatRoughness: 0.32 });
    var black = new THREE.MeshPhysicalMaterial({ color: 0x010102, metalness: 0, roughness: 0.06, clearcoat: 1, clearcoatRoughness: 0.04 });
    var lensGlass = new THREE.MeshPhysicalMaterial({ color: 0x05070d, metalness: 0.2, roughness: 0.05, clearcoat: 1 });
    var lensCoat = new THREE.MeshPhysicalMaterial({ color: 0x1a1440, metalness: 0.6, roughness: 0.12, emissive: 0x0a0618 });
    var flashMat = new THREE.MeshStandardMaterial({ color: 0xd9d2c0, roughness: 0.55 });

    innerCanvas = document.createElement("canvas");
    var iw = small ? 1280 : 2048;
    innerCanvas.width = iw;
    innerCanvas.height = Math.round(iw / SCREEN_RATIO);
    coverCanvas = document.createElement("canvas");
    coverCanvas.width = small ? 640 : 900;
    coverCanvas.height = Math.round(coverCanvas.width * (H - 2 * CB) / (W - 2 * CB));
    var aniso = renderer.capabilities.getMaxAnisotropy();
    innerTex = new THREE.CanvasTexture(innerCanvas);
    coverTex = new THREE.CanvasTexture(coverCanvas);
    [innerTex, coverTex].forEach(function (t) { t.encoding = THREE.sRGBEncoding; t.anisotropy = aniso; });

    function screenMat(tex) {
      // The picture glows; the glass over it still reflects the room.
      var m = new THREE.MeshStandardMaterial({ color: 0x000000, emissive: 0xffffff, emissiveMap: tex, roughness: 0.08, metalness: 0 });
      return m;
    }

    var bv = 0.075;
    function body(sh) {
      var g = new THREE.ExtrudeGeometry(sh, {
        depth: T - 2 * bv, bevelEnabled: true, bevelThickness: bv, bevelSize: bv,
        bevelOffset: -bv, bevelSegments: 6, curveSegments: 40,
      });
      g.translate(0, 0, -(T - 2 * bv) / 2);
      return new THREE.Mesh(g, [back, titanium]);
    }

    phone = new THREE.Group();

    // The half that stays: the right, with the cameras on its back.
    var right = new THREE.Group();
    right.add(body(shape(0, -H / 2, W, H / 2, r, R, R, r)));
    var rFront = new THREE.Mesh(new THREE.ShapeGeometry(shape(bv, -H / 2 + bv, W - bv, H / 2 - bv, r, R - bv, R - bv, r), 40), black);
    rFront.position.z = T / 2 + 0.002;
    right.add(rFront);
    var rScreenMat = screenMat(innerTex);
    var rScreen = new THREE.Mesh(face(shape(0, -H / 2 + B, W - B, H / 2 - B, 0, R - B, R - B, 0), -(W - B), W - B, -H / 2 + B, H / 2 - B), rScreenMat);
    rScreen.position.z = T / 2 + 0.004;
    right.add(rScreen);

    // The camera plateau, top corner of the back: two lenses and the flash.
    var px = W - 1.8, py = H / 2 - 1.18;
    var plat = new THREE.ExtrudeGeometry(shape(-px - 1.5, py - 0.78, -px + 1.5, py + 0.78, 0.78, 0.78, 0.78, 0.78),
      { depth: 0.07, bevelEnabled: true, bevelThickness: 0.03, bevelSize: 0.03, bevelOffset: -0.03, bevelSegments: 4, curveSegments: 32 });
    plat.rotateY(Math.PI);
    plat.translate(0, 0, -T / 2 + 0.01);
    right.add(new THREE.Mesh(plat, [back, titanium]));
    [-0.74, 0.74].forEach(function (dx) {
      var ring = new THREE.Mesh(new THREE.CylinderGeometry(0.52, 0.55, 0.14, 64), titanium);
      ring.rotation.x = Math.PI / 2;
      ring.position.set(px + dx, py, -T / 2 - 0.15);
      right.add(ring);
      var glass = new THREE.Mesh(new THREE.CircleGeometry(0.43, 64), lensGlass);
      glass.rotation.y = Math.PI;
      glass.position.set(px + dx, py, -T / 2 - 0.225);
      right.add(glass);
      var coat = new THREE.Mesh(new THREE.CircleGeometry(0.2, 48), lensCoat);
      coat.rotation.y = Math.PI;
      coat.position.set(px + dx, py, -T / 2 - 0.227);
      right.add(coat);
    });
    var flash = new THREE.Mesh(new THREE.CircleGeometry(0.17, 40), flashMat);
    flash.rotation.y = Math.PI;
    flash.position.set(px - 2.25, py, -T / 2 - 0.004);
    right.add(flash);
    var mic = new THREE.Mesh(new THREE.CircleGeometry(0.05, 20), black);
    mic.rotation.y = Math.PI;
    mic.position.set(px - 1.85, py + 0.32, -T / 2 - 0.004);
    right.add(mic);

    // Buttons: Touch ID on the outer edge, volume on the top edge.
    function key(w, h, d, x, y, z) {
      var k = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), titanium);
      k.position.set(x, y, z);
      right.add(k);
    }
    key(0.07, 1.5, 0.3, W + 0.02, 2.1, 0);
    key(1.0, 0.07, 0.3, 1.9, H / 2 + 0.02, 0);
    key(1.0, 0.07, 0.3, 3.1, H / 2 + 0.02, 0);
    phone.add(right);

    // The half that folds: the left, with the cover display on its back.
    leftPivot = new THREE.Group();
    leftPivot.position.z = Z0;
    var left = new THREE.Group();
    left.position.z = -Z0;
    left.add(body(shape(-W, -H / 2, 0, H / 2, R, r, r, R)));
    var lFront = new THREE.Mesh(new THREE.ShapeGeometry(shape(-W + bv, -H / 2 + bv, -bv, H / 2 - bv, R - bv, r, r, R - bv), 40), black);
    lFront.position.z = T / 2 + 0.002;
    left.add(lFront);
    var lScreenMat = screenMat(innerTex);
    var lScreen = new THREE.Mesh(face(shape(-(W - B), -H / 2 + B, 0, H / 2 - B, R - B, 0, 0, R - B), -(W - B), W - B, -H / 2 + B, H / 2 - B), lScreenMat);
    lScreen.position.z = T / 2 + 0.004;
    left.add(lScreen);
    // The cover side: black glass, then the display, facing outwards.
    var lBackGlass = new THREE.Mesh(new THREE.ShapeGeometry(shape(bv, -H / 2 + bv, W - bv, H / 2 - bv, r, R - bv, R - bv, r), 40), black);
    lBackGlass.geometry.rotateY(Math.PI);
    lBackGlass.position.z = -T / 2 - 0.002;
    left.add(lBackGlass);
    coverMat = screenMat(coverTex);
    var cover = new THREE.Mesh(face(shape(CB, -H / 2 + CB, W - CB, H / 2 - CB, 0.5, R - CB, R - CB, 0.5), CB, W - CB, -H / 2 + CB, H / 2 - CB), coverMat);
    cover.geometry.rotateY(Math.PI);
    cover.position.z = -T / 2 - 0.004;
    left.add(cover);
    leftPivot.add(left);
    phone.add(leftPivot);
    innerMats = [lScreenMat, rScreenMat];

    // The hinge cover: half a cylinder that turns half as far as the fold,
    // so it hides inside the body when open and is the spine when closed.
    spine = new THREE.Mesh(new THREE.CylinderGeometry(T + G / 2, T + G / 2, H - 0.12, 64, 1, true, Math.PI / 2, Math.PI), blasted);
    spine.position.z = Z0;
    phone.add(spine);

    pose = new THREE.Group();
    pose.add(phone);
    scene3.add(pose);

    // A soft shadow on the floor below: the phone stands, it does not float.
    var sc = document.createElement("canvas");
    sc.width = sc.height = 256;
    var sg = sc.getContext("2d"), grd = sg.createRadialGradient(128, 128, 0, 128, 128, 128);
    grd.addColorStop(0, "rgba(0,0,0,.6)"); grd.addColorStop(1, "rgba(0,0,0,0)");
    sg.fillStyle = grd; sg.fillRect(0, 0, 256, 256);
    shadow = new THREE.Mesh(new THREE.PlaneGeometry(1, 1),
      new THREE.MeshBasicMaterial({ map: new THREE.CanvasTexture(sc), transparent: true, depthWrite: false }));
    shadow.rotation.x = -Math.PI / 2;
    shadow.position.y = -H / 2 - 0.9;
    scene3.add(shadow);

    resize();
    built = true;
  }

  // ---------- screens: drawn only when what they show changes ----------

  var cache = {}, innerKey = "", coverKey = "";
  function stateCanvas(chapter, step, k) {
    var key = chapter + ":" + step + ":" + k.toFixed(2);
    if (cache[key]) return cache[key];
    var keys = Object.keys(cache);
    if (keys.length > 3) delete cache[keys[0]];
    var c = document.createElement("canvas");
    c.width = innerCanvas.width;
    c.height = innerCanvas.height;
    Screens.inner(c.getContext("2d"), c.width, c.height, chapter, step, k);
    return (cache[key] = c);
  }
  // What the inner display shows for a chapter and its hold progress.
  function innerState(ch, h) {
    if (ch <= 0) return [1, 0, 0];
    if (ch >= N - 1) return [4, 2, 1];
    var steps = Screens.STEPS[ch];
    var step = Math.min(steps - 1, Math.floor(h * steps));
    var k = ch === 2 && step === 2 ? clamp((h * steps - 2) / 0.75) : ch === 2 ? 0 : 1;
    if (ch === 2 && step < 2) k = 0;
    return [ch, step, Math.round(k * 50) / 50];
  }
  function drawScreens(sc) {
    var a, b = null, mix = 0;
    if (sc.hold >= 0) a = innerState(sc.hold, sc.h);
    else { a = innerState(sc.from, 1); b = innerState(sc.from + 1, 0); mix = Math.round(sc.m * 25) / 25; }
    var key = a.join() + "|" + (b ? b.join() : "") + "|" + mix;
    if (key !== innerKey) {
      innerKey = key;
      var ctx = innerCanvas.getContext("2d");
      ctx.globalAlpha = 1;
      ctx.drawImage(stateCanvas(a[0], a[1], a[2]), 0, 0);
      if (b && mix > 0) { ctx.globalAlpha = mix; ctx.drawImage(stateCanvas(b[0], b[1], b[2]), 0, 0); ctx.globalAlpha = 1; }
      innerTex.needsUpdate = true;
    }
    var which = sc.s >= 2.5 ? 1 : 0;
    if (String(which) !== coverKey) {
      coverKey = String(which);
      Screens.cover(coverCanvas.getContext("2d"), coverCanvas.width, coverCanvas.height, which);
      coverTex.needsUpdate = true;
    }
  }

  // ---------- frame, pose, render ----------

  var view = { portrait: false };
  function resize() {
    if (!renderer) return;
    var w = frame.clientWidth, h = frame.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    view.portrait = w < 768 || h > w * 1.1;
    // Desktop: the phone right of the words. Portrait: above them.
    var cx = view.portrait ? 0 : 0.3, cy = view.portrait ? 0.34 : 0.02;
    camera.setViewOffset(w, h, -cx * w / 2, cy * h / 2, w, h);
    var t = Math.tan((camera.fov * Math.PI) / 360);
    var fw = view.portrait ? 0.9 : 0.52, fh = view.portrait ? 0.44 : 0.7;
    view.d = Math.max((2 * W + 0.8) / (fw * 2 * t * camera.aspect), (H + 0.8) / (fh * 2 * t));
    camera.updateProjectionMatrix();
    cache = {}; innerKey = ""; coverKey = "";
    queue();
  }

  var cur = null, target = null, raf = 0, last = 0;
  function render() {
    raf = 0;
    if (!built || !visible) return;
    var now = performance.now(), dt = Math.min(0.05, (now - last) / 1000 || 0.016);
    last = now;
    // A light spring after the scroll, so a flick of the wheel glides.
    var a = 1 - Math.exp(-dt * 10);
    cur.x += (target.x - cur.x) * a;
    cur.enter += (target.enter - cur.enter) * a;
    var settled = Math.abs(target.x - cur.x) < 1e-4 && Math.abs(target.enter - cur.enter) < 1e-4;
    if (settled) { cur.x = target.x; cur.enter = target.enter; }

    var sc = scene(cur.x);
    var th = foldAngle(sc.s);
    var closed = (1 - Math.cos(th)) / 2; // 0 open, 1 closed

    leftPivot.rotation.y = th;
    spine.rotation.y = th / 2;
    phone.position.set(-(W / 2) * closed, 0, -Z0 * closed);

    // The arrival: the back and its cameras first, turning to the cover.
    var intro = ease(clamp(cur.enter * 0.75 + clamp((cur.x + 0.5) * 2) * 0.25));
    var yaw, pitch;
    if (sc.s < 1) { yaw = lerp(Math.PI - 0.62, 0.4, intro); yaw = lerp(yaw, 0.16, ease(sc.s)); pitch = lerp(0.16, 0.07, sc.s); }
    else if (sc.s <= N - 2) { yaw = lerp(0.16, -0.16, (sc.s - 1) / (N - 3)); pitch = 0.07; }
    else { var e = ease(sc.s - (N - 2)); yaw = lerp(-0.16, -0.42, e); pitch = lerp(0.07, 0.12, e); }
    pose.rotation.set(pitch, yaw, sc.s < 1 ? lerp(0.05, 0, intro) : 0);

    var d = view.d * lerp(1, 0.9, closed);
    camera.position.set(0, 0.4, d);
    camera.lookAt(0, 0, 0);
    shadow.scale.set(lerp(2 * W + 3, W + 3, closed), 4.2, 1);

    // The inner display wakes as it opens; the cover sleeps as it is hidden.
    var awake = clamp((1 - closed) * 1.6 - 0.1);
    innerMats.forEach(function (m) { m.emissiveIntensity = lerp(0.04, 1, awake); });
    coverMat.emissiveIntensity = lerp(0.1, 1, clamp(closed * 1.4 - 0.2));

    drawScreens(sc);
    renderer.render(scene3, camera);
    hudUpdate(cur.x, sc);
    if (!settled) queue();
  }
  function queue() { if (!raf && visible) raf = requestAnimationFrame(render); }

  var onChapter = -1;
  function hudUpdate(x, sc) {
    var ch = Math.round(Math.min(N - 1, Math.max(0, x)));
    if (ch !== onChapter) {
      onChapter = ch;
      items.forEach(function (li, i) { li.classList.toggle("on", i === ch); });
      tc.textContent = String(ch + 1).padStart(2, "0") + " / " + String(N).padStart(2, "0");
      nameEl.textContent = items[ch].querySelector(".k").textContent;
      bars.forEach(function (b, i) { b.setAttribute("aria-current", i === ch ? "step" : "false"); });
    }
    bars.forEach(function (b, i) { b.style.setProperty("--fill", clamp(x - (i - 0.5)).toFixed(3)); });
  }

  // ---------- wiring ----------

  items[0].classList.add("on");
  function onScroll() { if (!built) return; target = scrollState(); if (!cur) cur = scrollState(); queue(); }
  addEventListener("scroll", onScroll, { passive: true });
  addEventListener("resize", function () { resize(); onScroll(); });

  new IntersectionObserver(function (es) {
    visible = es[0].isIntersecting;
    if (visible) { last = performance.now(); onScroll(); }
  }).observe(section);

  // Built when the section is a screen and a half away, never at page load.
  var near = new IntersectionObserver(function (es) {
    if (!es[0].isIntersecting) return;
    near.disconnect();
    Promise.all([loadThree(), fontsReady()]).then(function (res) {
      THREE = res[0];
      build();
      onScroll();
      if (document.fonts) document.fonts.addEventListener("loadingdone", function () { cache = {}; innerKey = ""; coverKey = ""; queue(); });
    }).catch(still);
  }, { rootMargin: "150% 0px" });
  near.observe(section);
})();

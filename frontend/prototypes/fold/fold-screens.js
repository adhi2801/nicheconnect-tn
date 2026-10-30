// The fold's screens, drawn in code onto a canvas (no photographs, D-142).
//
// The inner display is two apps side by side: the brand on the left half,
// the creator on the right, the crease between them. The cover display is
// what the closed phone shows. Every figure is sample data, and each screen
// keeps the product's own words: "read from the creator's screenshot",
// never "verified" (D-070); the money goes brand to creator directly, and
// Colyv only records it (CLAUDE.md constraint 1).
//
// Each half is drawn in design units 400 wide, scaled to the canvas, so the
// same drawing serves a phone's small texture and a desktop's large one.

window.ColyvFoldScreens = (function () {
  "use strict";

  var C = {
    bg: "#F7F1E6", card: "#FFFDF8", ink: "#1B1512", muted: "#6E6258", line: "#E7DCCB",
    brand: "#7A1428", brandSoft: "#F6E4E6", ok: "#0B7A46", okSoft: "#E1F2E8",
    warn: "#8A5300", warnSoft: "#FBEEDA", soft: "#F1E8D8", night: "#F6EAD2", nightMuted: "#C9BBA3",
  };
  var UI = '"Plus Jakarta Sans", -apple-system, "Segoe UI", system-ui, sans-serif';
  var BODY = '-apple-system, "SF Pro Text", "Segoe UI", system-ui, sans-serif';
  var SERIF = '"Fraunces", Georgia, serif';
  var MONO = '"JetBrains Mono", ui-monospace, Menlo, monospace';

  // How many states each chapter steps through while it holds on screen.
  var STEPS = [1, 2, 3, 3, 3, 1];

  // ---------- drawing primitives, in design units ----------

  function rr(c, x, y, w, h, r) {
    c.beginPath();
    c.moveTo(x + r, y);
    c.arcTo(x + w, y, x + w, y + h, r);
    c.arcTo(x + w, y + h, x, y + h, r);
    c.arcTo(x, y + h, x, y, r);
    c.arcTo(x, y, x + w, y, r);
    c.closePath();
  }
  function font(c, size, weight, family) { c.font = weight + " " + size + "px " + family; }
  function text(c, s, x, y, size, weight, color, family, align) {
    font(c, size, weight, family || BODY);
    c.fillStyle = color;
    c.textAlign = align || "left";
    c.fillText(s, x, y);
    return c.measureText(s).width;
  }
  function wrap(c, s, x, y, maxW, size, lh, weight, color, family) {
    font(c, size, weight, family || BODY);
    c.fillStyle = color;
    c.textAlign = "left";
    var words = s.split(" "), line = "";
    for (var i = 0; i < words.length; i++) {
      var next = line ? line + " " + words[i] : words[i];
      if (c.measureText(next).width > maxW && line) { c.fillText(line, x, y); y += lh; line = words[i]; }
      else line = next;
    }
    if (line) { c.fillText(line, x, y); y += lh; }
    return y;
  }
  function spaced(c, s, x, y, size, color, align) {
    font(c, size, 700, UI);
    if ("letterSpacing" in c) c.letterSpacing = size * 0.1 + "px";
    c.fillStyle = color;
    c.textAlign = align || "left";
    c.fillText(s.toUpperCase(), x, y);
    if ("letterSpacing" in c) c.letterSpacing = "0px";
  }
  function card(c, x, y, w, h, fill) {
    rr(c, x, y, w, h, 18);
    c.fillStyle = fill || C.card;
    c.fill();
    c.strokeStyle = C.line;
    c.lineWidth = 1;
    c.stroke();
  }
  function pill(c, s, x, y, fg, bg, align) {
    font(c, 13, 700, UI);
    var w = c.measureText(s).width + 24;
    var left = align === "right" ? x - w : x;
    rr(c, left, y, w, 26, 13);
    c.fillStyle = bg;
    c.fill();
    text(c, s, left + 12, y + 18, 13, 700, fg, UI);
    return w;
  }
  function tick(c, x, y, size, color) {
    c.beginPath();
    c.moveTo(x, y + size * 0.52);
    c.lineTo(x + size * 0.38, y + size * 0.88);
    c.lineTo(x + size, y + size * 0.12);
    c.strokeStyle = color;
    c.lineWidth = size * 0.16;
    c.lineCap = "round";
    c.lineJoin = "round";
    c.stroke();
  }
  function button(c, s, x, y, w, kind) {
    rr(c, x, y, w, 46, 13);
    if (kind === "primary") { c.fillStyle = C.brand; c.fill(); }
    else { c.fillStyle = C.card; c.fill(); c.strokeStyle = C.line; c.lineWidth = 1.5; c.stroke(); }
    text(c, s, x + w / 2, y + 29, 15, 700, kind === "primary" ? "#fff" : C.ink, UI, "center");
  }
  function row(c, label, value, x, y, w) {
    text(c, label, x, y, 14, 500, C.muted);
    font(c, 15, 600, BODY);
    var vw = c.measureText(value).width;
    text(c, value, x + w, y, 15, 600, C.ink, BODY, "right");
    c.fillStyle = C.line;
    c.fillRect(x, y + 13, w, 1);
    return vw;
  }
  function banner(c, s, x, y, w, fg, bg, withTick) {
    var h = 50;
    rr(c, x, y, w, h, 14);
    c.fillStyle = bg;
    c.fill();
    if (withTick) tick(c, x + 16, y + 17, 16, fg);
    wrap(c, s, x + (withTick ? 42 : 16), y + 30, w - 56, 14, 18, 600, fg);
  }
  function avatar(c, initials, x, y, r, fg, bg) {
    c.beginPath();
    c.arc(x, y, r, 0, Math.PI * 2);
    c.fillStyle = bg;
    c.fill();
    text(c, initials, x, y + r * 0.36, r * 0.72, 800, fg, UI, "center");
  }

  // Raised gold, as Thanjavur gilding (TAMIL_DESIGN_ROOTS 5, 12.5): a dark
  // under-edge, the gold body, a thin lit ridge. Only on what is sealed.
  function goldStroke(c, path, width, x0, x1, onLight) {
    var g = c.createLinearGradient(x0, 0, x1, 0);
    // on a light ground the gold is deeper, so it holds its contrast
    var stops = onLight ? ["#6b4708", "#b88a2c", "#7c560f", "#c99b3a", "#5e3d06"]
      : ["#8a6416", "#f0cf7e", "#b8892a", "#f6e3a3", "#9c7420"];
    [0, 0.3, 0.55, 0.8, 1].forEach(function (at, i) { g.addColorStop(at, stops[i]); });
    c.lineCap = "round";
    c.lineJoin = "round";
    c.save();
    c.translate(0, width * 0.28);
    path();
    c.strokeStyle = "rgba(60, 38, 6, .45)";
    c.lineWidth = width;
    c.stroke();
    c.restore();
    path();
    c.strokeStyle = g;
    c.lineWidth = width;
    c.stroke();
    c.save();
    c.translate(0, -width * 0.18);
    path();
    c.strokeStyle = "rgba(255, 246, 214, .55)";
    c.lineWidth = width * 0.22;
    c.stroke();
    c.restore();
  }

  // The seal: the deal's own fingerprint, drawn as a guilloche rosette, the
  // engraving banknotes and certificates carry because it is hard to forge.
  // Its waves come from the fingerprint's bytes, so no two deals share a seal
  // and the pattern is ours, not a borrowed motif. Drawn from the crease
  // outwards on both sides at once, the brand's half and the creator's half,
  // closing where they meet; `k` (0 to 1) is how far. `ink` draws it in one
  // flat colour instead of raised gold (the app mark).
  function sealParams(fp) {
    var b = [0, 2, 4, 6].map(function (i) { return parseInt(fp.slice(i, i + 2), 16); });
    return { m: 5 + (b[0] % 5), n: 13 + (b[1] % 8), p: (b[2] / 255) * Math.PI * 2, lines: 7 };
  }
  function seal(c, cx, cy, R, fp, k, width, ink, onLight) {
    var q = sealParams(fp), steps = 360, top = -Math.PI / 2;
    var span = Math.PI * k, n = Math.max(2, Math.round(steps * k));
    function rho(t, j, band) {
      var d = (j / q.lines) * Math.PI * 2;
      if (band === 0) return R * (0.74 + 0.15 * Math.sin(q.m * t + d) + 0.05 * Math.sin(q.n * t + q.p + d));
      return R * (0.38 + 0.06 * Math.sin((q.m + 3) * t + d + q.p));
    }
    function arc(j, band, dir) {
      for (var i = 0; i <= n; i++) {
        var t = top + dir * span * (i / n), r = rho(t, j, band);
        var x = cx + r * Math.cos(t), y = cy + r * Math.sin(t);
        if (i === 0) c.moveTo(x, y); else c.lineTo(x, y);
      }
    }
    function path() {
      c.beginPath();
      for (var j = 0; j < q.lines; j++) { arc(j, 0, 1); arc(j, 0, -1); }
      for (var h = 0; h < 4; h++) { arc(h, 1, 1); arc(h, 1, -1); }
      // the border: two fine rings, drawn the same way
      [1.0, 1.06].forEach(function (f) {
        for (var dir = -1; dir <= 1; dir += 2) {
          for (var i = 0; i <= n; i++) {
            var t = top + dir * span * (i / n);
            var x = cx + R * f * Math.cos(t), y = cy + R * f * Math.sin(t);
            if (i === 0) c.moveTo(x, y); else c.lineTo(x, y);
          }
        }
      });
    }
    if (ink) {
      path();
      c.strokeStyle = ink;
      c.lineWidth = width;
      c.lineJoin = "round";
      c.stroke();
      return;
    }
    goldStroke(c, path, width, cx - R, cx + R, onLight);
  }

  // ---------- the parts every pane shares ----------

  function statusBar(c, time, dark) {
    var col = dark ? C.night : C.ink;
    text(c, time, 26, 30, 15, 650, col);
    for (var i = 0; i < 4; i++) { c.fillStyle = col; c.fillRect(318 + i * 6, 25 - i * 3, 4, 5 + i * 3); }
    rr(c, 348, 17, 26, 13, 4);
    c.strokeStyle = col; c.lineWidth = 1.2; c.stroke();
    rr(c, 350, 19, 18, 9, 2.5);
    c.fillStyle = col; c.fill();
  }
  function header(c, role, name, initials) {
    spaced(c, role, 24, 70, 11, C.muted);
    text(c, name, 24, 96, 21, 700, C.ink, UI);
    avatar(c, initials, 360, 80, 20, C.brand, C.brandSoft);
  }
  function footer(c, h, entries, latest) {
    c.fillStyle = C.soft;
    c.fillRect(0, h - 58, 400, 58);
    c.fillStyle = C.line;
    c.fillRect(0, h - 58, 400, 1);
    // a two-link chain: every entry is sealed to the one before it
    c.strokeStyle = C.muted; c.lineWidth = 1.6;
    rr(c, 24, h - 36, 13, 9, 4.5); c.stroke();
    rr(c, 32, h - 36, 13, 9, 4.5); c.stroke();
    text(c, "On the record · " + entries + " entries", 54, h - 27, 13, 700, C.ink, UI);
    text(c, latest, 376, h - 27, 12, 500, C.muted, BODY, "right");
  }

  // ---------- the inner display, chapter by chapter ----------

  var BRAND = { role: "Brand", name: "Thendral Sweets", initials: "TS" };
  var CREATOR = { role: "Creator", name: "Priya · @priyaeats", initials: "PE" };
  var ENTRIES = {
    "1:0": [1, "invite sent"], "1:1": [2, "invite accepted"],
    "2:0": [4, "brand accepted"], "2:1": [5, "creator accepted"], "2:2": [5, "sealed"],
    "3:0": [5, "waiting for proof"], "3:1": [6, "proof sent"], "3:2": [7, "proof approved"],
    "4:0": [7, "payment due"], "4:1": [8, "marked paid"], "4:2": [9, "receipt confirmed"],
  };
  var TIMES = { "1:0": "10:40", "1:1": "10:42", "2:0": "10:58", "2:1": "11:03", "2:2": "11:03",
    "3:0": "6:18", "3:1": "6:20", "3:2": "9:15", "4:0": "5:38", "4:1": "5:40", "4:2": "6:12" };

  function invite(c, side, step) {
    if (side === "brand") {
      card(c, 16, 120, 368, 196);
      spaced(c, "Campaign · published", 34, 150, 11, C.muted);
      text(c, "Diwali sweets reel", 34, 180, 22, 700, C.ink, UI);
      var x = 34;
      ["Paid", "Madurai", "Food"].forEach(function (s) { x += pill(c, s, x, 196, C.ink, C.soft) + 8; });
      row(c, "Budget", "₹6,000 – ₹9,000", 34, 260, 332);
      row(c, "Needed by", "4 Nov 2026", 34, 296, 332);
      spaced(c, "Invited", 24, 352, 11, C.muted);
      card(c, 16, 366, 368, 132);
      avatar(c, "PE", 56, 406, 22, C.brand, C.brandSoft);
      text(c, "Priya · @priyaeats", 90, 402, 16, 700, C.ink, UI);
      text(c, "Food · Madurai · 18.2K followers", 90, 424, 13, 500, C.muted);
      wrap(c, "Fits: food niche, Madurai, inside the budget", 34, 452, 330, 13, 18, 500, C.muted);
      if (step === 0) pill(c, "Invite sent · waiting", 34, 464, C.warn, C.warnSoft);
      else pill(c, "Accepted · 10:42 am", 34, 464, C.ok, C.okSoft);
    } else {
      card(c, 16, 120, 368, 300);
      spaced(c, "Invite · from Thendral Sweets", 34, 150, 11, C.muted);
      text(c, "Diwali sweets reel", 34, 180, 22, 700, C.ink, UI);
      text(c, "₹8,000", 34, 236, 44, 500, C.ink, SERIF);
      text(c, "paid directly to you", 34, 260, 13, 500, C.muted);
      row(c, "Deliverable", "1 reel, 30–45 s", 34, 302, 332);
      row(c, "Post by", "4 Nov 2026", 34, 338, 332);
      row(c, "Usage rights", "30 days", 34, 374, 332);
      if (step === 0) {
        button(c, "Accept invite", 16, 440, 368, "primary");
        button(c, "Not now", 16, 496, 368);
      } else {
        banner(c, "You accepted at 10:42 am. The deal memo is next.", 16, 440, 368, C.ok, C.okSoft, true);
      }
    }
  }

  function memo(c, side, step) {
    card(c, 16, 120, 368, 262);
    spaced(c, "Deal memo · version 1", 34, 150, 11, C.muted);
    text(c, "Diwali sweets reel", 34, 180, 22, 700, C.ink, UI);
    row(c, "Deliverable", "1 Instagram reel", 34, 220, 332);
    row(c, "Post by", "4 Nov 2026", 34, 254, 332);
    row(c, "Amount", "₹8,000, by UPI", 34, 288, 332);
    row(c, "Usage rights", "30 days", 34, 322, 332);
    row(c, "Disclosure", "Paid-partnership label", 34, 356, 332);
    var y = 404;
    function party(label, done, time) {
      c.beginPath();
      c.arc(34, y - 5, 11, 0, Math.PI * 2);
      c.fillStyle = done ? C.okSoft : C.soft;
      c.fill();
      if (done) tick(c, 28, y - 11, 12, C.ok);
      text(c, label, 54, y, 14, 600, C.ink);
      text(c, done ? time : "waiting", 384, y, 13, 500, done ? C.ok : C.muted, BODY, "right");
      y += 32;
    }
    if (step === 2) {
      // both have accepted: one line says so, and the seal takes the space
      party("Both sides accepted", true, "11:03 am");
      return;
    }
    party("Thendral Sweets accepted", true, "10:58 am");
    party(side === "creator" ? "You accepted" : "Priya accepted", step >= 1, "11:03 am");
    if (step === 0 && side === "creator") {
      button(c, "Accept memo", 16, 470, 178, "primary");
      button(c, "Ask for a change", 206, 470, 178);
    } else if (step === 0) {
      banner(c, "Waiting for Priya to accept.", 16, 470, 368, C.warn, C.warnSoft);
    }
    // step 2 leaves this space to the seal, drawn across both halves
  }

  function proof(c, side, step) {
    if (side === "creator") {
      card(c, 16, 120, 368, 250);
      spaced(c, "Send proof", 34, 150, 11, C.muted);
      text(c, "Diwali sweets reel", 34, 180, 22, 700, C.ink, UI);
      text(c, "Link to the post", 34, 214, 13, 600, C.muted);
      rr(c, 34, 224, 332, 44, 11);
      c.fillStyle = C.bg; c.fill(); c.strokeStyle = C.line; c.lineWidth = 1; c.stroke();
      text(c, "instagram.com/reel/C9xT4…", 48, 252, 14, 500, C.ink, MONO);
      rr(c, 34, 290, 22, 22, 6);
      c.fillStyle = C.brand; c.fill();
      tick(c, 39, 295, 12, "#fff");
      wrap(c, "I added the paid-partnership label", 66, 306, 290, 14, 19, 600, C.ink);
      text(c, "Recorded with the proof", 66, 330, 12, 500, C.muted);
      if (step === 0) button(c, "Send proof", 16, 392, 368, "primary");
      else if (step === 1) banner(c, "Sent at 6:20 pm. Thendral Sweets has 7 days to answer.", 16, 392, 368, C.ok, C.okSoft, true);
      else banner(c, "Approved by Thendral Sweets. Payment is due by 11 Nov.", 16, 392, 368, C.ok, C.okSoft, true);
    } else if (step === 0) {
      card(c, 16, 120, 368, 160);
      spaced(c, "Proof", 34, 150, 11, C.muted);
      text(c, "Waiting for the reel", 34, 182, 20, 700, C.ink, UI);
      wrap(c, "Priya posts by 4 Nov. You will be told the moment proof arrives.", 34, 212, 330, 14, 20, 500, C.muted);
    } else {
      card(c, 16, 120, 368, 330);
      spaced(c, "Proof · from Priya", 34, 150, 11, C.muted);
      // the reel's tile, drawn: a sweet box seen from above, no photograph
      rr(c, 34, 166, 120, 170, 12);
      var g = c.createLinearGradient(34, 166, 154, 336);
      g.addColorStop(0, "#5c1020"); g.addColorStop(1, "#2b0a12");
      c.fillStyle = g; c.fill();
      for (var i = 0; i < 3; i++) for (var j = 0; j < 4; j++) {
        c.beginPath();
        c.arc(58 + i * 36, 196 + j * 36, 12, 0, Math.PI * 2);
        c.fillStyle = (i + j) % 2 ? "#e9c77a" : "#f4e4c1";
        c.fill();
      }
      c.beginPath(); c.moveTo(84, 236); c.lineTo(84, 266); c.lineTo(110, 251); c.closePath();
      c.fillStyle = "rgba(255,255,255,.92)"; c.fill();
      text(c, "Reel · 38 s", 170, 186, 16, 700, C.ink, UI);
      text(c, "Posted 3 Nov, 6:02 pm", 170, 208, 13, 500, C.muted);
      text(c, "12.4K views", 170, 246, 20, 700, C.ink, UI);
      wrap(c, "read from the creator's screenshot", 170, 268, 200, 12, 16, 500, C.muted);
      pill(c, "Label confirmed", 170, 300, C.ok, C.okSoft);
      if (step === 1) {
        button(c, "Approve", 34, 372, 160, "primary");
        button(c, "Ask for a fix", 206, 372, 160);
      } else {
        banner(c, "Approved at 9:15 am, 4 Nov. Payment due by 11 Nov.", 34, 368, 332, C.ok, C.okSoft, true);
      }
    }
  }

  function payment(c, side, step, gold) {
    if (side === "brand") {
      card(c, 16, 120, 368, 216);
      spaced(c, "Pay Priya directly", 34, 150, 11, C.muted);
      text(c, "₹8,000", 34, 206, 44, 500, C.ink, SERIF);
      text(c, "due by 11 Nov", 34, 230, 13, 500, C.muted);
      row(c, "UPI ID", "priyaeats@oksbi", 34, 270, 332);
      wrap(c, "Check the name your UPI app shows before you pay.", 34, 304, 330, 13, 18, 500, C.muted);
      if (step === 0) {
        button(c, "Open my UPI app", 16, 356, 368, "primary");
        button(c, "Mark as paid", 16, 412, 368);
      } else {
        banner(c, "Marked paid at 5:40 pm · UTR ••••2207", 16, 356, 368, C.ok, C.okSoft, true);
        if (step === 2) banner(c, "Priya confirmed it arrived at 6:12 pm.", 16, 418, 368, C.ok, C.okSoft, true);
        else banner(c, "Waiting for Priya to confirm it arrived.", 16, 418, 368, C.warn, C.warnSoft);
      }
    } else {
      card(c, 16, 120, 368, 230);
      spaced(c, "Payment", 34, 150, 11, C.muted);
      if (step === 0) {
        text(c, "Due by 11 Nov", 34, 184, 20, 700, C.ink, UI);
        wrap(c, "Thendral Sweets pays you directly. You confirm when it arrives.", 34, 214, 330, 14, 20, 500, C.muted);
      } else {
        wrap(c, "Thendral Sweets says they paid", 34, 184, 330, 16, 22, 700, C.ink, UI);
        text(c, "₹8,000", 34, 246, 44, 500, C.ink, SERIF);
        text(c, "UTR ••••2207 · 5:40 pm, 8 Nov", 34, 276, 13, 500, C.muted, MONO);
        if (step === 1) {
          button(c, "Yes, it arrived", 16, 370, 178, "primary");
          button(c, "Not received", 206, 370, 178);
        } else if (gold) {
          rr(c, 16, 370, 368, 64, 16);
          var g = c.createLinearGradient(16, 0, 384, 0);
          g.addColorStop(0, "#f3e3b5"); g.addColorStop(0.5, "#fbf1d4"); g.addColorStop(1, "#ead39a");
          c.fillStyle = g; c.fill();
          c.strokeStyle = "#c79a3a"; c.lineWidth = 1.5; c.stroke();
          tick(c, 36, 392, 18, "#7a5410");
          text(c, "Confirmed received · 6:12 pm", 66, 400, 15, 700, "#5e3f08", UI);
        }
      }
    }
    text(c, "Colyv never holds the money. It records who said what, and when.", 200, 560, 12, 500, C.muted, BODY, "center");
  }

  var CHAPTERS = { 1: invite, 2: memo, 3: proof, 4: payment };

  // The whole inner display for one state. `k` is the seal's progress in
  // chapter 2, step 2.
  function inner(c, w, h, chapter, step, k) {
    var half = w / 2, u = half / 400, hu = h / u;
    var key = chapter + ":" + step;
    ["brand", "creator"].forEach(function (side, i) {
      c.save();
      c.translate(i * half, 0);
      c.scale(u, u);
      c.fillStyle = C.bg;
      c.fillRect(0, 0, 400, hu);
      statusBar(c, TIMES[key] || "10:40");
      var who = side === "brand" ? BRAND : CREATOR;
      header(c, who.role, who.name, who.initials);
      CHAPTERS[chapter](c, side, step, true);
      footer(c, hu, ENTRIES[key][0], ENTRIES[key][1]);
      c.restore();
    });
    // the crease: a hair of shadow, as the real one is nearly invisible
    var g = c.createLinearGradient(half - 6 * u, 0, half + 6 * u, 0);
    g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(0.5, "rgba(60,40,20,.10)"); g.addColorStop(1, "rgba(0,0,0,0)");
    c.fillStyle = g;
    c.fillRect(half - 6 * u, 0, 12 * u, h);

    if (chapter === 2 && step === 2) {
      c.save();
      c.translate(half, 0);
      c.scale(u, u);
      var cy = 468;
      seal(c, 0, cy, 44, "a3f977c1", k, 1.25, null, true);
      if (k > 0.98) {
        text(c, "Sealed", -60, cy - 4, 15, 800, "#7a5410", UI, "right");
        text(c, "30 Oct, 11:03 am", -60, cy + 16, 12, 500, "#7a5410", BODY, "right");
        text(c, "Fingerprint", 60, cy - 4, 15, 800, "#7a5410", UI);
        text(c, "a3f9 77c1", 60, cy + 16, 12, 500, "#7a5410", MONO);
      }
      c.restore();
    }
  }

  // ---------- the cover display ----------

  function wallpaper(c, hu) {
    var g = c.createLinearGradient(0, 0, 0, hu);
    g.addColorStop(0, "#151b36"); g.addColorStop(0.55, "#221a35"); g.addColorStop(1, "#090b14");
    c.fillStyle = g;
    c.fillRect(0, 0, 400, hu);
    var glow = c.createRadialGradient(200, 120, 10, 200, 120, 320);
    glow.addColorStop(0, "rgba(243,217,164,.20)"); glow.addColorStop(1, "rgba(243,217,164,0)");
    c.fillStyle = glow;
    c.fillRect(0, 0, 400, hu);
  }
  function punch(c) {
    c.beginPath(); c.arc(200, 28, 11, 0, Math.PI * 2); c.fillStyle = "#000"; c.fill();
    c.beginPath(); c.arc(200, 28, 4, 0, Math.PI * 2); c.fillStyle = "#1a2236"; c.fill();
  }
  function mark(c, x, y, s) {
    rr(c, x, y, s, s, s * 0.24);
    c.fillStyle = C.brand;
    c.fill();
    seal(c, x + s / 2, y + s / 2, s * 0.36, "a3f977c1", 1, s * 0.022, "#fbefd9");
  }

  function cover(c, w, h, which) {
    var u = w / 400, hu = h / u;
    c.save();
    c.scale(u, u);
    wallpaper(c, hu);
    statusBar(c, which === 0 ? "10:30" : "6:12", true);
    punch(c);
    text(c, which === 0 ? "Thursday, 30 October" : "Saturday, 8 November", 200, 104, 18, 600, C.nightMuted, UI, "center");
    text(c, which === 0 ? "10:30" : "6:12", 200, 196, 92, 800, C.night, UI, "center");
    if (which === 0) {
      var y = hu - 236;
      rr(c, 16, y, 368, 150, 26);
      c.fillStyle = "rgba(246,234,210,.13)"; c.fill();
      c.strokeStyle = "rgba(246,234,210,.16)"; c.lineWidth = 1; c.stroke();
      mark(c, 34, y + 20, 42);
      spaced(c, "Colyv", 88, y + 38, 12, C.nightMuted);
      text(c, "now", 366, y + 38, 13, 500, C.nightMuted, BODY, "right");
      text(c, "New invite: Diwali sweets reel", 88, y + 64, 17, 700, C.night, UI);
      wrap(c, "Thendral Sweets, Madurai · ₹8,000 for 1 reel, posted by 4 Nov", 34, y + 96, 332, 15, 21, 500, C.nightMuted);
      text(c, "Open to read the whole deal", 200, hu - 40, 13, 600, "rgba(246,234,210,.55)", UI, "center");
    } else {
      var sy = hu * 0.5;
      seal(c, 200, sy, 76, "a3f977c1", 1, 1.1);
      text(c, "Deal complete", 200, sy + 128, 30, 800, C.night, UI, "center");
      text(c, "₹8,000 paid directly by UPI", 200, sy + 160, 16, 600, C.nightMuted, BODY, "center");
      text(c, "Confirmed by Priya · 8 Nov, 6:12 pm", 200, sy + 186, 15, 500, C.nightMuted, BODY, "center");
      text(c, "Sealed record · 9 entries · a3f9 77c1", 200, hu - 44, 13, 500, "#d8b25a", MONO, "center");
    }
    c.restore();
  }

  return { STEPS: STEPS, inner: inner, cover: cover };
})();

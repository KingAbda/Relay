/* Relay — elevated motion layer
   Lenis smooth scroll + GSAP ScrollTrigger choreography, magnetic UI,
   brand intro, scroll-driven reveals/counters/parallax.
   Degrades gracefully if a CDN fails or reduced-motion is set. */
(function () {
  "use strict";

  // Honour OS reduced-motion, or an explicit ?static=1 "lite" mode (skips
  // intro + scroll animation, renders everything settled). Good for low-power
  // devices, accessibility, and deterministic screenshots.
  var liteMode = /[?&]static=1/.test(window.location.search);
  var reduceMotion = liteMode || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (liteMode) document.documentElement.classList.add("lite-mode");
  var isTouch = window.matchMedia("(hover: none)").matches;
  var hasGSAP = typeof window.gsap !== "undefined";
  var hasLenis = typeof window.Lenis !== "undefined";

  /* ───────────────────────── Brand intro ───────────────────────── */
  (function intro() {
    var el = document.getElementById("brandIntro");
    if (!el) return;
    // Plays on every home-page load (the markup only exists on home). Skipped
    // for reduced-motion users.
    var isHome = document.body.getAttribute("data-page") === "home";
    if (reduceMotion || !isHome) {
      el.parentNode && el.parentNode.removeChild(el);
      document.body.classList.add("intro-done");
      return;
    }
    document.body.classList.add("intro-active");
    el.classList.add("playing");
    var finish = function () {
      if (el.classList.contains("lifting")) return;
      el.classList.add("lifting");
      document.body.classList.remove("intro-active");
      document.body.classList.add("intro-done");
      window.dispatchEvent(new Event("relay:intro-done"));
      setTimeout(function () { el.parentNode && el.parentNode.removeChild(el); }, 900);
    };
    el.addEventListener("click", finish); // click to skip
    setTimeout(finish, 3900); // total choreography length (stage 1 + stage 2)
  })();

  /* ───────────────────── Smooth scroll (Lenis) ──────────────────── */
  var lenis = null;
  if (hasLenis && !reduceMotion) {
    lenis = new window.Lenis({
      duration: 1.05,
      easing: function (t) { return Math.min(1, 1.001 - Math.pow(2, -10 * t)); },
      smoothWheel: true,
      lerp: 0.1,
    });
    window.__lenis = lenis;
    if (hasGSAP && window.ScrollTrigger) {
      lenis.on("scroll", window.ScrollTrigger.update);
      window.gsap.ticker.add(function (time) { lenis.raf(time * 1000); });
      window.gsap.ticker.lagSmoothing(0);
    } else {
      var raf = function (t) { lenis.raf(t); requestAnimationFrame(raf); };
      requestAnimationFrame(raf);
    }
    // In-page anchor links route through Lenis for buttery jumps.
    document.querySelectorAll('a[href^="#"]').forEach(function (a) {
      a.addEventListener("click", function (e) {
        var id = a.getAttribute("href");
        if (id.length < 2) return;
        var target = document.querySelector(id);
        if (!target) return;
        e.preventDefault();
        lenis.scrollTo(target, { offset: -80, duration: 1.2 });
      });
    });
  }

  /* ───────────────────── Scroll progress + nav ──────────────────── */
  var bar = document.getElementById("scrollProgress");
  var nav = document.getElementById("siteNav");
  function onScrollUI() {
    var st = window.pageYOffset || document.documentElement.scrollTop;
    var h = document.documentElement.scrollHeight - window.innerHeight;
    if (bar) bar.style.transform = "scaleX(" + (h > 0 ? st / h : 0) + ")";
    if (nav) nav.classList.toggle("scrolled", st > 12);
  }
  (lenis ? lenis.on.bind(lenis, "scroll") : function (cb) { window.addEventListener("scroll", cb, { passive: true }); })(onScrollUI);
  onScrollUI();

  /* ─────────────────────── Cursor glow ──────────────────────────── */
  (function cursor() {
    var glow = document.getElementById("cursorGlow");
    if (!glow || isTouch || reduceMotion) { glow && glow.remove(); return; }
    var x = window.innerWidth / 2, y = window.innerHeight / 2, tx = x, ty = y;
    window.addEventListener("mousemove", function (e) { tx = e.clientX; ty = e.clientY; });
    (function loop() {
      x += (tx - x) * 0.12; y += (ty - y) * 0.12;
      glow.style.transform = "translate(" + x + "px," + y + "px)";
      requestAnimationFrame(loop);
    })();
  })();

  /* ───────────────────── Magnetic elements ──────────────────────── */
  if (!isTouch && !reduceMotion) {
    document.querySelectorAll("[data-magnetic]").forEach(function (el) {
      var strength = parseFloat(el.getAttribute("data-magnetic-strength")) || 0.4;
      el.addEventListener("mousemove", function (e) {
        var r = el.getBoundingClientRect();
        var mx = e.clientX - (r.left + r.width / 2);
        var my = e.clientY - (r.top + r.height / 2);
        el.style.transform = "translate(" + mx * strength + "px," + my * strength + "px)";
      });
      el.addEventListener("mouseleave", function () { el.style.transform = ""; });
    });
  }

  /* ─────────────────────── Gauge helpers ───────────────────────── */
  // The progress ring that belongs to a given count-up number (if any).
  function ringFor(el) {
    var wrap = el.closest && el.closest(".gauge-wrap");
    return wrap ? wrap.querySelector(".gauge-progress") : null;
  }
  // Paint a ring at a fixed value (used for reduced-motion / no-GSAP states).
  function paintRing(ring, v) {
    if (!ring) return;
    ring.style.animation = "none";
    ring.style.strokeDasharray = v + " 100";
    ring.style.strokeDashoffset = "0";
  }
  // Reset a ring to empty so it can draw in on scroll.
  function emptyRing(ring) {
    if (!ring) return;
    ring.style.animation = "none";
    ring.style.strokeDasharray = "0 100";
    ring.style.strokeDashoffset = "0";
  }

  /* ─────────────────── GSAP scroll choreography ─────────────────── */
  function initGSAP() {
    if (!hasGSAP || !window.ScrollTrigger) { fallbackReveals(); return; }
    var gsap = window.gsap;
    gsap.registerPlugin(window.ScrollTrigger);

    if (reduceMotion) {
      document.querySelectorAll("[data-reveal],[data-reveal-stagger] > *,[data-split]")
        .forEach(function (el) { gsap.set(el, { clearProps: "all", opacity: 1 }); });
      return; // counters handled by initGauges()
    }

    // Headline line/word reveal — elements tagged data-split get a clip-up.
    gsap.utils.toArray("[data-split]").forEach(function (el) {
      gsap.from(el, {
        scrollTrigger: { trigger: el, start: "top 88%" },
        yPercent: 110, opacity: 0, duration: 1, ease: "power4.out",
      });
    });

    // Single element reveals.
    gsap.utils.toArray("[data-reveal]").forEach(function (el) {
      gsap.from(el, {
        scrollTrigger: { trigger: el, start: "top 90%" },
        y: 40, opacity: 0, duration: 0.9, ease: "power3.out",
        delay: parseFloat(el.getAttribute("data-reveal")) || 0,
      });
    });

    // Staggered children reveals.
    gsap.utils.toArray("[data-reveal-stagger]").forEach(function (group) {
      gsap.from(group.children, {
        scrollTrigger: { trigger: group, start: "top 85%" },
        y: 48, opacity: 0, duration: 0.85, ease: "power3.out", stagger: 0.09,
      });
    });

    // Parallax — positive data-parallax moves slower (depth).
    gsap.utils.toArray("[data-parallax]").forEach(function (el) {
      var amt = parseFloat(el.getAttribute("data-parallax")) || 60;
      gsap.to(el, {
        yPercent: -amt / 10, ease: "none",
        scrollTrigger: { trigger: el.closest("section") || el, start: "top bottom", end: "bottom top", scrub: 1 },
      });
    });

    // Velocity-reactive marquee: scroll speed nudges direction/speed.
    var track = document.querySelector(".skill-marquee .marquee-track");
    if (track) {
      var base = -0.6, cur = base, dir = 1, x = 0;
      window.ScrollTrigger.create({
        onUpdate: function (self) {
          dir = self.direction;
          cur = base * (1 + Math.min(Math.abs(self.getVelocity() / 280), 4));
        },
      });
      track.style.animation = "none";
      var half = 0;
      function measure() { half = track.scrollWidth / 2; }
      measure(); window.addEventListener("resize", measure);
      gsap.ticker.add(function () {
        x += cur * dir;
        if (half) { if (x <= -half) x += half; if (x > 0) x -= half; }
        track.style.transform = "translateX(" + x + "px)";
      });
    }

    // Pinned credit-loop: steps light up as you scrub through.
    var loop = document.querySelector("[data-pin-loop]");
    if (loop && window.innerWidth > 820) {
      var steps = gsap.utils.toArray("[data-pin-loop] .loop-step");
      var tl = gsap.timeline({
        scrollTrigger: { trigger: loop, start: "top 18%", end: "+=" + (steps.length * 320), pin: true, scrub: 0.6 },
      });
      steps.forEach(function (s, i) {
        tl.fromTo(s, { opacity: 0.22, y: 34, scale: 0.95 },
          { opacity: 1, y: 0, scale: 1, duration: 1, ease: "power2.out" }, i * 1.1);
        var arrow = s.nextElementSibling;
        if (arrow && arrow.classList.contains("loop-arrow")) {
          tl.fromTo(arrow, { opacity: 0.15, x: -10 }, { opacity: 1, x: 0, duration: 0.5 }, i * 1.1 + 0.6);
        }
      });
    }

    // Hero board subtle scrub drift.
    var board = document.querySelector(".hero-board");
    if (board) {
      gsap.to(board, {
        yPercent: 6, ease: "none",
        scrollTrigger: { trigger: ".campus-hero", start: "top top", end: "bottom top", scrub: 1 },
      });
    }

    window.ScrollTrigger.refresh();
  }

  // CSS-only fallback when GSAP is unavailable (IntersectionObserver).
  function fallbackReveals() {
    var els = document.querySelectorAll("[data-reveal],[data-reveal-stagger],[data-split]");
    if (!("IntersectionObserver" in window)) {
      els.forEach(function (e) { e.classList.add("in"); }); return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } });
    }, { threshold: 0.15 });
    els.forEach(function (e) { e.classList.add("reveal-css"); io.observe(e); });
  }

  /* ─────────────────── Hero board 3D tilt on mouse ──────────────── */
  if (!isTouch && !reduceMotion) {
    var tilt = document.querySelector("[data-tilt]");
    if (tilt) {
      tilt.addEventListener("mousemove", function (e) {
        var r = tilt.getBoundingClientRect();
        var px = (e.clientX - r.left) / r.width - 0.5;
        var py = (e.clientY - r.top) / r.height - 0.5;
        tilt.style.transform = "perspective(1100px) rotateY(" + px * 7 + "deg) rotateX(" + (-py * 7) + "deg)";
      });
      tilt.addEventListener("mouseleave", function () {
        tilt.style.transform = "perspective(1100px) rotateY(0) rotateX(0)";
      });
    }
  }

  /* ───────────────── FAQ accordion (single-open) ────────────────── */
  (function faq() {
    var items = document.querySelectorAll(".relay-accordion details");
    items.forEach(function (item) {
      item.addEventListener("toggle", function () {
        if (!item.open) return;
        items.forEach(function (o) { if (o !== item) o.removeAttribute("open"); });
      });
    });
  })();

  /* ───────────── Kinetic 3D word-swapper (Framer feel) ──────────────
     Mirrors the "3D Roll" Framer component: each word flips up on X with a
     spring; an invisible longest-word ghost reserves a stable, centered slot
     so the two words always line up. */
  function initSwap() {
    var swaps = [].slice.call(document.querySelectorAll("[data-swap]"));
    if (!swaps.length) return;
    var all = [];
    var groups = swaps.map(function (s) {
      var raw = s.getAttribute("data-words") || s.textContent || "";
      var words = raw.split(",").map(function (w) { return w.trim(); }).filter(Boolean);
      all = all.concat(words);
      s.textContent = "";
      var ghost = document.createElement("span"); ghost.className = "kx-ghost";
      var word = document.createElement("span"); word.className = "kx-word"; word.textContent = words[0];
      s.appendChild(ghost); s.appendChild(word);
      return { el: s, words: words, ghost: ghost, cur: word };
    });
    // Reserve every slot to the single longest word so both rows align.
    var longest = all.reduce(function (a, b) { return b.length > a.length ? b : a; }, "");
    groups.forEach(function (g) { g.ghost.textContent = longest; });
    if (reduceMotion) return; // first pair shown statically

    var n = groups.reduce(function (m, g) { return Math.min(m, g.words.length); }, Infinity);
    var idx = 0, timer = null;
    function swap() {
      idx = (idx + 1) % n;
      groups.forEach(function (g) {
        var next = document.createElement("span");
        next.className = "kx-word"; next.textContent = g.words[idx];
        g.el.appendChild(next);
        var out = g.cur; g.cur = next;
        if (hasGSAP) {
          var gsap = window.gsap;
          // Scale & Pop: incoming scales up + fades in; outgoing eases out.
          // Gentler overshoot + less shrink keeps the whole word legible the
          // entire time and stops glyphs ballooning past their slot.
          gsap.set(next, { scale: 0.86, opacity: 0 });
          gsap.to(next, { scale: 1, opacity: 1, duration: 0.6, ease: "back.out(1.3)" });
          gsap.to(out, { scale: 1.06, opacity: 0, duration: 0.42, ease: "power2.in",
            onComplete: function () { if (out.parentNode) out.parentNode.removeChild(out); } });
        } else if (out.parentNode) {
          out.parentNode.removeChild(out);
        }
      });
    }
    function start() { if (!timer) timer = setInterval(swap, 2500); }
    function stop() { if (timer) { clearInterval(timer); timer = null; } }
    start();
    document.addEventListener("visibilitychange", function () { document.hidden ? stop() : start(); });
  }
  // Run after webfonts load so the ghost slot is measured accurately.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(initSwap);
  } else {
    window.addEventListener("load", initSwap);
  }

  /* ───────────── "How credits work" — looping arrow ───────────── */
  function initCreditLoop() {
    var root = document.querySelector("[data-loop]");
    if (!root) return;
    var steps = [].slice.call(root.querySelectorAll(".loop-step"));
    var arrows = [].slice.call(root.querySelectorAll("[data-loop-arrow]"));
    var wrapSvg = root.querySelector("[data-loop-wrap]");
    function active(k) {
      steps.forEach(function (s, i) { s.classList.toggle("is-active", i === k); });
    }
    function clearArrows() {
      arrows.forEach(function (a) { a.classList.remove("is-on", "is-glow"); });
    }
    function glowArrow(k) {
      arrows.forEach(function (a, i) { a.classList.toggle("is-on", i <= k); a.classList.toggle("is-glow", i === k); });
    }

    // Build the wrap-around arc from step 3 back to step 1 (drawn once, updated on resize).
    var SVGNS = "http://www.w3.org/2000/svg", lwLine = null, lwHead = null;
    function buildWrap() {
      if (!wrapSvg || steps.length < 2) return;
      if (!lwLine) {
        lwLine = document.createElementNS(SVGNS, "path"); lwLine.setAttribute("class", "lw-line"); lwLine.setAttribute("pathLength", "1");
        lwHead = document.createElementNS(SVGNS, "path"); lwHead.setAttribute("class", "lw-head"); lwHead.setAttribute("pathLength", "1");
        wrapSvg.appendChild(lwLine); wrapSvg.appendChild(lwHead);
      }
      var rb = root.getBoundingClientRect();
      var s1 = steps[0].getBoundingClientRect(), s3 = steps[steps.length - 1].getBoundingClientRect();
      wrapSvg.setAttribute("viewBox", "0 0 " + rb.width + " " + rb.height);
      var x3 = s3.left - rb.left + s3.width / 2, x1 = s1.left - rb.left + s1.width / 2;
      var yTop = s1.bottom - rb.top, yArc = rb.height - 6;
      lwLine.setAttribute("d", "M" + x3 + " " + yTop + " C " + x3 + " " + yArc + ", " + x1 + " " + yArc + ", " + x1 + " " + (yTop + 7));
      lwHead.setAttribute("d", "M" + (x1 - 7) + " " + (yTop + 15) + " L " + x1 + " " + (yTop + 5) + " L " + (x1 + 7) + " " + (yTop + 15));
    }
    buildWrap();
    window.addEventListener("resize", buildWrap);

    var shafts = arrows.map(function (a) { return a.querySelector(".la-shaft"); });
    var heads = arrows.map(function (a) { return a.querySelector(".la-head"); });
    var wrapPaths = lwLine ? [lwLine, lwHead] : [];
    if (reduceMotion) {
      active(0);
      arrows.forEach(function (a) { a.classList.add("is-on"); });
      shafts.concat(heads).forEach(function (p) { if (p) p.style.strokeDashoffset = "0"; });
      return;
    }
    if (!hasGSAP) {
      function setPath(p, offset, opacity) {
        if (!p) return;
        p.style.strokeDashoffset = String(offset);
        if (opacity !== undefined) p.style.opacity = String(opacity);
      }
      function resetFallback() {
        shafts.concat(heads).forEach(function (p) { setPath(p, 1, 1); });
        wrapPaths.forEach(function (p) { setPath(p, 1, 0); });
        clearArrows();
      }
      function fallbackLoop() {
        resetFallback();
        active(0);
        setTimeout(function () { glowArrow(0); setPath(shafts[0], 0); setPath(heads[0], 0); }, 750);
        setTimeout(function () { arrows[0] && arrows[0].classList.remove("is-glow"); active(1); }, 1600);
        setTimeout(function () { glowArrow(1); setPath(shafts[1], 0); setPath(heads[1], 0); }, 2350);
        setTimeout(function () { arrows[1] && arrows[1].classList.remove("is-glow"); active(2); }, 3200);
        setTimeout(function () { clearArrows(); }, 4100);
      }
      fallbackLoop();
      window.setInterval(fallbackLoop, 4600);
      return;
    }
    var gsap = window.gsap;
    var arrowPaths = shafts.concat(heads);
    var allPaths = arrowPaths.concat(wrapPaths);

    var tl = gsap.timeline({ repeat: -1, paused: true, defaults: { ease: "power2.out" } });
    tl.call(function () {
        gsap.set(arrowPaths, { strokeDashoffset: 1, opacity: 1 });
        gsap.set(wrapPaths, { strokeDashoffset: 1, opacity: 0 });
        clearArrows();
        active(0);
      })
      // ── Card 1: hold before motion ──
      .to({}, { duration: 0.7 })
      // ── Arrow 1: glow + draw ──
      .add(function () { glowArrow(0); })
      .to(shafts[0], { strokeDashoffset: 0, duration: 0.4 })
      .to(heads[0], { strokeDashoffset: 0, duration: 0.15 })
      .to({}, { duration: 0.3 })
      .add(function () { arrows[0].classList.remove("is-glow"); active(1); })
      // ── Card 2: hold, then arrow 2 ──
      .to({}, { duration: 0.7 })
      .add(function () { glowArrow(1); })
      .to(shafts[1], { strokeDashoffset: 0, duration: 0.4 })
      .to(heads[1], { strokeDashoffset: 0, duration: 0.15 })
      .to({}, { duration: 0.3 })
      .add(function () { arrows[1].classList.remove("is-glow"); active(2); })
      // ── Card 3: hold, then reset ──
      .to({}, { duration: 0.8 })
      .add(function () { clearArrows(); active(0); })
      .to(arrowPaths, { opacity: 0, duration: 0.15 });

    window.ScrollTrigger && window.gsap.registerPlugin(window.ScrollTrigger);
    if (window.ScrollTrigger) {
      window.ScrollTrigger.create({
        trigger: root, start: "top 80%",
        onEnter: function () { buildWrap(); tl.restart(); },
        onEnterBack: function () { tl.play(); },
        onLeave: function () { tl.pause(); },
        onLeaveBack: function () { tl.pause(); },
      });
    } else { tl.play(); }
  }

  /* ─── Gauges: count number + draw ring 0→% on enter (robust) ───── */
  function animateCount(el, ring, dur) {
    var end = parseFloat(el.getAttribute("data-count")) || 0;
    if (hasGSAP) {
      var obj = { v: 0 };
      window.gsap.to(obj, { v: end, duration: dur, ease: "power2.out", onUpdate: function () {
        el.textContent = Math.round(obj.v);
        if (ring) ring.style.strokeDasharray = obj.v.toFixed(2) + " 100";
      } });
    } else {
      var t0 = null;
      (function tick(t) {
        if (t0 === null) t0 = t;
        var p = Math.min((t - t0) / (dur * 1000), 1), v = end * (1 - Math.pow(1 - p, 2));
        el.textContent = Math.round(v);
        if (ring) ring.style.strokeDasharray = v.toFixed(2) + " 100";
        if (p < 1) requestAnimationFrame(tick);
      })(performance.now());
    }
  }
  function initGauges() {
    var counts = [].slice.call(document.querySelectorAll("[data-count]"));
    if (!counts.length) return;
    if (reduceMotion) {
      counts.forEach(function (el) { el.textContent = el.getAttribute("data-count"); paintRing(ringFor(el), el.getAttribute("data-count")); });
      return;
    }
    // Reset to empty, then animate when each enters the viewport.
    counts.forEach(function (el) { el.textContent = "0"; emptyRing(ringFor(el)); });
    if (!("IntersectionObserver" in window)) {
      counts.forEach(function (el) { animateCount(el, ringFor(el), 1.8); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        io.unobserve(en.target);
        animateCount(en.target, ringFor(en.target), 1.8);
      });
    }, { threshold: 0.45 });
    counts.forEach(function (el) { io.observe(el); });
  }

  function boot() { initGSAP(); initGauges(); initCreditLoop(); }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

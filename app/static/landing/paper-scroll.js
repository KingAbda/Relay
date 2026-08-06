/* Relay landing camera.

   Writes a single scroll progress value (--p, 0 → 1) plus the per-act opacities
   onto the stage element. Every transform in paper-scroll.css is derived from those,
   so the CSS owns the look and this file only owns "where are we".

   Uses a lightweight lerp to smooth the camera movement so rapid scrolls don't
   feel jittery. The lerp chases the raw scroll position each frame. */

(function () {
  "use strict";

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (reduced.matches) return;

  var wrap = document.querySelector(".stage-wrap");
  var stage = document.querySelector(".stage");
  if (!wrap || !stage) return;

  var acts = [
    document.querySelector(".act-1"),
    document.querySelector(".act-2"),
    document.querySelector(".act-3")
  ];

  function clamp(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }

  /* Smoothstep — eases the ends so acts don't snap on or off. */
  function ramp(v, a, b) {
    var t = clamp((v - a) / (b - a));
    return t * t * (3 - 2 * t);
  }

  /* Visible between `inA`→`inB`, hidden again from `outA`→`outB`. */
  function band(p, inA, inB, outA, outB) {
    return ramp(p, inA, inB) * (1 - ramp(p, outA, outB));
  }

  /* ?p=0.42 pins the camera at a fixed point without scrolling, which is how
     the styleframes are captured. */
  var forced = /[?&]p=(0?\.\d+|0|1(?:\.0+)?)\b/.exec(location.search);
  var pinned = forced ? clamp(parseFloat(forced[1])) : null;

  /* Lerp factor — higher = snappier, lower = smoother. 0.12 feels buttery
     without lagging behind fast scrolls. */
  var LERP = 0.12;

  var ticking = false;
  var travel = 0;
  var targetP = 0;   /* raw scroll position */
  var currentP = 0;  /* lerped position we actually render */
  var lastWrittenP = -1;

  function measure() {
    travel = Math.max(0, wrap.offsetHeight - stage.offsetHeight);
  }

  function lerp(a, b, t) {
    return a + (b - a) * t;
  }

  function update() {
    ticking = false;

    /* Chase the raw target — this runs every rAF so even if scroll stops
       the lerp keeps catching up over a few frames. */
    currentP = lerp(currentP, targetP, LERP);

    /* Once we're close enough, snap to avoid floating-point drift. */
    if (Math.abs(targetP - currentP) < 0.0002) {
      currentP = targetP;
    }

    var p = pinned !== null ? pinned : currentP;

    /* Skip rewriting CSS when nothing changed. */
    if (Math.abs(p - lastWrittenP) < 0.0001) {
      /* Keep the loop alive while the lerp hasn't settled. */
      if (currentP !== targetP && !ticking) {
        ticking = true;
        requestAnimationFrame(update);
      }
      return;
    }
    lastWrittenP = p;

    var a1 = 1 - ramp(p, 0.16, 0.30);
    var a2 = band(p, 0.34, 0.46, 0.60, 0.70);
    var a3 = ramp(p, 0.68, 0.78);

    stage.style.setProperty("--p", p.toFixed(4));
    stage.style.setProperty("--a1", a1.toFixed(3));
    stage.style.setProperty("--a2", a2.toFixed(3));
    stage.style.setProperty("--a3", a3.toFixed(3));

    /* The three steps arrive one after another rather than together. */
    stage.style.setProperty("--n1", ramp(p, 0.74, 0.82).toFixed(3));
    stage.style.setProperty("--n2", ramp(p, 0.80, 0.88).toFixed(3));
    stage.style.setProperty("--n3", ramp(p, 0.86, 0.94).toFixed(3));

    /* Keep faded-out acts out of the tab order and off the screen reader. */
    [a1, a2, a3].forEach(function (a, i) {
      if (acts[i]) acts[i].setAttribute("aria-hidden", a < 0.05 ? "true" : "false");
    });

    /* Keep looping while the lerp hasn't caught up to the target. */
    if (currentP !== targetP && !ticking) {
      ticking = true;
      requestAnimationFrame(update);
    }
  }

  function onScroll() {
    /* Read raw scroll position on every event. */
    targetP = travel > 0 ? clamp(-wrap.getBoundingClientRect().top / travel) : 0;
    if (pinned !== null) targetP = pinned;
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(update);
    }
  }

  function onResize() {
    measure();
    /* Re-sync so we don't lerp from a stale position. */
    targetP = travel > 0 ? clamp(-wrap.getBoundingClientRect().top / travel) : 0;
    if (pinned !== null) targetP = pinned;
    currentP = targetP;
    lastWrittenP = -1;
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(update);
    }
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onResize, { passive: true });
  window.addEventListener("load", function () { measure(); targetP = 0; currentP = 0; lastWrittenP = -1; update(); }, { once: true });
  if (window.ResizeObserver) {
    new ResizeObserver(onResize).observe(wrap);
  }
  measure();
  update();
})();

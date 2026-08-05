/* Relay landing camera.

   Writes a single scroll progress value (--p, 0 → 1) plus the per-act opacities
   onto the stage element. Every transform in paper-scroll.css is derived from those,
   so the CSS owns the look and this file only owns "where are we".

   Reads are batched into a rAF tick so a fast scroll cannot thrash layout. */

(function () {
  "use strict";

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

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
     the styleframes are captured. Mirrors the ?theme= hook on the other
     explore pages. Ignored unless the parameter is present. */
  var forced = /[?&]p=(0?\.\d+|0|1(?:\.0+)?)\b/.exec(location.search);
  var pinned = forced ? clamp(parseFloat(forced[1])) : null;

  var ticking = false;

  function resetForReducedMotion() {
    ["--p", "--a1", "--a2", "--a3", "--n1", "--n2", "--n3"].forEach(function (name) {
      stage.style.removeProperty(name);
    });
    acts.forEach(function (act) {
      if (!act) return;
      act.removeAttribute("aria-hidden");
      act.removeAttribute("inert");
    });
  }

  function update() {
    ticking = false;

    if (reduced.matches) {
      resetForReducedMotion();
      return;
    }

    var travel = wrap.offsetHeight - stage.offsetHeight;
    var p = travel > 0 ? clamp(-wrap.getBoundingClientRect().top / travel) : 0;
    if (pinned !== null) p = pinned;

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
      if (!acts[i]) return;
      var hidden = a < 0.05;
      acts[i].setAttribute("aria-hidden", hidden ? "true" : "false");
      acts[i].toggleAttribute("inert", hidden);
    });
  }

  function onScroll() {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(update);
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("resize", onScroll);
  if (typeof reduced.addEventListener === "function") {
    reduced.addEventListener("change", onScroll);
  } else if (typeof reduced.addListener === "function") {
    reduced.addListener(onScroll);
  }
  update();
})();

/* Relay landing camera.

   Wheel input is normalized into one continuous, speed-limited camera move
   while the illustrated stage is active. Native scrolling resumes at either
   edge. CSS owns the visuals; this file keeps them synchronized and keeps
   inactive acts out of the accessibility tree. */

(function () {
  "use strict";

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce), (max-width: 760px) and (max-height: 700px)");
  var wrap = document.querySelector(".stage-wrap");
  var stage = document.querySelector(".stage");
  if (!wrap || !stage) return;

  var acts = [
    document.querySelector(".act-1"),
    document.querySelector(".act-2"),
    document.querySelector(".act-3")
  ];

  function clamp(v) { return v < 0 ? 0 : v > 1 ? 1 : v; }

  function ramp(v, a, b) {
    var t = clamp((v - a) / (b - a));
    return t * t * (3 - 2 * t);
  }

  function band(p, inA, inB, outA, outB) {
    return ramp(p, inA, inB) * (1 - ramp(p, outA, outB));
  }

  /* ?p=0.42 pins the camera for deterministic styleframes. */
  var forced = /[?&]p=(0?\.\d+|0|1(?:\.0+)?)\b/.exec(location.search);
  var pinned = forced ? clamp(parseFloat(forced[1])) : null;
  var travel = 0;
  var stageStart = 0;
  var lastWrittenP = -1;
  var ticking = false;
  var controlledTarget = 0;
  var controlledFrame = 0;
  var controlledActive = false;
  var lastControlTime = 0;
  var INPUT_SCALE = 0.85;
  var MAX_INPUT_DELTA = 120;
  var MAX_FORWARD_SPEED = 0.96;
  var MAX_REVERSE_SPEED = 0.84;

  function rawProgress() {
    if (pinned !== null) return pinned;
    return travel > 0 ? clamp(-wrap.getBoundingClientRect().top / travel) : 0;
  }

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

  function schedule() {
    if (ticking || reduced.matches) return;
    ticking = true;
    requestAnimationFrame(update);
  }

  function update() {
    ticking = false;
    if (reduced.matches) {
      resetForReducedMotion();
      return;
    }

    var p = rawProgress();
    if (Math.abs(p - lastWrittenP) >= 0.0001) {
      lastWrittenP = p;
      var a1 = 1 - ramp(p, 0.16, 0.30);
      var a2 = band(p, 0.34, 0.46, 0.60, 0.70);
      var a3 = ramp(p, 0.68, 0.78);

      stage.style.setProperty("--p", p.toFixed(4));
      stage.style.setProperty("--a1", a1.toFixed(3));
      stage.style.setProperty("--a2", a2.toFixed(3));
      stage.style.setProperty("--a3", a3.toFixed(3));
      stage.style.setProperty("--n1", ramp(p, 0.74, 0.82).toFixed(3));
      stage.style.setProperty("--n2", ramp(p, 0.80, 0.88).toFixed(3));
      stage.style.setProperty("--n3", ramp(p, 0.86, 0.94).toFixed(3));

      [a1, a2, a3].forEach(function (opacity, index) {
        if (!acts[index]) return;
        var hidden = opacity < 0.05;
        acts[index].setAttribute("aria-hidden", hidden ? "true" : "false");
        acts[index].toggleAttribute("inert", hidden);
      });
    }

  }

  function measureAndUpdate() {
    cancelControlledScroll();
    travel = Math.max(0, wrap.offsetHeight - stage.offsetHeight);
    stageStart = wrap.getBoundingClientRect().top + window.scrollY;
    lastWrittenP = -1;
    schedule();
  }

  function onScroll() {
    schedule();
  }

  function cancelControlledScroll() {
    cancelAnimationFrame(controlledFrame);
    controlledActive = false;
    controlledFrame = 0;
    controlledTarget = window.scrollY;
  }

  function controlledScrollFrame(now) {
    var current = window.scrollY;
    var difference = controlledTarget - current;
    var elapsed = lastControlTime ? Math.min(now - lastControlTime, 34) : 16;
    var maxSpeed = difference > 0 ? MAX_FORWARD_SPEED : MAX_REVERSE_SPEED;
    var maxStep = maxSpeed * elapsed;
    var step = difference * 0.16;
    lastControlTime = now;

    if (Math.abs(step) > maxStep) step = Math.sign(step) * maxStep;
    if (Math.abs(difference) < 0.5) {
      window.scrollTo(0, controlledTarget);
      controlledActive = false;
      controlledFrame = 0;
      return;
    }

    window.scrollTo(0, current + step);
    controlledFrame = requestAnimationFrame(controlledScrollFrame);
  }

  function wheelDeltaPixels(event) {
    var delta = event.deltaY;
    if (event.deltaMode === 1) delta *= 16;
    if (event.deltaMode === 2) delta *= window.innerHeight;
    return delta;
  }

  function normalizeWheelDelta(delta) {
    return Math.max(-MAX_INPUT_DELTA, Math.min(MAX_INPUT_DELTA, delta));
  }

  function queueControlledDelta(rawDelta, stageEnd) {
    /* A fast upward flick means “replay the stage.” Keep the cinematic speed
       cap, but send the target to the beginning so momentum cannot stop the
       reverse sequence halfway through. Gentle input remains incremental. */
    if (rawDelta < -MAX_INPUT_DELTA) {
      controlledTarget = stageStart;
      return;
    }

    var delta = normalizeWheelDelta(rawDelta);
    controlledTarget = Math.max(
      stageStart,
      Math.min(stageEnd, controlledTarget + delta * INPUT_SCALE)
    );
  }

  function shouldCatchReverseEntry(rawDelta, y, stageEnd) {
    var fastEntryRange = Math.max(window.innerHeight * 1.5, 900);
    var fastEntry = rawDelta < -MAX_INPUT_DELTA &&
      y <= stageEnd + fastEntryRange;

    return rawDelta < 0 &&
      (controlledActive || fastEntry || y + rawDelta <= stageEnd + 2);
  }

  function startControlledMove(target) {
    cancelAnimationFrame(controlledFrame);
    controlledTarget = target;
    controlledActive = true;
    lastControlTime = 0;
    controlledFrame = requestAnimationFrame(controlledScrollFrame);
  }

  function onWheel(event) {
    if (pinned !== null || reduced.matches) return;

    var rawDelta = wheelDeltaPixels(event);
    var delta = normalizeWheelDelta(rawDelta);
    if (Math.abs(delta) < 1) return;

    var y = window.scrollY;
    var stageEnd = stageStart + travel;
    if (y > stageEnd + 2) {
      if (shouldCatchReverseEntry(rawDelta, y, stageEnd)) {
        event.preventDefault();
        if (!controlledActive) {
          /* Anchor at the final frame before rewinding. Without this handoff,
             browser momentum can leap from the FAQ straight to the hero. */
          window.scrollTo(0, stageEnd);
          controlledTarget = stageEnd;
        }
        queueControlledDelta(rawDelta, stageEnd);
        if (!controlledActive) startControlledMove(controlledTarget);
      }
      return;
    }
    if (y < stageStart - 2) return;

    if ((delta < 0 && y <= stageStart + 4) ||
        (delta > 0 && y >= stageEnd - 4)) {
      cancelControlledScroll();
      return;
    }

    event.preventDefault();
    if (!controlledActive) controlledTarget = y;
    queueControlledDelta(rawDelta, stageEnd);

    if (!controlledActive) {
      startControlledMove(controlledTarget);
    }
  }

  function onMotionPreferenceChange() {
    if (reduced.matches) {
      cancelControlledScroll();
      resetForReducedMotion();
      return;
    }
    measureAndUpdate();
  }

  window.addEventListener("scroll", onScroll, { passive: true });
  window.addEventListener("wheel", onWheel, { passive: false });
  window.addEventListener("pointerdown", cancelControlledScroll, { passive: true });
  window.addEventListener("keydown", cancelControlledScroll, { passive: true });
  window.addEventListener("resize", measureAndUpdate, { passive: true });
  window.addEventListener("load", measureAndUpdate, { once: true });
  if (window.ResizeObserver) new ResizeObserver(measureAndUpdate).observe(wrap);
  if (typeof reduced.addEventListener === "function") {
    reduced.addEventListener("change", onMotionPreferenceChange);
  } else if (typeof reduced.addListener === "function") {
    reduced.addListener(onMotionPreferenceChange);
  }

  if (reduced.matches) resetForReducedMotion();
  else measureAndUpdate();
})();

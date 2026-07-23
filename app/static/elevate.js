/* Relay — test version 1
   One motion idea: a quiet scroll reveal. Plus the functional bits —
   mobile menu, nav border on scroll, single-open FAQ, and a slow
   highlight cycle on the credit loop. Honours prefers-reduced-motion
   and an explicit ?static=1 lite mode. */
(function () {
  "use strict";

  var liteMode = /[?&]static=1/.test(window.location.search);
  var reduceMotion = liteMode || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (liteMode) document.documentElement.classList.add("static-mode");

  /* ── Mobile menu + dashboard show-target buttons ── */
  var menuToggle = document.getElementById("menuToggle");
  var navLinks = document.getElementById("navLinks");
  if (menuToggle && navLinks) {
    menuToggle.addEventListener("click", function () {
      var open = navLinks.classList.toggle("responsive");
      menuToggle.setAttribute("aria-expanded", String(open));
    });
  }
  document.querySelectorAll("[data-show-target]").forEach(function (button) {
    button.addEventListener("click", function () {
      var target = document.getElementById(button.getAttribute("data-show-target"));
      if (!target) return;
      target.style.display = "block";
      button.setAttribute("aria-expanded", "true");
      var firstField = target.querySelector("input, select, textarea, button");
      if (firstField) firstField.focus();
    });
  });

  /* ── Nav border once the page scrolls ── */
  var nav = document.getElementById("siteNav");
  function onScroll() {
    if (nav) nav.classList.toggle("scrolled", (window.pageYOffset || 0) > 12);
  }
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  /* ── Scroll reveal (the one motion idea) ── */
  function initReveals() {
    var els = document.querySelectorAll("[data-reveal],[data-reveal-stagger],[data-split]");
    if (reduceMotion || !("IntersectionObserver" in window)) {
      els.forEach(function (e) { e.classList.add("in"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { threshold: 0.15 });
    els.forEach(function (e) { e.classList.add("reveal-css"); io.observe(e); });
  }

  /* ── FAQ accordion, single-open ── */
  function initFaq() {
    var items = document.querySelectorAll(".faq-list details");
    items.forEach(function (item) {
      item.addEventListener("toggle", function () {
        if (!item.open) return;
        items.forEach(function (o) { if (o !== item) o.removeAttribute("open"); });
      });
    });
  }

  /* ── Credit loop: slow highlight cycle 1 → 2 → 3 ── */
  function initCreditLoop() {
    var root = document.querySelector("[data-loop]");
    if (!root) return;
    var steps = [].slice.call(root.querySelectorAll(".loop-step"));
    var arrows = [].slice.call(root.querySelectorAll(".loop-arrow"));
    if (!steps.length) return;

    if (reduceMotion) {
      arrows.forEach(function (a) { a.classList.add("is-on"); });
      return;
    }

    var idx = -1, timer = null;
    function tick() {
      idx = (idx + 1) % steps.length;
      steps.forEach(function (s, i) { s.classList.toggle("is-active", i === idx); });
      // Arrows light up behind the active step, then all fade on reset.
      arrows.forEach(function (a, i) { a.classList.toggle("is-on", idx > 0 && i < idx); });
    }
    function start() { if (!timer) { tick(); timer = setInterval(tick, 2800); } }
    function stop() {
      if (timer) { clearInterval(timer); timer = null; }
      idx = -1;
      steps.forEach(function (s) { s.classList.remove("is-active"); });
      arrows.forEach(function (a) { a.classList.remove("is-on"); });
    }
    if ("IntersectionObserver" in window) {
      new IntersectionObserver(function (entries) {
        entries.forEach(function (en) { en.isIntersecting ? start() : stop(); });
      }, { threshold: 0.3 }).observe(root);
    } else {
      start();
    }
    document.addEventListener("visibilitychange", function () {
      if (document.hidden) { stop(); } else { start(); }
    });
  }

  function boot() { initReveals(); initFaq(); initCreditLoop(); }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();

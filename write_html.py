# Write Relay index.html
import re

html = r"""{% extends "base.html" %}
{% block title %}Home{% endblock %}
{% block content %}
<div class="hero">
  <div class="hero-inner container">
    <div class="hero-text reveal">
      <div class="hero-badge">{% if pilot_vertical %}Now piloting <strong>{{ pilot_vertical_name }}</strong> at NYU{% else %}Now piloting at NYU{% endif %}</div>
      <h1 class="hero-title">Trade skills.<br><span class="grad-text">Not invoices.</span></h1>
      <p class="hero-sub">A campus network where students share their talents and learn from each other. Paid in time credits, not cash.</p>
      <div class="hero-actions">
        {% if user %}
          <a href="/dashboard" class="btn btn-primary">Go to Dashboard</a>
          <a href="/browse" class="btn btn-secondary">Browse Skills</a>
        {% else %}
          <a href="/signup" class="btn btn-primary">Join the waitlist</a>
          <a href="/browse" class="btn btn-secondary">Browse skills</a>
        {% endif %}
      </div>
      <div class="hero-check"><div class="hero-check-icon"><span>&#10003;</span></div><span class="hero-check-text">30 min = 1 credit. Earn by teaching, spend by learning.</span></div>
    </div>
    <div class="hero-visual reveal reveal-delay-2">
      <div class="hero-ring"></div><div class="hero-ring"></div><div class="hero-ring"></div>
      <div class="hero-emblem"><span>R</span></div>
      <div class="hero-geo hero-geo-1"></div><div class="hero-geo hero-geo-2"></div><div class="hero-geo hero-geo-3"></div>
    </div>
  </div>
</div>

<section class="section">
  <div class="container section-center">
    <div class="section-label reveal">The problem</div>
    <h2 class="section-title reveal reveal-delay-1">Favor culture isn't fair culture.</h2>
  </div>
  <div class="container stat-grid" style="margin-top:40px;">
    <div class="card stat-card reveal reveal-delay-1"><div class="stat-value">70%</div><p class="stat-label">of students have a skill to teach but no one to share it with</p></div>
    <div class="card stat-card reveal reveal-delay-2"><div class="stat-value">85%</div><p class="stat-label">want to learn something but can't find a mentor on campus</p></div>
    <div class="card stat-card reveal reveal-delay-3"><div class="stat-value">75%</div><p class="stat-label">prefer skill trades over cash for peer-to-peer learning</p></div>
  </div>
</section>

<section class="section" id="how">
  <div class="container section-center">
    <div class="section-label reveal">How it works</div>
    <h2 class="section-title reveal reveal-delay-1">The relay race.</h2>
    <p class="section-sub reveal reveal-delay-2">A simple loop: you teach, you earn, you spend, you learn.</p>
  </div>
  <div class="container" style="margin-top:40px;">
    <div class="grid-4">
      <div class="card step-card reveal reveal-delay-1"><div class="step-num">1</div><h3 class="step-title">Every 30 min = 1 credit</h3><p class="step-desc">Your time is standardized. A session is one unit, no matter the skill.</p></div>
      <div class="card step-card reveal reveal-delay-2"><div class="step-num">2</div><h3 class="step-title">Earn by teaching</h3><p class="step-desc">Every session you lead adds credits to your account.</p></div>
      <div class="card step-card reveal reveal-delay-3"><div class="step-num">3</div><h3 class="step-title">Spend by learning</h3><p class="step-desc">Use credits to book sessions with anyone on the network.</p></div>
      <div class="card step-card reveal reveal-delay-4"><div class="step-num">4</div><h3 class="step-title">Verified by .edu</h3><p class="step-desc">Only university students with a valid .edu email can join.</p></div>
    </div>
  </div>
</section>

<section class="section" id="faq">
  <div class="container" style="max-width:760px;">
    <div class="section-label reveal">Questions</div>
    <h2 class="section-title reveal reveal-delay-1" style="margin-bottom:32px;">The honest answers.</h2>
    <div style="display:grid;gap:12px;">
      <details class="faq-item reveal reveal-delay-1"><summary>Is Relay free? <span class="faq-plus">+</span></summary><p class="faq-answer">Yes. Joining is free &mdash; you earn credits by teaching and spend them to learn. No cash changes hands between peers.</p></details>
      <details class="faq-item reveal reveal-delay-2"><summary>What if I only want to learn? <span class="faq-plus">+</span></summary><p class="faq-answer">New members start with a few free credits to get going. But Relay works best when everyone shares something.</p></details>
      <details class="faq-item reveal reveal-delay-3"><summary>Is the teacher any good? <span class="faq-plus">+</span></summary><p class="faq-answer">Everyone is a verified student. You rate each session afterward &mdash; the best teachers rise to the top.</p></details>
      <details class="faq-item reveal reveal-delay-4"><summary>Who can join right now? <span class="faq-plus">+</span></summary><p class="faq-answer">We're starting with NYU students this fall. Add your email to be in the first cohort.</p></details>
    </div>
  </div>
</section>

<section class="cta-section">
  <div class="container">
    <div class="cta-card reveal">
      <div class="cta-label">Built for students. Powered by collaboration.</div>
      <h2 class="cta-title">Ready to trade skills?</h2>
      <p class="cta-sub">Join the waitlist and be the first to know when Relay launches at your campus. Your first 3 credits are on us.</p>
      <div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;margin-top:8px;position:relative;z-index:1;">{% if user %}<a href="/dashboard" class="btn btn-primary">Go to Dashboard</a>{% else %}<a href="/signup" class="btn btn-primary">Get early access</a>{% endif %}</div>
      <div style="font-size:13px;color:#64748B;position:relative;z-index:1;">First sign-ups get <b style="color:var(--cta);">free starter credits.</b></div>
    </div>
  </div>
</section>

<style>@media(max-width:900px){.grid-4{grid-template-columns:1fr 1fr!important}}@media(max-width:720px){section{padding:60px 0!important}.stat-grid{grid-template-columns:1fr!important}.grid-4{grid-template-columns:1fr!important}}</style>
<script>(function(){var r=document.querySelectorAll('.reveal');if(!r.length)return;function c(){var h=window.innerHeight;r.forEach(function(e){if(e.classList.contains('visible'))return;var b=e.getBoundingClientRect();if(b.top<h-60)e.classList.add('visible')})}window.addEventListener('scroll',c);window.addEventListener('resize',c);c()})();</script>
{% endblock %}
"""

path = r'C:\Users\ATouray\relay-local\app\templates\index.html'
with open(path, 'w') as f:
    f.write(html)
print(f'Written {len(html)} bytes to {path}')

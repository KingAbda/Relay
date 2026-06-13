css = """/* Relay v2: Inspired by Apple, Stripe, Figma, Lusion, Reaktor */
:root{--bg:#F8FAFC;--bg-2:#F1F5F9;--panel:#FFF;--panel-line:rgba(37,99,235,0.12);--ink:#1E293B;--muted:#64748B;--primary:#2563EB;--primary-soft:#60A5FA;--primary-deep:#1D4ED8;--primary-bg:rgba(37,99,235,0.08);--cta:#F97316;--cta-soft:#FB923C;--cta-shadow:rgba(249,115,22,0.25);--success:#10B981;--display:"Inter",sans-serif;--body:"Inter",sans-serif;--radius:14px;--radius-xl:16px;--shadow:0 1px 3px rgba(30,41,59,0.06);--shadow-lg:0 10px 25px rgba(30,41,59,0.08);--nav-bg:rgba(248,250,252,0.85);--card-hover-border:rgba(37,99,235,0.2);--border-light:#E2E8F0}
[data-theme="dark"]{--bg:#0F172A;--bg-2:#1E293B;--panel:#1E293B;--panel-line:rgba(96,165,250,0.12);--ink:#F1F5F9;--muted:#94A3B8;--primary:#60A5FA;--primary-soft:#93C5FD;--primary-deep:#2563EB;--primary-bg:rgba(96,165,250,0.1);--cta:#FB923C;--cta-shadow:rgba(251,146,60,0.25);--success:#34D399;--shadow:0 1px 3px rgba(0,0,0,0.3);--shadow-lg:0 10px 25px rgba(0,0,0,0.5);--nav-bg:rgba(15,23,42,0.85);--card-hover-border:rgba(96,165,250,0.25);--border-light:rgba(148,163,184,0.15)}
*{box-sizing:border-box;margin:0;padding:0}
html{scroll-behavior:smooth}
body{font-family:var(--body);background:var(--bg);color:var(--ink);line-height:1.6;min-height:100vh;display:flex;flex-direction:column;transition:background .3s,color .3s}
a{color:var(--primary);text-decoration:none}
a:hover{color:var(--primary-soft)}

/* Background FX — Stripe gradient mesh + Lusion floating orb */
.bg-fx{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
.bg-fx::before{content:"";position:absolute;inset:-10%;background:radial-gradient(60% 50% at 75% 12%,rgba(37,99,235,.10),transparent 60%),radial-gradient(55% 45% at 10% 80%,rgba(249,115,22,.08),transparent 60%),radial-gradient(50% 60% at 50% 70%,rgba(16,185,129,.06),transparent 55%),linear-gradient(180deg,var(--bg),var(--bg-2) 55%,var(--bg));animation:ambientPulse 8s ease-in-out infinite alternate}
@keyframes ambientPulse{0%{opacity:0.7;transform:scale(1)}100%{opacity:1;transform:scale(1.03)}}
.bg-fx::after{content:"";position:absolute;width:600px;height:600px;border-radius:50%;background:radial-gradient(circle,rgba(37,99,235,.06),transparent 70%);top:-10%;right:-5%;animation:floatOrb 12s ease-in-out infinite alternate}
@keyframes floatOrb{0%{transform:translate(0,0) scale(1)}50%{transform:translate(-30px,40px) scale(1.1)}100%{transform:translate(20px,-20px) scale(0.95)}}
.grid-overlay{position:absolute;inset:0;background-image:linear-gradient(rgba(37,99,235,.04)1px,transparent 1px),linear-gradient(90deg,rgba(37,99,235,.04)1px,transparent 1px);background-size:64px 64px;mask-image:radial-gradient(circle at 50% 30%,#000 30%,transparent 80%)}
.page{position:relative;z-index:1;flex:1;display:flex;flex-direction:column}
.container{width:100%;max-width:1100px;margin:0 auto;padding:0 24px}

/* Nav — Apple clean minimal */
nav{padding:14px 0;border-bottom:1px solid var(--panel-line);background:var(--nav-bg);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);position:sticky;top:0;z-index:100}
nav .container{display:flex;align-items:center;justify-content:space-between}
nav .logo{display:flex;align-items:center;gap:10px;font-family:var(--display);font-weight:700;font-size:1.25rem;color:var(--ink);text-decoration:none;letter-spacing:-0.02em;transition:opacity .2s}
nav .logo:hover{opacity:0.8}
nav .logo-icon{width:32px;height:32px;background:var(--primary);border-radius:8px;display:flex;align-items:center;justify-content:center;font-family:var(--display);font-weight:800;font-size:16px;color:#FFF;transition:transform .3s,border-radius .3s}
nav .logo:hover .logo-icon{transform:scale(1.05);border-radius:10px}
nav .nav-links{display:flex;align-items:center;gap:28px}
nav .nav-links a{color:var(--muted);text-decoration:none;font-size:0.88rem;font-weight:500;transition:color .2s}
nav .nav-links a:hover{color:var(--ink)}
.nav-join{background:var(--cta);color:#FFF!important;padding:8px 20px;border-radius:999px;font-weight:600!important;font-size:0.82rem!important;transition:all .25s!important;box-shadow:0 2px 8px var(--cta-shadow)}
.nav-join:hover{transform:translateY(-1px);box-shadow:0 6px 16px var(--cta-shadow);color:#FFF!important}
.credit-badge{background:var(--primary-bg);color:var(--primary);padding:4px 14px;border-radius:999px;font-size:0.82rem;font-weight:600;font-family:var(--display);border:1px solid var(--panel-line)}
.theme-toggle{background:var(--panel);border:1px solid var(--panel-line);border-radius:999px;width:38px;height:38px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:1.1rem;color:var(--muted);transition:all .25s}
.theme-toggle:hover{border-color:var(--primary);color:var(--primary);transform:rotate(15deg)}

/* Buttons — Figma clean */
.btn{display:inline-flex;align-items:center;gap:8px;padding:12px 28px;border-radius:10px;font-family:var(--body);font-size:0.92rem;font-weight:600;text-decoration:none;cursor:pointer;border:none;transition:all .25s;letter-spacing:0.02em}
.btn-primary{background:var(--cta);color:#FFF;box-shadow:0 4px 12px var(--cta-shadow)}
.btn-primary:hover{transform:translateY(-2px);box-shadow:0 8px 20px var(--cta-shadow)}
.btn-secondary{background:var(--panel);color:var(--ink);border:1.5px solid var(--border-light)}
.btn-secondary:hover{background:var(--bg-2);border-color:var(--primary);color:var(--primary)}
.btn-sm{padding:10px 24px;font-size:0.82rem;border-radius:8px}

/* Hero — Reaktor bold typography + Apple product showcase */
.hero{padding:80px 0 40px;position:relative}
.hero-inner{display:flex;flex-direction:row;align-items:center;gap:60px}
.hero-text{flex:1;max-width:560px;display:flex;flex-direction:column;gap:24px}
.hero-badge{padding:6px 16px;background:var(--primary-bg);border-radius:999px;width:fit-content;font-family:var(--display);font-size:12px;font-weight:600;color:var(--primary);letter-spacing:0.5px;border:1px solid var(--panel-line)}
.hero-title{font-size:64px;letter-spacing:-3px;line-height:1.02;margin:0;color:var(--ink);font-weight:800}
.hero-title .grad-text{background:linear-gradient(135deg,var(--primary),var(--cta));-webkit-background-clip:text;background-clip:text;color:transparent}
.hero-sub{font-size:18px;color:var(--muted);line-height:1.7;margin:0;max-width:480px}
.hero-actions{display:flex;gap:12px;flex-wrap:wrap}
.hero-check{display:flex;align-items:center;gap:8px}
.hero-check-icon{width:20px;height:20px;border-radius:10px;background:var(--success);display:flex;align-items:center;justify-content:center;flex-shrink:0}
.hero-check-icon span{font-size:10px;color:#FFF}
.hero-check-text{font-size:13px;color:var(--muted)}

/* Apple-inspired hero emblem + Lusion rings */
.hero-visual{flex:1;display:flex;align-items:center;justify-content:center;position:relative;min-height:420px}
.hero-emblem{width:180px;height:180px;background:linear-gradient(135deg,var(--primary),var(--primary-deep));border-radius:40px;display:flex;align-items:center;justify-content:center;box-shadow:0 20px 60px rgba(37,99,235,0.2);animation:emblemFloat 6s ease-in-out infinite;position:relative;z-index:2}
.hero-emblem span{font-family:var(--display);font-weight:800;font-size:80px;color:#FFF;letter-spacing:-4px}
@keyframes emblemFloat{0%,100%{transform:translateY(0) scale(1)}50%{transform:translateY(-12px) scale(1.02)}}
.hero-ring{position:absolute;border-radius:50%;border:2px solid var(--primary);opacity:0.08;animation:ringPulse 4s ease-in-out infinite}
.hero-ring:nth-child(2){width:280px;height:280px;animation-delay:0s}
.hero-ring:nth-child(3){width:360px;height:360px;animation-delay:1s}
.hero-ring:nth-child(4){width:440px;height:440px;animation-delay:2s}
@keyframes ringPulse{0%,100%{transform:scale(1);opacity:0.08}50%{transform:scale(1.05);opacity:0.03}}

/* Stripe floating geometric accents */
.hero-geo{position:absolute;pointer-events:none}
.hero-geo-1{top:10%;right:15%;width:60px;height:60px;border-radius:16px;background:rgba(249,115,22,0.08);transform:rotate(15deg);animation:geoDrift 7s ease-in-out infinite}
.hero-geo-2{bottom:15%;left:10%;width:40px;height:40px;border-radius:50%;background:rgba(16,185,129,0.08);animation:geoDrift 9s ease-in-out infinite reverse}
.hero-geo-3{top:30%;left:5%;width:30px;height:30px;border-radius:8px;background:rgba(37,99,235,0.06);transform:rotate(45deg);animation:geoDrift 6s ease-in-out infinite}
@keyframes geoDrift{0%,100%{transform:translateY(0) rotate(0deg)}50%{transform:translateY(-15px) rotate(10deg)}}

/* Sections */
.section{padding:100px 0;position:relative}
.section-label{font-family:var(--display);letter-spacing:2px;text-transform:uppercase;font-size:11px;font-weight:600;color:var(--primary);margin-bottom:16px}
.section-title{font-size:40px;letter-spacing:-1.5px;margin:0;color:var(--ink);font-weight:700}
.section-sub{color:var(--muted);font-size:17px;margin-top:12px;line-height:1.6}
.section-center{text-align:center}

/* Figma scroll-reveal */
.reveal{opacity:0;transform:translateY(30px);transition:opacity .7s,transform .7s}
.reveal.visible{opacity:1;transform:translateY(0)}
.reveal-delay-1{transition-delay:0.1s}
.reveal-delay-2{transition-delay:0.2s}
.reveal-delay-3{transition-delay:0.3s}

/* Cards */
.card{background:var(--panel);border:1px solid var(--panel-line);border-radius:var(--radius-xl);padding:28px;transition:all .3s;box-shadow:var(--shadow)}
.card:hover{border-color:var(--card-hover-border);transform:translateY(-4px);box-shadow:var(--shadow-lg)}
.step-card{padding:32px 28px;display:flex;flex-direction:column;gap:14px;align-items:flex-start}
.step-num{width:48px;height:48px;border-radius:14px;background:var(--primary-bg);display:flex;align-items:center;justify-content:center;font-family:var(--display);font-weight:800;font-size:20px;color:var(--primary);transition:all .3s}
.step-card:hover .step-num{background:var(--primary);color:#FFF;transform:scale(1.05)}
.step-title{font-size:17px;font-weight:600;margin:0;color:var(--ink)}
.step-desc{color:var(--muted);font-size:13px;line-height:1.6;margin:0}
.stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:20px}
.stat-card{text-align:center;padding:40px 28px}
.stat-value{font-family:var(--display);font-weight:800;font-size:52px;letter-spacing:-2px;color:var(--primary);line-height:1}
.stat-label{color:var(--muted);font-size:14px;margin-top:12px;line-height:1.4}
.form-group{margin-bottom:20px}
.form-group label{display:block;font-size:0.82rem;color:var(--muted);margin-bottom:6px;font-weight:600;text-transform:uppercase;letter-spacing:.04em}
.form-input,.form-select,.form-textarea{width:100%;padding:12px 16px;background:var(--bg-2);border:1px solid var(--border-light);border-radius:10px;color:var(--ink);font-family:var(--body);font-size:0.95rem;transition:all .2s}
.form-input:focus,.form-select:focus,.form-textarea:focus{outline:none;border-color:var(--primary);box-shadow:0 0 0 3px rgba(37,99,235,.15)}
.form-textarea{min-height:90px;resize:vertical}
h1,h2,h3,h4{font-family:var(--display);font-weight:700;line-height:1.3}
h1{font-size:2.5rem;letter-spacing:-0.03em}
h2{font-size:1.8rem;letter-spacing:-0.02em}
.muted{color:var(--muted)}
.grad-text{background:linear-gradient(135deg,var(--primary),var(--cta));-webkit-background-clip:text;background-clip:text;color:transparent}

/* FAQ */
.faq-item{background:var(--panel);border:1px solid var(--panel-line);border-radius:14px;padding:0 24px;transition:border-color .25s}
.faq-item:hover{border-color:var(--card-hover-border)}
.faq-item summary{font-family:var(--display);font-weight:600;font-size:16px;cursor:pointer;list-style:none;padding:20px 0;display:flex;justify-content:space-between;align-items:center}
.faq-item summary::-webkit-details-marker{display:none}
.faq-plus{color:var(--cta);font-size:22px;font-weight:300;transition:transform .25s}
.faq-item[open] .faq-plus{transform:rotate(45deg)}
.faq-answer{color:var(--muted);font-size:15px;padding:0 0 24px;line-height:1.6}

/* CTA — Apple dark hero */
.cta-section{padding:100px 0;position:relative}
.cta-card{text-align:center;background:var(--ink);border-radius:28px;padding:80px 40px;display:flex;flex-direction:column;align-items:center;gap:16px;position:relative;overflow:hidden}
.cta-card::before{content:"";position:absolute;inset:0;background:radial-gradient(60% 50% at 30% 20%,rgba(37,99,235,.15),transparent 60%),radial-gradient(50% 40% at 80% 70%,rgba(249,115,22,.1),transparent 50%);pointer-events:none}
.cta-label{font-family:var(--display);letter-spacing:2px;text-transform:uppercase;font-size:11px;font-weight:600;color:var(--primary-soft);position:relative}
.cta-title{font-size:40px;color:#FFF;margin:0;position:relative;letter-spacing:-1.5px}
.cta-sub{color:#94A3B8;font-size:16px;max-width:500px;margin:0;line-height:1.6;position:relative}
table{width:100%;border-collapse:collapse}
th{text-align:left;font-size:0.78rem;color:var(--muted);text-transform:uppercase;letter-spacing:.06em;padding:10px 14px;border-bottom:1px solid var(--panel-line)}
td{padding:12px 14px;border-bottom:1px solid var(--panel-line);font-size:0.9rem}
footer{margin-top:auto;padding:28px 0;border-top:1px solid var(--panel-line);text-align:center;color:var(--muted);font-size:0.85rem}
footer a{color:var(--primary)}
@media(max-width:900px){.hero-inner{flex-direction:column!important}}
@media(max-width:768px){
.stat-grid{grid-template-columns:1fr}
nav .nav-links{gap:10px}
nav .nav-links a{font-size:0.78rem}
h1{font-size:1.8rem}
.hero-title{font-size:40px}
.section-title{font-size:28px}
.cta-title{font-size:28px}
.cta-card{padding:48px 24px}
.card{padding:16px}
.hero-emblem{width:120px;height:120px}
.hero-emblem span{font-size:52px}
.hero{padding:40px 0 20px}
.section{padding:60px 0}
.stat-value{font-size:36px}
}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""
with open(r'C:\Users\ATouray\relay-local\app\static\style.css', 'w') as f:
    f.write(css)
print('CSS written')

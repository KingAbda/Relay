# PRISM-SCAN ANALYSIS — RELAY_BUSINESS_PLAN.md

**Lens applied:**
> "Trace every explicit claim this artifact embeds. For each, assume it is false. Trace the corruption. Build three alternatives, each inverting one claim. Predict which false claim causes the slowest, most invisible failure."

**Date:** 2026-07-29  
**Artifact:** RELAY_BUSINESS_PLAN.md (v2.0, June 13, 2026)  
**Status:** Historical planning document (self-described)

---

## FINDINGS TABLE

| # | Embedded Claim | If FALSE → What Breaks? | Corruption Path | Severity | Fixable? | Detection Signal |
|---|---|---|---|---|---|---|
| 1 | **300+ student interviews completed** | Demand validation evaporates. Every downstream claim ("70% would teach", "85% want to learn") rests on this sample. Without real interviews, the entire product-market fit assertion is fabricated. | → P-M fit claimed but fake → wrong features built → users join, find nothing useful → churn → "we validated this!" is exposed as fraud when no interview artifacts exist. | **CRITICAL** | No — if fabricated, cannot retroactively conduct them. Can conduct them now but the document's claims were deceptive. | Interviews were documented? Raw notes exist? Can interviewees be re-contacted? |
| 2 | **Financial Status: Break-even** | The business is actually cash-negative or burning. Every comfort statement ("you can't lose money", "emergency playbook") is hollow. | → Founder makes decisions assuming zero risk → burns time on non-viable path → misses real income opportunities → eventual cash crisis → bail at a cost. | **HIGH** | Yes — determine true burn rate, update claims. If actually cash-negative, the whole emergency playbook (section A) is misinformation. | Revenue data vs server costs. Are there paying users or just cost outlay? |
| 3 | **MVP: Live and operational** | No working product exists. The launch checklist (P0 items: rating system, Stripe, mobile responsive, onboarding) are missing — contradicting "MVP is shipping". | → Users who sign up in trial encounter broken flows → zero retention → word-of-mouth is negative → reputation damage ("vaporware") → future launches tainted before they start. | **CRITICAL** | Yes — ship the MVP. But the document contradicts itself: P0 says "Fix before launch" implying MVP is NOT operational. | Can a new user sign up and complete a session today? P0 list would be empty if MVP were live. |
| 4 | **70% of 300+ students have a skill they'd teach if compensated fairly** | Supply won't materialize. The marketplace has no teachers. | → Early users find no listings → leave → cold-start problem persists → network effects never kick in → marketplace graveyard. | **HIGH** | Partially — could retrain survey methodology. But if the stat was fabricated or leading-question-biased, supply gap is real. | Skill listing count vs user count on platform. Are students actually listing? |
| 5 | **85% want to learn something but can't cost-justify a mentor** | Demand won't materialize. Students are actually satisfied with YouTube/friends/AI. | → No learners → teachers earn no credits → teachers leave → platform empty on both sides. The value prop ("filling the gap") is imaginary. | **HIGH** | Partially — pivot positioning. But core thesis fails. | Session booking data. Do users actively seek sessions? |
| 6 | **75% supply-demand match rate** | The marketplace is structurally unbalanced. For every skill offered, there's no corresponding learner (or vice versa). | → Mismatch means frustrated users on both sides → teachable skills have no demand, wanted skills have no teachers → credits become useless currency → abandonment. | **HIGH** | Yes — with enough users, matches improve. But at small scale this kills the platform. | Actual match rate from platform data. Skill categories offered vs requested. |
| 7 | **Students spend $40-80/hr on tutoring, $20/mo on Skillshare** | The reference pricing is wrong, making $14.99 look cheap against a straw man. If actual comparison price is $0 (free alternatives), value perception collapses. | → Pricing feels expensive vs free (YouTube, friends, Reddit) → no conversion → monetization fails → "1-2 UberEats" argument is false comfort → $0 revenue. | **MEDIUM** | Yes — validate actual student spending on learning. But if wrong, pricing psychology is self-deceptive. | Student budget surveys. What do students actually spend on skill acquisition? |
| 8 | **Network effects: each new user adds both supply AND demand** | Users are either teachers OR learners, not both. Most sign up to learn, few to teach. Classic marketplace imbalance. | → Asymmetric growth (many learners, few teachers) → long wait times → learners churn → teachers have no students → death spiral. Balanced growth is NOT automatic; it requires active curation. | **HIGH** | Partially — can incentivize teaching. But the claim that it's "built-in" is false, leading to under-investment in supply acquisition. | Ratio of teaching listings to learning searches. What % of users both teach AND learn? |
| 9 | **NYU is a captive, dense audience (60K)** | NYU students don't actually interact across schools/departments. The 60K number includes graduate students, remote programs, commuters, faculty — many won't participate. | → TAM is actually 5-10K → growth caps early → $11K/mo projections are unreachable → plan assumes more oxygen than exists. | **MEDIUM** | No — TAM is structural. But can expand to other schools. | Current signup rate vs NYU population. What % of NYU is actually engaged? |
| 10 | **AI tutoring can't do hands-on skills — Relay fills the gap** | AI CAN teach hands-on skills (gym form via video analysis, guitar via audio feedback, public speaking via speech recognition). The differentiation window is closing. | → Competitive moat erodes → students choose free AI over peer teaching → Relay's value prop ("live > video") becomes "human > AI" but AI quality improves → premium for human diminishes. | **MEDIUM** | No — this is a market trend, not controllable. Relay must prove human teaching is dramatically better than AI. | User surveys: why choose Relay over AI? Is "human interaction" valued enough to pay or trade credits? |
| 11 | **Post-COVID students crave in-person interaction** | Students have normalized hybrid/digital. In-person interaction is actually higher-friction (commute, scheduling, social anxiety). | → Students prefer async/remote → relay sessions require synchronous commitment → scheduling friction → lower completion rates → credits lock up → engagement drops. | **MEDIUM** | No — behavioral trend, not controllable. Can offer remote sessions as alternative. | Session format data: in-person vs remote completion rates. |
| 12 | **$14.99 is an impulse buy (less than UberEats)** | Students don't think about $14.99/month subscriptions the same as one-off UberEats. Monthly recurring charges face more scrutiny than a single meal. | → Subscription hesitation → freemium users never convert → $6,750/mo revenue projection fails → unit economics don't work. The UberEats comparison is a logical fallacy. | **HIGH** | Yes — test actual willingness to pay at $14.99/mo before building full infrastructure. | Stripe donation test results (Week 1 plan). How many donate? |
| 13 | **15% Starter + 5% Pro conversion on 3,000 users = $11K/mo** | Conversion rates are aspirational, not validated. If actual conversion is 3% Starter + 1% Pro (common for freemium), revenue at 3,000 users = $1,350/mo — barely covering costs. | → Overinvestment based on false projections → founder believes "it's working" until revenue data disproves it → slow bleed → missed pivot timing. The projection is the most dangerous single number in the document. | **CRITICAL** | Yes — lower projections, set conservative thresholds. But the damage is psychological: founder optimism baked into financial planning. | Actual conversion data after launch. Compare to 15%/5% claim. |
| 14 | **Free tier hooks them — switching cost is real** | Free users invest little effort (2 credits used up fast) and leave. Without network effects locking them in, there's no switching cost — just abandonment. | → Freemium acts as a leaky bucket → users churn after free credits → "hook" never sets → paid conversion near zero → unlimited free usage becomes cost center. | **HIGH** | Yes — redesign onboarding to force value demonstration before free credits expire. But the claim as stated is misleading. | Free user → paid conversion rate. What % of free users ever return after using 2 credits? |
| 15 | **One syllabus mention = 50-200 students. FREE.** | Professors say "here's a tool" and 0-5 students actually sign up. Syllabus mentions are low-engagement (students ignore optional tools). Claim assumes 100% capture rate. | → Distribution playbook overestimates organic reach → low-cost channels under-deliver → paid acquisition needed → costs rise → unit economics break → business doesn't scale. | **HIGH** | Yes — can A/B test professor referrals vs other channels. But the "FREE" part masks that it's also near-zero impact if unvalidated. | Track referral links from professor mentions. Actual signup-per-syllabus measurement. |
| 16 | **Costs ~$300/mo total overhead** | Hidden costs exist: Stripe fees at scale ($200-500 at 3K users), but also payment processing on credits (implicit liability), moderation costs, customer support time (founder labor). | → Real cost structure is $500-1,000/mo → profit margins thinner → break-even point higher → timeline to sustainability extended → founder subsidy expectation is wrong. | **MEDIUM** | Yes — audit all costs including founder time valuation. But the $300/mo gives false comfort about sustainability. | Actual bank statements vs projections. Include founder labor opportunity cost. |
| 17 | **Rating system, proficiency dots, no-show protection, .edu verification are "already built"** | These features are partially built or broken (see P0: "Rating & review system — you have partial code"). The claim of "already built" contradicts the P0 checklist. | → Quality control collapses at launch → bad teachers proliferate → students have bad sessions → negative reviews → platform dies. The mitigation stack is aspirational code, not deployed. | **HIGH** | Yes — finish and test before launch. But the document explicitly contradicts itself on this point. | P0 items completion status. Are ratings functional in production? |
| 18 | **$5 was too cheap — $14.99 is optimal** | $5 tests showed nothing about $14.99 viability. "Too cheap" might mean students valued it at $0 (free), not $15. The $5 → $15 jump is unsupported by evidence. | → Price anchoring fails → $14.99 feels expensive relative to perceived value → zero conversions → founder assumes "price isn't the problem, confidence is" (final quote) — dangerously self-serving. | **MEDIUM** | Yes — run A/B pricing test, but acknowledge $5 data doesn't prove $15 works. The quote on the last line is a cultish mantra that discourages honest pricing analysis. | Price elasticity test results. What's the actual demand curve? |
| 19 | **Safety net: founder has multiple income streams, technical skills, audience** | The founder is over-leveraged. "Multiple income streams" may mean nothing sustainable. The audience doesn't imply ability to earn. This claim enables riskier bets than prudent. | → Founder makes aggressive decisions assuming a safety net that might not exist → catastrophe is higher consequence than planned → "don't bet the farm" is contradicted by "you can't lose money". | **MEDIUM** | Yes — honestly assess personal financial runway. But the claim as written justifies over-optimism. | Founder's actual financial reserves vs minimum viable runway. |
| 20 | **"Your price was never the problem. Your confidence was. Triple it."** | This closing mantra inverts the entire analysis. It directly contradicts the claim that $14.99 is validated by $5 testing. If confidence (not evidence) drives pricing, the entire monetization section is self-deception. | → Founder sets pricing by bravado, not data → misses actual willingness-to-pay → either leaves money on table or prices out market → motivational quote replaces empirical rigor. | **MEDIUM** | Yes — treat as closing flourish, not strategy. But it reveals a pattern: motivational framing overriding analytical honesty. | Compare pricing decisions to actual user research. Is pricing data-driven or confidence-driven? |

---

## CORRUPTION CHAIN — HOW FALSE CLAIMS INTERACT

If the top claims are false, they don't fail independently — they cascade:

```
300+ interviews FALSE
    → Demand validation is fiction
    → "70% would teach" / "85% want to learn" / "75% match rate" are all ungrounded
        → Product-market fit is false
            → Network effects never materialize
                → Conversion projections (15%/5%) are fantasy
                    → Revenue projections are fiction
                        → "Break-even" status is wrong
                            → Emergency playbook rests on false safety
                                → Entire document is a house of cards
```

---

## THREE ALTERNATIVES — EACH INVERTING ONE CLAIM

### Alternative A: Invert Claim #13 — "Conversion is 2% Starter, 0.5% Pro"
*Instead of 15%/5%, assume realistic freemium conversion.*

| 3,000 Users | Original Projection | Alternative A |
|---|---|---|
| Starter ($14.99) | 450 users → $6,750 | 60 users → $900 |
| Pro ($29.99) | 150 users → $4,500 | 15 users → $450 |
| **Monthly Revenue** | **$11,250** | **$1,350** |
| Costs | ~$300 | ~$300 (fixed) |
| **Net** | **~$11K/mo** | **~$1K/mo** |

**Outcome:** Relay is a side project, not a business. Founder must make peace with $1K/mo or pivot. The "launch and evaluate in September" timeline still works but the bar for success is far lower.

### Alternative B: Invert Claim #8 — "Most users only learn, never teach"
*Instead of dual-role users, assume 90% learners / 10% teachers.*

A marketplace with 10:1 demand/supply ratio means teachers are overwhelmed (10 sessions each), quality drops, wait times are long. The credit economy (teach=+1, learn=-1) becomes deflationary — learners earn no credits, can't learn. Fewer sessions happen. The "network effects are built in" claim was a structural misunderstanding. Active curation/subsidization of teachers is required — fundamentally different operational model.

### Alternative C: Invert Claim #3 — "MVP is NOT live; it's a landing page with a mock UI"
*The "live and operational" MVP is actually a prototype or design mock.*

The P0 checklist (rating system, Stripe, onboarding, mobile responsive) confirms this is the real state. If the document were honest: "MVP is pre-launch, key features missing, no payments, no quality system." The August launch becomes a true launch, not a feature-complete expansion. Less overconfidence risk, but harder fundraising narrative. All "break-even" and "current users" claims must be restated as "zero users, zero revenue, building."

---

## SLOWEST, MOST INVISIBLE FAILURE

**Winner: Claim #13 — Conversion rate projection (15% Starter, 5% Pro).**

**Why:** This is the most dangerous false claim because:

1. **It's self-confirming:** The founder sets up pricing, launches, and gets 3% conversion. But 3% of 3,000 is still 90 users = $1,350/mo — enough to feel "alive" but not enough to sustain. The founder rationalizes: "We just need 5X more users!" So they pour energy into growth (not pricing or product), burning months chasing a user number that mathematically can never yield the projected revenue at actual conversion rates.

2. **No immediate signal:** Low conversion doesn't crash the system overnight. Sessions still happen. Credits still trade. But the business bleeds slowly — founder time, opportunity cost, emotional energy. The failure signal (revenue < $5K/mo at significant user base) takes 6-9 months to appear clearly.

3. **The document's own contingency plans miss it:** The emergency playbook says "If 0% pay in month 1, pivot." But 3% isn't 0%. It's just enough to keep hope alive. The playbook doesn't have a "what if it's 3%?" scenario — that's the deadliest zone.

4. **The closing quote actively discourages fixing it:** "Your price was never the problem. Your confidence was. Triple it." — This frames pricing skepticism as a character flaw, not an analytical question. If conversion is low, the founder's instinct (reinforced by the document) is to double down on belief, not to question the assumption.

**Failure timeline under this false claim:** Month 1-3: 2-3% conversion, ~$1K/mo → "We need more users!" → Month 4-6: growth push to 5,000 users → conversion drops to 2% (early adopters were most motivated) → $1,500/mo → Month 7-9: founder realizes math doesn't work → 9 months of full-time effort yields side-project revenue → burnout or pivot.

---

## CONSTRAINT NOTE

This analysis treats the document as a **truth-claiming artifact** for the purpose of adversarial prism-scan. The document itself contains a disclaimer (line 4) stating it is a "historical planning document — not current product or release evidence" and that it contains "projections, unverified claims, monetization ideas." However, the document simultaneously asserts concrete states (break-even, 300+ interviews, MVP live) as factual. The prism-scan methodology assumes these claims are made earnestly and tests their failure modes when inverted. The disclaimer does not shield the claims from analysis — it merely notes their unverified status, which makes the prism-scan findings *more* relevant, not less.

---

## SUMMARY

| Metric | Value |
|--------|-------|
| Claims analyzed | 20 |
| Critical severity | 3 (#1: 300 interviews, #3: MVP live, #13: conversion %) |
| High severity | 10 |
| Medium severity | 7 |
| Slowest invisible failure | Claim #13 — conversion rate projection (self-confirming, no immediate blow-up, document encourages doubling down) |
| Most actionable fix | Conduct actual pricing/valuation experiments before committing to $14.99 (see Week 1 plan: Stripe donate test) |
| Fatal if all false | Yes — the document would describe a business that doesn't exist, with projections that can't be met, using a playbook that addresses wrong risks |

# Intentionally disabled controlled-trial features

Last updated: 2026-07-13

These exclusions are part of the trial contract, not temporary UI hiding. The listed routes return `404`, their controls and claims are not rendered, and route regression tests cover the containment boundary.

| Feature | Trial behavior | Re-enable only after |
|---|---|---|
| Referral rewards and share links | No reward is granted at signup; referral UI and promotional copy are removed. | Verified eligibility event, per-invite uniqueness, abuse limits, reconciliation, terms, and operator monitoring are approved and tested. |
| Proof-video rewards | `/proof-video` returns `404`; proof links, badges, and marketing permission claims are absent. | Exact HTTPS-host validation, content moderation, one reward source per approved proof, versioned content permission, withdrawal, and abuse tests pass. |
| Student ambassadors | `/become-ambassador` returns `404`; no badge or reward is shown. | Least-privilege role assignment is operator-controlled, audited, reasoned, revocable, and has no implicit administrator powers. |
| User-triggered timeout maintenance | `/admin/timeout-sessions` returns `404`. | An authenticated scheduled command is idempotent, source-unique, logged, alerted, and tested on PostgreSQL against the approved settlement policy. |
| Public request board and claiming | `/requests`, `/add-request`, and `/claim-request/*` return `404`. | Privacy, category screening, atomic claiming, learner consent, credit holds, notifications, moderation, and PostgreSQL concurrency tests pass. |
| Recurring sessions | No recurrence controls are rendered and the trial accepts only one session request at a time. | Series pricing, per-occurrence holds, reminders, cancellation, no-show/dispute policy, and concurrency tests pass. |
| Top-ups and memberships | `/top-up`, `/membership`, and `/membership/join` return `404`; pricing plans are not rendered. | A separately approved payments project covers provider integration, disclosures, refunds, taxes, chargebacks, security review, and production evidence. |
| Variable credit pricing | Every trial listing and session is charged exactly one integer credit. | Post-trial research explicitly approves a new model and all copy, ledger, refund, payout, consent, and migration behavior is updated together. |
| Automatic demo seeding | `/seed-demo` returns `404`; automatic seeding is off by default and cannot run in production. | A privacy-safe staging-only seed command is isolated from production and has deterministic cleanup/test procedures. |
| Unsupported reputation badges | Ambassador, inferred reliability, no-show, report, and proof badges are not rendered. | Each retained indicator derives from immutable, auditable events with an appeal/correction path and tested display rules. |
| Homepage campaign and paid-plan sections | Research, poster/map campaign, street mockup, and pricing sections are not rendered. | Claims, asset provenance, page weight, actual campaign approval, and supported product behavior are documented and verified. |

Disabling a route does not prove broader trial readiness. The launch matrix remains authoritative, and the current verdict remains **NO-GO**.

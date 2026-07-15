# Controlled-trial rehearsal checklist

Last updated: 2026-07-13

Run only in an approved production-like staging environment with synthetic accounts. Record timestamp, environment/revision, operator, expected result, actual result, redacted evidence link, and PASS/FAIL for every row. Any blank or failed row keeps G12 at **NOT TESTED**.

Preview `flask prepare-rehearsal-data` before an explicitly authorized apply. The reserved fixture supports repeatable state/ledger drills but cannot prove signup, institutional verification, or real inbox delivery; use separately approved inbox-backed participants for those rows.

| Journey | Required proof |
|---|---|
| Two-user happy path | Invited signup, consent, real inbox verification, starter grant once, creative listing, one-credit request, timezone display, exact location/link acceptance, both completion confirmations, one payout, two reviews, reconciliation |
| Repeat session | Same pair and skill complete a second independent session; exactly one hold and payout per session |
| Cancellation | Requested and confirmed cancellations each refund once; repeat action changes nothing |
| Expired request | Dry run reports candidate; authenticated apply cancels/refunds once; repeat run is empty |
| Session reminder | Dry run reports only upcoming confirmed sessions; unauthenticated apply fails; authenticated repeat runs create one delivery per active participant and surface provider failure |
| Failed email | Provider rejection is visible to user/operator, secret-free failed record exists, token/body absent from logs, safe retry succeeds |
| Unverified attacker | Cannot onboard, see identities, list, book, accept, complete, moderate, or gain credits |
| Listing safety | Creative listing succeeds at one credit; other-category and prohibited-topic submissions return an honest error; stored markup is stripped |
| Host/XSS abuse | Attacker-controlled Host does not alter emailed URL; meeting-host substring and stored-script payloads are rejected/escaped; CSP console is clean |
| Block/report | Block stops contact and active interaction; report enters moderator queue with no target access |
| No-show | Grace period enforced; report creates dispute; moderator refund reconciles |
| Completed dispute | Moderator reversal debits teacher and restores learner exactly once; repeat resolution does nothing |
| Suspension | Reason/evidence required; target sessions revoked; suspended account cannot continue |
| Deletion | JSON export downloads; password-confirmed closure replaces direct identifiers, revokes session, disables listings, and preserves only the documented pseudonymized reconcilable audit records |
| Recovery | Backup is restored into isolated target; schema revision, readiness, row counts, login/reset, session flow, and reconciliation pass |
| Rollback | Jointly compatible application/database rollback is exercised and timed; decision/stop criteria are recorded |
| Accessibility | 375/500/768/1440 widths, 200% zoom, keyboard-only order, visible focus, skip link, form names/errors, reduced motion, and targeted screen-reader review pass |
| Performance | Served assets and key pages meet documented budget; no disabled campaign media is requested |

Required final sign-offs: primary moderator, technical operator, privacy owner, rollback approver, and trial decision-maker. Sign-off is external evidence, not a repository test.

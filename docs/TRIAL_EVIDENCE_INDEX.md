# Relay trial evidence index

Last updated: 2026-08-02

This is the per-requirement locator for `TRIAL_READINESS_MATRIX.md`. Automated evidence uses the warning-strict command below unless a different command is named:

```text
.venv/bin/python -W error::DeprecationWarning -m unittest discover -v
```

An implementation or test locator is not itself a PASS. The status and missing external proof remain authoritative in the readiness matrix.

## Audit issues

| ID | Implementation / file evidence | Test / command evidence |
|---|---|---|
| C01 | `app/trial_config.py`, `app/database.py`, `app/main.py`, `render.yaml`, `render.staging.yaml`, `requirements.txt`, `tests/production_infrastructure.py` | Provider-URL regression selects Psycopg 3; exact-candidate CI booted production-shaped configuration against disposable PostgreSQL 16 and Redis 7.4, enforced exact head, and returned readiness `200`; repeat in staging |
| C02 | `app/ledger.py:LedgerService.hold_for_session`, `app/main.py:request_session` | `test_booking_holds_exactly_one_credit_and_reconciles` |
| C03 | `app/ledger.py:refund_session` requires a source hold; `cancel_session`, `settle_expired_requests` | Cancellation/expiry repeat tests and missing-hold fail-closed regression |
| C04 | `app/ledger.py:payout_session` requires an unrefunded source hold; `complete_session` | Repeat-session payout/reconciliation and missing-hold fail-closed regressions |
| C05 | Row locks, unique ledger sources, guarded `tests/postgres_concurrency.py` | Three PostgreSQL 16.14 competing-action tests pass against only disposable `relay_migration_ci` |
| C06 | Production enforces 10–20 unique domain-valid invites; `signup`, `verify_email`, `require_verified_user`, privacy-safe `browse` | Production config, starter-credit, and both unverified authorization tests |
| C07 | Referral grant/UI omitted; program listed in `DISABLED_FEATURES.md` | `test_unsafe_trial_routes_are_intentionally_unavailable`; rendered-home containment test |
| C08 | `proof_video` returns `404`; proof UI unavailable | `test_unsafe_trial_routes_are_intentionally_unavailable` |
| C09 | Bonus/proof/ambassador routes unavailable; verification is sole starter source | Unsafe-route test; repeat verification/ledger source-uniqueness tests |
| C10 | `become_ambassador` returns `404`; moderator roles are server-controlled | Unsafe-route test; moderator suspension/audit test |
| C11 | Request board/add/claim routes return `404` | `test_unsafe_trial_routes_are_intentionally_unavailable` |
| C12 | `validate_meeting_details`, `accept_session`; exact locations/hosts only | Acceptance/cancellation test; `test_meeting_host_substring_attack_is_rejected` |
| C13 | `app/email_service.py`, `EmailDelivery`, `send_email` | Failed verification and failed session delivery tests; real provider/inbox evidence absent |
| C14 | `absolute_url`, hashed secrets, canonical `RELAY_PUBLIC_URL`, required production proxy-hop counts | Attacker-Host, canonical-link, and rightmost-trusted-proxy regressions |
| C15 | `app/database.py`, `migrations/versions/20260713_00_*`, `migrations/versions/20260713_01_*`, `migrations/versions/20260731_01_*`, `tests/legacy_schema.py`, `MIGRATION_PLAN.md` | Five SQLite safety cases plus guarded PostgreSQL cases prove fresh/no-drift, representative legacy upgrade+rollback, and fail-closed audit-event rollback |
| H01 | Account-aware failure counter and 15-minute lock in `login` | `test_failed_logins_increment_and_lock_known_account` |
| H02 | Hashed login-identity throttling, account-scoped protected-mutation limits, shared-storage readiness and explicit proxy-hop validation in `app/main.py`, pinned Redis client | Campus-IP isolation plus `tests.redis_proxy`: two app instances share disposable Redis 7.4.9 limits, spoofed leftmost input is ignored, and an independent address retains allowance; production readiness passes with the same store |
| H03 | Cryptographic hashed verification secret, expiry, resend cooldown, and route-specific verification/resend limits | Expired-verification and starter-credit repeat tests; production shared-limit storage remains H02/G07 |
| H04 | 12-hour session, `session_version`, non-active login rejection, reset/suspend/delete session and reset-link revocation | Password-reset, suspension, and account-closure tests |
| H05 | `add_security_headers`, self-hosted JS/assets, `base.html` | CSP regression plus four-width browser runs with no external requests, console/page errors, or request failures |
| H06 | `SessionStateMachine`, confirmed-only `complete_session` | `test_requested_session_cannot_be_completed`; illegal-transition test |
| H07 | Round-trip DST-safe Eastern-to-UTC validation, bounded dates, participant-only `session_details.html` | Acceptance/schedule/cancellation route test; DST gap/fold parser regression |
| H08 | Locked resolution rejects closed cases and invalid dispute action types; dismiss restores prior session state; refund/payout/reversal require their source ledger events; completed reversals use the original settlement as an immutable cross-case source and close the session | Block, suspension, no-show/refund, dispute-dismissal, malformed-settlement, completed-dispute, same-case and cross-case repeat-resolution tests |
| H09 | `app/policies.py`, fail-closed category config, validated `add_skill` | `test_listing_scope_rejects_other_categories_and_prohibited_topics`; category configuration tests |
| H10 | `ConsentAcceptance`, `record_current_consents`, `consent.html` | `test_current_versioned_consents_are_required_and_recorded` |
| H11 | Comprehensive participant-associated `export_account`, direct-identifier replacement in `delete_account`, truthful pseudonymization/retention language, and a `202` warning when cancellation-email delivery fails after closure | Export contents and account-closure audit/ledger/delivery-failure tests |
| H12 | Verified-only `view_profile`; public `browse.html` suppresses identity, links and free-form descriptions | Public preview contact-detail regression and unverified authorization tests |
| H13 | User/moderator/admin role checks; protected moderator queue; audit actions | Report-resolution suspension/audit regression |
| H14 | Integer/check/unique constraints in `app/models.py`; locked review creation handles uniqueness races | Database-negative, ledger source-uniqueness, and repeat-review route tests |
| H15 | Exact runtime/dev pins, fail-closed `scripts/check_direct_advisories.py`, pinned pip-audit, `DEPENDENCY_REVIEW.md` | `pip check`, 14-pin PyPI check, resolved-graph pip-audit, and 88 warning-strict tests pass |
| H16 | `render.yaml` provisions no database; `BACKUP_RESTORE_RUNBOOK.md` | YAML parse passes; no real backup/restore transcript exists |
| H17 | Production-path route/CLI suite in `tests/test_trial_containment.py` | Warning-strict discovery command; exact final count recorded in matrix |
| M01 | `TrialConfig.credit_cost == 1`; booking ignores legacy listing price | Trial configuration and booking/ledger tests |
| M02 | Monetization flag false; pricing/top-up/membership unavailable | Unsafe-route and rendered-home containment tests |
| M03 | Single starter/price source in `app/trial_config.py` and template globals | Trial configuration and starter-verification tests |
| M04 | No recurrence input or route; one request creates one session | `rg -n -i 'recurr' app/templates`; request/booking test |
| M05 | Source-recipient uniqueness plus row-locked delivery retries cover request/accept/reminder/cancel/expiry/complete/no-show/dispute | Failed-delivery tests; both reminder CLI tests; cancellation/expiry delivery assertions |
| M06 | `session_details.html` and session action routes | Acceptance/cancellation route test plus block/no-show/dispute drills |
| M07 | Proof route/UI/reward unavailable | Unsafe-route and rendered-home containment tests |
| M08 | One configurable `creative` vertical, production rejects missing/`all` | Both trial-category configuration tests; listing-scope route test |
| M09 | Quiet scroll reveal with fail-closed explicit static and OS reduced-motion modes in `elevate.js`/`style.css` | Motion regression plus fresh isolated Chrome reduced/static runs: all reveals opaque and zero active animation |
| M10 | Skip link, active-form labels, mobile menu state, focus target/treatment, dark-mode AA palette contrast, and reduced/static-motion CSS/JS | `tests/test_public_surface.py`, containment regressions, and fresh isolated Chrome at 375/500/768/1440 plus 200% reflow, keyboard/focus, labeling, contrast, reveal, and screenshot checks |
| M11 | External Google Font, disabled campaign/media, and dormant hero poster are not requested; served logo has intrinsic dimensions | Asset regression plus fresh browser same-origin request inventory with no external/request/console failures; no official performance/Core Web Vitals claim |
| M12 | Reviewed redesign/edge-case/operations changes are merged; blueprint auto-deploy is off | Application commit `1132a149` is on `main` and GitHub Actions run `30608587671` passed |
| M13 | Liveness/readiness with exact Alembic-head and shared-limiter enforcement, request IDs, structured request/error events, no-store responses, aggregate health report | Connectivity/stale-revision/missing-Redis and Redis-exception fail-closed regressions plus fresh 2026-07-23 `tests.production_infrastructure` exact-head readiness `200` with disposable PostgreSQL/Redis |
| M14 | Public timeout route `404`; authenticated dry-run-first settlement/reminder CLIs | Expired/reminder tests plus local apply-mode refusal without scheduler authentication and clean authenticated no-candidate runs |
| M15 | `.github/workflows/ci.yml` with least privilege, source/readiness checks, compile/tests, direct/resolved scans, disposable PostgreSQL migration/concurrency, Redis shared-limit/proxy, and production-readiness jobs | Exact-candidate workflow run `30608587671` passed on `1132a149`; staging remains absent |
| M16 | `trial-health-report`, `TRIAL_METRICS.md` | Aggregate read-only PII-free metrics regression |
| L01 | Unsafe one-off repair utilities are absent; `MIGRATION_PLAN.md` and guarded commands replace the approach | Synchronized base and candidate name-status inspection |
| L02 | Unsupported badges/counters removed from rendered profile/dashboard | Rendered containment/privacy tests; `rg -n -i 'ambassador|proof badge' app/templates` review |

## Launch gates

| Gate | Implementation / file evidence | Test / command and external boundary |
|---|---|---|
| G01 | Staging and production both reject weak secrets, non-PostgreSQL/non-Redis settings, bad cohort shape and non-SMTP email; psycopg/migrations exist; readiness checks DB revision and limiter storage | Local production-shaped exact-head readiness passes against disposable PostgreSQL/Redis; real SMTP/provider and staging remain NOT TESTED |
| G02 | Integer ledger, unique sources, row-locking code, guarded PostgreSQL concurrency module | Local repeat-session tests and all three PostgreSQL 16.14 competing-action tests reconcile against disposable `relay_migration_ci` |
| G03 | Verification gates and delayed source-unique starter award | Unverified authorization matrix and repeat-verification tests |
| G04 | Schedule/location/link/accept/cancel implementation | Local route tests pass; two-participant browser rehearsal absent |
| G05 | Full moderation and ledger-resolution implementation | Automated block/report/suspend/no-show/dispute, dismissal, malformed-settlement, and repeat-resolution drills pass; named human drill absent |
| G06 | `BACKUP_RESTORE_RUNBOOK.md` | Local synthetic custom-format dump/isolated restore passed at exact head with matching counts and reconciliation; no real encrypted/provider backup or operator-signed restore transcript |
| G07 | CSRF/CSP/host/auth/XSS tests, explicit trusted-proxy boundary, account-scoped rate policies, shared Redis integration, rendered markup/CSS check, secret-pattern check, direct-pin check, pip-audit, and `DEPENDENCY_REVIEW.md` | Local controls, advisory scans, two-instance Redis sharing, spoof resistance, and participant isolation pass; repeat with deployed proxy/NAT in G12 |
| G08 | Disabled-feature contract and rendered truthfulness/control containment tests | Fresh 2026-07-23 isolated Chrome run: ten public routes, expected controls/copy, strict same-origin CSP, no external font/media request, and no console/page/request errors |
| G09 | Accessibility code, contrast regression, responsive/reveal checks, and temporary `/private/tmp/relay-browser-qa-20260723/` evidence | Fresh isolated Chrome passes 375/500/768/1440, 200% reflow, keyboard/focus/skip-link, menu, reduced/static motion, labels, IDs/H1s, images, reveal settling, and minimum checked 5.13:1 contrast; official performance trace and human AT review not claimed |
| G10 | `TRIAL_OPERATIONS_RUNBOOK.md` roles/targets/procedures | Roles and monitored inbox remain explicitly unassigned |
| G11 | Versioned consent mechanism and draft-labeled legal pages | Consent and public policy truthfulness regressions pass; counsel/privacy approval absent |
| G12 | Dry-run-first `prepare-rehearsal-data`, `TRIAL_REHEARSAL_CHECKLIST.md`, and component route/CLI drills | Synthetic fixture regression passes locally; checklist has not been executed in production-like staging and recovery remains blocked |

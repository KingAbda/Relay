# Privacy-conscious controlled-trial metrics

Last updated: 2026-07-13

`flask trial-health-report` emits aggregate, read-only operational counts: active/verified/onboarded participants, separately identified synthetic-rehearsal participant count, active listings, each session state, open safety reports/disputes, failed email deliveries, and ledger discrepancies. It emits no names, addresses, notes, meeting details, report narratives, tokens, or message bodies.

Primary trial evidence should answer:

- Can vetted participants verify, list, request, meet, and settle safely?
- Do repeat sessions occur without ledger drift?
- What share of requests reach confirmation and completion?
- How often do cancellation, no-show, block, report, or dispute paths occur?
- Can the named operator respond within the published target?
- Do participant interviews indicate real utility and acceptable safety/privacy?

The repository provides counts, not a live analytics vendor. Before reporting rates, document the numerator, denominator, observation window, excluded synthetic accounts, and small-cohort privacy risk. Do not publish slices that identify a participant. A zero incident count is not proof that the system is safe.

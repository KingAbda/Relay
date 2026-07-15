# Relay controlled-trial contract

Last updated: 2026-07-13

This contract is the default for repository behavior until a newer explicit founder decision replaces it.

- Cohort: 10–20 invited, manually vetted NYU participants.
- Access: invite-only signup, institutional email verification, and verified-participant authorization for full marketplace/profile access.
- Category: exactly one configured trial category.
- Session price: exactly one integer credit per 30-minute session.
- Starter credits: configured once and granted only after verification and trial eligibility are both satisfied.
- Payments: disabled; no paid-plan or top-up claims.
- Rewards: referrals, proof-video credits, and ambassador rewards disabled.
- Privilege: no self-service elevated roles.
- Scope exclusions: recurring bookings and public request-board claiming disabled.
- Privacy: anonymous visitors may receive a limited, non-identifying preview; full profiles require a verified trial participant.
- Logistics: a session uses an agreed public location or a user-supplied, validated HTTPS link. Relay never invents meeting links.

## Default category decision

The safest existing default is `creative`.

The repository taxonomy is `creative`, `academic`, `technical`, `social`, `lifestyle`, `finance`, `languages`, `trades`, and `other`. `creative` has multiple existing examples (guitar, music production, and visual design), is broad enough to recruit a small supply cohort, and avoids the elevated baseline risks present in fitness/wellness, finance, trades, medical-adjacent, or unrestricted `other` instruction. Topic-level prohibitions still apply inside the category.

Development and test environments may default to `creative` for deterministic local work. Production must fail closed unless `RELAY_TRIAL_CATEGORY` is explicitly set to one allowed category; `all` is never a valid controlled-trial value.

This is an engineering risk decision, not proof of sufficient teacher supply. The founder/trial operator must confirm that enough vetted creative teachers exist before recruitment.

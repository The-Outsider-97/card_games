# Card Games security and release-verification register

Updated 7 November 2026. Findings are divided into **verified checks** and **open blockers**. Passing these checks is not a substitute for independent penetration testing or deployment review.

## Verified in this development environment

| Boundary | Check / evidence |
| --- | --- |
| SLAI local host | `LocalServer` loopback only, unique bootstrap token and mutation marker; shared HTTP integration test rejects mutation without the marker. |
| Local data | Shared SLAI `Database` transactional SQLite and versioned migrations; matches are loaded into validated engine models before updates. |
| AI confidentiality | Agent observation is seat-filtered; service refuses to reveal an AI hand when queried by its player ID. |
| Account access | SLAI AuthService is the only password authority. Local account sessions store access and refresh **hashes**, not tokens. Refresh token rotates and prior access mapping is removed; logout invalidates session cookies. Adapter tests verify rotation, logout and profile restrictions. |
| Remote seat auth | Online server derives actor identity **only** from a hashed seat token. One-time invitation, host-only invite and seat revocation, stale-revision rejection and idempotent action IDs are tested. |
| Hidden information | Unspent Fourfold cards and locked orders, and Four-Color hands, are only visible to the owner of an online seat. Tests cover unauthorized cross-seat reads. |
| Network isolation | Remote rooms run in a separate process, not the protected SLAI `LocalServer`; a non-loopback listener requires a TLS certificate and key. HTTP origin allowlist, body limit, no-store/nosniff headers and room-creation rate limiter are enforced. |
| Rules integrity | Fourfold official PDF worked examples, invalid order rollback, special abilities, Foundations, final score ties, and online reload tested. Four-Color regression tests remain green. |
| Static checks | `node --check` client code, `python -m compileall`, `git diff --check`. |

## Open release blockers

1. **No external security audit** of the public room service, including active-network interception, reverse proxy, hosting process isolation, dependency audit, persistent rate limiting, abuse prevention, log policy and restoration drills. Current per-process room creation rate limiter is not sufficient for internet abuse resilience.
2. **Not a global account system.** Remote seat capabilities are independent from SLAI user accounts. There is no integrated persistent remote identity, identity recovery, hosted matchmaking, room moderation, user block list or paid service entitlement.
3. **Account dependencies incomplete in this test container.** Full `AuthService` import fails because the SLAI v2.4 `src.functions` package imports optional `phonenumbers`. Account behavior was tested against its documented public API contract using a substitute, not a successful real-login end-to-end run. Verify with the complete target Windows SLAI installation and configuration.
4. **Browser visual QA unavailable in the current workspace.** Headless Chromium fails at process startup (`socket() failed: Operation not permitted`). The separate desktop browser runs but cannot reach the isolated local test service (`ERR_CONNECTION_REFUSED`). Thus actual card layout, hit targets, responsive behavior and keyboard workflows are not certified.
5. **Incomplete product polish:** Accessible controls, reduced-motion behavior, color independence, animation pacing and small-screen layout need manual cross-browser and assistive-technology testing. The current client is JavaScript without strict TypeScript static analysis.
6. **Human play and AI quality:** SLAI BaseAgent specialization was constructed and called in real verification runs; scripted win-rate samples do not establish a strong difficulty ladder or strategic balance. More seeds, independent AI policies, baseline comparisons and human experiments are required.
7. **Asset approvals:** Missing Fourfold King of Hearts illustration, duplicate Spades King filename; symbols variant lacks Reverse/neutral faces and an approved suit-to-color rules mapping.
8. **Production operations:** Set up real TLS certificate lifecycle, encrypted backups, backup restoration tests, monitoring, uptime and error-budget targets, support/recovery workflows and an explicit privacy/retention policy before public deployment.

## Recommended manual release gate

On Windows with the complete SLAI v2.4 environment: start the local launcher, create/sign in/refresh/edit profile/log out, finish a Fourfold 12-round human+AI match, finish a Four-Color match, restart and resume saved games, open two real network-separated browsers and complete a two-human online room, verify seat secrecy and revoked invitations, then repeat at 1366×768 and 1920×1080 with keyboard-only navigation. Record pass/fail screenshots and logs without credentials or private cards. Do not mark production-ready until the open security and quality blockers are resolved.

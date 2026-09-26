# Threat model

SSO Lab is a **public** website that intentionally demonstrates insecure protocol handling. The design goal is
that the deliberate weaknesses can only ever hurt the visitor's own throwaway demo session.

## What we protect

| Asset | Why it matters |
|---|---|
| The GCP project and its bill | Public endpoints can be abused for compute or storage |
| Visitors' traces | Contain demo tokens and whatever a visitor typed in the lab |
| The teaching IdP's signing keys | If the IdP is weak, lessons about "trust the IdP" become false |
| Visitors' real credentials | People sometimes type real passwords into any login form |
| The CI/CD pipeline | A deploy identity is a path to take over the site |

## Threats and mitigations

| Threat | Mitigation | Status |
|---|---|---|
| Cost / resource abuse | Cloud Run max 3 instances per service, per-IP rate limits (stricter for session creation), per-session event cap (500), 24 h TTL on all data, $50 budget alert | M0 |
| Reading another visitor's trace | Trace read access needs an HttpOnly cookie secret; only its SHA-256 is stored. The public session id (used in URLs) only allows *appending* | M0 |
| Open redirect via the IdP | Return URLs must exactly match a registered URL (no prefix/pattern matching) | M0 |
| Clickjacking of login or consent screens | `frame-ancestors 'none'` on every response | M0 |
| XSS on protocol pages | Strict CSP (`script-src 'self'` or a per-response nonce), all server-rendered values escaped, React for the UI | M0 |
| Leaking codes/tokens in logs, Referer or caches | `Referrer-Policy: no-referrer`, `Cache-Control: no-store` on protocol responses, proxy headers (including client IP) dropped from traces | M0 |
| Rate-limit bypass with spoofed `X-Forwarded-For` | Only the right-most entry (appended by Google's front end) is trusted | M0 |
| Stolen deploy credentials | No service account keys: GitHub OIDC → Workload Identity Federation, limited to this repo's numeric id and `main`. Deployer has `run.developer` (can't change IAM). Actions pinned to commit SHAs | M0 |
| Visitors entering real passwords | Site-wide banner; demo accounts listed on the login page; `password` form fields are redacted before a trace is stored | M0 / M2 |
| Codes, tokens and sessions in the teaching IdP | PKCE required for every client; exact `redirect_uri` matching (errors never redirect to an unverified URI); codes single-use (atomic take) and valid 60 s; refresh tokens rotate; `iss` in the authorization response (RFC 9207); IdP login form bound to a transaction cookie (no login CSRF against the IdP) | M2 |
| Demo tokens visible in the playground | Deliberate, for learning, and labelled as such. They are issued for demo users only, expire within minutes (ID/access) or hours (refresh), and the playground says real apps keep tokens server-side | M2 |
| Attack Lab leaking beyond the visitor | Vulnerable toggles only weaken App A's validation, only for that visitor's lab session. The IdP is never weakened | M3 |
| SSRF through a "bring your own IdP" feature | Not offered. If ever added: allowlist only | Design |
| Automated abuse (bots creating sessions) | Rate limits now; add Cloudflare Turnstile before session creation if abuse appears | Planned |
| XML attacks on SAML | Parser refuses DTDs and entities, no network (XXE); only RSA-SHA256/SHA-256 signatures accepted; verified against the certificate from the IdP's metadata, never one embedded in the message; the user is read only from the element the signature covers, and a document with more than one assertion is rejected (signature wrapping) | M3 |
| SAML response misuse | IdP posts only to the SP's registered ACS URL; SP checks Issuer, Destination/Recipient, Audience, NotBefore/NotOnOrAfter; `InResponseTo` must match a pending request, which is consumed (no unsolicited or replayed responses); assertion IDs kept in a replay cache until they expire; `RelayState` only redirects to local paths | M3 |

## Known limitations

- The IdP's RSA signing key is stored in Firestore (readable by the runtime service account) rather than in
  KMS, and is not rotated. Fine for a demo whose tokens protect nothing; a real IdP would use an HSM/KMS and
  rotate keys via the JWKS.

- Rate limits are per instance (in memory), so the real ceiling is `limit × instances`. Acceptable for a demo
  with `max_instances = 3`; a load balancer with Cloud Armor would be needed for anything larger.
- Traces are visible to anyone holding the visitor's browser cookie, which is by design.

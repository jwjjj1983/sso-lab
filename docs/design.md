# Design notes

## Goal

Let engineers who have never looked underneath "Sign in with Google" drive real SSO protocols themselves:
see every hop, understand what each party checks, and see what goes wrong when a check is skipped.

## Decisions

| Decision | Choice | Why |
|---|---|---|
| Identity Provider | Custom teaching IdP (Python) | Every check is readable teaching code, every hop can be traced, and Attack Lab toggles are easy. Keycloak or a hosted IdP would be a black box |
| Topology | One image, three Cloud Run services on separate hostnames | Real cross-site cookie and redirect behaviour, and a true two-app SSO demo |
| Domain | Default `run.app` URLs | Free. `run.app` is on the Public Suffix List, so each service is its own site. URLs are config, so a custom domain can be added later |
| Access | Public internet | Hardened accordingly, see [threat-model.md](threat-model.md) |
| v1 scope | OIDC (with Attack Lab and App B), SAML later | Get the most-used protocol right first |
| Trace transport | Server-Sent Events | One-way server → browser is all we need; simpler than WebSockets and works through Cloud Run |
| Trace storage | Firestore (memory store in dev) | Serverless, TTL deletes, and snapshot listeners give live updates across instances without polling |
| Login UX | Popup that reports back via `postMessage` | The playground stays on screen. Iframes are wrong here: IdPs rightly refuse to be framed |

## Recording rule

Each HTTP exchange is recorded exactly once, by the party that sees all of it: front-channel requests by the
receiving actor (request + the redirect it answers with), back-channel requests by the calling actor. Work
inside one party (generating PKCE values, validating an ID token) is a `local` event with its check results.

Front-channel routes only *tag* a request (`tag(request, lab_session, step, response_step=…)`);
`RecordingMiddleware` records it with the final response headers (CSP, `Set-Cookie`…) and holds the response
until the event is stored, so the browser can never reach the next hop before this one is in the trace.
Password form fields are redacted; demo client secrets and tokens are shown on purpose.

## OIDC playground (M2)

- The teaching IdP (`idp/oidc.py`) and the apps' OIDC client (`rp/oidc.py`) are written to be read: each
  check is explicit, in order, with the reason next to it.
- App A runs in **guided** mode for the playground: after the callback it stops, and the playground triggers
  the token exchange, UserInfo and refresh through small lab endpoints (`/api/lab/oidc/*`). App B runs in
  **auto** mode, like a normal app, which is what makes the single sign-on moment visible.
- Short-lived protocol state (IdP sessions, codes, tokens, in-flight logins) lives in the store's expiring
  records, so it works across Cloud Run instances. Codes are consumed atomically (Firestore transaction).
- The IdP's lab-only `lab_session` parameter on `/authorize` is how it knows which visitor's trace to write to;
  it grants append access only.

## Protocol pages

`/protocols/<slug>/<tab>` with tabs Overview · Components · Sequence · Playground · Security · Learn more.

All protocol content lives in typed modules under `frontend/src/content/` (one `ProtocolSpec` per
protocol) rather than MDX. The content is mostly structured (lanes, steps, checks, threats, links), and
typing it means a mistyped lane or threat id fails a test instead of rendering a broken diagram.

The **flow spec** is the single source for the sequence diagram, the step details and the security tab's
"checked at step N" links. Step ids (`oidc.token`, …) are also the `step` values the backend recorder puts on
trace events, so the M2 playground can light up the diagram step a live request belongs to.
`?step=<id>` deep-links to a step.

The sequence diagram is a custom SVG rather than Mermaid, because it needs per-step selection, keyboard
navigation (one tab stop, arrow keys, `aria-current="step"`) and channel styling (front channel solid orange,
back channel dashed teal) so the distinction does not rely on colour alone.

External links are checked weekly by `scripts/check_links.py` (YouTube via oEmbed, since deleted videos still
return 200).

## SAML playground (M3)

- Messages are built by hand with lxml (`idp/saml.py`, `rp/saml.py`) so they can be read; XML Signature uses
  `signxml` (enveloped, exclusive C14N, RSA-SHA256). `signxml` returns the element the signature covers, and
  the SP reads *only* from it: that is the signature-wrapping defense, and the playground shows it as a check.
- The IdP's signing certificate is self-signed, created once and kept in the store; SPs learn it from the
  IdP's metadata, never from the message.
- The IdP login page and session are shared with OIDC: sign in through either protocol and both get SSO.
- The response arrives as a cross-site form POST, which carries no `SameSite=Lax` cookies, so the SP finds
  its AuthnRequest by `InResponseTo` in a server-side cache (single use). The playground explains this.
- "Sign out everywhere" reuses the OIDC logout endpoint to end the IdP session; SAML Single Logout is not
  implemented.

## Future work

- **Attack Lab**: per-lab-session toggles that switch off one of App A's checks (`state`, `nonce`, `aud`,
  signature / `alg`, SAML audience or signature-wrapping) and a button that runs the matching attack. Only
  App A is ever weakened, never the IdP. PKCE: the IdP will require PKCE only for clients registered as needing
  it (App A stays strict), and the code-interception attack runs against a separate, deliberately weak demo
  client (decided 2026-09-26).
- More OAuth flows: client credentials, device code.
- SAML Single Logout and IdP-initiated SSO (with its risks).

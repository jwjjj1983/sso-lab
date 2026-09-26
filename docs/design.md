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
receiving actor (request + the redirect it answers with), back-channel requests by the calling actor.

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

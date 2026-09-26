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

## Playground page (M1–M2)

Tabs: Overview · Components · Sequence · Playground · Security · Learn more.
The playground has three panes: a sequence diagram with the current step highlighted, step controls, and an
HTTP inspector (raw / decoded / explained). A per-protocol *flow spec* (actors, steps, explanations,
references) drives the diagram, the stepper and the docs, so they cannot drift apart.

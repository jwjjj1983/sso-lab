# SSO Lab

An interactive playground for learning Single Sign-On protocols (OIDC on top of OAuth 2.0, SAML 2.0):
real redirects, real signatures, and every front- and back-channel message captured and explained.

> ⚠️ Demo only. Every credential in this repo is a throwaway demo credential. Never enter a real password.

## How it works

Three actors run as three separate sites, so cookies, redirects and cross-site rules behave exactly
as they do in production SSO:

| Actor | Role | Local dev | Cloud Run |
|---|---|---|---|
| **IdP** | Teaching Identity Provider | `idp.localhost:8000` | `sso-lab-idp` |
| **App A** | Relying party, plus the playground UI and lab API | `app-a.localhost:5173` | `sso-lab-app-a` |
| **App B** | Second relying party, to show *single* sign-on across apps | `app-b.localhost:8000` | `sso-lab-app-b` |

Every HTTP exchange between them is written to the visitor's **trace** by a flight recorder and streamed
to the playground over Server-Sent Events:

- **Front channel** (browser → actor): recorded by the actor that receives it, including the redirect it sends back.
- **Back channel** (actor → actor, e.g. the OAuth token request): recorded by the caller. This is the part a browser normally never shows you.

One container image plays every role (`SSO_LAB_ROLE=idp|app-a|app-b`). Locally, `SSO_LAB_ROLE=all` runs all three
in one process and routes by `Host` header. Traces live in memory locally and in Firestore on GCP, where they
are deleted by TTL after 24 hours.

## Quick start

Needs [uv](https://docs.astral.sh/uv/), Node 24 and pnpm.

```bash
make install
make dev          # then open http://app-a.localhost:5173/lab/diagnostics
```

Chrome, Firefox and Safari resolve `*.localhost` to your machine automatically.

```bash
make test         # backend + frontend tests
make lint
make image        # run the production image (all actors) on http://app-a.localhost:8000
```

The Firestore store tests run against the emulator: `docker compose up -d firestore`, then
`FIRESTORE_EMULATOR_HOST=localhost:8080 uv run pytest` in `backend/`.

## Layout

```
backend/            FastAPI (Python 3.12, uv)
  src/sso_lab/
    lab/            lab sessions, trace model, recorder, stores, lab API
    idp/            teaching IdP: OIDC (discovery, JWKS, /authorize, /token, /userinfo, logout) and SAML (metadata, SSO)
    rp/             relying parties (App A / App B): OIDC client and SAML service provider
    demo.py         demo users and client registrations (throwaway, checked in on purpose)
frontend/           React + TypeScript + Vite + Tailwind
  src/content/      protocol content: flow specs, threats, reading lists (drives the pages)
infra/terraform/    Cloud Run, Firestore, Artifact Registry, GitHub OIDC deploy identity
docs/               design notes and threat model
```

## Roadmap

- [x] **M0 Foundation**: three-site topology, trace recorder + live stream, CI/CD, infra
- [x] **M1 Learn**: "What is SSO?" home page, protocol pages (overview, components, sequence diagram, security, reading list) for OIDC and SAML
- [x] **M2 OIDC playground**: teaching IdP, authorization code + PKCE step by step, ID token validation explained check by check, UserInfo, refresh, single sign-on into App B, logout
- [x] **M3 SAML playground**: SP-initiated SSO (Redirect + POST bindings), metadata, signed assertions validated check by check (signature, wrapping, audience, InResponseTo, replay…), SSO shared with OIDC

Future ideas (see [docs/design.md](docs/design.md#future-work)): the Attack Lab, client credentials and device code flows, SAML Single Logout.

## Security

See [docs/threat-model.md](docs/threat-model.md). Found a real vulnerability (not a deliberate Attack Lab one)?
Please open a private security advisory on this repo.

import type { ProtocolSpec } from './types'

export const oidc: ProtocolSpec = {
  slug: 'oidc',
  name: 'OpenID Connect',
  shortName: 'OIDC',
  tagline: 'An identity layer on top of OAuth 2.0: the app gets a signed ID token that says who signed in.',
  facts: [
    { label: 'Published', value: '2014, on top of OAuth 2.0 (2012)' },
    { label: 'Answers', value: 'Who is the user? (plus: may this app call APIs for them?)' },
    { label: 'Format', value: 'JSON over HTTPS; ID token is a signed JWT' },
    { label: 'Channels', value: 'Code via the browser, tokens on the back channel' },
    { label: 'Typical use', value: 'Consumer sign-in, modern workforce SSO, mobile and SPA apps' },
  ],
  playgroundStatus: 'Interactive playground arrives in milestone 2.',

  overview: {
    whatItIs: [
      'OAuth 2.0 was designed for delegated access: letting an app call an API on your behalf ("this photo printer may read my photos") without handing it your password. It hands out access tokens, but on purpose says nothing about who the user is.',
      'OpenID Connect adds the missing piece for sign-in. Alongside the access token, the identity provider returns an ID token: a signed JSON Web Token (JWT) with claims such as `sub` (a stable user id), `email` and `name`, addressed to one specific app (`aud`) and valid for a few minutes.',
      'The recommended flow for any app, from server-rendered sites to single-page and mobile apps, is the authorization code flow with PKCE. It is the flow this lab walks through.',
    ],
    useWhen: [
      'You are building anything new: web, mobile, SPA or CLI. OIDC is JSON over HTTPS and well supported by libraries.',
      'You want "Sign in with Google / Microsoft / Apple / GitHub".',
      'Your app also needs to call APIs with the user\'s permission: one flow gives you both an ID token and an access token.',
    ],
    avoidWhen: [
      'An enterprise customer\'s IdP only speaks SAML. Many still do, which is why most B2B apps support both.',
      'You only need machine-to-machine access with no user involved. Use the OAuth client credentials grant instead.',
    ],
  },

  components: [
    {
      term: 'End user',
      aka: ['resource owner'],
      inLab: 'You, as a demo user such as alice',
      description: 'The person signing in. They type their password at the IdP only, never at the app.',
    },
    {
      term: 'User agent',
      inLab: 'Your browser',
      description:
        'Carries the front-channel messages: every redirect between app and IdP passes through it. Anything it carries is visible to the user, browser extensions and history, so it must not carry long-lived secrets.',
    },
    {
      term: 'Relying Party',
      aka: ['RP', 'client', 'OAuth client'],
      inLab: 'App A (and App B)',
      description:
        'The app that wants to know who you are. It is registered with the IdP in advance and gets a `client_id` (and, for server-side apps, a `client_secret`).',
    },
    {
      term: 'OpenID Provider',
      aka: ['OP', 'identity provider', 'IdP', 'authorization server'],
      inLab: 'The lab IdP',
      description:
        'Authenticates the user, keeps the single sign-on session, and issues codes and tokens. Okta, Microsoft Entra ID, Google, Auth0 and Keycloak are all OpenID Providers.',
    },
    {
      term: 'Resource server',
      aka: ['API'],
      inLab: 'The IdP\'s `/userinfo` endpoint',
      description:
        'An API that accepts access tokens. It is not needed for sign-in itself, which is why it is not in the diagram.',
    },
  ],

  artifacts: [
    {
      term: 'Authorization code',
      inLab: '`code` on the callback URL',
      description:
        'A short-lived, single-use ticket the IdP hands to the app through the browser. It is useless on its own: the app must redeem it on the back channel with its client credentials and the PKCE verifier.',
    },
    {
      term: 'ID token',
      inLab: 'JWT in the token response',
      description:
        'Proof of authentication for one app. A JWT signed by the IdP. The app must validate the signature, `iss`, `aud`, `exp` and `nonce` before trusting any claim in it.',
    },
    {
      term: 'Access token',
      inLab: 'Bearer token for `/userinfo`',
      description:
        'Lets the app call APIs. It is for the API, not the app: never treat it as proof of who signed in.',
    },
    {
      term: 'Refresh token',
      inLab: 'Long-lived token in the token response',
      description: 'Gets new access tokens without sending the user back to the IdP. Keep it server side.',
    },
    {
      term: 'Discovery document',
      aka: ['`/.well-known/openid-configuration`'],
      inLab: 'Served by the lab IdP',
      description: 'JSON that lists the IdP\'s endpoints, supported features and where to find its signing keys.',
    },
    {
      term: 'JWKS',
      aka: ['JSON Web Key Set'],
      inLab: '`/jwks` on the lab IdP',
      description:
        'The IdP\'s public signing keys. Apps match the `kid` in a token header to a key here. Publishing keys by URL is what makes key rotation painless.',
    },
  ],

  flow: {
    id: 'oidc-authorization-code-pkce',
    title: 'Authorization code flow with PKCE',
    description:
      'The recommended flow for every kind of app. Tokens only travel on the back channel; the browser only ever carries a short-lived, single-use code.',
    lanes: [
      {
        id: 'browser',
        label: 'Browser',
        kind: 'browser',
        description: 'You and your browser (the user agent).',
      },
      {
        id: 'app',
        label: 'App A',
        kind: 'app',
        description: 'The relying party: an app with its own server.',
      },
      {
        id: 'idp',
        label: 'IdP',
        kind: 'idp',
        description: 'The OpenID Provider.',
      },
    ],
    steps: [
      {
        id: 'oidc.register',
        from: 'app',
        to: 'idp',
        channel: 'setup',
        label: 'Register client (once)',
        title: 'Before any login: register the app',
        summary:
          'An admin registers App A with the IdP. The app gets a `client_id` and `client_secret`; the IdP records the exact redirect URIs the app may use.',
        details: [
          'The app also reads the IdP\'s discovery document at `/.well-known/openid-configuration` to learn its endpoints and where its signing keys are published.',
          'The registered redirect URI list is a security control: it is the only place the IdP will ever send codes.',
        ],
        http: `GET /.well-known/openid-configuration HTTP/1.1
Host: idp.example

HTTP/1.1 200 OK
Content-Type: application/json

{
  "issuer": "https://idp.example",
  "authorization_endpoint": "https://idp.example/authorize",
  "token_endpoint": "https://idp.example/token",
  "jwks_uri": "https://idp.example/jwks",
  "code_challenge_methods_supported": ["S256"]
}`,
        threats: ['redirect-uri'],
      },
      {
        id: 'oidc.login',
        from: 'browser',
        to: 'app',
        channel: 'front',
        label: 'GET /login',
        title: 'The user clicks "Sign in"',
        summary: 'The browser asks App A for a protected page or clicks a sign-in button. App A has no session for this user yet.',
      },
      {
        id: 'oidc.prepare',
        from: 'app',
        to: 'app',
        channel: 'local',
        label: 'Create state, nonce, PKCE',
        title: 'App A prepares three one-time values',
        summary:
          'App A generates random `state`, `nonce` and a PKCE `code_verifier`, and stores them in the user\'s session (a cookie on App A\'s own site).',
        details: [
          '`state` ties the eventual callback to this browser session, which stops attackers from injecting their own login (login CSRF).',
          '`nonce` ends up inside the ID token, which ties the token to this login attempt and stops replay.',
          'The PKCE `code_verifier` stays secret. Only its SHA-256 hash, the `code_challenge`, is sent to the IdP. Whoever redeems the code later must prove they know the verifier.',
        ],
        http: `code_verifier  = random 43-128 chars, e.g. "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
code_challenge = BASE64URL(SHA256(code_verifier))
               = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"`,
        threats: ['login-csrf', 'code-interception', 'token-replay'],
      },
      {
        id: 'oidc.authorize-redirect',
        from: 'app',
        to: 'browser',
        channel: 'front',
        label: '302 → IdP /authorize',
        title: 'App A redirects the browser to the IdP',
        summary:
          'App A answers with a redirect to the IdP\'s authorization endpoint, describing what it wants in the query string.',
        details: [
          '`scope=openid` is what turns an OAuth request into an OpenID Connect sign-in.',
          'Nothing secret is in this URL: it is visible in the address bar and history.',
        ],
        http: `HTTP/1.1 302 Found
Location: https://idp.example/authorize
  ?response_type=code
  &client_id=app-a
  &redirect_uri=https%3A%2F%2Fapp-a.example%2Fcallback
  &scope=openid%20profile%20email
  &state=af0ifjsldkj
  &nonce=n-0S6_WzA2Mj
  &code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
  &code_challenge_method=S256`,
      },
      {
        id: 'oidc.authorize',
        from: 'browser',
        to: 'idp',
        channel: 'front',
        label: 'GET /authorize?…',
        title: 'The browser arrives at the IdP',
        summary:
          'The IdP checks that `client_id` is registered and that `redirect_uri` exactly matches one registered for it, then shows its login page.',
        checks: [
          '`client_id` is a known client',
          '`redirect_uri` exactly matches a registered URI (no prefix or wildcard matching)',
          '`response_type` and `scope` are allowed for this client',
        ],
        threats: ['redirect-uri'],
      },
      {
        id: 'oidc.authenticate',
        from: 'browser',
        to: 'idp',
        channel: 'front',
        label: 'POST /login',
        title: 'The user signs in at the IdP',
        summary:
          'The user types their password (plus MFA or a passkey) on the IdP\'s own page. The app never sees the password.',
        details: [
          'The IdP sets its own session cookie. That cookie is the "single" in single sign-on: next time any app sends this browser to the IdP, it can skip the login page.',
          'The IdP may also ask for consent: "App A wants to see your email address".',
        ],
      },
      {
        id: 'oidc.issue-code',
        from: 'idp',
        to: 'browser',
        channel: 'front',
        label: '302 → callback?code&state',
        title: 'The IdP redirects back with a code',
        summary:
          'The IdP creates a single-use authorization code, bound to the client, the redirect URI and the PKCE challenge, and redirects the browser back to App A.',
        details: ['The code lives for seconds to a minute and can be redeemed once.'],
        http: `HTTP/1.1 302 Found
Location: https://app-a.example/callback
  ?code=SplxlOBeZQQYbYS6WxSbIA
  &state=af0ifjsldkj`,
      },
      {
        id: 'oidc.callback',
        from: 'browser',
        to: 'app',
        channel: 'front',
        label: 'GET /callback?code&state',
        title: 'The browser delivers the code to App A',
        summary: 'App A checks that `state` matches the value it stored in this browser\'s session.',
        checks: ['`state` equals the value stored in the session, and is then deleted'],
        threats: ['login-csrf'],
      },
      {
        id: 'oidc.token',
        from: 'app',
        to: 'idp',
        channel: 'back',
        label: 'POST /token',
        title: 'App A redeems the code on the back channel',
        summary:
          'App A\'s server calls the IdP directly, authenticating as itself and proving it holds the PKCE `code_verifier`.',
        details: [
          'This request never touches the browser, so the tokens in the response never appear in a URL, the history or an extension.',
        ],
        http: `POST /token HTTP/1.1
Host: idp.example
Authorization: Basic YXBwLWE6ZGVtby1zZWNyZXQ=
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=SplxlOBeZQQYbYS6WxSbIA
&redirect_uri=https%3A%2F%2Fapp-a.example%2Fcallback
&code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk`,
        checks: [
          'The client authenticates (`client_secret` or a signed assertion)',
          'The code was issued to this client and has not been used before',
          '`redirect_uri` is identical to the one in the authorization request',
          'SHA-256 of `code_verifier` equals the stored `code_challenge`',
        ],
        threats: ['code-interception'],
      },
      {
        id: 'oidc.tokens',
        from: 'idp',
        to: 'app',
        channel: 'back',
        label: '200 { id_token, access_token }',
        title: 'The IdP returns tokens',
        summary: 'The response carries the ID token (who signed in), an access token (for APIs) and often a refresh token.',
        http: `HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store

{
  "id_token": "eyJhbGciOiJSUzI1NiIsImtpZCI6IjFlOWdkazcifQ.eyJpc3MiOi...",
  "access_token": "SlAV32hkKG",
  "token_type": "Bearer",
  "expires_in": 3600,
  "refresh_token": "8xLOxBtZp8"
}`,
      },
      {
        id: 'oidc.validate',
        from: 'app',
        to: 'app',
        channel: 'local',
        label: 'Validate ID token',
        title: 'App A validates the ID token',
        summary:
          'Before trusting a single claim, App A verifies the token. The signing key comes from the IdP\'s JWKS, fetched over HTTPS and cached.',
        http: `// Decoded ID token payload
{
  "iss": "https://idp.example",
  "sub": "alice",
  "aud": "app-a",
  "exp": 1790000600,
  "iat": 1790000000,
  "nonce": "n-0S6_WzA2Mj",
  "email": "alice@example.com"
}`,
        checks: [
          'Signature is valid, using the IdP key whose `kid` is in the token header',
          '`alg` is the one expected for this IdP (never `none`, never switched to HS256)',
          '`iss` is exactly the IdP\'s issuer',
          '`aud` contains App A\'s `client_id`',
          '`exp` is in the future (with a small clock-skew allowance)',
          '`nonce` equals the value stored in the session',
        ],
        threats: ['alg-confusion', 'audience', 'token-replay'],
      },
      {
        id: 'oidc.session',
        from: 'app',
        to: 'browser',
        channel: 'front',
        label: '302 + Set-Cookie',
        title: 'App A signs the user in',
        summary:
          'App A creates its own session for `sub` = alice and sets a session cookie. From now on App A relies on its own session, not the IdP.',
        details: [
          'Tokens stay on App A\'s server (the "backend for frontend" pattern), so a script injected into the page cannot steal them.',
          'If the user now opens App B, App B starts the same flow, but the IdP recognises its own session cookie and skips the login page. That is single sign-on.',
        ],
        http: `HTTP/1.1 302 Found
Location: /
Set-Cookie: app_session=…; HttpOnly; Secure; SameSite=Lax; Path=/`,
        threats: ['token-storage'],
      },
    ],
  },

  threats: [
    {
      id: 'login-csrf',
      name: 'Login CSRF (missing `state` check)',
      attack:
        'The attacker starts a login with their own account, stops before the callback, and tricks the victim\'s browser into opening the callback URL. The victim is now signed in to the app as the attacker and may, for example, save their card details into the attacker\'s account.',
      defense: 'Send a random `state`, store it in the session, and reject any callback whose `state` does not match.',
      attackLab: true,
    },
    {
      id: 'code-interception',
      name: 'Authorization code interception (no PKCE)',
      attack:
        'A malicious app registered for the same custom URL scheme, a leaky proxy log or a browser extension grabs the code from the redirect and redeems it before the real app does.',
      defense:
        'PKCE: only the party holding the original `code_verifier` can redeem the code. Required for public clients and recommended for all clients by the OAuth security best practices (RFC 9700).',
      attackLab: true,
    },
    {
      id: 'redirect-uri',
      name: 'Redirect URI manipulation',
      attack:
        'If the IdP matches redirect URIs by prefix or pattern, an attacker can craft a login link whose `redirect_uri` points to a page they control (or an open redirect on the real site), and the IdP delivers the victim\'s code there.',
      defense: 'Register full redirect URIs and compare them with exact string matching, both at `/authorize` and at `/token`.',
      attackLab: true,
    },
    {
      id: 'token-replay',
      name: 'ID token replay (missing `nonce` check)',
      attack:
        'An ID token captured from an earlier login (or issued to the attacker) is injected into a new login flow, and the app accepts it.',
      defense: 'Send a random `nonce`, and reject ID tokens whose `nonce` claim does not match the value stored in the session.',
      attackLab: true,
    },
    {
      id: 'alg-confusion',
      name: 'Signature bypass (`alg: none`, algorithm confusion)',
      attack:
        'The attacker edits the token and sets `"alg": "none"`, or switches RS256 to HS256 so a library "verifies" the HMAC using the IdP\'s public key as the secret. Naive libraries then accept a forged token.',
      defense: 'Pin the expected algorithm per IdP, never accept `none`, and use a maintained JWT library.',
      attackLab: true,
    },
    {
      id: 'audience',
      name: 'Token confusion (missing `aud` check)',
      attack:
        'A token the IdP issued to a different app, perhaps a malicious app the attacker registered, is presented to App A. It has a valid IdP signature, so App A accepts it.',
      defense: 'Check that `aud` contains your own `client_id` (and `azp` when there are several audiences).',
      attackLab: true,
    },
    {
      id: 'token-storage',
      name: 'Tokens stolen from the browser',
      attack:
        'Tokens kept in `localStorage` or returned in URL fragments (the deprecated implicit flow) can be read by any script injected into the page or leaked through history and Referer headers.',
      defense:
        'Keep tokens on the server and give the browser an HttpOnly session cookie. Use the code flow, never the implicit flow. Send `Referrer-Policy: no-referrer` on pages that handle codes.',
    },
    {
      id: 'mix-up',
      name: 'IdP mix-up',
      attack:
        'An app that trusts several IdPs is tricked into sending a code from an honest IdP to an attacker-controlled IdP\'s token endpoint.',
      defense:
        'Remember which IdP each login was started with, and check the `iss` response parameter (RFC 9207) on the callback.',
    },
  ],

  resources: [
    {
      title: 'OpenID Connect Core 1.0',
      url: 'https://openid.net/specs/openid-connect-core-1_0.html',
      kind: 'spec',
      source: 'OpenID Foundation',
      note: 'The ID token, its claims and the validation rules. Section 3.1 is the code flow.',
    },
    {
      title: 'OpenID Connect Discovery 1.0',
      url: 'https://openid.net/specs/openid-connect-discovery-1_0.html',
      kind: 'spec',
      source: 'OpenID Foundation',
      note: 'The `/.well-known/openid-configuration` document.',
    },
    {
      title: 'RFC 6749: The OAuth 2.0 Authorization Framework',
      url: 'https://datatracker.ietf.org/doc/html/rfc6749',
      kind: 'spec',
      source: 'IETF',
      note: 'The foundation OIDC builds on: roles, grants and endpoints.',
    },
    {
      title: 'RFC 7636: Proof Key for Code Exchange (PKCE)',
      url: 'https://datatracker.ietf.org/doc/html/rfc7636',
      kind: 'spec',
      source: 'IETF',
      note: 'Short and readable; explains the code interception attack it prevents.',
    },
    {
      title: 'RFC 7519: JSON Web Token (JWT)',
      url: 'https://datatracker.ietf.org/doc/html/rfc7519',
      kind: 'spec',
      source: 'IETF',
      note: 'The format of the ID token.',
    },
    {
      title: 'OAuth 2.0 Simplified',
      url: 'https://www.oauth.com/',
      kind: 'guide',
      source: 'Aaron Parecki',
      note: 'The friendliest complete guide, by a co-editor of OAuth 2.1.',
    },
    {
      title: 'An Illustrated Guide to OAuth and OpenID Connect',
      url: 'https://developer.okta.com/blog/2019/10/21/illustrated-guide-to-oauth-and-oidc',
      kind: 'guide',
      source: 'Okta Developer',
      note: 'Cartoon walkthrough of the same flow as this page.',
    },
    {
      title: 'OAuth 2.0 and OpenID Connect (in plain English)',
      url: 'https://www.youtube.com/watch?v=996OiexHze0',
      kind: 'video',
      source: 'OktaDev · Nate Barbettini',
      note: 'The classic one-hour introduction: why OAuth exists and how OIDC completes it.',
    },
    {
      title: 'Everything You Ever Wanted to Know About OAuth and OIDC',
      url: 'https://www.youtube.com/watch?v=8aCyojTIW6U',
      kind: 'video',
      source: 'OktaDev · Aaron Parecki',
      note: 'A deeper tour, including what changes with OAuth 2.1.',
    },
    {
      title: 'RFC 9700: Best Current Practice for OAuth 2.0 Security',
      url: 'https://datatracker.ietf.org/doc/html/rfc9700',
      kind: 'security',
      source: 'IETF',
      note: 'The current rules: PKCE everywhere, exact redirect matching, no implicit flow.',
    },
    {
      title: 'OAuth 2.0 authentication vulnerabilities',
      url: 'https://portswigger.net/web-security/oauth',
      kind: 'security',
      source: 'PortSwigger Web Security Academy',
      note: 'Free hands-on labs for many of the attacks on the Security tab.',
    },
    {
      title: 'OAuth 2.0 Cheat Sheet',
      url: 'https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html',
      kind: 'security',
      source: 'OWASP',
      note: 'A checklist for implementers.',
    },
    {
      title: 'OAuth: When Things Go Wrong',
      url: 'https://www.youtube.com/watch?v=H6MxsFMAoP8',
      kind: 'video',
      source: 'OktaDev',
      note: 'Real-world OAuth failures and what they teach.',
    },
  ],
}

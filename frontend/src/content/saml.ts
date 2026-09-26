import type { ProtocolSpec } from './types'

export const saml: ProtocolSpec = {
  slug: 'saml',
  name: 'SAML 2.0',
  shortName: 'SAML',
  tagline: 'The enterprise workhorse: the IdP sends the app a signed XML assertion through the browser.',
  facts: [
    { label: 'Published', value: '2005 (OASIS)' },
    { label: 'Answers', value: 'Who is the user, and what attributes do they have?' },
    { label: 'Format', value: 'XML with XML Signature' },
    { label: 'Channels', value: 'Request and signed response both carried by the browser' },
    { label: 'Typical use', value: 'Enterprise workforce SSO into SaaS apps' },
  ],
  playgroundStatus: 'Sign in for real and watch every request.',

  overview: {
    whatItIs: [
      'Security Assertion Markup Language 2.0 predates OAuth and was built for one job: letting a company\'s identity provider vouch for its employees to other companies\' apps. If your employer\'s Okta tile opens Salesforce or Workday, that is very often SAML.',
      'The IdP issues an assertion: an XML document saying "this is alice, she authenticated at 09:14 with a password, this statement is for Salesforce and valid until 09:19", signed with the IdP\'s private key.',
      'Unlike the OIDC code flow, there is usually no back channel. The signed assertion itself travels through the browser in an HTML form post, so everything rests on the app validating that signature correctly.',
    ],
    useWhen: [
      'You sell to enterprises: their IT teams expect "SAML SSO" and their IdPs (Okta, Entra ID, Ping, ADFS) all support it.',
      'You need to integrate with an existing SAML federation, such as many universities and governments.',
    ],
    avoidWhen: [
      'You are building consumer sign-in or a mobile app: OIDC is simpler and designed for it.',
      'You need an access token to call APIs: SAML only answers "who is this".',
    ],
  },

  components: [
    {
      term: 'Principal',
      aka: ['subject', 'user'],
      inLab: 'You, as a demo user such as alice',
      description: 'The person being vouched for.',
    },
    {
      term: 'User agent',
      inLab: 'Your browser',
      description:
        'Carries both the request (in a redirect URL) and the signed response (in an auto-submitting HTML form). It sees everything, so the assertion must be protected by its signature, not by secrecy.',
    },
    {
      term: 'Service Provider',
      aka: ['SP', 'relying party'],
      inLab: 'App A (and App B)',
      description:
        'The app. It is identified by an entity ID (a URI) and receives assertions at its Assertion Consumer Service (ACS) URL.',
    },
    {
      term: 'Identity Provider',
      aka: ['IdP', 'asserting party'],
      inLab: 'The lab IdP',
      description: 'Authenticates the user, keeps the single sign-on session, and signs assertions.',
    },
  ],

  artifacts: [
    {
      term: 'Metadata',
      inLab: 'XML exchanged once at setup',
      description:
        'Each side publishes an XML document with its entity ID, endpoints and certificates. Exchanging metadata is how the trust relationship is set up.',
    },
    {
      term: 'AuthnRequest',
      inLab: '`SAMLRequest` in the redirect URL',
      description:
        'The SP\'s request: "please authenticate this user for me and send the answer to this ACS URL". It carries an `ID` the response must echo.',
    },
    {
      term: 'Response and Assertion',
      inLab: '`SAMLResponse` in the form post',
      description:
        'The IdP\'s answer. The assertion inside holds the subject (`NameID`), the conditions (validity window and audience), how the user authenticated, and attributes such as email and groups.',
    },
    {
      term: 'Signing certificate',
      aka: ['X.509 certificate'],
      inLab: 'In the IdP metadata',
      description:
        'The SP verifies signatures with the certificate it got from the IdP\'s metadata, never with a certificate embedded in the incoming message.',
    },
    {
      term: 'RelayState',
      inLab: 'Travels with the request and response',
      description: 'An opaque value the SP uses to remember where the user was going, echoed back by the IdP.',
    },
    {
      term: 'Bindings',
      aka: ['HTTP-Redirect', 'HTTP-POST'],
      inLab: 'Redirect for the request, POST for the response',
      description:
        'How messages are carried. Requests are small and go in a URL (deflated and base64-encoded); signed responses are large and go in a form post.',
    },
  ],

  flow: {
    id: 'saml-sp-initiated',
    title: 'SP-initiated SSO (Redirect and POST bindings)',
    description:
      'The most common SAML flow: the user starts at the app, is sent to the IdP, and comes back carrying a signed assertion.',
    lanes: [
      {
        id: 'browser',
        label: 'Browser',
        kind: 'browser',
        description: 'You and your browser (the user agent).',
      },
      {
        id: 'sp',
        label: 'App A (SP)',
        kind: 'app',
        description: 'The service provider.',
      },
      {
        id: 'idp',
        label: 'IdP',
        kind: 'idp',
        description: 'The identity provider.',
      },
    ],
    steps: [
      {
        id: 'saml.metadata',
        from: 'sp',
        to: 'idp',
        channel: 'setup',
        label: 'Exchange metadata (once)',
        title: 'Before any login: exchange metadata',
        summary:
          'An admin gives the IdP the SP\'s metadata (entity ID, ACS URL) and gives the SP the IdP\'s metadata (entity ID, SSO URL, signing certificate).',
        details: ['This is the only moment the SP learns which certificate to trust. Everything later depends on it.'],
        http: `<md:EntityDescriptor entityID="https://idp.example/saml">
  <md:IDPSSODescriptor protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">
    <md:KeyDescriptor use="signing">
      <ds:KeyInfo><ds:X509Data><ds:X509Certificate>MIIC…</ds:X509Certificate></ds:X509Data></ds:KeyInfo>
    </md:KeyDescriptor>
    <md:SingleSignOnService
        Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect"
        Location="https://idp.example/saml/sso"/>
  </md:IDPSSODescriptor>
</md:EntityDescriptor>`,
        threats: ['embedded-cert'],
      },
      {
        id: 'saml.access',
        from: 'browser',
        to: 'sp',
        channel: 'front',
        label: 'GET /dashboard',
        title: 'The user opens the app',
        summary: 'The browser asks for a protected page. The SP has no session for this user.',
      },
      {
        id: 'saml.request',
        from: 'sp',
        to: 'sp',
        channel: 'local',
        label: 'Build AuthnRequest',
        title: 'The SP builds an AuthnRequest',
        summary: 'The SP creates a request with a fresh random `ID` and remembers that ID for this browser.',
        http: `<samlp:AuthnRequest
    ID="_a1b2c3d4"
    Version="2.0"
    IssueInstant="2026-09-26T09:14:00Z"
    Destination="https://idp.example/saml/sso"
    AssertionConsumerServiceURL="https://app-a.example/saml/acs"
    ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST">
  <saml:Issuer>https://app-a.example/saml</saml:Issuer>
</samlp:AuthnRequest>`,
        threats: ['unsolicited'],
      },
      {
        id: 'saml.redirect',
        from: 'sp',
        to: 'browser',
        channel: 'front',
        label: '302 → IdP ?SAMLRequest',
        title: 'The SP redirects the browser to the IdP',
        summary:
          'HTTP-Redirect binding: the XML is deflate-compressed, base64-encoded and URL-encoded into the query string, with `RelayState` alongside.',
        http: `HTTP/1.1 302 Found
Location: https://idp.example/saml/sso
  ?SAMLRequest=fZFNT8MwDIb%2FSpV7…
  &RelayState=%2Fdashboard`,
      },
      {
        id: 'saml.sso',
        from: 'browser',
        to: 'idp',
        channel: 'front',
        label: 'GET /saml/sso?SAMLRequest',
        title: 'The browser arrives at the IdP',
        summary:
          'The IdP decodes the request, checks the SP is one it knows, and that the ACS URL is registered for that SP.',
        checks: ['`Issuer` is a known SP', '`AssertionConsumerServiceURL` matches the SP\'s registered ACS URL'],
      },
      {
        id: 'saml.authenticate',
        from: 'browser',
        to: 'idp',
        channel: 'front',
        label: 'POST /login',
        title: 'The user signs in at the IdP',
        summary:
          'The user authenticates on the IdP\'s page, unless the IdP already has a session for them. That existing session is what makes the second app instant.',
      },
      {
        id: 'saml.issue',
        from: 'idp',
        to: 'idp',
        channel: 'local',
        label: 'Build and sign assertion',
        title: 'The IdP builds and signs the response',
        summary:
          'The assertion states who the user is, for which SP, for how long, and in reply to which request. The IdP signs it with its private key.',
        http: `<saml:Assertion ID="_e5f6" IssueInstant="2026-09-26T09:14:05Z" Version="2.0">
  <saml:Issuer>https://idp.example/saml</saml:Issuer>
  <ds:Signature>… signs the element with ID "_e5f6" …</ds:Signature>
  <saml:Subject>
    <saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">alice@example.com</saml:NameID>
    <saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">
      <saml:SubjectConfirmationData InResponseTo="_a1b2c3d4"
          Recipient="https://app-a.example/saml/acs"
          NotOnOrAfter="2026-09-26T09:19:05Z"/>
    </saml:SubjectConfirmation>
  </saml:Subject>
  <saml:Conditions NotBefore="2026-09-26T09:14:00Z" NotOnOrAfter="2026-09-26T09:19:05Z">
    <saml:AudienceRestriction>
      <saml:Audience>https://app-a.example/saml</saml:Audience>
    </saml:AudienceRestriction>
  </saml:Conditions>
  <saml:AuthnStatement AuthnInstant="2026-09-26T09:14:04Z">…</saml:AuthnStatement>
</saml:Assertion>`,
      },
      {
        id: 'saml.post-form',
        from: 'idp',
        to: 'browser',
        channel: 'front',
        label: '200 auto-submit form',
        title: 'The IdP hands the browser a self-submitting form',
        summary:
          'HTTP-POST binding: the response is too big for a URL, so the IdP returns an HTML page whose form posts the base64 `SAMLResponse` to the SP\'s ACS URL.',
        http: `<form method="post" action="https://app-a.example/saml/acs">
  <input type="hidden" name="SAMLResponse" value="PHNhbWxwOlJlc3BvbnNl…">
  <input type="hidden" name="RelayState" value="/dashboard">
</form>
<script>document.forms[0].submit()</script>`,
      },
      {
        id: 'saml.acs',
        from: 'browser',
        to: 'sp',
        channel: 'front',
        label: 'POST /saml/acs',
        title: 'The browser posts the response to the SP',
        summary:
          'This is a cross-site POST. Cookies marked `SameSite=Lax` are not sent with it, so the SP cannot rely on its usual session cookie here to look up the request ID. A classic SAML integration gotcha.',
        details: [
          'App A therefore keeps each AuthnRequest in a server-side cache and finds it by the response\'s `InResponseTo`, removing it as it does so: a response can only ever answer one request, once.',
        ],
      },
      {
        id: 'saml.validate',
        from: 'sp',
        to: 'sp',
        channel: 'local',
        label: 'Validate signature + conditions',
        title: 'The SP validates everything',
        summary:
          'The SP must validate the signature and every condition, and must read the user from exactly the element that was signed.',
        checks: [
          'Signature is valid, using the certificate from the IdP\'s metadata',
          'The assertion used is exactly the element the signature covers (no signature wrapping)',
          '`Issuer` is the expected IdP',
          '`Audience` is this SP\'s entity ID; `Recipient`/`Destination` is this ACS URL',
          '`InResponseTo` matches a request this SP sent',
          'Now is between `NotBefore` and `NotOnOrAfter`',
          'The assertion `ID` has not been seen before (replay cache)',
        ],
        threats: ['xsw', 'unsigned', 'audience', 'replay', 'embedded-cert', 'unsolicited', 'xxe', 'comments'],
      },
      {
        id: 'saml.session',
        from: 'sp',
        to: 'browser',
        channel: 'front',
        label: '302 → RelayState + Set-Cookie',
        title: 'The SP signs the user in',
        summary: 'The SP creates its own session for alice and redirects to where they were going (`RelayState`).',
        details: ['Only redirect to a local path from `RelayState`, or it becomes an open redirect.'],
      },
    ],
  },

  threats: [
    {
      id: 'xsw',
      name: 'XML Signature Wrapping (XSW)',
      attack:
        'The attacker keeps the IdP\'s correctly signed assertion but moves it somewhere else in the document, and inserts a forged assertion ("I am admin") where the app looks for the user. The signature still verifies, because it covers the original element, but the app reads the forged one.',
      defense:
        'Use a hardened SAML library, and read the subject only from the exact element whose signature was verified. Reject documents with more than one assertion.',
      attackLab: true,
    },
    {
      id: 'unsigned',
      name: 'Accepting unsigned assertions',
      attack: 'The attacker strips the `<ds:Signature>` element and edits the assertion. Some implementations skip verification when there is no signature.',
      defense: 'Require a valid signature on the assertion (or the whole response) every time.',
      attackLab: true,
    },
    {
      id: 'audience',
      name: 'Missing audience or recipient checks',
      attack:
        'A valid assertion the IdP issued for a different app (maybe one the attacker controls) is replayed to this app, which accepts it because the signature is genuine.',
      defense: 'Check `Audience` against your entity ID and `Recipient`/`Destination` against your ACS URL.',
      attackLab: true,
    },
    {
      id: 'replay',
      name: 'Assertion replay',
      attack: 'A captured assertion is posted again, by an attacker or from browser history, to sign in a second time.',
      defense: 'Enforce `NotOnOrAfter`, check `InResponseTo`, and cache assertion IDs until they expire.',
      attackLab: true,
    },
    {
      id: 'embedded-cert',
      name: 'Trusting the certificate in the message',
      attack:
        'The attacker signs a forged assertion with their own key and includes their own certificate in `<ds:KeyInfo>`. An app that verifies against that embedded certificate accepts it.',
      defense: 'Only verify with the certificate configured from the IdP\'s metadata.',
    },
    {
      id: 'comments',
      name: 'Comment injection in NameID',
      attack:
        'An attacker with an account `admin@example.com.evil.com` edits their own signed assertion so the NameID reads `admin@example.com<!---->.evil.com`. Canonicalization ignores comments, so the signature still verifies, but some XML libraries return only the text before the comment: the app sees `admin@example.com`.',
      defense: 'Use patched SAML and XML libraries that canonicalize text nodes consistently.',
    },
    {
      id: 'xxe',
      name: 'XML External Entities (XXE)',
      attack: 'A crafted document makes the XML parser read local files or make network requests while parsing the response.',
      defense: 'Disable DTDs and external entity resolution in the XML parser.',
    },
    {
      id: 'unsolicited',
      name: 'IdP-initiated (unsolicited) responses',
      attack:
        'With IdP-initiated SSO there is no request to match, so `InResponseTo` cannot be checked. That makes injected or replayed responses much harder to detect.',
      defense: 'Prefer SP-initiated SSO. If IdP-initiated is required, keep assertions very short-lived and keep a strict replay cache.',
    },
  ],

  resources: [
    {
      title: 'SAML 2.0 Technical Overview',
      url: 'https://docs.oasis-open.org/security/saml/Post2.0/sstc-saml-tech-overview-2.0.html',
      kind: 'spec',
      source: 'OASIS',
      note: 'Start here rather than the core spec: readable, with diagrams of each profile.',
    },
    {
      title: 'SAML 2.0 Core',
      url: 'https://docs.oasis-open.org/security/saml/v2.0/saml-core-2.0-os.pdf',
      kind: 'spec',
      source: 'OASIS',
      note: 'Assertions and protocol messages, element by element.',
    },
    {
      title: 'SAML 2.0 Bindings',
      url: 'https://docs.oasis-open.org/security/saml/v2.0/saml-bindings-2.0-os.pdf',
      kind: 'spec',
      source: 'OASIS',
      note: 'HTTP-Redirect and HTTP-POST, including how requests are deflated and encoded.',
    },
    {
      title: 'Understanding SAML',
      url: 'https://developer.okta.com/docs/concepts/saml/',
      kind: 'guide',
      source: 'Okta Developer',
      note: 'SP- and IdP-initiated flows from a developer\'s point of view.',
    },
    {
      title: 'How SAML Authentication Works',
      url: 'https://auth0.com/blog/how-saml-authentication-works/',
      kind: 'guide',
      source: 'Auth0',
      note: 'A walkthrough with annotated XML.',
    },
    {
      title: 'A Developer\'s Guide to SAML',
      url: 'https://www.youtube.com/watch?v=l-6QSEqDJPo',
      kind: 'video',
      source: 'OktaDev · Nick Gamb',
      note: 'A 28-minute tour of the protocol and its pitfalls.',
    },
    {
      title: 'SAML Security Cheat Sheet',
      url: 'https://cheatsheetseries.owasp.org/cheatsheets/SAML_Security_Cheat_Sheet.html',
      kind: 'security',
      source: 'OWASP',
      note: 'The validation checklist, with references to real attacks.',
    },
    {
      title: 'On Breaking SAML: Be Whoever You Want to Be',
      url: 'https://www.usenix.org/conference/usenixsecurity12/technical-sessions/presentation/somorovsky',
      kind: 'security',
      source: 'USENIX Security 2012',
      note: 'The paper that found signature wrapping in 11 of 14 major SAML frameworks.',
    },
    {
      title: 'The Fragile Lock: Novel Bypasses for SAML Authentication',
      url: 'https://portswigger.net/research/the-fragile-lock',
      kind: 'security',
      source: 'PortSwigger Research',
      note: 'Recent research showing these bugs are still being found.',
    },
  ],
}

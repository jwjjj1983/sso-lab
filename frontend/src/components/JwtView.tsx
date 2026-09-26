// Decodes a JWT in the browser (nothing is sent anywhere) and explains each part.

const CLAIMS: Record<string, string> = {
  iss: 'Issuer: which IdP made this token. Must be exactly the IdP you trust.',
  sub: 'Subject: a stable, unique id for the user at this IdP. Use this, not email, as the user key.',
  aud: 'Audience: which app this token is for. Must contain your client_id.',
  exp: 'Expiry time. Reject the token after this.',
  iat: 'Issued at.',
  auth_time: 'When the user actually authenticated at the IdP (can be long before iat, thanks to SSO).',
  nonce: 'Echo of the random value the app sent. Proves this token belongs to this login.',
  name: 'Profile claim (scope "profile").',
  email: 'Email claim (scope "email").',
  email_verified: 'Whether the IdP verified the email address.',
  alg: 'Signature algorithm. The app must insist on the one it expects.',
  kid: 'Key id: which key in the IdP\'s JWKS signed this token.',
  typ: 'Token type.',
}

const TIME_CLAIMS = new Set(['exp', 'iat', 'auth_time'])

function decodePart(part: string): Record<string, unknown> | null {
  try {
    const base64 = part.replace(/-/g, '+').replace(/_/g, '/')
    const json = decodeURIComponent(
      Array.from(atob(base64), (c) => '%' + c.charCodeAt(0).toString(16).padStart(2, '0')).join(''),
    )
    return JSON.parse(json) as Record<string, unknown>
  } catch {
    return null
  }
}

export function JwtView({ token }: { token: string }) {
  const [header, payload, signature] = token.split('.')
  const decodedHeader = decodePart(header ?? '')
  const decodedPayload = decodePart(payload ?? '')

  return (
    <div className="space-y-3">
      <p className="rounded-md bg-surface-2 p-2 font-mono text-xs break-all">
        <span className="text-front">{header}</span>.<span className="text-accent">{payload}</span>.
        <span className="text-back">{signature}</span>
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <ClaimTable title="Header" tone="text-front" claims={decodedHeader} />
        <ClaimTable title="Payload (claims)" tone="text-accent" claims={decodedPayload} />
      </div>
      <p className="text-xs text-muted">
        <span className="font-semibold text-back">Signature:</span> the IdP's RSA signature over header and payload.
        Anyone can read a JWT; only the IdP's private key can produce a valid signature, which the app checks with the
        public key from the IdP's JWKS.
      </p>
    </div>
  )
}

function ClaimTable({
  title,
  tone,
  claims,
}: {
  title: string
  tone: string
  claims: Record<string, unknown> | null
}) {
  return (
    <section className="min-w-0">
      <h4 className={`mb-1 text-xs font-semibold tracking-wide uppercase ${tone}`}>{title}</h4>
      {claims === null ? (
        <p className="text-sm text-err">Not valid base64url JSON.</p>
      ) : (
        <dl className="space-y-1.5 text-sm">
          {Object.entries(claims).map(([name, value]) => (
            <div key={name}>
              <dt className="font-mono text-xs">
                <span className="font-semibold">{name}</span>:{' '}
                <span className="break-all">{JSON.stringify(value)}</span>
                {TIME_CLAIMS.has(name) && typeof value === 'number' && (
                  <span className="text-muted"> ({new Date(value * 1000).toLocaleTimeString()})</span>
                )}
              </dt>
              {CLAIMS[name] && <dd className="text-xs text-muted">{CLAIMS[name]}</dd>}
            </div>
          ))}
        </dl>
      )}
    </section>
  )
}

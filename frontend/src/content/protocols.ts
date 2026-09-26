import { oidc } from './oidc'
import { saml } from './saml'
import type { ProtocolSpec, Resource } from './types'

export const PROTOCOLS: ProtocolSpec[] = [oidc, saml]

export function getProtocol(slug: string | undefined): ProtocolSpec | undefined {
  return PROTOCOLS.find((p) => p.slug === slug)
}

/** Reading list for the home page: SSO in general, before picking a protocol. */
export const GENERAL_RESOURCES: Resource[] = [
  {
    title: 'What Is Single Sign-on (SSO)? How It Works',
    url: 'https://www.youtube.com/watch?v=O1cRJWYF-g4',
    kind: 'video',
    source: 'ByteByteGo',
    note: 'A short animated overview of SSO, SAML and OIDC.',
  },
  {
    title: 'What is single sign-on (SSO)?',
    url: 'https://www.cloudflare.com/learning/access-management/what-is-sso/',
    kind: 'guide',
    source: 'Cloudflare Learning Center',
    note: 'Plain-language explanation of SSO, its benefits and its risks.',
  },
  {
    title: 'OAuth 2.0 and OpenID Connect (in plain English)',
    url: 'https://www.youtube.com/watch?v=996OiexHze0',
    kind: 'video',
    source: 'OktaDev · Nate Barbettini',
    note: 'The talk most engineers learn OAuth and OIDC from.',
  },
  {
    title: 'A Developer\'s Guide to SAML',
    url: 'https://www.youtube.com/watch?v=l-6QSEqDJPo',
    kind: 'video',
    source: 'OktaDev · Nick Gamb',
    note: 'SAML for developers in under half an hour.',
  },
]

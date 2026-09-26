import { render, screen } from '@testing-library/react'
import { JwtView } from './JwtView'

// Like an IdP: JSON, UTF-8 encoded, then base64url.
const b64url = (value: object) =>
  btoa(String.fromCharCode(...new TextEncoder().encode(JSON.stringify(value))))
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=+$/, '')

describe('JwtView', () => {
  it('decodes header and claims and explains them', () => {
    const token = `${b64url({ alg: 'RS256', kid: 'k1' })}.${b64url({ sub: 'alice', aud: 'app-a', name: 'Zoë' })}.sig`
    render(<JwtView token={token} />)
    expect(screen.getByText('"RS256"')).toBeInTheDocument()
    expect(screen.getByText('"alice"')).toBeInTheDocument()
    expect(screen.getByText('"Zoë"')).toBeInTheDocument() // UTF-8 survives base64url decoding
    expect(screen.getByText(/Must contain your client_id/)).toBeInTheDocument()
  })

  it('says so when a part is not valid', () => {
    render(<JwtView token="not.a-token.at-all" />)
    expect(screen.getAllByText(/not valid base64url JSON/i)).toHaveLength(2)
  })
})

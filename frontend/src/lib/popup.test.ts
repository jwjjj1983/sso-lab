import { runInPopup } from './popup'

function fakePopup() {
  const popup = { closed: false } as unknown as Window
  vi.spyOn(window, 'open').mockReturnValue(popup)
  return popup
}

function post(data: unknown, origin: string, source: unknown) {
  window.dispatchEvent(new MessageEvent('message', { data, origin, source: source as Window }))
}

afterEach(() => vi.restoreAllMocks())

describe('runInPopup', () => {
  it('ignores messages from other origins or other windows', async () => {
    const popup = fakePopup()
    const settled = vi.fn()
    const done = runInPopup('/rp/oidc/login', 'sso-lab:oidc', ['https://app-b.example']).then(settled)

    post({ type: 'sso-lab:oidc', stage: 'signed-in' }, 'https://evil.example', popup)
    post({ type: 'sso-lab:oidc', stage: 'signed-in' }, 'https://app-b.example', window)
    post({ type: 'something-else' }, 'https://app-b.example', popup)
    await Promise.resolve()
    expect(settled).not.toHaveBeenCalled()

    post({ type: 'sso-lab:oidc', stage: 'signed-in' }, 'https://app-b.example', popup)
    await done
    expect(settled).toHaveBeenCalledWith({ type: 'sso-lab:oidc', stage: 'signed-in' })
  })

  it('rejects when the flow reports an error', async () => {
    const popup = fakePopup()
    const done = runInPopup('/x', 'sso-lab:oidc')
    post({ type: 'sso-lab:oidc', stage: 'error', message: 'state mismatch' }, window.location.origin, popup)
    await expect(done).rejects.toThrow('state mismatch')
  })

  it('explains a blocked popup', async () => {
    vi.spyOn(window, 'open').mockReturnValue(null)
    await expect(runInPopup('/x', 'sso-lab:oidc')).rejects.toThrow(/blocked/)
  })
})

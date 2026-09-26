/**
 * Run a front-channel flow in a popup and wait for its last page to report back.
 *
 * The popup travels App A -> IdP -> App A. Only the final page, back on our own origin, may
 * post a message; messages from any other origin are ignored.
 */
export function runInPopup<T extends { type: string }>(url: string, messageType: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const popup = window.open(url, 'sso-lab-flow', 'popup,width=520,height=680')
    if (!popup) {
      reject(new Error('The popup was blocked. Allow popups for this site and try again.'))
      return
    }

    const cleanup = () => {
      window.removeEventListener('message', onMessage)
      window.clearInterval(closedPoll)
    }
    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== popup) return
      if (event.data?.type !== messageType) return
      cleanup()
      resolve(event.data as T)
    }
    const closedPoll = window.setInterval(() => {
      if (popup.closed) {
        cleanup()
        reject(new Error('The popup was closed before the flow finished.'))
      }
    }, 500)

    window.addEventListener('message', onMessage)
  })
}

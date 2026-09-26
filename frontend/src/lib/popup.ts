/**
 * Run a front-channel flow in a popup and wait for its last page to report back.
 *
 * The popup travels app -> IdP -> app. Only its final page posts a message, and only messages
 * from the origins we expect (by default our own) are accepted. Anything else could be a
 * page the popup was sent to pretending to be the app.
 */
export interface PopupMessage {
  type: string
  stage?: string
  message?: string
  app?: string
}

export function runInPopup<T extends PopupMessage = PopupMessage>(
  url: string,
  messageType: string,
  allowedOrigins: string[] = [window.location.origin],
): Promise<T> {
  return new Promise((resolve, reject) => {
    const popup = window.open(url, 'sso-lab-flow', 'popup,width=520,height=720')
    if (!popup) {
      reject(new Error('The popup was blocked. Allow popups for this site and try again.'))
      return
    }

    const cleanup = () => {
      window.removeEventListener('message', onMessage)
      window.clearInterval(closedPoll)
    }
    const onMessage = (event: MessageEvent) => {
      if (!allowedOrigins.includes(event.origin) || event.source !== popup) return
      const data = event.data as T | undefined
      if (data?.type !== messageType) return
      cleanup()
      if (data.stage === 'error') reject(new Error(data.message ?? 'The flow failed.'))
      else resolve(data)
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

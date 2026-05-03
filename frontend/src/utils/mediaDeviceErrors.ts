/**
 * Copy for camera/mic failures on phones — Chrome will not re-show the prompt after Block until site permissions reset.
 */

function trustedHttpsWorkaroundLines(): string[] {
  return [
    '',
    'If Chrome never shows an Allow dialog:',
    'Many Android Chromes silently block camera/mic on LAN URLs that use a dev/self-signed certificate (Vite HTTPS), even after you tap Continue.',
    '',
    'Use a tunnel with a real certificate, then open that https URL:',
    '  • ngrok:   npx ngrok http 5173',
    '  • cloudflared:   cloudflared tunnel --url http://localhost:5173',
    'Then use the printed https link + path /mobile?code=YOURCODE',
  ]
}

export function describeMobileCameraMicFailure(error: unknown): string {
  const domName = error instanceof DOMException ? error.name : ''
  const errName = error instanceof Error ? error.name : ''
  const name = domName || errName

  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
    return [
      'Camera or microphone was blocked or never prompted.',
      'Use the blue “Retry camera & mic” after changing settings.',
      '',
      'Chrome Android: Settings → Site settings → Camera → this site → Allow (same for Microphone).',
      'Or ⋮ → Clear browsing data → Advanced → Site settings only.',
      '',
      'If you truly never saw a prompt:',
      ...trustedHttpsWorkaroundLines(),
    ].join('\n')
  }

  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return 'No camera or microphone was found. Check that another app can use them, then tap Retry.'
  }

  if (name === 'NotReadableError' || name === 'TrackStartError') {
    return [
      'Camera or mic is in use or not readable. Close other apps using them, then tap Retry.',
      ...trustedHttpsWorkaroundLines(),
    ].join('\n')
  }

  const msg = error instanceof Error ? error.message : String(error)
  return [
    `Could not open camera/microphone (${msg || name || 'unknown error'}).`,
    '',
    'If HTTPS is weak (browser warning/certificate invalid), Chrome may suppress permission dialogs — try the tunnel workaround below.',
    ...trustedHttpsWorkaroundLines(),
  ].join('\n')
}

// Maps getUserMedia failures to messages an administrator can act on. Pure => unit-tested.
export function describeCameraError(err, isSecure = true) {
  const name = (err && err.name) || '';
  if (!isSecure) {
    return { title: 'Camera needs a secure connection', message: 'Browsers only allow camera access on https:// pages or on http://localhost. Open the site via HTTPS or localhost.' };
  }
  switch (name) {
    case 'NotAllowedError':
    case 'PermissionDeniedError':
      return { title: 'Camera permission denied', message: 'Allow camera access for this site in your browser (address-bar camera icon / site settings), then press Try again.' };
    case 'NotFoundError':
    case 'DevicesNotFoundError':
      return { title: 'No camera found', message: 'Connect a webcam and press Try again.' };
    case 'NotReadableError':
    case 'TrackStartError':
      return { title: 'Camera is busy', message: 'Another application or browser tab is using the camera. Close it and press Try again.' };
    case 'OverconstrainedError':
    case 'ConstraintNotSatisfiedError':
      return { title: 'Selected camera unavailable', message: 'That camera is no longer available. Pick another one or press Try again.' };
    case 'SecurityError':
      return { title: 'Camera blocked', message: 'Camera access is blocked by browser or site policy.' };
    default:
      if (err && err.code === 'unsupported') return { title: 'Camera not supported', message: 'This browser does not support camera access (getUserMedia).' };
      return { title: 'Could not start the camera', message: (err && err.message) || 'Unknown error.' };
  }
}


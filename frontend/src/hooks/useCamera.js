import { useCallback, useEffect, useRef, useState } from 'react';
import { describeCameraError } from '../lib/cameraErrors.js';

export default function useCamera() {
  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const canvasRef = useRef(null);
  const [status, setStatus] = useState('idle'); // idle | starting | active | error
  const [error, setError] = useState(null);
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  const releaseStream = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => { t.onended = null; t.stop(); });
      streamRef.current = null;
    }
  }, []);

  const refreshDevices = useCallback(async () => {
    try {
      const all = await navigator.mediaDevices.enumerateDevices();
      setDevices(all.filter((d) => d.kind === 'videoinput'));
    } catch { /* devices unavailable; ignore */ }
  }, []);

  const stop = useCallback(() => {
    releaseStream();
    if (videoRef.current) videoRef.current.srcObject = null;
    setStatus('idle');
  }, [releaseStream]);

  const start = useCallback(async (wantedId) => {
    setError(null);
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError(describeCameraError({ code: 'unsupported' }, window.isSecureContext));
      setStatus('error');
      return false;
    }
    if (!window.isSecureContext) {
      setError(describeCameraError({}, false));
      setStatus('error');
      return false;
    }
    releaseStream(); // restart cleanly when switching devices
    setStatus('starting');
    try {
      const video = { width: { ideal: 1280 }, height: { ideal: 720 } };
      if (wantedId) video.deviceId = { exact: wantedId };
      else video.facingMode = 'user';
      const stream = await navigator.mediaDevices.getUserMedia({ video, audio: false });
      streamRef.current = stream;
      const track = stream.getVideoTracks()[0];
      track.onended = () => {
        setError({ title: 'Camera disconnected', message: 'The video stream stopped (camera unplugged or taken by another app). Press Try again.' });
        setStatus('error');
        stream.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      };
      const v = videoRef.current;
      if (v) {
        v.srcObject = stream;
        await v.play().catch(() => {});
        setSize({ width: v.videoWidth, height: v.videoHeight });
      }
      setDeviceId((track.getSettings && track.getSettings().deviceId) || wantedId || null);
      setStatus('active');
      refreshDevices(); // labels become available only after permission is granted
      return true;
    } catch (e) {
      setError(describeCameraError(e, window.isSecureContext));
      setStatus('error');
      return false;
    }
  }, [refreshDevices, releaseStream]);

  const switchCamera = useCallback(async () => {
    if (devices.length < 2) return;
    const i = devices.findIndex((d) => d.deviceId === deviceId);
    const next = devices[(i + 1) % devices.length];
    await start(next.deviceId);
  }, [devices, deviceId, start]);

  // JPEG of the current frame, downscaled to maxWidth (keeps bandwidth and inference cost low)
  const captureFrame = useCallback(({ maxWidth = 640, quality = 0.8 } = {}) => new Promise((resolve) => {
    const v = videoRef.current;
    if (!v || !v.videoWidth || v.readyState < 2) { resolve(null); return; }
    const scale = Math.min(1, maxWidth / v.videoWidth);
    const w = Math.round(v.videoWidth * scale);
    const h = Math.round(v.videoHeight * scale);
    const c = canvasRef.current || (canvasRef.current = document.createElement('canvas'));
    c.width = w; c.height = h;
    c.getContext('2d').drawImage(v, 0, 0, w, h);
    c.toBlob((b) => resolve(b), 'image/jpeg', quality);
  }), []);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return undefined;
    const onMeta = () => setSize({ width: v.videoWidth, height: v.videoHeight });
    v.addEventListener('loadedmetadata', onMeta);
    return () => v.removeEventListener('loadedmetadata', onMeta);
  }, []);

  useEffect(() => releaseStream, [releaseStream]); // release the camera when the page unmounts

  return { videoRef, status, error, devices, deviceId, size, start, stop, switchCamera, captureFrame, active: status === 'active' };
}

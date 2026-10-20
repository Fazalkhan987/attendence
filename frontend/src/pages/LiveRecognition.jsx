import { useCallback, useEffect, useRef, useState } from 'react';
import { Camera, CameraOff, CheckCircle2, FlipHorizontal, Info, Play, RefreshCw, Square, Wifi, WifiOff } from 'lucide-react';
import useCamera from '../hooks/useCamera.js';
import { useAuth } from '../context/AuthContext.jsx';
import { useToast } from '../context/ToastContext.jsx';
import { formatTime } from '../lib/format.js';
import { Badge, PageHeader, Spinner, StatusBadge } from '../components/ui.jsx';

const SEND_INTERVAL_MS = 120;
const WS_PATH = '/ws/live';
const COLORS = { recognized: '#10b981', unknown: '#f43f5e', verifying: '#f59e0b', low_quality: '#94a3b8' };

function wsUrl() {
  const base = import.meta.env?.VITE_WS_BASE;
  if (base) return base + WS_PATH;
  return `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}${WS_PATH}`;
}

function faceLabel(f) {
  if (f.status === 'recognized') return [`${f.name} · ${f.person_id}`, `det ${f.det_score} · sim ${f.similarity ?? '–'}${f.attendance ? ` · ✓ ${formatTime(f.attendance.time)}` : ''}`];
  if (f.status === 'unknown') return ['Unknown', `det ${f.det_score}${f.similarity != null ? ` · sim ${f.similarity}` : ''}`];
  if (f.status === 'low_quality') return [f.message || 'Low quality', `det ${f.det_score}`];
  return ['Verifying…', `det ${f.det_score}${f.similarity != null ? ` · sim ${f.similarity}` : ''}`];
}

function drawOverlay(canvas, container, faces, frame, mirror) {
  if (!canvas || !container) return;
  const w = container.clientWidth;
  const h = container.clientHeight;
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (!frame.width || !frame.height) return;
  const sx = w / frame.width;
  const sy = h / frame.height;
  ctx.lineWidth = 3;
  ctx.font = '600 13px Inter, system-ui, sans-serif';
  ctx.textBaseline = 'top';
  faces.forEach((f) => {
    let [x1, y1, x2, y2] = f.bbox;
    x1 *= sx; x2 *= sx; y1 *= sy; y2 *= sy;
    if (mirror) { const a = w - x2; x2 = w - x1; x1 = a; }
    const color = COLORS[f.status] || COLORS.verifying;
    ctx.strokeStyle = color;
    ctx.strokeRect(x1, y1, x2 - x1, y2 - y1);
    const [l1, l2] = faceLabel(f);
    const w1 = Math.max(ctx.measureText(l1).width, ctx.measureText(l2).width) + 14;
    const top = y1 - 42 < 0 ? y2 : y1 - 42;
    ctx.fillStyle = color;
    ctx.fillRect(x1 - 1.5, top, w1, 42);
    ctx.fillStyle = '#fff';
    ctx.fillText(l1, x1 + 5, top + 5);
    ctx.font = '500 11px Inter, system-ui, sans-serif';
    ctx.fillText(l2, x1 + 5, top + 24);
    ctx.font = '600 13px Inter, system-ui, sans-serif';
  });
}

export default function LiveRecognition() {
  const cam = useCamera();
  const toast = useToast();
  const { logout } = useAuth();
  const [conn, setConn] = useState('off'); // off | connecting | connected | retrying
  const [faces, setFaces] = useState([]);
  const [checkins, setCheckins] = useState([]);
  const [banner, setBanner] = useState(null);
  const [stats, setStats] = useState({ latency: 0, fps: 0 });
  const [mirror, setMirror] = useState(true);

  const wsRef = useRef(null);
  const inflight = useRef(false);
  const inflightSince = useRef(0);
  const frameRef = useRef({ width: 0, height: 0 });
  const facesRef = useRef([]);
  const lastResultAt = useRef(0);
  const overlayRef = useRef(null);
  const boxRef = useRef(null);
  const bannerTimer = useRef(null);
  const lastErrorToast = useRef(0);

  const showBanner = useCallback((b) => {
    setBanner(b);
    clearTimeout(bannerTimer.current);
    bannerTimer.current = setTimeout(() => setBanner(null), 4500);
  }, []);

  const handleMessage = useCallback((msg) => {
    if (msg.type === 'ready') { setConn('connected'); return; }
    if (msg.type === 'pong') return;
    if (msg.type === 'error') {
      inflight.current = false;
      if (Date.now() - lastErrorToast.current > 8000) { lastErrorToast.current = Date.now(); toast.error(msg.message || 'Recognition error.'); }
      return;
    }
    if (msg.type !== 'result') return;
    inflight.current = false;
    const now = performance.now();
    if (lastResultAt.current) setStats({ latency: msg.latency_ms, fps: Math.round(1000 / (now - lastResultAt.current)) });
    lastResultAt.current = now;
    frameRef.current = { width: msg.width, height: msg.height };
    facesRef.current = msg.faces;
    setFaces(msg.faces);
    msg.events.forEach((ev) => {
      if (ev.type !== 'attendance') return;
      if (ev.outcome === 'already_marked') {
        showBanner({ tone: 'info', title: ev.name, text: `Already marked today at ${formatTime(ev.time)}` });
      } else {
        showBanner({ tone: 'success', title: ev.name, text: `Attendance recorded: ${ev.status} at ${formatTime(ev.time)}` });
        toast.success(`${ev.name} marked ${ev.status} at ${formatTime(ev.time)}`);
        setCheckins((c) => [{ ...ev, key: `${ev.person_id}-${Date.now()}` }, ...c].slice(0, 30));
      }
    });
  }, [showBanner, toast]);

  // WebSocket lifecycle: connect while the camera is active, reconnect with back-off, stop with the camera.
  useEffect(() => {
    if (!cam.active) { setConn('off'); return undefined; }
    let cancelled = false;
    let retry = 0;
    let timer = null;
    const connect = () => {
      if (cancelled) return;
      setConn(retry ? 'retrying' : 'connecting');
      const ws = new WebSocket(wsUrl());
      wsRef.current = ws;
      ws.onmessage = (e) => { try { handleMessage(JSON.parse(e.data)); } catch { /* ignore malformed */ } };
      ws.onopen = () => { retry = 0; inflight.current = false; };
      ws.onclose = (e) => {
        inflight.current = false;
        if (cancelled) return;
        if (e.code === 4401) { toast.error('Your session expired. Please sign in again.'); logout(); return; }
        if (e.code === 4403) { setConn('off'); toast.error('Connection refused: origin not allowed.'); return; }
        retry += 1;
        setConn('retrying');
        timer = setTimeout(connect, Math.min(1000 * 2 ** Math.min(retry, 4), 10000));
      };
      ws.onerror = () => { /* onclose follows */ };
    };
    connect();
    return () => { cancelled = true; clearTimeout(timer); if (wsRef.current) { wsRef.current.onclose = null; wsRef.current.close(); wsRef.current = null; } setFaces([]); };
  }, [cam.active, handleMessage, logout, toast]);

  // Frame sender: one frame in flight at a time (natural back-pressure), ~8 fps max.
  useEffect(() => {
    if (!cam.active || conn !== 'connected') return undefined;
    let stopped = false;
    let timer = null;
    const tick = async () => {
      if (stopped) return;
      const ws = wsRef.current;
      if (inflight.current && Date.now() - inflightSince.current > 6000) inflight.current = false; // lost response
      if (!inflight.current && ws && ws.readyState === WebSocket.OPEN) {
        inflight.current = true; inflightSince.current = Date.now();
        try {
          const blob = await cam.captureFrame({ maxWidth: 640, quality: 0.7 });
          if (blob && !stopped && ws.readyState === WebSocket.OPEN) ws.send(blob); else inflight.current = false;
        } catch { inflight.current = false; }
      }
      timer = setTimeout(tick, SEND_INTERVAL_MS);
    };
    tick();
    return () => { stopped = true; clearTimeout(timer); };
  }, [cam.active, conn, cam.captureFrame]); // eslint-disable-line react-hooks/exhaustive-deps

  // Redraw boxes whenever results change or the window resizes
  useEffect(() => { drawOverlay(overlayRef.current, boxRef.current, faces, frameRef.current, mirror); }, [faces, mirror, cam.size]);
  useEffect(() => {
    const onResize = () => drawOverlay(overlayRef.current, boxRef.current, facesRef.current, frameRef.current, mirror);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [mirror]);
  useEffect(() => () => clearTimeout(bannerTimer.current), []);

  const ratio = cam.size.width && cam.size.height ? `${cam.size.width} / ${cam.size.height}` : '16 / 9';
  const connBadge = {
    connected: <Badge tone="green"><Wifi className="h-3 w-3" />Connected</Badge>,
    connecting: <Badge tone="amber"><Spinner className="h-3 w-3" />Connecting</Badge>,
    retrying: <Badge tone="amber"><WifiOff className="h-3 w-3" />Reconnecting…</Badge>,
    off: <Badge>Camera off</Badge>,
  }[conn];
  const recognised = faces.filter((f) => f.status === 'recognized');

  return (
    <>
      <PageHeader title="Live camera" subtitle="Recognised people are marked present automatically (once per day).">
        {connBadge}
        {cam.active && <span className="hidden text-xs text-slate-500 sm:inline">{stats.latency} ms · {stats.fps || 0} fps</span>}
      </PageHeader>

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <div ref={boxRef} className="relative overflow-hidden rounded-2xl bg-slate-900 shadow-card" style={{ aspectRatio: ratio }}>
            <video ref={cam.videoRef} playsInline muted autoPlay className={`absolute inset-0 h-full w-full object-cover ${mirror ? '-scale-x-100' : ''} ${cam.active ? '' : 'invisible'}`} />
            <canvas ref={overlayRef} className="pointer-events-none absolute inset-0 h-full w-full" />

            {banner && (
              <div className={`absolute inset-x-4 top-4 flex items-center gap-3 rounded-xl px-4 py-3 text-white shadow-lg ${banner.tone === 'success' ? 'bg-emerald-600' : 'bg-sky-600'}`} role="status">
                {banner.tone === 'success' ? <CheckCircle2 className="h-7 w-7 shrink-0" /> : <Info className="h-7 w-7 shrink-0" />}
                <div><p className="text-lg font-semibold leading-tight">{banner.title}</p><p className="text-sm text-white/90">{banner.text}</p></div>
              </div>
            )}

            {!cam.active && (
              <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 p-6 text-center text-slate-200">
                {cam.status === 'starting' && <><Spinner className="h-9 w-9 !text-slate-200" /><p>Waiting for camera permission…</p></>}
                {cam.status === 'error' && <>
                  <CameraOff className="h-10 w-10 text-rose-300" /><p className="text-lg font-medium">{cam.error?.title}</p>
                  <p className="max-w-md text-sm text-slate-300">{cam.error?.message}</p>
                  <button className="btn-secondary" onClick={() => cam.start(cam.deviceId)}><RefreshCw className="h-4 w-4" />Try again</button></>}
                {cam.status === 'idle' && <>
                  <Camera className="h-10 w-10 text-slate-400" /><p className="max-w-sm text-sm text-slate-300">Start the camera to recognise registered people. Your browser will ask for permission the first time.</p>
                  <button className="btn-primary" onClick={() => cam.start()}><Play className="h-4 w-4" />Start camera</button></>}
              </div>
            )}
          </div>

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {cam.active
              ? <button className="btn-danger" onClick={cam.stop}><Square className="h-4 w-4" />Stop camera</button>
              : <button className="btn-primary" onClick={() => cam.start(cam.deviceId)} disabled={cam.status === 'starting'}><Play className="h-4 w-4" />Start camera</button>}
            {cam.devices.length > 1 && (
              <>
                <select className="input w-auto max-w-[220px]" value={cam.deviceId || ''} onChange={(e) => cam.start(e.target.value)} aria-label="Select camera">
                  {cam.devices.map((d, i) => <option key={d.deviceId} value={d.deviceId}>{d.label || `Camera ${i + 1}`}</option>)}
                </select>
                <button className="btn-secondary" onClick={cam.switchCamera} disabled={!cam.active}><RefreshCw className="h-4 w-4" />Switch</button>
              </>
            )}
            <button className="btn-secondary" onClick={() => setMirror((m) => !m)}><FlipHorizontal className="h-4 w-4" />{mirror ? 'Mirrored' : 'Not mirrored'}</button>
          </div>
          <p className="mt-3 flex gap-2 text-xs text-slate-500"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />A person is marked only after several consistent matches. Unknown, uncertain and low-quality faces never create attendance. Face recognition alone cannot detect photos or screens held up to the camera.</p>
        </div>

        <div className="space-y-6">
          <section className="card p-4">
            <h2 className="mb-3 font-semibold text-slate-900">In view now ({faces.length})</h2>
            {faces.length === 0 ? <p className="text-sm text-slate-500">{cam.active ? 'No faces detected.' : 'Camera is off.'}</p> : (
              <ul className="space-y-2">
                {faces.map((f) => (
                  <li key={f.id} className="flex items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2 text-sm">
                    <span className="min-w-0 truncate font-medium text-slate-800">{f.status === 'recognized' ? f.name : f.status === 'unknown' ? 'Unknown' : f.status === 'low_quality' ? (f.message || 'Low quality') : 'Verifying…'}</span>
                    <span className="shrink-0 text-xs text-slate-500">{f.status === 'recognized' ? `sim ${f.similarity}` : `det ${f.det_score}`}</span>
                  </li>
                ))}
              </ul>
            )}
            {recognised.length > 0 && <p className="mt-3 text-xs text-emerald-700">{recognised.length} recognised</p>}
          </section>

          <section className="card p-4">
            <div className="mb-3 flex items-center justify-between"><h2 className="font-semibold text-slate-900">Checked in this session</h2>{checkins.length > 0 && <button className="text-xs text-slate-500 hover:text-slate-700" onClick={() => setCheckins([])}>Clear</button>}</div>
            {checkins.length === 0 ? <p className="text-sm text-slate-500">Nobody yet.</p> : (
              <ul className="max-h-80 space-y-2 overflow-y-auto">
                {checkins.map((c) => (
                  <li key={c.key} className="flex items-center justify-between gap-2 rounded-lg border border-emerald-100 bg-emerald-50/60 px-3 py-2 text-sm">
                    <div className="min-w-0"><p className="truncate font-medium text-slate-900">{c.name}</p><p className="text-xs text-slate-500">{c.person_id} · {formatTime(c.time)}</p></div>
                    <StatusBadge status={c.status} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </>
  );
}

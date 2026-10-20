import { useCallback, useEffect, useRef, useState } from 'react';
import { Camera, CameraOff, CheckCircle2, ImagePlus, RefreshCw, Trash2, TriangleAlert, XCircle } from 'lucide-react';
import { api } from '../lib/api.js';
import useCamera from '../hooks/useCamera.js';
import { useToast } from '../context/ToastContext.jsx';
import { ConfirmDialog, Modal, Spinner } from './ui.jsx';

const MAX_SHOTS = 20;
const PROMPTS = ['Look straight at the camera', 'Turn your head slightly left', 'Turn your head slightly right', 'Tilt your chin slightly up', 'Tilt your chin slightly down', 'Neutral expression', 'Slight smile'];

export default function FaceEnrollModal({ open, person, onClose, onDone }) {
  const cam = useCamera();
  const toast = useToast();
  const [shots, setShots] = useState([]); // { id, blob, url, name }
  const [auto, setAuto] = useState(true);
  const [feedback, setFeedback] = useState(null);
  const [saving, setSaving] = useState(false);
  const [report, setReport] = useState(null);
  const [dup, setDup] = useState(null);
  const [error, setError] = useState('');
  const [minSamples, setMinSamples] = useState(5);
  const [confirmClear, setConfirmClear] = useState(false);
  const [clearing, setClearing] = useState(false);
  const [existing, setExisting] = useState(0);
  const fileRef = useRef(null);
  const shotsRef = useRef([]);
  const lastShotAt = useRef(0);
  const nextId = useRef(1);
  shotsRef.current = shots;
  const target = Math.max(minSamples, 8);

  const addShot = useCallback((blob, name) => {
    if (shotsRef.current.length >= MAX_SHOTS) return;
    const id = nextId.current++;
    setShots((s) => [...s, { id, blob, url: URL.createObjectURL(blob), name: name || `capture-${id}.jpg` }]);
    setReport(null);
    setDup(null);
  }, []);

  const removeShot = (id) => setShots((s) => { const x = s.find((i) => i.id === id); if (x) URL.revokeObjectURL(x.url); return s.filter((i) => i.id !== id); });

  // open / close lifecycle
  useEffect(() => {
    if (!open) return undefined;
    setShots([]); setFeedback(null); setReport(null); setDup(null); setError(''); setExisting(person?.face_samples || 0);
    api.systemStatus().then((s) => setMinSamples(s.min_enrollment_samples || 5)).catch(() => {});
    cam.start();
    return () => { cam.stop(); shotsRef.current.forEach((s) => URL.revokeObjectURL(s.url)); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, person?.person_id]);

  // live quality feedback (+ optional auto-capture) while the camera runs
  useEffect(() => {
    if (!open || !cam.active) return undefined;
    let stopped = false;
    let busy = false;
    const timer = setInterval(async () => {
      if (busy || stopped) return;
      busy = true;
      try {
        const small = await cam.captureFrame({ maxWidth: 640, quality: 0.8 });
        if (!small || stopped) return;
        const fb = await api.people.checkFrame(small);
        if (stopped) return;
        setFeedback(fb);
        if (auto && fb.ok && shotsRef.current.length < MAX_SHOTS && Date.now() - lastShotAt.current > 1300) {
          const big = await cam.captureFrame({ maxWidth: 1280, quality: 0.92 });
          if (big && !stopped) { lastShotAt.current = Date.now(); addShot(big); }
        }
      } catch (e) {
        if (!stopped) setFeedback({ ok: false, reasons: [e.message], bbox: null });
      } finally {
        busy = false;
      }
    }, 900);
    return () => { stopped = true; clearInterval(timer); };
  }, [open, cam.active, auto, addShot]); // eslint-disable-line react-hooks/exhaustive-deps

  async function manualCapture() {
    const blob = await cam.captureFrame({ maxWidth: 1280, quality: 0.92 });
    if (blob) { lastShotAt.current = Date.now(); addShot(blob); } else toast.error('Camera is not ready yet.');
  }

  function onFiles(e) {
    Array.from(e.target.files || []).slice(0, MAX_SHOTS - shots.length).forEach((f) => addShot(f, f.name));
    e.target.value = '';
  }

  async function save(allowDup = false) {
    setSaving(true); setError(''); setDup(null);
    try {
      const res = await api.people.enroll(person.person_id, shots.map((s) => new File([s.blob], s.name, { type: s.blob.type || 'image/jpeg' })), allowDup);
      setReport(res.report);
      shotsRef.current.forEach((x) => URL.revokeObjectURL(x.url));
      setShots([]); setExisting(res.person.face_samples);
      toast.success(`Face registered for ${person.full_name} (${res.person.face_samples} samples).`);
      onDone(res.person);
    } catch (err) {
      if (err.code === 'insufficient_samples') { setReport(err.details.report); setError(err.message); }
      else if (err.code === 'possible_duplicate_identity') { setDup(err.details.candidates || []); setError(err.message); }
      else setError(err.message);
    } finally {
      setSaving(false);
    }
  }

  async function clearExisting() {
    setClearing(true);
    try {
      const r = await api.people.clearFaces(person.person_id);
      setExisting(0); toast.success('Existing face data removed.'); onDone(r.person); setConfirmClear(false);
    } catch (err) { toast.error(err.message); } finally { setClearing(false); }
  }

  const rejectedReason = (i) => { const s = report?.samples?.[i]; return s && !s.accepted ? s.reasons.join('; ') : null; };
  const box = feedback?.bbox && feedback.width ? feedback.bbox : null;
  const ratio = cam.size.width && cam.size.height ? `${cam.size.width} / ${cam.size.height}` : '16 / 9';
  const mirrored = true;

  return (
    <>
      <Modal open={open} onClose={onClose} size="xl" title={`Register face: ${person?.full_name || ''} (${person?.person_id || ''})`} closeDisabled={saving}
        footer={<>
          <button className="btn-secondary" onClick={onClose} disabled={saving}>Close</button>
          <button className="btn-primary" disabled={saving || shots.length === 0} onClick={() => save(false)}>
            {saving ? <><Spinner className="h-4 w-4 !text-white" />Analysing…</> : `Save ${shots.length} photo${shots.length === 1 ? '' : 's'}`}
          </button>
        </>}>
        <div className="grid gap-5 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <div className="relative overflow-hidden rounded-xl bg-slate-900" style={{ aspectRatio: ratio }}>
              <video ref={cam.videoRef} playsInline muted autoPlay className={`h-full w-full object-cover ${mirrored ? '-scale-x-100' : ''} ${cam.active ? '' : 'invisible'}`} />
              {cam.active && box && (
                <div className={`absolute rounded-md border-2 ${feedback.ok ? 'border-emerald-400' : 'border-amber-400'}`}
                  style={{ left: `${(1 - box[2] / feedback.width) * 100}%`, top: `${(box[1] / feedback.height) * 100}%`, width: `${((box[2] - box[0]) / feedback.width) * 100}%`, height: `${((box[3] - box[1]) / feedback.height) * 100}%` }} />
              )}
              {!cam.active && (
                <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 p-6 text-center text-slate-200">
                  {cam.status === 'starting' && <><Spinner className="h-8 w-8 !text-slate-200" /><p className="text-sm">Waiting for camera permission…</p></>}
                  {cam.status === 'error' && <><CameraOff className="h-9 w-9 text-rose-300" /><p className="font-medium">{cam.error?.title}</p><p className="max-w-sm text-sm text-slate-300">{cam.error?.message}</p>
                    <button className="btn-secondary btn-sm" onClick={() => cam.start(cam.deviceId)}><RefreshCw className="h-4 w-4" />Try again</button></>}
                  {cam.status === 'idle' && <button className="btn-primary" onClick={() => cam.start()}><Camera className="h-4 w-4" />Start camera</button>}
                </div>
              )}
              {cam.active && (
                <div className={`absolute inset-x-0 bottom-0 px-3 py-2 text-sm ${feedback?.ok ? 'bg-emerald-600/90 text-white' : 'bg-slate-900/80 text-amber-100'}`}>
                  {feedback ? (feedback.ok ? 'Good: hold still' : feedback.reasons.join(' · ')) : 'Looking for a face…'}
                </div>
              )}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <button className="btn-primary" onClick={manualCapture} disabled={!cam.active}><Camera className="h-4 w-4" />Capture now</button>
              <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-slate-600"><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} className="h-4 w-4 rounded border-slate-300 text-indigo-600" />Auto-capture when quality is good</label>
              <button className="btn-secondary" onClick={() => fileRef.current?.click()}><ImagePlus className="h-4 w-4" />Upload photos</button>
              <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={onFiles} />
              {cam.devices.length > 1 && <button className="btn-secondary" onClick={cam.switchCamera}><RefreshCw className="h-4 w-4" />Switch camera</button>}
            </div>
            <p className="mt-3 text-sm text-slate-600"><strong>Tip:</strong> {PROMPTS[shots.length % PROMPTS.length]}. Good lighting, no sunglasses or masks, one person in view.</p>
          </div>

          <div className="lg:col-span-2">
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="font-medium text-slate-800">Captured photos ({shots.length})</span>
              <span className={shots.length >= target ? 'text-emerald-600' : 'text-slate-500'}>aim for {target}+ (min {minSamples})</span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full bg-indigo-500 transition-all" style={{ width: `${Math.min(100, (shots.length / target) * 100)}%` }} /></div>

            {existing > 0 && (
              <div className="mt-3 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
                {person.full_name} already has {existing} face samples; new photos are added to them.
                <button className="mt-2 flex items-center gap-1 font-medium text-rose-700 hover:underline" onClick={() => setConfirmClear(true)}><Trash2 className="h-4 w-4" />Remove existing face data</button>
              </div>
            )}

            {error && <div role="alert" className="mt-3 flex gap-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800"><XCircle className="mt-0.5 h-4 w-4 shrink-0" /><span>{error}</span></div>}
            {dup && (
              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                <p className="flex items-center gap-2 font-medium"><TriangleAlert className="h-4 w-4" />Possible duplicate identity</p>
                <ul className="mt-1 list-disc pl-5">{dup.map((c) => <li key={c.person_id}>{c.name} ({c.person_id}) similarity {c.similarity}</li>)}</ul>
                <button className="btn-secondary btn-sm mt-2" onClick={() => save(true)} disabled={saving}>This is a different person: register anyway</button>
              </div>
            )}
            {report && !error && (
              <div className="mt-3 flex gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /><div>{report.accepted} accepted, {report.rejected} rejected. Total samples: {report.total_samples}.
                {report.samples.filter((x) => !x.accepted).map((x) => <p key={x.index} className="text-xs text-emerald-800/80">{x.source}: {x.reasons.join('; ')}</p>)}</div></div>
            )}

            <div className="mt-3 grid max-h-72 grid-cols-3 gap-2 overflow-y-auto pr-1">
              {shots.map((s, i) => {
                const why = rejectedReason(i);
                return (
                  <div key={s.id} className={`group relative overflow-hidden rounded-lg border-2 ${why ? 'border-rose-400' : 'border-transparent'}`} title={why || s.name}>
                    <img src={s.url} alt={`Capture ${i + 1}`} className="aspect-square w-full object-cover" />
                    {why && <span className="absolute inset-x-0 bottom-0 line-clamp-2 bg-rose-600/90 px-1 py-0.5 text-[10px] leading-tight text-white">{why}</span>}
                    <button onClick={() => removeShot(s.id)} aria-label={`Remove photo ${i + 1}`} className="absolute right-1 top-1 rounded-full bg-slate-900/70 p-1 text-white opacity-0 transition group-hover:opacity-100 focus:opacity-100"><Trash2 className="h-3 w-3" /></button>
                  </div>
                );
              })}
              {shots.length === 0 && <p className="col-span-3 py-6 text-center text-sm text-slate-400">No photos yet.</p>}
            </div>
          </div>
        </div>
      </Modal>
      <ConfirmDialog open={confirmClear} danger busy={clearing} title="Remove face data?" confirmLabel="Remove"
        message={`This permanently deletes the stored face data of ${person?.full_name}. They will not be recognised until a new face is registered.`}
        onConfirm={clearExisting} onClose={() => setConfirmClear(false)} />
    </>
  );
}

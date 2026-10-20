import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';

const ToastContext = createContext(null);
const STYLES = {
  success: { icon: CheckCircle2, cls: 'border-emerald-200 bg-emerald-50 text-emerald-900', ic: 'text-emerald-600' },
  error: { icon: AlertCircle, cls: 'border-rose-200 bg-rose-50 text-rose-900', ic: 'text-rose-600' },
  info: { icon: Info, cls: 'border-sky-200 bg-sky-50 text-sky-900', ic: 'text-sky-600' },
};

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id) => setToasts((t) => t.filter((x) => x.id !== id)), []);
  const push = useCallback((type, message, ms = 4500) => {
    const id = nextId.current++;
    setToasts((t) => [...t.slice(-3), { id, type, message }]);
    if (ms) setTimeout(() => dismiss(id), ms);
  }, [dismiss]);

  const api = useMemo(() => ({
    success: (m, ms) => push('success', m, ms),
    error: (m, ms) => push('error', m, ms ?? 7000),
    info: (m, ms) => push('info', m, ms),
  }), [push]);

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="pointer-events-none fixed right-4 top-4 z-[100] flex w-full max-w-sm flex-col gap-2" aria-live="polite">
        {toasts.map((t) => {
          const s = STYLES[t.type];
          const Icon = s.icon;
          return (
            <div key={t.id} role="status" className={`pointer-events-auto flex items-start gap-3 rounded-lg border p-3 shadow-lg ${s.cls}`}>
              <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${s.ic}`} />
              <p className="flex-1 text-sm">{t.message}</p>
              <button onClick={() => dismiss(t.id)} aria-label="Dismiss" className="opacity-60 hover:opacity-100"><X className="h-4 w-4" /></button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>');
  return ctx;
}

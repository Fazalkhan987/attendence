import { useEffect, useState } from 'react';
import { api } from '../lib/api.js';
import { useToast } from '../context/ToastContext.jsx';
import { Field, Modal, Spinner } from './ui.jsx';

const EMPTY = { person_id: '', full_name: '', type: 'student', department: '', class_name: '', email: '', phone: '', notes: '' };

export default function PersonFormModal({ open, person, onClose, onSaved }) {
  const editing = Boolean(person);
  const toast = useToast();
  const [form, setForm] = useState(EMPTY);
  const [errors, setErrors] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setForm(person ? { ...EMPTY, ...Object.fromEntries(Object.entries(person).map(([k, v]) => [k, v ?? ''])) } : EMPTY);
      setErrors({});
    }
  }, [open, person]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    const local = {};
    if (!editing && !form.person_id.trim()) local.person_id = 'ID is required.';
    if (form.full_name.trim().length < 2) local.full_name = 'Enter the full name.';
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    try {
      const body = { ...form, person_id: form.person_id.trim() };
      const saved = editing ? await api.people.update(person.person_id, body) : await api.people.create(body);
      toast.success(editing ? 'Changes saved.' : `${saved.full_name} added. Next: register their face.`);
      onSaved(saved, !editing);
    } catch (err) {
      if (err.code === 'duplicate_id') setErrors({ person_id: 'This ID is already in use. Choose a different ID.' });
      else if (/person_id|ID/i.test(err.message) && err.status === 422) setErrors({ person_id: err.message });
      else setErrors({ form: err.message });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal open={open} onClose={onClose} title={editing ? 'Edit person' : 'Add person'} closeDisabled={busy}
      footer={<>
        <button type="button" className="btn-secondary" onClick={onClose} disabled={busy}>Cancel</button>
        <button type="submit" form="person-form" className="btn-primary" disabled={busy}>{busy && <Spinner className="h-4 w-4 !text-white" />}{editing ? 'Save changes' : 'Add person'}</button>
      </>}>
      <form id="person-form" onSubmit={submit} className="grid gap-4 sm:grid-cols-2" noValidate>
        {errors.form && <div role="alert" className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700 sm:col-span-2">{errors.form}</div>}
        <Field label="ID *" htmlFor="pf-id" error={errors.person_id} hint="Student / employee number. Cannot be changed later.">
          <input id="pf-id" className="input" value={form.person_id} onChange={set('person_id')} disabled={editing} maxLength={64} autoFocus={!editing} />
        </Field>
        <Field label="Type" htmlFor="pf-type">
          <select id="pf-type" className="input" value={form.type} onChange={set('type')}>
            <option value="student">Student</option><option value="employee">Employee</option>
          </select>
        </Field>
        <div className="sm:col-span-2">
          <Field label="Full name *" htmlFor="pf-name" error={errors.full_name}><input id="pf-name" className="input" value={form.full_name} onChange={set('full_name')} maxLength={120} autoFocus={editing} /></Field>
        </div>
        <Field label="Department" htmlFor="pf-dept"><input id="pf-dept" className="input" value={form.department} onChange={set('department')} maxLength={80} /></Field>
        <Field label="Class / section" htmlFor="pf-class"><input id="pf-class" className="input" value={form.class_name} onChange={set('class_name')} maxLength={80} /></Field>
        <Field label="Email" htmlFor="pf-email"><input id="pf-email" type="email" className="input" value={form.email} onChange={set('email')} maxLength={254} /></Field>
        <Field label="Phone" htmlFor="pf-phone"><input id="pf-phone" type="tel" className="input" value={form.phone} onChange={set('phone')} maxLength={32} /></Field>
        <div className="sm:col-span-2">
          <Field label="Notes" htmlFor="pf-notes"><textarea id="pf-notes" rows={2} className="input" value={form.notes} onChange={set('notes')} maxLength={500} /></Field>
        </div>
      </form>
    </Modal>
  );
}

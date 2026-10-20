import { useState } from 'react';
import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { CalendarCheck, LayoutDashboard, LogOut, Menu, ScanFace, Settings, ShieldCheck, Users, X } from 'lucide-react';
import { useAuth } from '../context/AuthContext.jsx';
import { formatDate, initials, todayISO } from '../lib/format.js';

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/people', label: 'People', icon: Users },
  { to: '/live', label: 'Live Camera', icon: ScanFace },
  { to: '/attendance', label: 'Attendance', icon: CalendarCheck },
  { to: '/settings', label: 'Settings', icon: Settings },
];
const TITLES = { '/': 'Dashboard', '/people': 'People', '/live': 'Live Camera', '/attendance': 'Attendance', '/settings': 'Settings' };

function SidebarContent({ onNavigate }) {
  return (
    <div className="flex h-full flex-col bg-slate-900 text-slate-300">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600 text-white"><ShieldCheck className="h-5 w-5" /></div>
        <div>
          <p className="font-semibold leading-tight text-white">Smart Attendance</p>
          <p className="text-xs text-slate-400">Face recognition</p>
        </div>
      </div>
      <nav className="flex-1 space-y-1 px-3 py-2">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} onClick={onNavigate}
            className={({ isActive }) => `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition ${isActive ? 'bg-slate-800 text-white' : 'hover:bg-slate-800/60 hover:text-white'}`}>
            <Icon className="h-5 w-5" />{label}
          </NavLink>
        ))}
      </nav>
      <p className="px-5 py-4 text-xs text-slate-500">Face recognition can be fooled by photos or screens. Review attendance records regularly.</p>
    </div>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const { pathname } = useLocation();
  const title = TITLES[pathname] || 'Smart Attendance';

  return (
    <div className="min-h-screen">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-64 lg:block"><SidebarContent /></aside>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={() => setOpen(false)} />
          <div className="relative h-full w-64">
            <SidebarContent onNavigate={() => setOpen(false)} />
            <button className="absolute right-2 top-3 rounded-md p-1 text-slate-300 hover:bg-slate-800" onClick={() => setOpen(false)} aria-label="Close menu"><X className="h-5 w-5" /></button>
          </div>
        </div>
      )}

      <div className="lg:pl-64">
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur sm:px-6">
          <div className="flex items-center gap-3">
            <button className="rounded-md p-2 text-slate-600 hover:bg-slate-100 lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu"><Menu className="h-5 w-5" /></button>
            <div>
              <p className="font-semibold text-slate-900">{title}</p>
              <p className="hidden text-xs text-slate-500 sm:block">{formatDate(todayISO())}</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="hidden text-right sm:block">
              <p className="text-sm font-medium text-slate-800">{user?.display_name}</p>
              <p className="text-xs text-slate-500">Administrator</p>
            </div>
            <div className="flex h-9 w-9 items-center justify-center rounded-full bg-indigo-100 text-sm font-semibold text-indigo-700" aria-hidden="true">{initials(user?.display_name)}</div>
            <button className="btn-secondary btn-sm" onClick={logout}><LogOut className="h-4 w-4" /><span className="hidden sm:inline">Sign out</span></button>
          </div>
        </header>
        <main className="mx-auto max-w-7xl px-4 py-6 sm:px-6"><Outlet /></main>
      </div>
    </div>
  );
}

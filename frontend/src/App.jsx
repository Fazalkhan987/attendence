import { Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout.jsx';
import ProtectedRoute from './components/ProtectedRoute.jsx';
import Attendance from './pages/Attendance.jsx';
import Dashboard from './pages/Dashboard.jsx';
import LiveRecognition from './pages/LiveRecognition.jsx';
import Login from './pages/Login.jsx';
import People from './pages/People.jsx';
import SettingsPage from './pages/Settings.jsx';

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="people" element={<People />} />
          <Route path="live" element={<LiveRecognition />} />
          <Route path="attendance" element={<Attendance />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

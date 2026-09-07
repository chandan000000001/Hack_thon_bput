import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import MainLayout from './components/layout/MainLayout';
import ProtectedRoute from './components/layout/ProtectedRoute';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import PhishingAnalysis from './pages/PhishingAnalysis';
import UrlAnalysis from './pages/UrlAnalysis';
import ImpersonationAnalysis from './pages/ImpersonationAnalysis';
import DeepfakeAnalysis from './pages/DeepfakeAnalysis';
import AccountTakeover from './pages/AccountTakeover';
import NetworkThreats from './pages/NetworkThreats';
import Alerts from './pages/Alerts';
import AlertDetail from './pages/AlertDetail';
import Incidents from './pages/Incidents';
import IncidentDetail from './pages/IncidentDetail';
import ResponseActions from './pages/ResponseActions';
import AuditLogs from './pages/AuditLogs';
import Reports from './pages/Reports';
import Settings from './pages/Settings';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            <ProtectedRoute>
              <MainLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/phishing" element={<PhishingAnalysis />} />
          <Route path="/url-analysis" element={<UrlAnalysis />} />
          <Route path="/impersonation" element={<ImpersonationAnalysis />} />
          <Route path="/deepfake" element={<DeepfakeAnalysis />} />
          <Route path="/account-takeover" element={<AccountTakeover />} />
          <Route path="/network-threats" element={<NetworkThreats />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/alerts/:id" element={<AlertDetail />} />
          <Route path="/incidents" element={<Incidents />} />
          <Route path="/incidents/:id" element={<IncidentDetail />} />
          <Route path="/response-actions" element={<ResponseActions />} />
          <Route path="/audit-logs" element={<AuditLogs />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/settings" element={<Settings />} />
        </Route>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  );
}

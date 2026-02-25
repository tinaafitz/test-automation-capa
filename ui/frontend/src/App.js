import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import CAPADashboard from './pages/CAPADashboard';
import MinikubeDashboard from './pages/MinikubeDashboard';
import { AppProvider } from './store/AppContext';
import ToastNotifications from './components/ToastNotifications';

function App() {
  return (
    <AppProvider>
      <Router>
        <div className="min-h-screen bg-gray-50">
          <ToastNotifications />
          <Routes>
            <Route path="/" element={<Navigate to="/mce" replace />} />
            <Route path="/mce" element={<CAPADashboard />} />
            <Route path="/minikube" element={<MinikubeDashboard />} />
          </Routes>
        </div>
      </Router>
    </AppProvider>
  );
}

export default App;

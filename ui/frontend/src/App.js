import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import MainDashboard from './pages/MainDashboard';
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
            <Route path="/" element={<MainDashboard />} />
            <Route path="/mce" element={<CAPADashboard />} />
            <Route path="/minikube" element={<MinikubeDashboard />} />
          </Routes>
        </div>
      </Router>
    </AppProvider>
  );
}

export default App;

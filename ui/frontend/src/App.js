import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import CAPADashboard from './pages/CAPADashboard';
import MinikubeDashboard from './pages/MinikubeDashboard';

function App() {
  return (
    <Router>
      <div className="min-h-screen bg-gray-50">
        <Routes>
          <Route path="/" element={<Navigate to="/mce" replace />} />
          <Route path="/mce" element={<CAPADashboard />} />
          <Route path="/minikube" element={<MinikubeDashboard />} />
        </Routes>
      </div>
    </Router>
  );
}

export default App;

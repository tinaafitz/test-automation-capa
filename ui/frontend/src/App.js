import React from 'react';
import { BrowserRouter as Router, Routes, Route, useLocation } from 'react-router-dom';
import MainDashboard from './pages/MainDashboard';
import CAPADashboard from './pages/CAPADashboard';
import MinikubeDashboard from './pages/MinikubeDashboard';
import AWSUsageDashboard from './pages/AWSUsageDashboard';
import AgentDashboard from './pages/AgentDashboard';
import PresentationMode from './pages/PresentationMode';
import { AIAssistantChat } from './components/chat/AIAssistantChat';
import { AppProvider } from './store/AppContext';
import ToastNotifications from './components/ToastNotifications';

function AppContent() {
  const location = useLocation();
  const theme = location.pathname.startsWith('/minikube') ? 'minikube' : 'mce';
  const hideBubble = location.pathname === '/tour';

  return (
    <div className="min-h-screen bg-gray-50">
      <ToastNotifications />
      <Routes>
        <Route path="/" element={<MainDashboard />} />
        <Route path="/mce" element={<CAPADashboard />} />
        <Route path="/minikube" element={<MinikubeDashboard />} />
        <Route path="/aws-usage" element={<AWSUsageDashboard />} />
        <Route path="/agents" element={<AgentDashboard />} />
        <Route path="/tour" element={<PresentationMode />} />
      </Routes>
      {!hideBubble && <AIAssistantChat theme={theme} />}
    </div>
  );
}

function App() {
  return (
    <AppProvider>
      <Router>
        <AppContent />
      </Router>
    </AppProvider>
  );
}

export default App;

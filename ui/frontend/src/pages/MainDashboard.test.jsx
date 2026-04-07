/**
 * Tests for MainDashboard page component.
 */

import React from 'react';
import { render, screen, act } from '@testing-library/react';

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
}));

jest.mock('@heroicons/react/24/outline', () => ({
  Bars3Icon: (props) => <svg data-testid="bars-icon" {...props} />,
  ClockIcon: (props) => <svg data-testid="clock-icon" {...props} />,
  ArrowPathIcon: (props) => <svg data-testid="arrow-path" {...props} />,
  TrashIcon: (props) => <svg data-testid="trash-icon" {...props} />,
  ChevronUpDownIcon: (props) => <svg data-testid="chevron-ud" {...props} />,
  ChevronDownIcon: (props) => <svg data-testid="chevron-down" {...props} />,
  ChevronRightIcon: (props) => <svg data-testid="chevron-right" {...props} />,
  BellIcon: (props) => <svg data-testid="bell-icon" {...props} />,
}));

jest.mock('../components/charts/JenkinsTestResultsTrend', () => () => (
  <div data-testid="jenkins-trend">Jenkins</div>
));

jest.mock('../components/charts/GitHubRepoActivity', () => () => (
  <div data-testid="github-activity">GitHub</div>
));

jest.mock('../components/charts/AWSQuotaWidget', () => () => (
  <div data-testid="aws-quota">AWS Quota</div>
));

jest.mock('../components/chat/AIAssistantChat', () => ({
  AIAssistantChat: () => <div data-testid="ai-chat">AI Chat</div>,
}));

jest.mock('../components/NotificationSettingsInline', () => () => (
  <div data-testid="notifications">Notifications</div>
));

jest.mock('./AWSUsageDashboard', () => () => (
  <div data-testid="aws-dashboard">AWS Dashboard</div>
));

jest.mock('../store/AppContext', () => ({
  useRecentOperationsContext: () => ({
    operations: [],
    addOperation: jest.fn(),
    removeOperation: jest.fn(),
    clearAll: jest.fn(),
  }),
}));

jest.mock('../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
  API_ENDPOINTS: { ROSA_CLUSTERS: '/api/rosa/clusters' },
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

// Clear sessionStorage cache
sessionStorage.removeItem('rosa-clusters-cache');

import MainDashboard from './MainDashboard';

beforeEach(() => {
  mockFetch.mockReset();
  sessionStorage.removeItem('rosa-clusters-cache');
  mockFetch.mockImplementation((url) => {
    if (url.includes('/api/credentials')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ credentials: { minikubeCluster: 'test' } }),
      });
    }
    if (url.includes('/api/rosa/clusters')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, clusters: [] }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ success: true, resources: [] }),
    });
  });
});

describe('MainDashboard', () => {
  it('renders dashboard widgets', async () => {
    await act(async () => {
      render(<MainDashboard />);
    });
    expect(screen.getByTestId('jenkins-trend')).toBeInTheDocument();
    expect(screen.getByTestId('github-activity')).toBeInTheDocument();
    expect(screen.getByTestId('aws-quota')).toBeInTheDocument();
  });

  it('fetches cluster data on mount', async () => {
    await act(async () => {
      render(<MainDashboard />);
    });
    expect(mockFetch).toHaveBeenCalled();
  });

  it('renders without crashing', async () => {
    await act(async () => {
      render(<MainDashboard />);
    });
    expect(document.body).toBeTruthy();
  });
});

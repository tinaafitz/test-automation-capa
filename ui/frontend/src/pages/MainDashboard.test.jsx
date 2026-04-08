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

  it('renders sidebar with CAPA Automation title', async () => {
    await act(async () => {
      render(<MainDashboard />);
    });
    expect(screen.getByText('CAPA Automation')).toBeInTheDocument();
  });

  it('renders navigation menu items', async () => {
    await act(async () => {
      render(<MainDashboard />);
    });
    expect(screen.getByText('Notifications')).toBeInTheDocument();
    expect(screen.getByText('AI Assistant')).toBeInTheDocument();
  });

  it('renders cluster section heading', async () => {
    await act(async () => {
      render(<MainDashboard />);
    });
    expect(screen.getAllByText(/Clusters/i).length).toBeGreaterThan(0);
  });

  it('renders recent tasks section', async () => {
    await act(async () => {
      render(<MainDashboard />);
    });
    expect(screen.getByText(/Recent Tasks/i)).toBeInTheDocument();
  });

  it('shows empty cluster state when no clusters', async () => {
    await act(async () => {
      render(<MainDashboard />);
    });
    // Wait for fetch to resolve and show empty state
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(screen.getByText(/No ROSA HCP clusters found/i)).toBeInTheDocument();
  });

  it('displays clusters when fetch returns data', async () => {
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
          json: async () => ({
            success: true,
            clusters: [
              { name: 'test-cluster-1', status: 'ready', version: '4.17', region: 'us-east-1', created: '2024-01-01T00:00:00Z' },
              { name: 'test-cluster-2', status: 'installing', version: '4.18', region: 'us-west-2', created: '2024-02-01T00:00:00Z' },
            ],
          }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, resources: [] }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<MainDashboard />);
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(screen.getByText('test-cluster-1')).toBeInTheDocument();
    expect(screen.getByText('test-cluster-2')).toBeInTheDocument();
  });

  it('shows error state when fetch fails', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/credentials')) {
        return Promise.reject(new Error('Network error'));
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<MainDashboard />);
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(screen.getByText(/Failed to load clusters/i)).toBeInTheDocument();
  });

  it('labels minikube clusters correctly', async () => {
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
          json: async () => ({
            success: true,
            clusters: [
              { name: 'mk-cluster', status: 'ready', version: '4.17', region: 'us-east-1' },
            ],
          }),
        });
      }
      if (url.includes('/api/minikube/get-active-resources')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            resources: [{ type: 'RosaControlPlane', name: 'mk-cluster' }],
          }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });

    await act(async () => {
      render(<MainDashboard />);
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(screen.getByText('mk-cluster')).toBeInTheDocument();
    expect(screen.getByText('Minikube')).toBeInTheDocument();
  });

  it('renders environment menu button', async () => {
    await act(async () => {
      render(<MainDashboard />);
    });
    expect(screen.getByTitle('Environment Menu')).toBeInTheDocument();
  });

  it('opens environment menu on click', async () => {
    const { fireEvent } = require('@testing-library/react');
    await act(async () => {
      render(<MainDashboard />);
    });
    const menuBtn = screen.getByTitle('Environment Menu');
    await act(async () => {
      fireEvent.click(menuBtn);
    });
    expect(screen.getByText('A Guided Tour')).toBeInTheDocument();
    expect(screen.getByText('MCE Environment')).toBeInTheDocument();
    expect(screen.getByText('Minikube Environment')).toBeInTheDocument();
  });

  it('shows At a Glance in environment menu', async () => {
    const { fireEvent } = require('@testing-library/react');
    await act(async () => {
      render(<MainDashboard />);
    });
    const menuBtn = screen.getByTitle('Environment Menu');
    await act(async () => {
      fireEvent.click(menuBtn);
    });
    expect(screen.getAllByText('At a Glance').length).toBeGreaterThan(0);
  });

  it('renders with recent operations from context', async () => {
    await act(async () => {
      render(<MainDashboard />);
    });
    // Even with empty operations, the section should render
    expect(screen.getByText(/Recent Tasks/i)).toBeInTheDocument();
  });

  it('renders refresh button for tasks', async () => {
    await act(async () => {
      render(<MainDashboard />);
    });
    // Should have refresh buttons (for clusters and tasks)
    const refreshButtons = screen.getAllByTestId('arrow-path');
    expect(refreshButtons.length).toBeGreaterThan(0);
  });

  it('renders jenkins and github sections', async () => {
    await act(async () => {
      render(<MainDashboard />);
    });
    expect(screen.getByText('Jenkins')).toBeInTheDocument();
    expect(screen.getByText('GitHub')).toBeInTheDocument();
  });
});

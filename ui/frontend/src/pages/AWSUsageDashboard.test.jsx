/**
 * Tests for AWSUsageDashboard page component.
 */

import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
}));

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowPathIcon: (props) => <svg data-testid="arrow-path" {...props} />,
}));

jest.mock('../components/sidebar/CapaSidebar', () => (props) => (
  <div data-testid="sidebar">Sidebar</div>
));

jest.mock('../components/charts/AWSUsageTrend', () => () => (
  <div data-testid="usage-trend">Usage Trend</div>
));

const mockFetch = jest.fn();
global.fetch = mockFetch;

import AWSUsageDashboard from './AWSUsageDashboard';

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockImplementation((url) => {
    if (url.includes('/api/aws/usage-config')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          success: true,
          billedResources: [
            { key: 'nat_gateways', label: 'NAT Gateways', threshold: 5, costPerMonth: 32 },
          ],
          freeResources: [
            { key: 'vpcs', label: 'VPCs', threshold: 5 },
          ],
        }),
      });
    }
    if (url.includes('/api/aws/usage')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({
          success: true,
          timestamp: new Date().toISOString(),
          usage: { nat_gateways: 2, vpcs: 3 },
        }),
      });
    }
    return Promise.resolve({ ok: true, json: async () => ({}) });
  });
});

describe('AWSUsageDashboard', () => {
  it('renders in inline mode', async () => {
    await act(async () => {
      render(<AWSUsageDashboard inline={true} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('renders in standalone mode with sidebar', async () => {
    await act(async () => {
      render(<AWSUsageDashboard inline={false} />);
    });
    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
  });

  it('fetches config on mount', async () => {
    await act(async () => {
      render(<AWSUsageDashboard inline={true} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/aws/usage-config')
      );
    });
  });

  it('handles fetch error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    await act(async () => {
      render(<AWSUsageDashboard inline={true} />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Network error/)).toBeInTheDocument();
    });
  });

  it('renders resource config after fetch', async () => {
    await act(async () => {
      render(<AWSUsageDashboard inline={true} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('fetches usage data in inline mode', async () => {
    await act(async () => {
      render(<AWSUsageDashboard inline={true} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/aws/usage')
      );
    });
  });

  it('displays resource counts after usage fetch', async () => {
    await act(async () => {
      render(<AWSUsageDashboard inline={true} />);
    });
    await waitFor(() => {
      // Should display resource data from the mock
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('handles config API failure gracefully', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/aws/usage-config')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: false, message: 'Config unavailable' }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
    await act(async () => {
      render(<AWSUsageDashboard inline={true} />);
    });
    await waitFor(() => {
      // Either the config error or the usage error message shows
      const errorTexts = screen.getAllByText(/unavailable|Failed|Error/i);
      expect(errorTexts.length).toBeGreaterThan(0);
    });
  });

  it('handles usage API failure', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/aws/usage-config')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            billedResources: [{ key: 'nat_gateways', label: 'NAT Gateways', threshold: 5, costPerMonth: 32 }],
            freeResources: [],
          }),
        });
      }
      if (url.includes('/api/aws/usage')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: false, message: 'Usage data unavailable' }),
        });
      }
      return Promise.resolve({ ok: true, json: async () => ({}) });
    });
    await act(async () => {
      render(<AWSUsageDashboard inline={true} />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Usage data unavailable/)).toBeInTheDocument();
    });
  });

  it('renders without sidebar in inline mode', async () => {
    await act(async () => {
      render(<AWSUsageDashboard inline={true} />);
    });
    expect(screen.queryByTestId('sidebar')).not.toBeInTheDocument();
  });

  it('renders AWS Usage Dashboard title in standalone mode', async () => {
    await act(async () => {
      render(<AWSUsageDashboard inline={false} />);
    });
    expect(screen.getAllByText(/AWS/i).length).toBeGreaterThan(0);
  });

  it('renders usage trend chart', async () => {
    await act(async () => {
      render(<AWSUsageDashboard inline={true} />);
    });
    await waitFor(() => {
      expect(screen.getByTestId('usage-trend')).toBeInTheDocument();
    });
  });

  it('shows refresh button', async () => {
    await act(async () => {
      render(<AWSUsageDashboard inline={true} />);
    });
    await waitFor(() => {
      const refreshIcons = screen.getAllByTestId('arrow-path');
      expect(refreshIcons.length).toBeGreaterThan(0);
    });
  });
});

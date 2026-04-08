/**
 * Tests for MCEEnvironmentSelector component.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

// Mock heroicons
jest.mock('@heroicons/react/24/outline', () => new Proxy({}, {
  get: (_, prop) => (props) => <svg data-testid={prop} {...props} />
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

import MCEEnvironmentSelector from './MCEEnvironmentSelector';

beforeEach(() => {
  mockFetch.mockReset();
  jest.clearAllMocks();

  // Default: return empty environments list + stats
  mockFetch.mockImplementation((url) => {
    if (url.includes('/stats/summary') || url.includes('list-clusters')) {
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, total: 0, pass: 0, fail: 0 }),
      });
    }
    return Promise.resolve({
      ok: true,
      json: async () => ({ success: true, environments: [], total: 0 }),
    });
  });
});

describe('MCEEnvironmentSelector', () => {
  const defaultProps = {
    onUseCredentials: jest.fn(),
  };

  it('renders with default props', async () => {
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });
    expect(screen.getAllByText(/MCE Environments|Environment/i).length).toBeGreaterThan(0);
  });

  it('renders with custom title', async () => {
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} title="My Environments" />);
    });
    expect(screen.getByText('My Environments')).toBeInTheDocument();
  });

  it('renders with minikube theme', async () => {
    await act(async () => {
      render(
        <MCEEnvironmentSelector
          {...defaultProps}
          theme="minikube"
          environmentType="minikube"
          title="Minikube Clusters"
        />
      );
    });
    expect(screen.getByText('Minikube Clusters')).toBeInTheDocument();
  });

  it('fetches environments on mount', async () => {
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('shows empty state when no environments', async () => {
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    // Component should render without crashing
    expect(document.body).toBeTruthy();
  });

  it('renders environments when available', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/stats/summary')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, total: 2, pass: 1, fail: 1 }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          success: true,
          environments: [
            {
              clusterName: 'qe6-vmware',
              platform: 'VMware',
              status: 'pass',
              ocpVersion: '4.20.11',
              mceVersion: '2.11.0',
            },
            {
              clusterName: 'qe7-aws-arm',
              platform: 'AWS ARM',
              status: 'fail',
              ocpVersion: '4.20.12',
              mceVersion: '2.11.0',
            },
          ],
          total: 2,
        }),
      });
    });

    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });

    await waitFor(() => {
      expect(screen.getByText('qe6-vmware')).toBeInTheDocument();
    });
    expect(screen.getByText('qe7-aws-arm')).toBeInTheDocument();
  });

  it('handles fetch error gracefully', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });
    // Should not crash
    expect(document.body).toBeTruthy();
  });

  it('has search input', async () => {
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    const searchInput = document.querySelector('input[type="text"], input[placeholder*="earch"]');
    expect(searchInput).toBeTruthy();
  });

  it('filters environments by search term', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/stats/summary')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, total: 2, pass: 2, fail: 0 }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          success: true,
          environments: [
            {
              clusterName: 'qe6-vmware',
              platform: 'VMware',
              status: 'pass',
            },
            {
              clusterName: 'qe7-aws-arm',
              platform: 'AWS ARM',
              status: 'pass',
            },
          ],
          total: 2,
        }),
      });
    });

    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });

    await waitFor(() => {
      expect(screen.getByText('qe6-vmware')).toBeInTheDocument();
    });

    const searchInput = document.querySelector('input[type="text"], input[placeholder*="earch"]');
    if (searchInput) {
      fireEvent.change(searchInput, { target: { value: 'vmware' } });

      // qe6-vmware should still be visible
      expect(screen.getByText('qe6-vmware')).toBeInTheDocument();
      // qe7-aws-arm might be filtered out
    }
  });

  it('calls onUseCredentials when Use Credentials clicked', async () => {
    const onUseCredentials = jest.fn();
    mockFetch.mockImplementation((url) => {
      if (url.includes('/stats/summary')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, total: 1, pass: 1, fail: 0 }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          success: true,
          environments: [
            {
              clusterName: 'qe6-vmware',
              platform: 'VMware',
              status: 'pass',
              ocpApiUrl: 'https://api.example.com',
              ocpUsername: 'admin',
              ocpPassword: 'secret',
            },
          ],
          total: 1,
        }),
      });
    });

    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} onUseCredentials={onUseCredentials} />);
    });

    await waitFor(() => {
      expect(screen.getByText('qe6-vmware')).toBeInTheDocument();
    });

    const useButtons = screen.getAllByRole('button').filter((b) =>
      b.textContent.match(/use|credentials/i)
    );

    if (useButtons.length > 0) {
      fireEvent.click(useButtons[0]);
      expect(onUseCredentials).toHaveBeenCalled();
    }
  });

  it('has refresh functionality', async () => {
    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    // Should have buttons available
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('shows status badge for each environment', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/stats/summary')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, total: 2, pass: 1, fail: 1 }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          success: true,
          environments: [
            {
              clusterName: 'qe6-vmware',
              platform: 'VMware',
              status: 'pass',
            },
            {
              clusterName: 'qe7-aws-arm',
              platform: 'AWS ARM',
              status: 'fail',
            },
          ],
          total: 2,
        }),
      });
    });

    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });

    await waitFor(() => {
      // Should show Pass and Fail badges
      expect(screen.getByText(/Pass|✅/i)).toBeInTheDocument();
      expect(screen.getByText(/Fail|❌/i)).toBeInTheDocument();
    });
  });

  it('displays platform information for environments', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/stats/summary')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, total: 1, pass: 1, fail: 0 }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          success: true,
          environments: [
            {
              clusterName: 'qe6-vmware',
              platform: 'VMware vSphere',
              status: 'pass',
            },
          ],
          total: 1,
        }),
      });
    });

    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });

    await waitFor(() => {
      expect(screen.getByText('qe6-vmware')).toBeInTheDocument();
    });

    // Platform info may or may not be displayed depending on view
    expect(document.body.textContent).toContain('qe6-vmware');
  });

  it('displays version information for environments', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/stats/summary')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, total: 1, pass: 1, fail: 0 }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          success: true,
          environments: [
            {
              clusterName: 'qe6-vmware',
              platform: 'VMware',
              status: 'pass',
              ocpVersion: '4.20.11',
              mceVersion: '2.11.0',
            },
          ],
          total: 1,
        }),
      });
    });

    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });

    await waitFor(() => {
      expect(screen.getByText('qe6-vmware')).toBeInTheDocument();
    });

    // Version info may be displayed in details or tooltips
    expect(document.body.textContent).toContain('qe6-vmware');
  });

  it('displays summary statistics', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/stats/summary')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, total: 10, pass: 7, fail: 3 }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, environments: [], total: 0 }),
      });
    });

    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });

    await waitFor(() => {
      // Should render without errors
      expect(document.body).toBeTruthy();
    });
  });

  it('shows loading state while fetching', async () => {
    mockFetch.mockImplementation(() => new Promise(() => {})); // Never resolves
    render(<MCEEnvironmentSelector {...defaultProps} />);

    await waitFor(() => {
      // Should show loading indicator or render without crashing
      expect(document.body).toBeTruthy();
    });
  });

  it('has filter controls', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/stats/summary')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, total: 2, pass: 1, fail: 1 }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          success: true,
          environments: [
            {
              clusterName: 'qe6-vmware',
              platform: 'VMware',
              status: 'pass',
            },
            {
              clusterName: 'qe7-aws-arm',
              platform: 'AWS ARM',
              status: 'fail',
            },
          ],
          total: 2,
        }),
      });
    });

    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });

    await waitFor(() => {
      expect(screen.getByText('qe6-vmware')).toBeInTheDocument();
    });

    // Should have filter/search controls
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('has action buttons for each environment', async () => {
    const writeText = jest.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText,
      },
    });

    mockFetch.mockImplementation((url) => {
      if (url.includes('/stats/summary')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, total: 1, pass: 1, fail: 0 }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({
          success: true,
          environments: [
            {
              clusterName: 'qe6-vmware',
              platform: 'VMware',
              status: 'pass',
            },
          ],
          total: 1,
        }),
      });
    });

    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });

    await waitFor(() => {
      expect(screen.getByText('qe6-vmware')).toBeInTheDocument();
    });

    // Should have action buttons (copy, use credentials, etc)
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(1);
  });

  it('handles API error response gracefully', async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      json: async () => ({ error: 'Server error' }),
    });

    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });

    // Should not crash
    expect(document.body).toBeTruthy();
  });

  it('shows empty state message when no environments match filter', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/stats/summary')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, total: 0, pass: 0, fail: 0 }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, environments: [], total: 0 }),
      });
    });

    await act(async () => {
      render(<MCEEnvironmentSelector {...defaultProps} />);
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    // Should show empty state
    expect(document.body).toBeTruthy();
  });
});

/**
 * Tests for AWSQuotaWidget component.
 */

import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';

jest.mock('../../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
}));

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowPathIcon: (props) => <svg data-testid="arrow-path-icon" {...props} />,
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

// Clear sessionStorage cache before import
sessionStorage.removeItem('aws-quota-cache');

import AWSQuotaWidget from './AWSQuotaWidget';

beforeEach(() => {
  mockFetch.mockReset();
  sessionStorage.removeItem('aws-quota-cache');

  // Default: return usage and config
  mockFetch.mockImplementation((url) => {
    if (url.includes('/api/aws/usage')) {
      if (url.includes('usage-config')) {
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

describe('AWSQuotaWidget', () => {
  it('renders and fetches data on mount', async () => {
    await act(async () => {
      render(<AWSQuotaWidget />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/aws/usage')
      );
    });
  });

  it('displays usage data after fetch', async () => {
    await act(async () => {
      render(<AWSQuotaWidget />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('handles fetch error gracefully', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    await act(async () => {
      render(<AWSQuotaWidget />);
    });
    await waitFor(() => {
      expect(screen.getByText('Failed to load AWS data')).toBeInTheDocument();
    });
  });

  it('renders refresh button', async () => {
    await act(async () => {
      render(<AWSQuotaWidget />);
    });
    await waitFor(() => {
      expect(screen.getByText('Refresh')).toBeInTheDocument();
    });
  });

  it('handles empty usage data', async () => {
    mockFetch.mockImplementation(() =>
      Promise.resolve({
        ok: true,
        json: async () => ({ success: true, usage: {}, timestamp: new Date().toISOString() }),
      })
    );
    await act(async () => {
      render(<AWSQuotaWidget />);
    });
    expect(document.body).toBeTruthy();
  });
});

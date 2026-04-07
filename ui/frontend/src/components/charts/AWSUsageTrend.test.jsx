/**
 * Tests for AWSUsageTrend component.
 */

import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';

jest.mock('@heroicons/react/24/outline', () => ({
  ArrowPathIcon: (props) => <svg data-testid="arrow-path-icon" {...props} />,
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

import AWSUsageTrend from './AWSUsageTrend';

beforeEach(() => {
  mockFetch.mockReset();
});

describe('AWSUsageTrend', () => {
  it('renders and fetches data on mount', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        trend: [],
        resource_keys: [],
      }),
    });
    await act(async () => {
      render(<AWSUsageTrend />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/aws/usage-trend')
      );
    });
  });

  it('renders trend data with resource keys', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        trend: [
          { date: '2026-04-01', nat_gateways: 2, vpcs: 3 },
          { date: '2026-04-02', nat_gateways: 3, vpcs: 3 },
        ],
        resource_keys: ['nat_gateways', 'vpcs'],
      }),
    });
    await act(async () => {
      render(<AWSUsageTrend />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('handles fetch error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    await act(async () => {
      render(<AWSUsageTrend />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Failed to fetch trend data/)).toBeInTheDocument();
    });
  });

  it('handles API error response', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: false,
        message: 'No data available',
      }),
    });
    await act(async () => {
      render(<AWSUsageTrend />);
    });
    await waitFor(() => {
      expect(screen.getByText(/No data available/)).toBeInTheDocument();
    });
  });

  it('renders empty state', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        trend: [],
        resource_keys: [],
      }),
    });
    await act(async () => {
      render(<AWSUsageTrend />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });
});

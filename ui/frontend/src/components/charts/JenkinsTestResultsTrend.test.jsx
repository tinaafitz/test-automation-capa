/**
 * Tests for JenkinsTestResultsTrend component.
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

sessionStorage.removeItem('jenkins-trend-cache');

import JenkinsTestResultsTrend from './JenkinsTestResultsTrend';

beforeEach(() => {
  mockFetch.mockReset();
  sessionStorage.removeItem('jenkins-trend-cache');
});

describe('JenkinsTestResultsTrend', () => {
  it('renders header', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, trend: [] }),
    });
    await act(async () => {
      render(<JenkinsTestResultsTrend />);
    });
    expect(screen.getByText('Jenkins Test Results')).toBeInTheDocument();
  });

  it('fetches data on mount', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, trend: [] }),
    });
    await act(async () => {
      render(<JenkinsTestResultsTrend />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/jenkins/test-results-trend'),
        expect.any(Object)
      );
    });
  });

  it('renders trend data', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        trend: [
          { buildNumber: 1, totalCount: 10, passCount: 8, failCount: 2, skipCount: 0 },
          { buildNumber: 2, totalCount: 12, passCount: 10, failCount: 1, skipCount: 1 },
        ],
      }),
    });
    await act(async () => {
      render(<JenkinsTestResultsTrend />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('handles fetch error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    await act(async () => {
      render(<JenkinsTestResultsTrend />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Network error/)).toBeInTheDocument();
    });
  });

  it('has refresh button', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, trend: [] }),
    });
    await act(async () => {
      render(<JenkinsTestResultsTrend />);
    });
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });
});

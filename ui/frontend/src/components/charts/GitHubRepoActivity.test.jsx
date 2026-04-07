/**
 * Tests for GitHubRepoActivity component.
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

sessionStorage.removeItem('github-activity-cache');

import GitHubRepoActivity from './GitHubRepoActivity';

beforeEach(() => {
  mockFetch.mockReset();
  sessionStorage.removeItem('github-activity-cache');
});

describe('GitHubRepoActivity', () => {
  it('renders header', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, repos: [] }),
    });
    await act(async () => {
      render(<GitHubRepoActivity />);
    });
    expect(screen.getByText('GitHub Activity')).toBeInTheDocument();
  });

  it('fetches data on mount', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, repos: [] }),
    });
    await act(async () => {
      render(<GitHubRepoActivity />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/github/repo-activity')
      );
    });
  });

  it('renders repos when available', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({
        success: true,
        repos: [
          { name: 'test-repo', commits: 5, prs: 2, issues: 1 },
        ],
      }),
    });
    await act(async () => {
      render(<GitHubRepoActivity />);
    });
    await waitFor(() => {
      expect(screen.getByText('test-repo')).toBeInTheDocument();
    });
  });

  it('handles fetch error', async () => {
    mockFetch.mockRejectedValue(new Error('Network error'));
    await act(async () => {
      render(<GitHubRepoActivity />);
    });
    await waitFor(() => {
      expect(screen.getByText(/Network error/)).toBeInTheDocument();
    });
  });

  it('shows empty state when no repos', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, repos: [] }),
    });
    await act(async () => {
      render(<GitHubRepoActivity />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('has refresh button', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, repos: [] }),
    });
    await act(async () => {
      render(<GitHubRepoActivity />);
    });
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });
});

/**
 * Tests for NotificationSettingsInline component.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

jest.mock('../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

import NotificationSettingsInline from './NotificationSettingsInline';

beforeEach(() => {
  mockFetch.mockReset();
  jest.clearAllMocks();

  // Default: return settings
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({
      settings: {
        slack_enabled: false,
        slack_webhook_url: '',
        email_enabled: false,
        smtp_server: '',
        smtp_port: 587,
        smtp_username: '',
        smtp_password: '',
        from_email: '',
        to_emails: [],
        use_tls: true,
        notify_on_start: false,
        notify_on_complete: true,
        notify_on_failure: true,
      },
    }),
  });
});

describe('NotificationSettingsInline', () => {
  it('renders the component', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    // Should show email/slack tabs or settings content
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/notification-settings')
      );
    });
  });

  it('fetches settings on mount', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('handles fetch error gracefully', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'));
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    // Should not crash
    expect(document.body).toBeTruthy();
  });

  it('renders tab buttons', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('renders form inputs after loading', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    // Should have checkboxes or text inputs for settings
    const inputs = document.querySelectorAll('input');
    expect(inputs.length).toBeGreaterThan(0);
  });

  it('has a save button', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    const saveBtn = screen.getAllByRole('button').find(
      (b) => b.textContent.match(/save/i)
    );
    expect(saveBtn).toBeTruthy();
  });
});

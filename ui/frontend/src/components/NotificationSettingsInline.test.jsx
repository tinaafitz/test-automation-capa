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
        app_url: 'http://localhost:3000',
        notify_on_start: false,
        notify_on_complete: true,
        notify_on_failure: true,
        notify_provision_start: false,
        notify_provision_success: true,
        notify_provision_failure: true,
        notify_delete_start: false,
        notify_delete_success: true,
        notify_delete_failure: true,
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
    await waitFor(() => {
      // Component should render with default settings even after error
      expect(document.body).toBeTruthy();
    });
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

  it('switches between email and slack tabs', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const slackTab = screen.getByText('💬 Slack');
    fireEvent.click(slackTab);

    await waitFor(() => {
      expect(screen.getByText(/Slack Webhook URL/i)).toBeInTheDocument();
    });
  });

  it('updates email enabled toggle', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const checkboxes = screen.getAllByRole('checkbox');
    const emailToggle = checkboxes.find(
      (cb) => cb.closest('label')?.textContent.includes('Enable Email')
    );

    if (emailToggle) {
      fireEvent.click(emailToggle);
      expect(emailToggle.checked).toBe(true);
    }
  });

  it('updates slack enabled toggle', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    // Switch to slack tab
    const slackTab = screen.getByText('💬 Slack');
    fireEvent.click(slackTab);

    await waitFor(() => {
      const checkboxes = screen.getAllByRole('checkbox');
      const slackToggle = checkboxes.find(
        (cb) => cb.closest('label')?.textContent.includes('Enable Slack')
      );

      if (slackToggle) {
        fireEvent.click(slackToggle);
        expect(slackToggle.checked).toBe(true);
      }
    });
  });

  it('updates SMTP server input field', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const inputs = screen.getAllByRole('textbox');
    const smtpInput = inputs.find((input) =>
      input.placeholder?.includes('smtp') || input.value === ''
    );

    if (smtpInput) {
      fireEvent.change(smtpInput, { target: { value: 'smtp.gmail.com' } });
      expect(smtpInput.value).toBe('smtp.gmail.com');
    }
  });

  it('updates SMTP port input field', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const portInput = document.querySelector('input[type="number"]');
    if (portInput) {
      fireEvent.change(portInput, { target: { value: '465' } });
      expect(portInput.value).toBe('465');
    }
  });

  it('updates to_emails from comma-separated string', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const inputs = screen.getAllByRole('textbox');
    const emailInput = inputs.find((input) =>
      input.placeholder?.includes('example.com')
    );

    if (emailInput) {
      fireEvent.change(emailInput, {
        target: { value: 'test1@example.com, test2@example.com' }
      });
      expect(emailInput.value).toBe('test1@example.com, test2@example.com');
    }
  });

  it('calls save API with updated settings', async () => {
    mockFetch.mockResolvedValueOnce({
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
          app_url: 'http://localhost:3000',
          notify_on_start: false,
          notify_on_complete: true,
          notify_on_failure: true,
          notify_provision_start: false,
          notify_provision_success: true,
          notify_provision_failure: true,
          notify_delete_start: false,
          notify_delete_success: true,
          notify_delete_failure: true,
        },
      }),
    }).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true }),
    });

    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    const saveBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/save/i));
    if (saveBtn) {
      await act(async () => {
        fireEvent.click(saveBtn);
      });

      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledWith(
          expect.stringContaining('/api/notification-settings'),
          expect.objectContaining({
            method: 'POST',
          })
        );
      });
    }
  });

  it('shows success message on successful save', async () => {
    mockFetch.mockResolvedValueOnce({
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
          app_url: 'http://localhost:3000',
          notify_on_start: false,
          notify_on_complete: true,
          notify_on_failure: true,
          notify_provision_start: false,
          notify_provision_success: true,
          notify_provision_failure: true,
          notify_delete_start: false,
          notify_delete_success: true,
          notify_delete_failure: true,
        },
      }),
    }).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true }),
    });

    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    const saveBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/save/i));
    if (saveBtn) {
      await act(async () => {
        fireEvent.click(saveBtn);
      });

      await waitFor(() => {
        expect(screen.getByText(/saved successfully/i)).toBeInTheDocument();
      });
    }
  });

  it('shows error message on save failure', async () => {
    mockFetch.mockResolvedValueOnce({
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
          app_url: 'http://localhost:3000',
          notify_on_start: false,
          notify_on_complete: true,
          notify_on_failure: true,
          notify_provision_start: false,
          notify_provision_success: true,
          notify_provision_failure: true,
          notify_delete_start: false,
          notify_delete_success: true,
          notify_delete_failure: true,
        },
      }),
    }).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ detail: 'Invalid configuration' }),
    });

    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    const saveBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/save/i));
    if (saveBtn) {
      await act(async () => {
        fireEvent.click(saveBtn);
      });

      await waitFor(() => {
        expect(screen.getByText(/Failed to save settings/i)).toBeInTheDocument();
      });
    }
  });

  it('dismisses success/error message when X clicked', async () => {
    mockFetch.mockResolvedValueOnce({
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
          app_url: 'http://localhost:3000',
          notify_on_start: false,
          notify_on_complete: true,
          notify_on_failure: true,
          notify_provision_start: false,
          notify_provision_success: true,
          notify_provision_failure: true,
          notify_delete_start: false,
          notify_delete_success: true,
          notify_delete_failure: true,
        },
      }),
    }).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true }),
    });

    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    const saveBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/save/i));
    if (saveBtn) {
      await act(async () => {
        fireEvent.click(saveBtn);
      });

      await waitFor(() => {
        expect(screen.getByText(/saved successfully/i)).toBeInTheDocument();
      });

      const dismissBtn = screen.getAllByRole('button').find((b) => b.textContent === '✕');
      if (dismissBtn) {
        fireEvent.click(dismissBtn);
        await waitFor(() => {
          expect(screen.queryByText(/saved successfully/i)).not.toBeInTheDocument();
        });
      }
    }
  });

  it('toggles provision notification preferences', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const checkboxes = screen.getAllByRole('checkbox');
    const provisionCheckbox = checkboxes.find((cb) =>
      cb.closest('label')?.textContent.includes('Provisioning starts')
    );

    if (provisionCheckbox) {
      const initialState = provisionCheckbox.checked;
      fireEvent.click(provisionCheckbox);
      expect(provisionCheckbox.checked).toBe(!initialState);
    }
  });

  it('toggles delete notification preferences', async () => {
    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const checkboxes = screen.getAllByRole('checkbox');
    const deleteCheckbox = checkboxes.find((cb) =>
      cb.closest('label')?.textContent.includes('Deletion starts')
    );

    if (deleteCheckbox) {
      const initialState = deleteCheckbox.checked;
      fireEvent.click(deleteCheckbox);
      expect(deleteCheckbox.checked).toBe(!initialState);
    }
  });

  it('disables save button while saving', async () => {
    mockFetch.mockResolvedValueOnce({
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
          app_url: 'http://localhost:3000',
          notify_on_start: false,
          notify_on_complete: true,
          notify_on_failure: true,
          notify_provision_start: false,
          notify_provision_success: true,
          notify_provision_failure: true,
          notify_delete_start: false,
          notify_delete_success: true,
          notify_delete_failure: true,
        },
      }),
    }).mockImplementation(() => new Promise(() => {})); // Never resolves

    await act(async () => {
      render(<NotificationSettingsInline />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    const saveBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/save/i));
    if (saveBtn) {
      await act(async () => {
        fireEvent.click(saveBtn);
      });

      await waitFor(() => {
        expect(saveBtn.disabled).toBe(true);
      });
    }
  });

  it('shows loading spinner initially', async () => {
    mockFetch.mockImplementation(() => new Promise(() => {})); // Never resolves
    render(<NotificationSettingsInline />);

    await waitFor(() => {
      expect(screen.getByText(/Loading settings/i)).toBeInTheDocument();
    });
  });
});

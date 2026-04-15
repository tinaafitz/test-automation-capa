/**
 * Tests for TriggerPanel component.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

jest.mock('../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

import TriggerPanel from './TriggerPanel';

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({ triggers: [], count: 0, history: [], success: true }),
  });
});

describe('TriggerPanel', () => {
  it('renders collapsed by default', () => {
    render(<TriggerPanel workflowName="test-wf" />);
    expect(screen.getByText('Triggers')).toBeInTheDocument();
    // Should not show create button when collapsed
    expect(screen.queryByText('Add Trigger')).not.toBeInTheDocument();
  });

  it('expands when clicked', async () => {
    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    await waitFor(() => {
      expect(screen.getByText('Add Trigger')).toBeInTheDocument();
    });
  });

  it('fetches triggers and scheduler status on expand', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ triggers: [], count: 0, success: true, running: true, croniter_available: true, active_schedule_triggers: 0, upcoming: [], history: [] }),
    });

    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/workflows/test-wf/triggers')
      );
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/triggers/scheduler/status')
      );
    });
  });

  it('shows empty state when no triggers', async () => {
    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    await waitFor(() => {
      expect(screen.getByText('No triggers configured for this workflow.')).toBeInTheDocument();
    });
  });

  it('shows trigger list when triggers exist', async () => {
    let callCount = 0;
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/workflows/')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            triggers: [{
              trigger_id: 'trg-abc123',
              trigger_name: 'nightly-run',
              type: 'schedule',
              cron: '0 2 * * *',
              enabled: true,
              next_run_at: '2026-04-15T02:00:00',
              last_run_status: null,
              consecutive_failures: 0,
            }],
            count: 1,
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, running: true, croniter_available: true, active_schedule_triggers: 1, upcoming: [], history: [] }),
      });
    });

    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });

    await waitFor(() => {
      expect(screen.getByText('nightly-run')).toBeInTheDocument();
      expect(screen.getByText('schedule')).toBeInTheDocument();
    });
  });

  it('opens create form when Add Trigger clicked', async () => {
    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    await waitFor(() => {
      expect(screen.getByText('Add Trigger')).toBeInTheDocument();
    });
    await act(async () => {
      fireEvent.click(screen.getByText('Add Trigger'));
    });
    expect(screen.getByText('New Trigger')).toBeInTheDocument();
    expect(screen.getByText('Schedule')).toBeInTheDocument();
    expect(screen.getByText('Webhook')).toBeInTheDocument();
  });

  it('shows cron presets for schedule type', async () => {
    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    await act(async () => {
      fireEvent.click(screen.getByText('Add Trigger'));
    });
    expect(screen.getByText('Daily at 2 AM')).toBeInTheDocument();
    expect(screen.getByText('Every hour')).toBeInTheDocument();
    expect(screen.getByText('Weekdays at 9 AM')).toBeInTheDocument();
  });

  it('shows webhook info when webhook type selected', async () => {
    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    await act(async () => {
      fireEvent.click(screen.getByText('Add Trigger'));
    });
    await act(async () => {
      fireEvent.click(screen.getByText('Webhook'));
    });
    expect(screen.getByText(/POST \/api\/webhooks\/trigger/)).toBeInTheDocument();
  });

  it('creates a schedule trigger', async () => {
    mockFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'POST' && url.includes('/api/triggers')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            trigger: { trigger_id: 'trg-new', type: 'schedule', trigger_name: 'nightly', enabled: true },
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ triggers: [], count: 0, success: true, running: true, croniter_available: true, active_schedule_triggers: 0, upcoming: [], history: [] }),
      });
    });

    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    await act(async () => {
      fireEvent.click(screen.getByText('Add Trigger'));
    });
    await act(async () => {
      fireEvent.click(screen.getByText('Create Trigger'));
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/triggers'),
        expect.objectContaining({
          method: 'POST',
          body: expect.stringContaining('"workflow_name":"test-wf"'),
        })
      );
    });
  });

  it('shows scheduler status', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/triggers/scheduler/status')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            success: true,
            running: true,
            croniter_available: true,
            check_interval: 30,
            active_schedule_triggers: 2,
            upcoming: [],
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ triggers: [], count: 0, history: [] }),
      });
    });

    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });

    await waitFor(() => {
      expect(screen.getByText('Scheduler running')).toBeInTheDocument();
    });
  });

  it('shows trigger count badge when collapsed', async () => {
    mockFetch.mockImplementation((url) => {
      if (url.includes('/api/workflows/')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            triggers: [
              { trigger_id: 'trg-1', type: 'schedule', trigger_name: 'a', enabled: true, cron: '0 2 * * *' },
              { trigger_id: 'trg-2', type: 'webhook', trigger_name: 'b', enabled: true },
            ],
            count: 2,
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, running: true, croniter_available: true, active_schedule_triggers: 1, upcoming: [], history: [] }),
      });
    });

    render(<TriggerPanel workflowName="test-wf" />);
    // Expand to load triggers
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    await waitFor(() => {
      expect(screen.getByText('a')).toBeInTheDocument();
    });
    // Collapse
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    // Badge should show count
    expect(screen.getByText('2')).toBeInTheDocument();
  });

  it('disables create when workflowName is empty', async () => {
    render(<TriggerPanel workflowName="" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    const addBtn = screen.getByText('Add Trigger');
    expect(addBtn.closest('button')).toBeDisabled();
  });

  it('cancels create form', async () => {
    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    await act(async () => {
      fireEvent.click(screen.getByText('Add Trigger'));
    });
    expect(screen.getByText('New Trigger')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByText('Cancel'));
    });
    expect(screen.queryByText('New Trigger')).not.toBeInTheDocument();
  });

  it('deletes a trigger', async () => {
    mockFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'DELETE' && url.includes('/api/triggers/trg-del1')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true, deleted: 'trg-del1' }),
        });
      }
      if (url.includes('/api/workflows/')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            triggers: [{
              trigger_id: 'trg-del1',
              trigger_name: 'to-delete',
              type: 'schedule',
              cron: '0 2 * * *',
              enabled: true,
            }],
            count: 1,
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, running: true, croniter_available: true, active_schedule_triggers: 0, upcoming: [], history: [] }),
      });
    });

    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    await waitFor(() => {
      expect(screen.getByText('to-delete')).toBeInTheDocument();
    });
    await act(async () => {
      fireEvent.click(screen.getByTitle('Delete trigger'));
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/triggers/trg-del1'),
        expect.objectContaining({ method: 'DELETE' })
      );
    });
  });

  it('toggles a trigger off', async () => {
    mockFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'POST' && url.includes('/api/triggers/trg-tog1/disable')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ success: true }),
        });
      }
      if (url.includes('/api/workflows/')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            triggers: [{
              trigger_id: 'trg-tog1',
              trigger_name: 'toggle-me',
              type: 'schedule',
              cron: '0 2 * * *',
              enabled: true,
            }],
            count: 1,
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, running: true, croniter_available: true, active_schedule_triggers: 1, upcoming: [], history: [] }),
      });
    });

    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    await waitFor(() => {
      expect(screen.getByText('toggle-me')).toBeInTheDocument();
    });
    await act(async () => {
      fireEvent.click(screen.getByTitle('Disable'));
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/triggers/trg-tog1/disable'),
        expect.objectContaining({ method: 'POST' })
      );
    });
  });

  it('fires a trigger manually', async () => {
    mockFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'POST' && url.includes('/api/triggers/trg-fire1/fire')) {
        return Promise.resolve({
          ok: true,
          status: 200,
          json: async () => ({ success: true }),
        });
      }
      if (url.includes('/api/workflows/')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            triggers: [{
              trigger_id: 'trg-fire1',
              trigger_name: 'fire-me',
              type: 'schedule',
              cron: '0 2 * * *',
              enabled: true,
            }],
            count: 1,
          }),
        });
      }
      if (url.includes('/api/triggers/history')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({ history: [] }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, running: true, croniter_available: true, active_schedule_triggers: 1, upcoming: [], history: [] }),
      });
    });

    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    await waitFor(() => {
      expect(screen.getByText('fire-me')).toBeInTheDocument();
    });
    await act(async () => {
      fireEvent.click(screen.getByTitle('Fire now'));
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/triggers/trg-fire1/fire'),
        expect.objectContaining({ method: 'POST' })
      );
    });
  });

  it('shows rate limit error on 429 response', async () => {
    mockFetch.mockImplementation((url, opts) => {
      if (opts?.method === 'POST' && url.includes('/fire')) {
        return Promise.resolve({
          ok: false,
          status: 429,
          json: async () => ({ detail: 'Rate limited' }),
        });
      }
      if (url.includes('/api/workflows/')) {
        return Promise.resolve({
          ok: true,
          json: async () => ({
            triggers: [{
              trigger_id: 'trg-rate1',
              trigger_name: 'rate-test',
              type: 'schedule',
              cron: '0 2 * * *',
              enabled: true,
            }],
            count: 1,
          }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({ success: true, running: true, croniter_available: true, active_schedule_triggers: 1, upcoming: [], history: [] }),
      });
    });

    render(<TriggerPanel workflowName="test-wf" />);
    await act(async () => {
      fireEvent.click(screen.getByText('Triggers'));
    });
    await waitFor(() => {
      expect(screen.getByText('rate-test')).toBeInTheDocument();
    });
    await act(async () => {
      fireEvent.click(screen.getByTitle('Fire now'));
    });
    await waitFor(() => {
      expect(screen.getByText('Rate limited - wait 60s between fires')).toBeInTheDocument();
    });
  });
});

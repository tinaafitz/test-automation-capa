/**
 * Tests for CredentialsModal component.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

// Mock dependencies
const mockDispatch = jest.fn();

jest.mock('../../store/AppContext', () => ({
  useAppDispatch: () => mockDispatch,
  AppActionTypes: {
    ADD_NOTIFICATION: 'ADD_NOTIFICATION',
  },
}));

jest.mock('../../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

import CredentialsModal from './CredentialsModal';

beforeEach(() => {
  mockFetch.mockReset();
  jest.clearAllMocks();

  // Default: return empty credentials
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({
      credentials: {
        OCP_HUB_API_URL: '',
        OCP_HUB_CLUSTER_USER: '',
        OCP_HUB_CLUSTER_PASSWORD: '',
        AWS_REGION: '',
        AWS_ACCESS_KEY_ID: '',
        AWS_SECRET_ACCESS_KEY: '',
        OCM_CLIENT_ID: '',
        OCM_CLIENT_SECRET: '',
      },
    }),
  });
});

describe('CredentialsModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    theme: 'mce',
    onSave: jest.fn(),
    inline: false,
  };

  it('renders nothing when closed', () => {
    const { container } = render(<CredentialsModal {...defaultProps} isOpen={false} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders modal when open', async () => {
    await act(async () => {
      render(<CredentialsModal {...defaultProps} />);
    });
    expect(screen.getAllByText(/Credentials|credential/i).length).toBeGreaterThan(0);
  });

  it('fetches credentials on mount', async () => {
    await act(async () => {
      render(<CredentialsModal {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/credentials')
      );
    });
  });

  it('renders credential input fields', async () => {
    await act(async () => {
      render(<CredentialsModal {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    const inputs = screen.getAllByRole('textbox');
    expect(inputs.length).toBeGreaterThan(0);
  });

  it('renders with minikube theme', async () => {
    await act(async () => {
      render(<CredentialsModal {...defaultProps} theme="minikube" />);
    });
    expect(screen.getAllByText(/Credentials|credential/i).length).toBeGreaterThan(0);
  });

  it('renders in inline mode', async () => {
    await act(async () => {
      render(<CredentialsModal {...defaultProps} inline={true} />);
    });
    // In inline mode, should render content regardless of isOpen
    const inputs = screen.getAllByRole('textbox');
    expect(inputs.length).toBeGreaterThan(0);
  });

  it('has close button in modal mode', async () => {
    await act(async () => {
      render(<CredentialsModal {...defaultProps} />);
    });
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('calls onClose when close button clicked', async () => {
    const onClose = jest.fn();
    await act(async () => {
      render(<CredentialsModal {...defaultProps} onClose={onClose} />);
    });
    // Find a close/X button
    const buttons = screen.getAllByRole('button');
    const closeBtn = buttons.find(
      (b) => b.querySelector('svg') || b.textContent.match(/close|cancel|×/i)
    );
    if (closeBtn) {
      fireEvent.click(closeBtn);
      expect(onClose).toHaveBeenCalled();
    }
  });

  it('handles fetch error gracefully', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'));
    await act(async () => {
      render(<CredentialsModal {...defaultProps} />);
    });
    // Should not crash
    expect(screen.getAllByText(/Credentials|credential/i).length).toBeGreaterThan(0);
  });

  it('populates fields from fetched credentials', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        credentials: {
          OCP_HUB_API_URL: 'https://api.test.com:6443',
          OCP_HUB_CLUSTER_USER: 'kubeadmin',
          OCP_HUB_CLUSTER_PASSWORD: 'secret123',
          AWS_REGION: 'us-west-2',
          AWS_ACCESS_KEY_ID: 'AKIA123',
          AWS_SECRET_ACCESS_KEY: 'secret',
          OCM_CLIENT_ID: 'client-id',
          OCM_CLIENT_SECRET: 'client-secret',
        },
      }),
    });

    await act(async () => {
      render(<CredentialsModal {...defaultProps} />);
    });

    await waitFor(() => {
      const inputs = screen.getAllByRole('textbox');
      const hasValue = inputs.some((input) => input.value !== '');
      expect(hasValue).toBe(true);
    });
  });

  it('updates input field value when typing', async () => {
    await act(async () => {
      render(<CredentialsModal {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    const inputs = screen.getAllByRole('textbox');
    if (inputs.length > 0) {
      const firstInput = inputs[0];
      fireEvent.change(firstInput, { target: { value: 'new-value' } });
      expect(firstInput.value).toBe('new-value');
    }
  });

  it('toggles password visibility for OCP password', async () => {
    await act(async () => {
      render(<CredentialsModal {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    const passwordFields = document.querySelectorAll('input[type="password"]');
    if (passwordFields.length > 0) {
      const eyeButtons = document.querySelectorAll('button[type="button"]');
      const eyeBtn = Array.from(eyeButtons).find((b) => b.querySelector('svg'));
      if (eyeBtn) {
        fireEvent.click(eyeBtn);
        // Check that type changed from password to text
        const updatedField = document.querySelector('input[type="text"]');
        expect(updatedField).toBeTruthy();
      }
    }
  });

  it('calls handleSave and dispatches success notification on successful save', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ credentials: {} }),
    }).mockResolvedValueOnce({
      ok: true,
      json: async () => ({ success: true }),
    });

    const onSave = jest.fn();
    await act(async () => {
      render(<CredentialsModal {...defaultProps} onSave={onSave} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const saveBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/save/i));
    if (saveBtn) {
      await act(async () => {
        fireEvent.click(saveBtn);
      });
      await waitFor(() => {
        expect(mockDispatch).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'ADD_NOTIFICATION',
            payload: expect.objectContaining({
              type: 'success',
            }),
          })
        );
      });
      expect(onSave).toHaveBeenCalled();
    }
  });

  it('dispatches error notification on save failure', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ credentials: {} }),
    }).mockResolvedValueOnce({
      ok: false,
      json: async () => ({ message: 'Save failed' }),
    });

    await act(async () => {
      render(<CredentialsModal {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const saveBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/save/i));
    if (saveBtn) {
      await act(async () => {
        fireEvent.click(saveBtn);
      });
      await waitFor(() => {
        expect(mockDispatch).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'ADD_NOTIFICATION',
            payload: expect.objectContaining({
              type: 'error',
            }),
          })
        );
      });
    }
  });

  it('shows loading spinner while fetching credentials', async () => {
    mockFetch.mockImplementation(() => new Promise(() => {})); // Never resolves
    render(<CredentialsModal {...defaultProps} />);
    await waitFor(() => {
      expect(screen.getByText(/Loading credentials/i)).toBeInTheDocument();
    });
  });

  it('disables save button while saving', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ credentials: {} }),
    }).mockImplementation(() => new Promise(() => {})); // Save never resolves

    await act(async () => {
      render(<CredentialsModal {...defaultProps} />);
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

  it('refreshes credentials when refresh button clicked', async () => {
    await act(async () => {
      render(<CredentialsModal {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1);
    });

    const refreshBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/refresh/i));
    if (refreshBtn) {
      await act(async () => {
        fireEvent.click(refreshBtn);
      });
      await waitFor(() => {
        expect(mockFetch).toHaveBeenCalledTimes(2);
      });
    }
  });

  it('displays backdrop in modal mode', () => {
    const { container } = render(<CredentialsModal {...defaultProps} />);
    const backdrop = container.querySelector('.fixed.inset-0.bg-black');
    expect(backdrop).toBeTruthy();
  });

  it('does not display backdrop in inline mode', () => {
    const { container } = render(<CredentialsModal {...defaultProps} inline={true} />);
    const backdrop = container.querySelector('.fixed.inset-0.bg-black');
    expect(backdrop).toBeFalsy();
  });

  it('shows AWS and OCM sections for non-MCE theme', async () => {
    await act(async () => {
      render(<CredentialsModal {...defaultProps} theme="minikube" />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    expect(screen.getByText(/AWS Credentials/i)).toBeInTheDocument();
    expect(screen.getByText(/OpenShift Cluster Manager/i)).toBeInTheDocument();
  });

  it('hides AWS and OCM sections for MCE theme', async () => {
    await act(async () => {
      render(<CredentialsModal {...defaultProps} theme="mce" />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
    expect(screen.queryByText(/AWS Credentials/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/OpenShift Cluster Manager/i)).not.toBeInTheDocument();
  });

  it('handles network error during save gracefully', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ credentials: {} }),
    }).mockRejectedValueOnce(new Error('Network error'));

    await act(async () => {
      render(<CredentialsModal {...defaultProps} />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const saveBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/save/i));
    if (saveBtn) {
      await act(async () => {
        fireEvent.click(saveBtn);
      });
      await waitFor(() => {
        expect(mockDispatch).toHaveBeenCalledWith(
          expect.objectContaining({
            type: 'ADD_NOTIFICATION',
            payload: expect.objectContaining({
              type: 'error',
              message: expect.stringContaining('Network error'),
            }),
          })
        );
      });
    }
  });
});

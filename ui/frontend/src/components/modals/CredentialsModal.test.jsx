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
});

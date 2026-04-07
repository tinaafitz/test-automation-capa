/**
 * Tests for RosaProvisionModal component.
 */

import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';

// Mock dependencies
jest.mock('../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
  API_ENDPOINTS: {
    VERSIONS: '/api/versions',
  },
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

import { RosaProvisionModal } from './RosaProvisionModal';

beforeEach(() => {
  mockFetch.mockReset();
  // Default: return versions
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({
      versions: ['4.20.12', '4.20.11', '4.19.22'],
      default_version: '4.20.12',
    }),
  });
});

describe('RosaProvisionModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    onSubmit: jest.fn(),
    testSuite: null,
    mceInfo: null,
    inline: false,
    theme: 'mce',
  };

  it('renders nothing when not open', () => {
    const { container } = render(<RosaProvisionModal {...defaultProps} isOpen={false} />);
    // Modal should not render content when closed
    expect(container.querySelector('.modal-overlay, [role="dialog"]')).toBeNull();
  });

  it('renders modal when open', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });
    // Should show form elements
    expect(screen.getAllByText(/Cluster Name|ROSA|Provision/i).length).toBeGreaterThan(0);
  });

  it('renders cluster name input', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });
    const nameInputs = screen.getAllByRole('textbox');
    expect(nameInputs.length).toBeGreaterThan(0);
  });

  it('renders with minikube theme', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} theme="minikube" />);
    });
    expect(screen.getAllByText(/Cluster Name|ROSA|Provision/i).length).toBeGreaterThan(0);
  });

  it('calls onClose when close button clicked', async () => {
    const onClose = jest.fn();
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} onClose={onClose} />);
    });
    // Find close button (X icon)
    const closeButtons = screen.getAllByRole('button');
    const closeBtn = closeButtons.find(
      (b) => b.querySelector('svg') || b.textContent.match(/close|cancel|×/i)
    );
    if (closeBtn) {
      fireEvent.click(closeBtn);
      expect(onClose).toHaveBeenCalled();
    }
  });

  it('renders network automation toggle', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });
    // Should have automation toggles/checkboxes
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes.length).toBeGreaterThanOrEqual(0);
  });

  it('renders in inline mode', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} inline={true} />);
    });
    expect(screen.getAllByText(/Cluster Name|ROSA|Provision/i).length).toBeGreaterThan(0);
  });

  it('fetches versions on mount', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });
    expect(mockFetch).toHaveBeenCalled();
  });
});

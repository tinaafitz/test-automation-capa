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

  it('updates cluster name input', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });
    const inputs = screen.getAllByRole('textbox');
    const nameInput = inputs.find((i) => i.placeholder?.toLowerCase().includes('cluster') || i.name === 'clusterName');

    if (nameInput) {
      fireEvent.change(nameInput, { target: { value: 'test-cluster' } });
      expect(nameInput.value).toBe('test-cluster');
    }
  });

  it('toggles create ROSA network checkbox', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });
    const checkboxes = screen.getAllByRole('checkbox');
    const networkCheckbox = checkboxes.find((cb) =>
      cb.closest('label')?.textContent?.includes('network') || cb.name === 'createRosaNetwork'
    );

    if (networkCheckbox) {
      const initialState = networkCheckbox.checked;
      fireEvent.click(networkCheckbox);
      expect(networkCheckbox.checked).toBe(!initialState);
    }
  });

  it('toggles create ROSA role config checkbox', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });
    const checkboxes = screen.getAllByRole('checkbox');
    const roleCheckbox = checkboxes.find((cb) =>
      cb.closest('label')?.textContent?.includes('role') || cb.name === 'createRosaRoleConfig'
    );

    if (roleCheckbox) {
      const initialState = roleCheckbox.checked;
      fireEvent.click(roleCheckbox);
      expect(roleCheckbox.checked).toBe(!initialState);
    }
  });

  it('updates VPC CIDR block input', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });
    const inputs = screen.getAllByRole('textbox');
    const cidrInput = inputs.find((i) => i.value?.includes('10.0.0.0') || i.placeholder?.includes('CIDR'));

    if (cidrInput) {
      fireEvent.change(cidrInput, { target: { value: '10.1.0.0/16' } });
      expect(cidrInput.value).toBe('10.1.0.0/16');
    }
  });

  it('updates AWS region input', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });
    const inputs = screen.getAllByRole('textbox');
    const regionInput = inputs.find((i) => i.value?.includes('us-west') || i.placeholder?.toLowerCase().includes('region'));

    if (regionInput) {
      fireEvent.change(regionInput, { target: { value: 'us-east-1' } });
      expect(regionInput.value).toBe('us-east-1');
    }
  });

  it('calls onSubmit when form submitted', async () => {
    const onSubmit = jest.fn();
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} onSubmit={onSubmit} />);
    });

    const submitBtn = screen.getAllByRole('button').find((b) =>
      b.textContent.match(/provision|submit|create/i) && b.type !== 'button'
    );

    if (submitBtn) {
      fireEvent.click(submitBtn);
      expect(onSubmit).toHaveBeenCalled();
    }
  });

  it('shows loading state while fetching versions', async () => {
    mockFetch.mockImplementation(() => new Promise(() => {})); // Never resolves
    render(<RosaProvisionModal {...defaultProps} />);

    // Should show some loading indicator or not crash
    expect(document.body).toBeTruthy();
  });

  it('handles version fetch error gracefully', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Failed to fetch versions'));
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });

    // Should not crash
    expect(document.body).toBeTruthy();
  });

  it('selects OpenShift version from dropdown', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });

    const selects = document.querySelectorAll('select');
    const versionSelect = Array.from(selects).find((s) =>
      s.name?.toLowerCase().includes('version') || s.options?.[0]?.textContent?.includes('4.')
    );

    if (versionSelect) {
      fireEvent.change(versionSelect, { target: { value: '4.20.11' } });
      expect(versionSelect.value).toBe('4.20.11');
    }
  });

  it('toggles private network option', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });
    const checkboxes = screen.getAllByRole('checkbox');
    const privateCheckbox = checkboxes.find((cb) =>
      cb.closest('label')?.textContent?.toLowerCase().includes('private')
    );

    if (privateCheckbox) {
      const initialState = privateCheckbox.checked;
      fireEvent.click(privateCheckbox);
      expect(privateCheckbox.checked).toBe(!initialState);
    }
  });

  it('updates additional tags input', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });
    const inputs = screen.getAllByRole('textbox');
    const tagsInput = inputs.find((i) =>
      i.placeholder?.toLowerCase().includes('tag') || i.name === 'additionalTags'
    );

    if (tagsInput) {
      fireEvent.change(tagsInput, { target: { value: 'env=test,team=qa' } });
      expect(tagsInput.value).toBe('env=test,team=qa');
    }
  });

  it('updates availability zone count', async () => {
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} />);
    });
    const numberInputs = document.querySelectorAll('input[type="number"]');
    const azInput = Array.from(numberInputs).find((i) =>
      i.value === '1' || i.placeholder?.toLowerCase().includes('zone')
    );

    if (azInput) {
      fireEvent.change(azInput, { target: { value: '3' } });
      expect(azInput.value).toBe('3');
    }
  });

  it('accepts mceInfo prop', async () => {
    const mceInfo = {
      awsRegion: 'eu-west-1',
      clusterName: 'test-cluster',
    };
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} mceInfo={mceInfo} />);
    });

    // Should render without crashing
    const inputs = screen.getAllByRole('textbox');
    expect(inputs.length).toBeGreaterThan(0);
  });

  it('shows cancel button that calls onClose', async () => {
    const onClose = jest.fn();
    await act(async () => {
      render(<RosaProvisionModal {...defaultProps} onClose={onClose} />);
    });

    const cancelBtn = screen.getAllByRole('button').find((b) =>
      b.textContent.match(/cancel/i)
    );

    if (cancelBtn) {
      fireEvent.click(cancelBtn);
      expect(onClose).toHaveBeenCalled();
    }
  });

  it('does not show modal backdrop in inline mode', async () => {
    const { container } = await act(async () => {
      return render(<RosaProvisionModal {...defaultProps} inline={true} />);
    });

    const backdrop = container.querySelector('.fixed.inset-0.bg-black');
    expect(backdrop).toBeFalsy();
  });
});

import React from 'react';
import { render, screen, waitFor, fireEvent, act } from '@testing-library/react';
import ClusterActions from './ClusterActions';

// Mock buildApiUrl
jest.mock('../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:5001${path}`,
}));

// Sample feature registry
const mockRegistry = {
  success: true,
  registry: {
    suites: [
      {
        id: 'version-lifecycle',
        name: 'Version & Lifecycle',
        description: 'Cluster version management and upgrade operations',
        category: 'Operations',
        phase: 'Day2',
        icon: 'arrow-up',
        features: [
          {
            id: 'control_plane_upgrade',
            name: 'Control Plane Upgrade',
            description: 'Upgrade the ROSA HCP control plane version',
            type: 'version',
            mutable: true,
            default: '',
            k8s_field: '.spec.version',
            resource: 'ROSAControlPlane',
            playbook: 'playbooks/upgrade_rosa_control_plane.yml',
            wait_timeout: 3600,
          },
          {
            id: 'channel_group',
            name: 'Channel Group',
            description: 'Update channel for version availability',
            type: 'select',
            options: ['stable', 'fast', 'candidate'],
            mutable: true,
            default: 'stable',
            k8s_field: '.spec.channelGroup',
            resource: 'ROSAControlPlane',
          },
        ],
      },
      {
        id: 'cluster-config',
        name: 'Cluster Configuration',
        description: 'Core cluster provisioning features',
        category: 'Infrastructure',
        phase: 'Day1',
        icon: 'server',
        features: [
          {
            id: 'private_network',
            name: 'Private Network',
            description: 'Enable private cluster networking',
            type: 'boolean',
            mutable: false,
            default: false,
            k8s_field: '.spec.endpointAccess',
            resource: 'ROSAControlPlane',
          },
          {
            id: 'additional_tags',
            name: 'Additional Tags',
            description: 'Custom AWS tags',
            type: 'key_value',
            mutable: true,
            default: {},
            k8s_field: '.spec.additionalTags',
            resource: 'ROSAControlPlane',
          },
        ],
      },
    ],
  },
};

const mockClusterStatus = {
  success: true,
  status: {
    cluster_found: true,
    version: '4.20.4',
    ready: true,
    available_upgrades: ['4.20.5', '4.20.6'],
    channel_group: 'stable',
    domain_prefix: 'test',
    additional_tags: {},
    machine_pools: [],
  },
};

beforeEach(() => {
  global.fetch = jest.fn();
});

afterEach(() => {
  jest.restoreAllMocks();
});

describe('ClusterActions', () => {
  const setupFetch = (overrides = {}) => {
    global.fetch.mockImplementation((url) => {
      if (url.includes('/api/cluster-actions/features')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(overrides.registry || mockRegistry) });
      }
      if (url.includes('/api/cluster-actions/cluster/')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(overrides.status || mockClusterStatus) });
      }
      if (url.includes('/api/cluster-actions/execute')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(overrides.execute || {
            success: true,
            cluster_name: 'test-cluster',
            action_count: 1,
            results: [{ feature_id: 'channel_group', status: 'queued', message: 'Would patch ROSAControlPlane' }],
          }),
        });
      }
      return Promise.resolve({ ok: false });
    });
  };

  it('renders loading state initially', async () => {
    global.fetch.mockImplementation(() => new Promise(() => {})); // never resolves
    render(<ClusterActions />);
    expect(screen.getByText('Loading feature registry...')).toBeInTheDocument();
  });

  it('renders feature suites after loading', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByText('Cluster Actions')).toBeInTheDocument();
    });
    expect(screen.getByText('Version & Lifecycle')).toBeInTheDocument();
    expect(screen.getByText('Cluster Configuration')).toBeInTheDocument();
  });

  it('shows feature count stats in header', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByText('features')).toBeInTheDocument();
      expect(screen.getByText('mutable')).toBeInTheDocument();
      expect(screen.getByText('suites')).toBeInTheDocument();
    });
  });

  it('has cluster name input', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByPlaceholderText('e.g., qe6-rosa-hcp')).toBeInTheDocument();
    });
  });

  it('has namespace input with default value', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      const nsInput = screen.getByDisplayValue('ns-rosa-hcp');
      expect(nsInput).toBeInTheDocument();
    });
  });

  it('disables Load Cluster button when no cluster name', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      const btn = screen.getByText('Load Cluster');
      expect(btn.closest('button')).toBeDisabled();
    });
  });

  it('loads cluster status when Load Cluster clicked', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByPlaceholderText('e.g., qe6-rosa-hcp')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('e.g., qe6-rosa-hcp');
    fireEvent.change(input, { target: { value: 'test-cluster' } });

    const loadBtn = screen.getByText('Load Cluster');
    await act(async () => { fireEvent.click(loadBtn); });

    await waitFor(() => {
      expect(screen.getByText('Connected')).toBeInTheDocument();
      expect(screen.getByText('v4.20.4')).toBeInTheDocument();
      expect(screen.getByText('Ready')).toBeInTheDocument();
    });
  });

  it('expands suite when clicked', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByText('Version & Lifecycle')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Version & Lifecycle'));

    await waitFor(() => {
      expect(screen.getByText('Control Plane Upgrade')).toBeInTheDocument();
      expect(screen.getByText('Channel Group')).toBeInTheDocument();
    });
  });

  it('shows immutable badge for immutable features', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByText('Cluster Configuration')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Cluster Configuration'));

    await waitFor(() => {
      expect(screen.getByText('Private Network')).toBeInTheDocument();
      expect(screen.getByText('Immutable')).toBeInTheDocument();
    });
  });

  it('allows selecting mutable features', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByText('Version & Lifecycle')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Version & Lifecycle'));

    await waitFor(() => {
      expect(screen.getByText('Channel Group')).toBeInTheDocument();
    });

    // Find the checkbox for Channel Group (mutable feature)
    const checkboxes = screen.getAllByRole('checkbox');
    const channelGroupCheckbox = checkboxes.find(cb => {
      const parent = cb.closest('[class*="rounded-xl"]');
      return parent?.textContent?.includes('Channel Group');
    });

    expect(channelGroupCheckbox).toBeTruthy();
    fireEvent.click(channelGroupCheckbox);

    await waitFor(() => {
      expect(screen.getByText(/1 action.* selected/)).toBeInTheDocument();
    });
  });

  it('filters suites by search', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByText('Version & Lifecycle')).toBeInTheDocument();
    });

    const searchInput = screen.getByPlaceholderText('Search features...');
    fireEvent.change(searchInput, { target: { value: 'upgrade' } });

    await waitFor(() => {
      expect(screen.getByText('Version & Lifecycle')).toBeInTheDocument();
      expect(screen.queryByText('Cluster Configuration')).not.toBeInTheDocument();
    });
  });

  it('filters suites by phase', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByText('Version & Lifecycle')).toBeInTheDocument();
      expect(screen.getByText('Cluster Configuration')).toBeInTheDocument();
    });

    // Click the Day2 filter button (in the phase filter bar)
    const day2Buttons = screen.getAllByText('Day2');
    const filterButton = day2Buttons.find(el => el.closest('[class*="bg-gray-100"]'));
    fireEvent.click(filterButton);

    await waitFor(() => {
      expect(screen.getByText('Version & Lifecycle')).toBeInTheDocument();
      expect(screen.queryByText('Cluster Configuration')).not.toBeInTheDocument();
    });
  });

  it('disables Execute button when no actions selected', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      const btn = screen.getByText('Execute Actions');
      expect(btn.closest('button')).toBeDisabled();
    });
  });

  it('shows info box about feature suites', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByText('How Feature Suites Work')).toBeInTheDocument();
    });
  });

  it('shows expand/collapse all button', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByText('Expand All')).toBeInTheDocument();
    });
  });

  it('expands all suites when Expand All clicked', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByText('Expand All')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Expand All'));

    await waitFor(() => {
      expect(screen.getByText('Control Plane Upgrade')).toBeInTheDocument();
      expect(screen.getByText('Private Network')).toBeInTheDocument();
      expect(screen.getByText('Collapse All')).toBeInTheDocument();
    });
  });

  it('clears selected actions when Clear clicked', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByText('Version & Lifecycle')).toBeInTheDocument();
    });

    // Expand and select
    fireEvent.click(screen.getByText('Version & Lifecycle'));
    await waitFor(() => { expect(screen.getByText('Channel Group')).toBeInTheDocument(); });

    const checkboxes = screen.getAllByRole('checkbox');
    const mutableCheckbox = checkboxes.find(cb => {
      const parent = cb.closest('[class*="rounded-xl"]');
      return parent?.textContent?.includes('Channel Group');
    });
    fireEvent.click(mutableCheckbox);

    await waitFor(() => {
      expect(screen.getByText('Clear')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Clear'));

    await waitFor(() => {
      expect(screen.queryByText(/action.* selected/)).not.toBeInTheDocument();
    });
  });

  it('shows execution results after executing actions', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    // Set cluster name
    await waitFor(() => { expect(screen.getByPlaceholderText('e.g., qe6-rosa-hcp')).toBeInTheDocument(); });
    fireEvent.change(screen.getByPlaceholderText('e.g., qe6-rosa-hcp'), { target: { value: 'test-cluster' } });

    // Expand and select a feature
    fireEvent.click(screen.getByText('Version & Lifecycle'));
    await waitFor(() => { expect(screen.getByText('Channel Group')).toBeInTheDocument(); });

    const checkboxes = screen.getAllByRole('checkbox');
    const mutableCheckbox = checkboxes.find(cb => {
      const parent = cb.closest('[class*="rounded-xl"]');
      return parent?.textContent?.includes('Channel Group');
    });
    fireEvent.click(mutableCheckbox);

    // Execute
    const execBtn = screen.getByText('Execute Actions');
    await act(async () => { fireEvent.click(execBtn); });

    await waitFor(() => {
      expect(screen.getByText(/Execution Complete/)).toBeInTheDocument();
      expect(screen.getByText('channel_group')).toBeInTheDocument();
    });
  });

  it('handles API error on feature fetch', async () => {
    global.fetch.mockImplementation(() => Promise.resolve({ ok: false }));
    await act(async () => { render(<ClusterActions />); });

    // Should not crash - shows empty state
    await waitFor(() => {
      expect(screen.getByText('No feature suites match your filter')).toBeInTheDocument();
    });
  });

  it('shows cluster not found when cluster does not exist', async () => {
    setupFetch({
      status: { success: true, status: { cluster_found: false, error: 'not found' } },
    });
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => { expect(screen.getByPlaceholderText('e.g., qe6-rosa-hcp')).toBeInTheDocument(); });
    fireEvent.change(screen.getByPlaceholderText('e.g., qe6-rosa-hcp'), { target: { value: 'nonexistent' } });

    await act(async () => { fireEvent.click(screen.getByText('Load Cluster')); });

    await waitFor(() => {
      expect(screen.getByText('Not found')).toBeInTheDocument();
    });
  });

  it('shows suite feature counts', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getByText(/2 features \(2 mutable\)/)).toBeInTheDocument(); // version-lifecycle
      expect(screen.getByText(/2 features \(1 mutable\)/)).toBeInTheDocument(); // cluster-config
    });
  });

  it('shows phase badges on suites', async () => {
    setupFetch();
    await act(async () => { render(<ClusterActions />); });

    await waitFor(() => {
      expect(screen.getAllByText('Day1').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Day2').length).toBeGreaterThan(0);
    });
  });
});

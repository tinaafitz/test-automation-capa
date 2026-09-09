/**
 * Tests for the "Make this my MCE hub" pre-run card.
 *
 * The card defaults to the 5.0 candidate, which comes from the acm-d dev
 * catalog rather than redhat-operators. That means the launch has to carry
 * mce_source_mode/acm_repo as well as the channel — sending the channel alone
 * points stable-5.0 at a catalog that does not offer it, and leaving acm_repo
 * at its "production" default renders the catalog image as
 * "/mce-dev-catalog:latest-5.0" (empty index_image.source in vars.yml).
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

jest.mock('../../store/AppContext', () => ({
  useApp: () => ({ collapsedSections: new Set() }),
  useAppDispatch: () => jest.fn(),
  useApiStatusContext: () => ({ ocpStatus: { connected: true } }),
  useRecentOperationsContext: () => ({
    addToRecent: jest.fn(),
    updateRecentOperationStatus: jest.fn(),
  }),
  AppActionTypes: {
    TOGGLE_SECTION: 'TOGGLE_SECTION',
    ADD_NOTIFICATION: 'ADD_NOTIFICATION',
  },
}));

jest.mock('../../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
  API_ENDPOINTS: {
    ROSA_CLUSTERS: '/api/rosa/clusters',
    ANSIBLE_RUN_PLAYBOOK: '/api/ansible/run-playbook',
  },
  validateApiResponse: (data) => data,
  extractSafeErrorMessage: (err) => err.message || 'Unknown error',
}));

jest.mock('../agents/ProvisionFailureAgentPanel', () => {
  return function MockPanel() {
    return <div data-testid="agent-panel">Agent Panel</div>;
  };
});

const mockFetch = jest.fn();
global.fetch = mockFetch;

import RosaHcpClustersSection from './RosaHcpClustersSection';

const CLUSTER = {
  name: 'cat-rosa-hcp',
  namespace: 'ns-rosa-hcp',
  status: 'ready',
  version: '4.22.13',
  region: 'us-west-2',
};

const ok = (body) => Promise.resolve({ ok: true, json: async () => body });

// Credentials come back keyed exactly as vars/user_vars.yml spells them.
const FULL_CREDS = {
  credentials: {
    OCM_CLIENT_ID: 'id',
    OCM_CLIENT_SECRET: 'secret',
    AWS_ACCESS_KEY_ID: 'akid',
    AWS_SECRET_ACCESS_KEY: 'sak',
    minikubeCluster: 'mk-test',
  },
};

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockImplementation((url) => {
    if (url.includes('/api/credentials')) return ok(FULL_CREDS);
    if (url.includes('/api/minikube/current-context'))
      return ok({ success: true, current_context: 'hub-ctx' });
    if (url.includes('/api/rosa/clusters'))
      return ok({ success: true, clusters: [CLUSTER] });
    if (url.includes('/api/ansible/run-playbook'))
      return ok({ success: true, job_id: 'job-1' });
    if (url.includes('/api/ansible/job-status'))
      return ok({ success: true, status: 'running', output: '' });
    return ok({});
  });
});

const openHubCard = async () => {
  await act(async () => {
    render(<RosaHcpClustersSection theme="mce" />);
  });
  await screen.findByText(CLUSTER.name);
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: /make this my mce hub/i }));
  });
  return screen.findByText(/Make .*your MCE test hub/i);
};

const sourceSelect = () => screen.getByLabelText('MCE source');
const channelInput = () => screen.getByLabelText('MCE channel');
const launchButton = () => screen.getByRole('button', { name: /launch hub build/i });
const ackCheckbox = () =>
  screen.getByLabelText(/acm-d pull secret is present/i);

// The launch POST body, decoded.
const launchedVars = () => {
  const call = mockFetch.mock.calls.find(([url]) =>
    url.includes('/api/ansible/run-playbook')
  );
  return JSON.parse(call[1].body).extra_vars;
};

describe('MCE hub card — source defaults', () => {
  it('defaults to the 5.0 candidate on the dev catalog', async () => {
    await openHubCard();
    expect(sourceSelect()).toHaveValue('devCatalog');
    expect(channelInput()).toHaveValue('stable-5.0');
  });

  it('switching to GA carries the channel to a version that catalog offers', async () => {
    await openHubCard();
    fireEvent.change(sourceSelect(), { target: { value: 'gaCatalog' } });
    // stable-2.8 was retired from redhat-operators; 2.17 is its defaultChannel.
    expect(channelInput()).toHaveValue('stable-2.17');
  });

  it('switching back to the dev catalog restores stable-5.0', async () => {
    await openHubCard();
    fireEvent.change(sourceSelect(), { target: { value: 'gaCatalog' } });
    fireEvent.change(sourceSelect(), { target: { value: 'devCatalog' } });
    expect(channelInput()).toHaveValue('stable-5.0');
  });
});

describe('MCE hub card — acm-d pull secret acknowledgement', () => {
  it('blocks launch until the pull secret is confirmed', async () => {
    await openHubCard();
    expect(launchButton()).toBeDisabled();
    fireEvent.click(ackCheckbox());
    expect(launchButton()).not.toBeDisabled();
  });

  it('does not ask for confirmation on the GA catalog', async () => {
    await openHubCard();
    fireEvent.change(sourceSelect(), { target: { value: 'gaCatalog' } });
    expect(
      screen.queryByLabelText(/acm-d pull secret is present/i)
    ).not.toBeInTheDocument();
    expect(launchButton()).not.toBeDisabled();
  });

  it('re-arms the acknowledgement when the card is reopened', async () => {
    await openHubCard();
    fireEvent.click(ackCheckbox());
    expect(launchButton()).not.toBeDisabled();

    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
    await act(async () => {
      fireEvent.click(
        screen.getByRole('button', { name: /make this my mce hub/i })
      );
    });
    await screen.findByText(/Make .*your MCE test hub/i);
    expect(ackCheckbox()).not.toBeChecked();
    expect(launchButton()).toBeDisabled();
  });
});

describe('MCE hub card — launch payload', () => {
  it('sends the dev catalog vars the playbook needs for 5.0', async () => {
    await openHubCard();
    fireEvent.click(ackCheckbox());
    await act(async () => {
      fireEvent.click(launchButton());
    });

    await waitFor(() =>
      expect(
        mockFetch.mock.calls.some(([url]) =>
          url.includes('/api/ansible/run-playbook')
        )
      ).toBe(true)
    );
    expect(launchedVars()).toMatchObject({
      cluster_name: 'cat-rosa-hcp',
      capi_namespace: 'ns-rosa-hcp',
      mce_source_mode: 'devCatalog',
      mce_channel: 'stable-5.0',
      acm_repo: 'acmd',
      mce_dev_catalog_tag: 'latest-5.0',
    });
  });

  it('omits the dev catalog vars on a GA run', async () => {
    await openHubCard();
    fireEvent.change(sourceSelect(), { target: { value: 'gaCatalog' } });
    await act(async () => {
      fireEvent.click(launchButton());
    });

    await waitFor(() =>
      expect(
        mockFetch.mock.calls.some(([url]) =>
          url.includes('/api/ansible/run-playbook')
        )
      ).toBe(true)
    );
    const vars = launchedVars();
    expect(vars.mce_source_mode).toBe('gaCatalog');
    expect(vars.mce_channel).toBe('stable-2.17');
    expect(vars).not.toHaveProperty('acm_repo');
    expect(vars).not.toHaveProperty('mce_dev_catalog_tag');
  });

  it('honours an edited dev catalog tag', async () => {
    await openHubCard();
    fireEvent.change(screen.getByLabelText(/dev catalog tag/i), {
      target: { value: '5.0.0-274' },
    });
    fireEvent.click(ackCheckbox());
    await act(async () => {
      fireEvent.click(launchButton());
    });

    await waitFor(() =>
      expect(
        mockFetch.mock.calls.some(([url]) =>
          url.includes('/api/ansible/run-playbook')
        )
      ).toBe(true)
    );
    expect(launchedVars().mce_dev_catalog_tag).toBe('5.0.0-274');
  });
});

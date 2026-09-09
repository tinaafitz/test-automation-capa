/**
 * Tests for the Express provisioning row.
 *
 * Motivating bugs:
 *  - the summary line rendered availableVersions[1] while handleSubmit sent
 *    defaultVersion, so the user was shown one version and provisioned another;
 *  - there was no way to reach a version OCM does not enumerate (5.0.0-rc.0).
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

jest.mock('../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
  API_ENDPOINTS: {
    VERSIONS: '/api/versions',
  },
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

// jsdom here has no webcrypto; the prefix generator needs getRandomValues.
Object.defineProperty(global, 'crypto', {
  value: { getRandomValues: (arr) => { arr[0] = 0xab; return arr; } },
  configurable: true,
});

import { ExpressProvision } from './RosaProvisionModal';

const respond = (body) => ({ ok: true, json: async () => body });

const STABLE = {
  versions: ['4.22.13', '4.22.12', '4.20.12'],
  pinned_versions: [],
  default_version: '4.22.13',
  channel_group: 'stable',
  source: 'ocm',
};

const CANDIDATE = {
  versions: ['5.0.0-rc.0', '4.22.13', '4.22.12'],
  pinned_versions: ['5.0.0-rc.0'],
  default_version: '4.22.13',
  channel_group: 'candidate',
  source: 'ocm',
};

const byChannel = (url) =>
  respond(url.includes('candidate') ? CANDIDATE : STABLE);

beforeEach(() => {
  mockFetch.mockReset();
  mockFetch.mockImplementation((url) => Promise.resolve(byChannel(url)));
});

const versionSelect = () => screen.getByLabelText('OpenShift Version');
const channelSelect = () => screen.getByLabelText('Channel');
const provisionButton = () => screen.getByRole('button', { name: /provision cluster/i });

// The version fetch disables Provision while it is in flight, so anything that
// changes the channel has to settle before a click can land.
const settled = () => waitFor(() => expect(provisionButton()).not.toBeDisabled());

const renderExpress = async (onSubmit = jest.fn()) => {
  render(<ExpressProvision onSubmit={onSubmit} />);
  await waitFor(() => expect(versionSelect()).not.toBeDisabled());
  return onSubmit;
};

describe('ExpressProvision version selection', () => {
  it('defaults to the version the API marks as default', async () => {
    await renderExpress();
    expect(versionSelect()).toHaveValue('4.22.13');
  });

  it('submits the version shown in the summary line', async () => {
    const onSubmit = await renderExpress();

    fireEvent.change(versionSelect(), { target: { value: '4.20.12' } });
    // Scoped to the summary line — the same string is also an <option>.
    expect(screen.getByText('4.20.12', { selector: 'span' })).toBeInTheDocument();

    fireEvent.click(provisionButton());
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].openShiftVersion).toBe('4.20.12');
  });

  it('refetches with the selected channel group', async () => {
    await renderExpress();
    fireEvent.change(channelSelect(), { target: { value: 'candidate' } });

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/versions?channel_group=candidate',
      ),
    );
  });

  it('labels pinned pre-release builds', async () => {
    await renderExpress();
    fireEvent.change(channelSelect(), { target: { value: 'candidate' } });

    await waitFor(() =>
      expect(screen.getByRole('option', { name: /5\.0\.0-rc\.0 \(pre-release\)/ })).toBeInTheDocument(),
    );
  });
});

describe('ExpressProvision 5.0 candidate quick pick', () => {
  it('submits 5.0.0-rc.0 on the candidate channel', async () => {
    const onSubmit = await renderExpress();

    fireEvent.click(screen.getByRole('button', { name: '5.0 candidate' }));
    await waitFor(() => expect(versionSelect()).toHaveValue('5.0.0-rc.0'));
    expect(channelSelect()).toHaveValue('candidate');

    await settled();
    fireEvent.click(provisionButton());
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      openShiftVersion: '5.0.0-rc.0',
      channelGroup: 'candidate',
    });
  });

  it('still works when the API does not enumerate 5.0.0-rc.0', async () => {
    // The pinned merge lives server-side; if it ever regresses, the preset
    // must not silently fall back to a different version.
    mockFetch.mockImplementation((url) =>
      Promise.resolve(
        respond(
          url.includes('candidate')
            ? { ...CANDIDATE, versions: ['4.22.13'], pinned_versions: [] }
            : STABLE,
        ),
      ),
    );
    const onSubmit = await renderExpress();

    fireEvent.click(screen.getByRole('button', { name: '5.0 candidate' }));
    await waitFor(() => expect(versionSelect()).toHaveValue('5.0.0-rc.0'));

    await settled();
    fireEvent.click(provisionButton());
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].openShiftVersion).toBe('5.0.0-rc.0');
    expect(screen.getByText(/Not in the candidate list/)).toBeInTheDocument();
  });

  it('keeps the preset version through the channel refetch', async () => {
    await renderExpress();
    fireEvent.click(screen.getByRole('button', { name: '5.0 candidate' }));

    await waitFor(() =>
      expect(mockFetch).toHaveBeenCalledWith(
        'http://localhost:8000/api/versions?channel_group=candidate',
      ),
    );
    // The response carries default_version 4.22.13; explicit intent wins.
    expect(versionSelect()).toHaveValue('5.0.0-rc.0');
  });

  it('follows the channel default for a "latest" pick', async () => {
    await renderExpress();
    fireEvent.click(screen.getByRole('button', { name: 'Latest candidate' }));

    await waitFor(() => expect(channelSelect()).toHaveValue('candidate'));
    await waitFor(() => expect(versionSelect()).toHaveValue('4.22.13'));
  });
});

describe('ExpressProvision manual override', () => {
  it('accepts a version that is not in the list', async () => {
    const onSubmit = await renderExpress();

    fireEvent.change(versionSelect(), { target: { value: '__other__' } });
    fireEvent.change(screen.getByPlaceholderText('5.0.0-rc.0'), {
      target: { value: '5.0.0-rc.1' },
    });

    fireEvent.click(provisionButton());
    await waitFor(() => expect(onSubmit).toHaveBeenCalled());
    expect(onSubmit.mock.calls[0][0].openShiftVersion).toBe('5.0.0-rc.1');
  });

  it('blocks submission on a malformed version', async () => {
    const onSubmit = await renderExpress();

    fireEvent.change(versionSelect(), { target: { value: '__other__' } });
    fireEvent.change(screen.getByPlaceholderText('5.0.0-rc.0'), {
      target: { value: 'abc' },
    });

    expect(provisionButton()).toBeDisabled();
    expect(screen.getByText(/Use x\.y\.z or x\.y\.z-rc\.N/)).toBeInTheDocument();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe('ExpressProvision degraded version list', () => {
  it('warns when the backend served its built-in list', async () => {
    mockFetch.mockImplementation(() =>
      Promise.resolve(respond({ ...STABLE, source: 'fallback', error: 'connection refused' })),
    );
    await renderExpress();

    expect(screen.getByText(/Couldn't reach OCM/)).toBeInTheDocument();
  });

  it('surfaces a fetch failure instead of submitting a guessed version', async () => {
    mockFetch.mockRejectedValue(new Error('network down'));
    const onSubmit = jest.fn();
    render(<ExpressProvision onSubmit={onSubmit} />);

    await waitFor(() => expect(screen.getByText(/Couldn't load versions/)).toBeInTheDocument());
    expect(provisionButton()).toBeDisabled();
    expect(onSubmit).not.toHaveBeenCalled();
  });
});

describe('ExpressProvision pre-release channel guard', () => {
  it('offers to switch a pre-release onto the candidate channel', async () => {
    await renderExpress();

    fireEvent.change(versionSelect(), { target: { value: '__other__' } });
    fireEvent.change(screen.getByPlaceholderText('5.0.0-rc.0'), {
      target: { value: '5.0.0-rc.0' },
    });

    expect(screen.getByText(/needs the candidate channel/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /switch to candidate/i }));
    await waitFor(() => expect(channelSelect()).toHaveValue('candidate'));
  });
});

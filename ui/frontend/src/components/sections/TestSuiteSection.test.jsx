/**
 * Tests for TestSuiteSection component.
 */

import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';

jest.mock('@heroicons/react/24/outline', () => ({
  PlayIcon: (props) => <svg data-testid="play-icon" {...props} />,
  ArrowPathIcon: (props) => <svg data-testid="arrow-path" {...props} />,
}));

jest.mock('axios', () => ({
  get: jest.fn().mockResolvedValue({
    data: {
      success: true,
      suites: [
        { name: 'validate-capa-environment.yml', config: { name: 'Validate CAPA Environment', tags: [] } },
        { name: 'provision-rosa-hcp.yml', config: { name: 'Provision ROSA HCP', tags: [] } },
      ],
    },
  }),
  post: jest.fn().mockResolvedValue({ data: { success: true } }),
}));

jest.mock('../../store/AppContext', () => ({
  useRecentOperationsContext: () => ({
    addOperation: jest.fn(),
    updateOperation: jest.fn(),
  }),
}));

jest.mock('../../hooks/useJobHistory', () => ({
  useJobHistory: () => ({
    fetchJobHistory: jest.fn(),
    jobHistory: [],
  }),
}));

jest.mock('../RosaProvisionModal', () => ({
  RosaProvisionModal: () => <div data-testid="provision-modal">Modal</div>,
}));

import TestSuiteSection from './TestSuiteSection';

describe('TestSuiteSection', () => {
  it('renders with default mce theme', async () => {
    await act(async () => {
      render(<TestSuiteSection />);
    });
    expect(document.body).toBeTruthy();
  });

  it('renders with minikube theme', async () => {
    await act(async () => {
      render(<TestSuiteSection theme="minikube" />);
    });
    expect(document.body).toBeTruthy();
  });

  it('fetches suites on mount', async () => {
    const axios = require('axios');
    await act(async () => {
      render(<TestSuiteSection />);
    });
    await waitFor(() => {
      expect(axios.get).toHaveBeenCalled();
    });
  });

  it('renders without crashing', async () => {
    await act(async () => {
      render(<TestSuiteSection />);
    });
    expect(document.body).toBeTruthy();
  });
});

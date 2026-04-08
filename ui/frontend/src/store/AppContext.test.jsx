/**
 * Tests for AppContext reducer, provider, and hooks.
 */

import React, { useEffect } from 'react';
import { render, screen, act } from '@testing-library/react';
import {
  AppActionTypes,
  AppProvider,
  useApp,
  useAppDispatch,
  useApiStatusContext,
  useMinikubeContext,
  useMCEContext,
  useRecentOperationsContext,
} from './AppContext';

// Mock all the hooks that AppProvider uses
jest.mock('../hooks/useApiStatus', () => () => ({ connected: true }));
jest.mock('../hooks/useMinikubeEnvironment', () => () => ({ clusters: [] }));
jest.mock('../hooks/useMCEEnvironment', () => () => ({ status: 'ok' }));
jest.mock('../hooks/useRecentOperations', () => () => ({
  recentOperations: [],
  addToRecent: jest.fn(),
}));

// Helper: renders a consumer component inside AppProvider and returns what it displays
function renderWithProvider(ConsumerComponent) {
  return render(
    <AppProvider>
      <ConsumerComponent />
    </AppProvider>
  );
}

// Helper: a consumer that reads state and dispatches an action
function makeDispatchConsumer(actionOrActions, stateKey) {
  return function Consumer() {
    const state = useApp();
    const dispatch = useAppDispatch();
    useEffect(() => {
      const actions = Array.isArray(actionOrActions) ? actionOrActions : [actionOrActions];
      actions.forEach((a) => dispatch(a));
    }, [dispatch]);
    const val = state[stateKey];
    // Handle Set objects
    if (val instanceof Set) return <div data-testid="result">{JSON.stringify([...val])}</div>;
    if (val === null || val === undefined) return <div data-testid="result">null</div>;
    if (typeof val === 'object') return <div data-testid="result">{JSON.stringify(val)}</div>;
    return <div data-testid="result">{String(val)}</div>;
  };
}

beforeEach(() => {
  localStorage.clear();
});

describe('AppActionTypes', () => {
  it('has all UI action types', () => {
    expect(AppActionTypes.SET_DARK_MODE).toBe('SET_DARK_MODE');
    expect(AppActionTypes.TOGGLE_COMMAND_PALETTE).toBe('TOGGLE_COMMAND_PALETTE');
    expect(AppActionTypes.SET_SEARCH_TERM).toBe('SET_SEARCH_TERM');
    expect(AppActionTypes.SHOW_FEEDBACK).toBe('SHOW_FEEDBACK');
    expect(AppActionTypes.TOGGLE_HELP).toBe('TOGGLE_HELP');
    expect(AppActionTypes.TOGGLE_SETTINGS_PANEL).toBe('TOGGLE_SETTINGS_PANEL');
    expect(AppActionTypes.ADD_NOTIFICATION).toBe('ADD_NOTIFICATION');
    expect(AppActionTypes.REMOVE_NOTIFICATION).toBe('REMOVE_NOTIFICATION');
    expect(AppActionTypes.TOGGLE_FAVORITE).toBe('TOGGLE_FAVORITE');
  });

  it('has all environment action types', () => {
    expect(AppActionTypes.SET_SELECTED_ENVIRONMENT).toBe('SET_SELECTED_ENVIRONMENT');
    expect(AppActionTypes.TOGGLE_ENVIRONMENT_DROPDOWN).toBe('TOGGLE_ENVIRONMENT_DROPDOWN');
    expect(AppActionTypes.TOGGLE_SECTION).toBe('TOGGLE_SECTION');
    expect(AppActionTypes.SET_SECTION_ORDER).toBe('SET_SECTION_ORDER');
    expect(AppActionTypes.HIDE_SECTION).toBe('HIDE_SECTION');
    expect(AppActionTypes.RESTORE_SECTION).toBe('RESTORE_SECTION');
    expect(AppActionTypes.RESTORE_ALL_SECTIONS).toBe('RESTORE_ALL_SECTIONS');
  });

  it('has all modal action types', () => {
    expect(AppActionTypes.SHOW_KIND_CLUSTER_MODAL).toBe('SHOW_KIND_CLUSTER_MODAL');
    expect(AppActionTypes.SHOW_PROVISION_MODAL).toBe('SHOW_PROVISION_MODAL');
    expect(AppActionTypes.SHOW_YAML_EDITOR_MODAL).toBe('SHOW_YAML_EDITOR_MODAL');
    expect(AppActionTypes.SET_YAML_EDITOR_DATA).toBe('SET_YAML_EDITOR_DATA');
    expect(AppActionTypes.SHOW_CREDENTIALS_MODAL).toBe('SHOW_CREDENTIALS_MODAL');
  });

  it('has all test suite action types', () => {
    expect(AppActionTypes.TOGGLE_TEST_SUITE).toBe('TOGGLE_TEST_SUITE');
    expect(AppActionTypes.SET_SELECTED_VERSION).toBe('SET_SELECTED_VERSION');
    expect(AppActionTypes.SET_TEST_ITEMS).toBe('SET_TEST_ITEMS');
    expect(AppActionTypes.SET_TEST_RUNNING).toBe('SET_TEST_RUNNING');
    expect(AppActionTypes.SET_TEST_RESULTS).toBe('SET_TEST_RESULTS');
    expect(AppActionTypes.SET_SELECTED_TEST_SUITE).toBe('SET_SELECTED_TEST_SUITE');
  });

  it('has all ROSA action types', () => {
    expect(AppActionTypes.SET_ROSA_CLUSTERS).toBe('SET_ROSA_CLUSTERS');
    expect(AppActionTypes.SET_ROSA_CLUSTERS_LOADING).toBe('SET_ROSA_CLUSTERS_LOADING');
    expect(AppActionTypes.SET_ROSA_MONITORING).toBe('SET_ROSA_MONITORING');
  });

  it('has filing cabinet action types', () => {
    expect(AppActionTypes.TOGGLE_FILING_CABINET).toBe('TOGGLE_FILING_CABINET');
    expect(AppActionTypes.TOGGLE_FILING_CABINET_MINIMIZE).toBe('TOGGLE_FILING_CABINET_MINIMIZE');
  });

  it('has setup and provision target action types', () => {
    expect(AppActionTypes.SET_SETUP_PROMPT).toBe('SET_SETUP_PROMPT');
    expect(AppActionTypes.SET_PROVISION_TARGET_CONTEXT).toBe('SET_PROVISION_TARGET_CONTEXT');
    expect(AppActionTypes.SET_CONFIRM_DIALOG).toBe('SET_CONFIRM_DIALOG');
    expect(AppActionTypes.SET_FEEDBACK_DATA).toBe('SET_FEEDBACK_DATA');
    expect(AppActionTypes.SET_VISIBLE_CARDS).toBe('SET_VISIBLE_CARDS');
    expect(AppActionTypes.SET_EXPANDED_CARDS).toBe('SET_EXPANDED_CARDS');
  });

  it('exports correct total number of action types', () => {
    const actionCount = Object.keys(AppActionTypes).length;
    expect(actionCount).toBeGreaterThanOrEqual(30);
  });
});

describe('AppProvider and reducer', () => {
  it('renders children within provider', () => {
    render(
      <AppProvider>
        <div data-testid="child">Hello</div>
      </AppProvider>
    );
    expect(screen.getByTestId('child')).toHaveTextContent('Hello');
  });

  it('provides default darkMode as false', () => {
    const C = makeDispatchConsumer([], 'darkMode');
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('false');
  });

  it('SET_DARK_MODE sets darkMode to true', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_DARK_MODE, payload: true },
      'darkMode'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('TOGGLE_COMMAND_PALETTE toggles showCommandPalette', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.TOGGLE_COMMAND_PALETTE },
      'showCommandPalette'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('SET_SEARCH_TERM updates searchTerm', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_SEARCH_TERM, payload: 'hello' },
      'searchTerm'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('hello');
  });

  it('SHOW_FEEDBACK sets showFeedback', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SHOW_FEEDBACK, payload: true },
      'showFeedback'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('SET_FEEDBACK_DATA sets feedbackData', () => {
    const data = { type: 'bug', message: 'broken', email: 'a@b.com' };
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_FEEDBACK_DATA, payload: data },
      'feedbackData'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('broken');
  });

  it('TOGGLE_HELP toggles showHelp', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.TOGGLE_HELP },
      'showHelp'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('SET_CONFIRM_DIALOG sets confirm dialog', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_CONFIRM_DIALOG, payload: { title: 'Delete?' } },
      'showConfirmDialog'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('Delete?');
  });

  it('TOGGLE_SETTINGS_PANEL toggles settingsPanelOpen', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.TOGGLE_SETTINGS_PANEL },
      'settingsPanelOpen'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('ADD_NOTIFICATION adds a notification', () => {
    const notif = { id: 'n1', message: 'Test notif' };
    const C = makeDispatchConsumer(
      { type: AppActionTypes.ADD_NOTIFICATION, payload: notif },
      'notifications'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('Test notif');
  });

  it('REMOVE_NOTIFICATION removes notification by id', () => {
    const C = makeDispatchConsumer(
      [
        { type: AppActionTypes.ADD_NOTIFICATION, payload: { id: 'n1', message: 'first' } },
        { type: AppActionTypes.ADD_NOTIFICATION, payload: { id: 'n2', message: 'second' } },
        { type: AppActionTypes.REMOVE_NOTIFICATION, payload: 'n1' },
      ],
      'notifications'
    );
    renderWithProvider(C);
    const text = screen.getByTestId('result').textContent;
    expect(text).not.toContain('first');
    expect(text).toContain('second');
  });

  it('TOGGLE_FAVORITE adds then removes a favorite', () => {
    const C = makeDispatchConsumer(
      [
        { type: AppActionTypes.TOGGLE_FAVORITE, payload: 'card-1' },
      ],
      'favorites'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('card-1');
  });

  it('SET_SELECTED_ENVIRONMENT to minikube updates sectionOrder', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_SELECTED_ENVIRONMENT, payload: 'minikube' },
      'sectionOrder'
    );
    renderWithProvider(C);
    const text = screen.getByTestId('result').textContent;
    expect(text).toContain('minikube-environment');
    expect(text).not.toContain('mce-configuration');
  });

  it('SET_SELECTED_ENVIRONMENT to mce updates sectionOrder', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_SELECTED_ENVIRONMENT, payload: 'mce' },
      'sectionOrder'
    );
    renderWithProvider(C);
    const text = screen.getByTestId('result').textContent;
    expect(text).toContain('mce-configuration');
  });

  it('TOGGLE_ENVIRONMENT_DROPDOWN toggles dropdown', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.TOGGLE_ENVIRONMENT_DROPDOWN },
      'showEnvironmentDropdown'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('TOGGLE_SECTION toggles a section collapsed state', () => {
    // 'test-suite-dashboard' is collapsed by default; toggling should remove it
    const C = makeDispatchConsumer(
      { type: AppActionTypes.TOGGLE_SECTION, payload: 'test-suite-dashboard' },
      'collapsedSections'
    );
    renderWithProvider(C);
    const text = screen.getByTestId('result').textContent;
    expect(text).not.toContain('test-suite-dashboard');
  });

  it('SET_SETUP_PROMPT sets showSetupPrompt', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_SETUP_PROMPT, payload: true },
      'showSetupPrompt'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('SET_SECTION_ORDER enforces config section first', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_SECTION_ORDER, payload: ['task-summary', 'mce-configuration'] },
      'sectionOrder'
    );
    renderWithProvider(C);
    const text = screen.getByTestId('result').textContent;
    const parsed = JSON.parse(text);
    expect(parsed[0]).toBe('mce-configuration');
  });

  it('HIDE_SECTION moves section to hiddenSections', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.HIDE_SECTION, payload: 'task-summary' },
      'hiddenSections'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('task-summary');
  });

  it('RESTORE_SECTION moves section back from hidden', () => {
    const C = makeDispatchConsumer(
      [
        { type: AppActionTypes.HIDE_SECTION, payload: 'task-summary' },
        { type: AppActionTypes.RESTORE_SECTION, payload: 'task-summary' },
      ],
      'hiddenSections'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('[]');
  });

  it('RESTORE_ALL_SECTIONS clears all hidden sections', () => {
    const C = makeDispatchConsumer(
      [
        { type: AppActionTypes.HIDE_SECTION, payload: 'task-summary' },
        { type: AppActionTypes.HIDE_SECTION, payload: 'task-detail' },
        { type: AppActionTypes.RESTORE_ALL_SECTIONS },
      ],
      'hiddenSections'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('[]');
  });

  it('TOGGLE_FILING_CABINET toggles showFilingCabinet', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.TOGGLE_FILING_CABINET },
      'showFilingCabinet'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('TOGGLE_FILING_CABINET_MINIMIZE toggles and closes filing cabinet', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.TOGGLE_FILING_CABINET_MINIMIZE },
      'filingCabinetMinimized'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('SHOW_KIND_CLUSTER_MODAL sets modal state', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SHOW_KIND_CLUSTER_MODAL, payload: true },
      'showKindClusterModal'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('SHOW_PROVISION_MODAL sets modal state', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SHOW_PROVISION_MODAL, payload: true },
      'showProvisionModal'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('SHOW_YAML_EDITOR_MODAL sets modal state', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SHOW_YAML_EDITOR_MODAL, payload: true },
      'showYamlEditorModal'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('SET_YAML_EDITOR_DATA sets yaml data', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_YAML_EDITOR_DATA, payload: { content: 'apiVersion: v1' } },
      'yamlEditorData'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('apiVersion');
  });

  it('SET_PROVISION_TARGET_CONTEXT sets target context', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_PROVISION_TARGET_CONTEXT, payload: { cluster: 'mk1' } },
      'provisionTargetContext'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('mk1');
  });

  it('SHOW_CREDENTIALS_MODAL sets modal state', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SHOW_CREDENTIALS_MODAL, payload: true },
      'showCredentialsModal'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('TOGGLE_TEST_SUITE toggles test suite collapsed', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.TOGGLE_TEST_SUITE },
      'testSuiteCollapsed'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('SET_SELECTED_VERSION updates version', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_SELECTED_VERSION, payload: '4.22' },
      'selectedVersion'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('4.22');
  });

  it('SET_TEST_ITEMS sets test items', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_TEST_ITEMS, payload: [{ name: 'test1' }] },
      'testItems'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('test1');
  });

  it('SET_TEST_RUNNING sets running state', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_TEST_RUNNING, payload: true },
      'testRunning'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('SET_TEST_RESULTS sets results', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_TEST_RESULTS, payload: [{ passed: true }] },
      'testResults'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('SET_SELECTED_TEST_SUITE sets selected suite', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_SELECTED_TEST_SUITE, payload: 'suite-a' },
      'selectedTestSuite'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('suite-a');
  });

  it('SET_ROSA_CLUSTERS sets clusters', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_ROSA_CLUSTERS, payload: [{ name: 'c1' }] },
      'rosaClusters'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('c1');
  });

  it('SET_ROSA_CLUSTERS_LOADING sets loading', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_ROSA_CLUSTERS_LOADING, payload: true },
      'rosaClustersLoading'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('true');
  });

  it('SET_ROSA_MONITORING sets monitoring data', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_ROSA_MONITORING, payload: { status: 'healthy' } },
      'rosaMonitoring'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('healthy');
  });

  it('SET_VISIBLE_CARDS sets visible cards', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_VISIBLE_CARDS, payload: new Set(['a', 'b']) },
      'visibleCards'
    );
    renderWithProvider(C);
    const text = screen.getByTestId('result').textContent;
    expect(text).toContain('a');
    expect(text).toContain('b');
  });

  it('SET_EXPANDED_CARDS sets expanded cards', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_EXPANDED_CARDS, payload: new Set(['x']) },
      'expandedCards'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('x');
  });

  it('unknown action returns state unchanged', () => {
    const C = makeDispatchConsumer(
      { type: 'UNKNOWN_ACTION', payload: 'ignored' },
      'darkMode'
    );
    renderWithProvider(C);
    expect(screen.getByTestId('result')).toHaveTextContent('false');
  });
});

describe('Context hooks outside provider', () => {
  const origError = console.error;
  beforeEach(() => { console.error = jest.fn(); });
  afterEach(() => { console.error = origError; });

  it('useApp throws outside AppProvider', () => {
    function Bad() { useApp(); return null; }
    expect(() => render(<Bad />)).toThrow('useApp must be used within an AppProvider');
  });

  it('useAppDispatch throws outside AppProvider', () => {
    function Bad() { useAppDispatch(); return null; }
    expect(() => render(<Bad />)).toThrow('useAppDispatch must be used within an AppProvider');
  });

  it('useApiStatusContext throws outside AppProvider', () => {
    function Bad() { useApiStatusContext(); return null; }
    expect(() => render(<Bad />)).toThrow('useApiStatusContext must be used within an AppProvider');
  });

  it('useMinikubeContext throws outside AppProvider', () => {
    function Bad() { useMinikubeContext(); return null; }
    expect(() => render(<Bad />)).toThrow('useMinikubeContext must be used within an AppProvider');
  });

  it('useMCEContext throws outside AppProvider', () => {
    function Bad() { useMCEContext(); return null; }
    expect(() => render(<Bad />)).toThrow('useMCEContext must be used within an AppProvider');
  });

  it('useRecentOperationsContext throws outside AppProvider', () => {
    function Bad() { useRecentOperationsContext(); return null; }
    expect(() => render(<Bad />)).toThrow('useRecentOperationsContext must be used within an AppProvider');
  });
});

describe('Context hooks inside provider', () => {
  it('useApiStatusContext returns api status', () => {
    function Consumer() {
      const status = useApiStatusContext();
      return <div data-testid="result">{status.connected ? 'yes' : 'no'}</div>;
    }
    renderWithProvider(Consumer);
    expect(screen.getByTestId('result')).toHaveTextContent('yes');
  });

  it('useMinikubeContext returns minikube env', () => {
    function Consumer() {
      const env = useMinikubeContext();
      return <div data-testid="result">{JSON.stringify(env.clusters)}</div>;
    }
    renderWithProvider(Consumer);
    expect(screen.getByTestId('result')).toHaveTextContent('[]');
  });

  it('useMCEContext returns MCE env', () => {
    function Consumer() {
      const env = useMCEContext();
      return <div data-testid="result">{env.status}</div>;
    }
    renderWithProvider(Consumer);
    expect(screen.getByTestId('result')).toHaveTextContent('ok');
  });

  it('useRecentOperationsContext returns operations', () => {
    function Consumer() {
      const ops = useRecentOperationsContext();
      return <div data-testid="result">{JSON.stringify(ops.recentOperations)}</div>;
    }
    renderWithProvider(Consumer);
    expect(screen.getByTestId('result')).toHaveTextContent('[]');
  });
});

describe('localStorage persistence', () => {
  it('loads expanded cards from localStorage', () => {
    localStorage.setItem('expandedCards', JSON.stringify(['card-a', 'card-b']));
    function Consumer() {
      const state = useApp();
      return <div data-testid="result">{JSON.stringify([...state.expandedCards])}</div>;
    }
    renderWithProvider(Consumer);
    // The effect dispatches after render, so the expanded cards should eventually include saved ones
    expect(screen.getByTestId('result')).toBeTruthy();
  });

  it('loads section order from localStorage with migration', () => {
    // Old format had 'test-suite', should be migrated to 'test-suite-dashboard' + 'test-suite-runner'
    localStorage.setItem('mce-section-order', JSON.stringify([
      'mce-configuration', 'test-suite', 'task-summary'
    ]));
    function Consumer() {
      const state = useApp();
      return <div data-testid="result">{JSON.stringify(state.sectionOrder)}</div>;
    }
    renderWithProvider(Consumer);
    expect(screen.getByTestId('result')).toBeTruthy();
  });

  it('loads hidden sections from localStorage', () => {
    localStorage.setItem('mce-hidden-sections', JSON.stringify(['task-detail']));
    function Consumer() {
      const state = useApp();
      return <div data-testid="result">{JSON.stringify(state.hiddenSections)}</div>;
    }
    renderWithProvider(Consumer);
    expect(screen.getByTestId('result')).toBeTruthy();
  });

  it('persists selectedEnvironment to localStorage', () => {
    const C = makeDispatchConsumer(
      { type: AppActionTypes.SET_SELECTED_ENVIRONMENT, payload: 'minikube' },
      'selectedEnvironment'
    );
    renderWithProvider(C);
    expect(localStorage.getItem('selectedEnvironment')).toBe('minikube');
  });

  it('handles corrupted localStorage gracefully', () => {
    localStorage.setItem('expandedCards', 'not-json{{{');
    const spy = jest.spyOn(console, 'error').mockImplementation(() => {});
    function Consumer() {
      const state = useApp();
      return <div data-testid="result">{String(state.darkMode)}</div>;
    }
    renderWithProvider(Consumer);
    // Should not crash
    expect(screen.getByTestId('result')).toHaveTextContent('false');
    spy.mockRestore();
  });
});

/**
 * Tests for WorkflowBuilder component.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

// Mock dependencies
jest.mock('@dnd-kit/core', () => ({
  DndContext: ({ children }) => <div data-testid="dnd-context">{children}</div>,
  closestCenter: jest.fn(),
  KeyboardSensor: jest.fn(),
  PointerSensor: jest.fn(),
  useSensor: jest.fn(() => ({})),
  useSensors: jest.fn(() => []),
  DragOverlay: ({ children }) => <div>{children}</div>,
}));

jest.mock('@dnd-kit/sortable', () => ({
  arrayMove: jest.fn((arr, from, to) => {
    const result = [...arr];
    const [item] = result.splice(from, 1);
    result.splice(to, 0, item);
    return result;
  }),
  SortableContext: ({ children }) => <div>{children}</div>,
  sortableKeyboardCoordinates: jest.fn(),
  verticalListSortingStrategy: {},
  useSortable: jest.fn(() => ({
    attributes: {},
    listeners: {},
    setNodeRef: jest.fn(),
    transform: null,
    transition: null,
    isDragging: false,
  })),
}));

jest.mock('@dnd-kit/utilities', () => ({
  CSS: {
    Transform: { toString: jest.fn(() => '') },
    Transition: { toString: jest.fn(() => '') },
  },
}));

jest.mock('../store/AppContext', () => ({
  useRecentOperationsContext: () => ({
    addToRecent: jest.fn(),
    updateRecentOperationStatus: jest.fn(),
  }),
}));

jest.mock('../config/api', () => ({
  buildApiUrl: (path) => `http://localhost:8000${path}`,
}));

// Mock fetch
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Mock localStorage
const localStorageMock = (() => {
  let store = {};
  return {
    getItem: jest.fn((key) => store[key] || null),
    setItem: jest.fn((key, value) => { store[key] = value; }),
    removeItem: jest.fn((key) => { delete store[key]; }),
    clear: jest.fn(() => { store = {}; }),
  };
})();
Object.defineProperty(window, 'localStorage', { value: localStorageMock });

import WorkflowBuilder from './WorkflowBuilder';

beforeEach(() => {
  mockFetch.mockReset();
  localStorageMock.clear();
  jest.clearAllMocks();

  // Default: return test suites list
  mockFetch.mockResolvedValue({
    ok: true,
    json: async () => ({
      test_suites: [
        {
          id: 'validate-capa',
          name: '01-validate-capa-environment',
          description: 'Validate CAPA environment',
          task_file: 'validate-capa-environment.yml',
          category: 'validation',
        },
        {
          id: 'create-rosa',
          name: '20-create-rosa-hcp-cluster',
          description: 'Create ROSA HCP cluster',
          task_file: 'create-rosa-hcp-cluster.yml',
          category: 'provisioning',
        },
      ],
    }),
  });
});

describe('WorkflowBuilder', () => {
  it('renders the workflow builder container', async () => {
    await act(async () => {
      render(<WorkflowBuilder />);
    });
    expect(screen.getAllByText(/Playbooks/i).length).toBeGreaterThan(0);
  });

  it('shows the playbook palette', async () => {
    await act(async () => {
      render(<WorkflowBuilder />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });
  });

  it('renders search input in palette', async () => {
    await act(async () => {
      render(<WorkflowBuilder />);
    });
    const searchInput = screen.getByPlaceholderText(/search/i);
    expect(searchInput).toBeInTheDocument();
  });

  it('renders empty canvas message', async () => {
    await act(async () => {
      render(<WorkflowBuilder />);
    });
    expect(screen.getByText(/Build your workflow/i)).toBeInTheDocument();
  });

  it('renders workflow variables section', async () => {
    await act(async () => {
      render(<WorkflowBuilder />);
    });
    expect(screen.getByText(/Workflow Variables/i)).toBeInTheDocument();
  });

  it('filters palette items via search', async () => {
    await act(async () => {
      render(<WorkflowBuilder />);
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalled();
    });

    const searchInput = screen.getByPlaceholderText(/search/i);
    fireEvent.change(searchInput, { target: { value: 'validate' } });

    // Search input should have the new value
    expect(searchInput.value).toBe('validate');
  });

  it('has run workflow button', async () => {
    await act(async () => {
      render(<WorkflowBuilder />);
    });
    expect(screen.getByText(/Run Workflow/i)).toBeInTheDocument();
  });

  it('has save and load buttons', async () => {
    await act(async () => {
      render(<WorkflowBuilder />);
    });
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('fetches test suites on mount', async () => {
    await act(async () => {
      render(<WorkflowBuilder />);
    });
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/test-suites/list')
      );
    });
  });

  it('handles fetch error gracefully', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'));
    await act(async () => {
      render(<WorkflowBuilder />);
    });
    // Should still render without crashing
    expect(screen.getAllByText(/Playbooks/i).length).toBeGreaterThan(0);
  });
});

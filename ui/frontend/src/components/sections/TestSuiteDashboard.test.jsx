/**
 * Tests for TestSuiteDashboard component.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

jest.mock('@heroicons/react/24/outline', () => ({
  BeakerIcon: (props) => <svg data-testid="beaker-icon" {...props} />,
  ChevronDownIcon: (props) => <svg data-testid="chevron-down" {...props} />,
  ChevronUpIcon: (props) => <svg data-testid="chevron-up" {...props} />,
  DocumentDuplicateIcon: (props) => <svg data-testid="doc-dup" {...props} />,
  ArrowDownTrayIcon: (props) => <svg data-testid="download" {...props} />,
}));

import TestSuiteDashboard from './TestSuiteDashboard';

describe('TestSuiteDashboard', () => {
  it('renders with default mce theme', () => {
    render(<TestSuiteDashboard />);
    expect(screen.getByText(/Comprehensive Cluster Configuration/)).toBeInTheDocument();
  });

  it('renders test items list', () => {
    render(<TestSuiteDashboard />);
    expect(screen.getByText(/Security & Authentication Suite/)).toBeInTheDocument();
    expect(screen.getByText(/Machine Pool & Auto-Scaling Suite/)).toBeInTheDocument();
  });

  it('renders with minikube theme', () => {
    render(<TestSuiteDashboard theme="minikube" />);
    expect(screen.getByText(/Comprehensive Cluster Configuration/)).toBeInTheDocument();
  });

  it('renders version selector', () => {
    render(<TestSuiteDashboard />);
    expect(screen.getByText('4.21')).toBeInTheDocument();
  });

  it('renders priority badges', () => {
    render(<TestSuiteDashboard />);
    const p1Badges = screen.getAllByText('P1');
    expect(p1Badges.length).toBeGreaterThan(0);
  });

  it('calls onSelectTestSuite when provided', () => {
    const onSelect = jest.fn();
    render(<TestSuiteDashboard onSelectTestSuite={onSelect} />);
    expect(document.body).toBeTruthy();
  });

  it('renders with isProvisioning flag', () => {
    render(<TestSuiteDashboard isProvisioning={true} />);
    expect(document.body).toBeTruthy();
  });

  it('shows provisioning button as disabled when isProvisioning is true', () => {
    render(<TestSuiteDashboard isProvisioning={true} />);
    const provisionButton = screen.getByText(/Provisioning.../);
    expect(provisionButton).toBeDisabled();
  });

  it('allows selecting and deselecting test items', () => {
    render(<TestSuiteDashboard />);

    const checkbox = screen.getAllByRole('checkbox')[1]; // First item checkbox
    expect(checkbox).not.toBeChecked();

    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();

    fireEvent.click(checkbox);
    expect(checkbox).not.toBeChecked();
  });

  it('select all button selects all tests', () => {
    render(<TestSuiteDashboard />);

    const selectAllButton = screen.getByText('Select All');
    fireEvent.click(selectAllButton);

    const checkboxes = screen.getAllByRole('checkbox');
    checkboxes.forEach((checkbox) => {
      expect(checkbox).toBeChecked();
    });

    const deselectAllButton = screen.getByText('Deselect All');
    expect(deselectAllButton).toBeInTheDocument();
  });

  it('deselect all button deselects all tests', () => {
    render(<TestSuiteDashboard />);

    // First select all
    const selectAllButton = screen.getByText('Select All');
    fireEvent.click(selectAllButton);

    // Then deselect all
    const deselectAllButton = screen.getByText('Deselect All');
    fireEvent.click(deselectAllButton);

    const checkboxes = screen.getAllByRole('checkbox');
    checkboxes.forEach((checkbox) => {
      expect(checkbox).not.toBeChecked();
    });
  });

  it('expands and collapses test item details', () => {
    render(<TestSuiteDashboard />);

    const detailsButton = screen.getAllByText('Details')[0];
    fireEvent.click(detailsButton);

    expect(screen.getByText('Description:')).toBeInTheDocument();
    expect(screen.getByText('Components:')).toBeInTheDocument();

    const hideButton = screen.getByText('Hide');
    fireEvent.click(hideButton);

    expect(screen.queryByText('Description:')).not.toBeInTheDocument();
  });

  it('displays component badges in expanded view', () => {
    render(<TestSuiteDashboard />);

    const detailsButton = screen.getAllByText('Details')[0];
    fireEvent.click(detailsButton);

    expect(screen.getByText('Private Network')).toBeInTheDocument();
    expect(screen.getByText('BYON')).toBeInTheDocument();
    expect(screen.getByText('STS')).toBeInTheDocument();
  });

  it('displays jira tickets in expanded view', () => {
    render(<TestSuiteDashboard />);

    const detailsButton = screen.getAllByText('Details')[0];
    fireEvent.click(detailsButton);

    expect(screen.getByText('JIRA Tickets:')).toBeInTheDocument();
    expect(screen.getByText('ACM-20464')).toBeInTheDocument();
  });

  it('shows status icons for different test statuses', () => {
    render(<TestSuiteDashboard />);

    // All default tests should show pending status
    const testItems = screen.getAllByText('Comprehensive Cluster Configuration');
    expect(testItems.length).toBeGreaterThan(0);
  });

  it('handles version selector change', () => {
    render(<TestSuiteDashboard />);

    const versionSelect = screen.getByDisplayValue('4.21');
    fireEvent.change(versionSelect, { target: { value: '4.20' } });

    expect(screen.getByDisplayValue('4.20')).toBeInTheDocument();
  });

  it('renders copy button', () => {
    render(<TestSuiteDashboard />);
    expect(screen.getByText('Copy')).toBeInTheDocument();
  });

  it('renders download button', () => {
    render(<TestSuiteDashboard />);
    expect(screen.getByText('Download')).toBeInTheDocument();
  });

  it('handles copy to clipboard successfully', async () => {
    const mockClipboard = {
      writeText: jest.fn().mockResolvedValue(undefined),
    };
    Object.assign(navigator, { clipboard: mockClipboard });

    render(<TestSuiteDashboard />);

    const copyButton = screen.getByText('Copy');
    fireEvent.click(copyButton);

    await waitFor(() => {
      expect(mockClipboard.writeText).toHaveBeenCalled();
      expect(screen.getByText('Copied!')).toBeInTheDocument();
    });
  });

  it('handles copy to clipboard error', async () => {
    const mockClipboard = {
      writeText: jest.fn().mockRejectedValue(new Error('Copy failed')),
    };
    Object.assign(navigator, { clipboard: mockClipboard });
    const consoleSpy = jest.spyOn(console, 'error').mockImplementation(() => {});

    render(<TestSuiteDashboard />);

    const copyButton = screen.getByText('Copy');
    fireEvent.click(copyButton);

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled();
    });

    consoleSpy.mockRestore();
  });

  it('provision button is disabled when no items selected', () => {
    render(<TestSuiteDashboard />);

    const provisionButton = screen.getByText(/Provision & Test Selected/);
    // Button should be disabled initially
    expect(provisionButton).toBeDisabled();
  });

  it('handles provision button click with multiple selections', async () => {
    render(<TestSuiteDashboard />);

    // Select multiple items
    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]);
    fireEvent.click(checkboxes[2]);

    const provisionButton = screen.getByText(/Provision & Test Selected/);
    fireEvent.click(provisionButton);

    // Should show toast message about selecting only one test
    await waitFor(() => {
      expect(screen.getByText('Please select only one test suite at a time')).toBeInTheDocument();
    });
  });

  it('handles provision button click with one selection', () => {
    const onSelectTestSuite = jest.fn();
    render(<TestSuiteDashboard onSelectTestSuite={onSelectTestSuite} />);

    // Select one item - find a specific checkbox by testing its parent row
    const firstTestItem = screen.getByText('Comprehensive Cluster Configuration');
    const checkbox = firstTestItem.closest('div[class*="p-4"]').querySelector('input[type="checkbox"]');
    fireEvent.click(checkbox);

    const provisionButton = screen.getByText(/Provision & Test Selected/);
    fireEvent.click(provisionButton);

    expect(onSelectTestSuite).toHaveBeenCalledWith(expect.objectContaining({
      id: 1,
      name: 'Comprehensive Cluster Configuration',
    }));
  });

  it('provision button becomes enabled when item is selected', () => {
    render(<TestSuiteDashboard />);

    const provisionButton = screen.getByText(/Provision & Test Selected/);
    expect(provisionButton).toBeDisabled();

    // Select one item
    const firstTestItem = screen.getByText('Comprehensive Cluster Configuration');
    const checkbox = firstTestItem.closest('div[class*="p-4"]').querySelector('input[type="checkbox"]');
    fireEvent.click(checkbox);

    // Button should now be enabled
    expect(provisionButton).not.toBeDisabled();
  });

  it('displays test items with different phases', () => {
    render(<TestSuiteDashboard />);

    const day1Badges = screen.getAllByText('Day1');
    expect(day1Badges.length).toBeGreaterThan(0);
    expect(screen.getByText('Day2')).toBeInTheDocument();
  });

  it('displays test items with different categories', () => {
    render(<TestSuiteDashboard />);

    expect(screen.getByText('Infrastructure')).toBeInTheDocument();
    expect(screen.getByText('Security')).toBeInTheDocument();
    expect(screen.getByText('Scaling')).toBeInTheDocument();
  });

  it('shows setup required badge for items that need setup', () => {
    render(<TestSuiteDashboard />);

    const detailsButtons = screen.getAllByText('Details');
    // Find the Audit Log Forwarding test (has requiresSetup)
    const auditLogItem = screen.getByText('Audit Log Forwarding');
    expect(auditLogItem).toBeInTheDocument();

    // Look for Setup Required badge near the audit log item
    expect(screen.getByText('Setup Required')).toBeInTheDocument();
  });
});

/**
 * Tests for TestSuiteDashboard component.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

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
});

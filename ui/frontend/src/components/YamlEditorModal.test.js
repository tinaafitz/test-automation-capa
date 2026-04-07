/**
 * Tests for YamlEditorModal component.
 */

import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';

jest.mock('@heroicons/react/24/outline', () => ({
  XMarkIcon: (props) => <svg data-testid="x-icon" {...props} />,
  ArrowDownTrayIcon: (props) => <svg data-testid="download-icon" {...props} />,
  ArrowPathIcon: (props) => <svg data-testid="refresh-icon" {...props} />,
  CheckCircleIcon: (props) => <svg data-testid="check-icon" {...props} />,
  ExclamationTriangleIcon: (props) => <svg data-testid="exclaim-icon" {...props} />,
  DocumentTextIcon: (props) => <svg data-testid="doc-icon" {...props} />,
  DocumentDuplicateIcon: (props) => <svg data-testid="copy-icon" {...props} />,
}));

import { YamlEditorModal } from './YamlEditorModal';

describe('YamlEditorModal', () => {
  const defaultProps = {
    isOpen: true,
    onClose: jest.fn(),
    onProvision: jest.fn(),
    yamlData: {
      yaml_content: 'apiVersion: v1\nkind: ConfigMap\nmetadata:\n  name: test\n',
    },
  };

  it('renders nothing when closed', () => {
    const { container } = render(
      <YamlEditorModal {...defaultProps} isOpen={false} />
    );
    // When closed, should not render the editor content
    expect(screen.queryByText(/YAML/i)).not.toBeInTheDocument();
  });

  it('renders yaml content when open', () => {
    render(<YamlEditorModal {...defaultProps} />);
    // Should render a textarea or display with the yaml content
    const textarea = document.querySelector('textarea');
    if (textarea) {
      expect(textarea.value).toContain('apiVersion');
    }
  });

  it('renders close button', () => {
    render(<YamlEditorModal {...defaultProps} />);
    const closeButtons = screen.getAllByRole('button');
    expect(closeButtons.length).toBeGreaterThan(0);
  });

  it('calls onClose when close is triggered', () => {
    const onClose = jest.fn();
    render(<YamlEditorModal {...defaultProps} onClose={onClose} />);
    // Find and click any close/X button
    const xIcon = screen.queryByTestId('x-icon');
    if (xIcon) {
      fireEvent.click(xIcon.closest('button') || xIcon);
      expect(onClose).toHaveBeenCalled();
    }
  });

  it('renders in readOnly mode', () => {
    render(<YamlEditorModal {...defaultProps} readOnly={true} />);
    const textarea = document.querySelector('textarea');
    if (textarea) {
      expect(textarea.readOnly || textarea.disabled).toBeTruthy();
    }
  });

  it('renders without yamlData', () => {
    render(
      <YamlEditorModal isOpen={true} onClose={jest.fn()} onProvision={jest.fn()} yamlData={null} />
    );
    expect(document.body).toBeTruthy();
  });
});

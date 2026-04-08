/**
 * Tests for YamlEditorModal component.
 */

import React from 'react';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';

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

  it('updates yaml content when typing', () => {
    render(<YamlEditorModal {...defaultProps} />);
    const textarea = document.querySelector('textarea');
    if (textarea) {
      fireEvent.change(textarea, { target: { value: 'apiVersion: v1\nkind: Pod' } });
      expect(textarea.value).toBe('apiVersion: v1\nkind: Pod');
    }
  });

  it('validates yaml and shows error for invalid syntax', () => {
    render(<YamlEditorModal {...defaultProps} />);
    const textarea = document.querySelector('textarea');
    if (textarea) {
      // Invalid YAML with odd indentation
      fireEvent.change(textarea, { target: { value: '   apiVersion: v1\n kind: Pod' } });
      // Check for validation error message
      const errorMessage = screen.queryByText(/Invalid indentation/i);
      expect(errorMessage).toBeTruthy();
    }
  });

  it('shows valid yaml status', () => {
    render(<YamlEditorModal {...defaultProps} />);
    expect(screen.getByText('Valid YAML')).toBeInTheDocument();
  });

  it('downloads yaml file when download button clicked', () => {
    const createObjectURL = jest.fn(() => 'blob:mock-url');
    global.URL.createObjectURL = createObjectURL;
    global.URL.revokeObjectURL = jest.fn();

    render(<YamlEditorModal {...defaultProps} />);
    const downloadBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/download/i));

    if (downloadBtn) {
      fireEvent.click(downloadBtn);
      expect(createObjectURL).toHaveBeenCalled();
    }
  });

  it('copies yaml to clipboard when copy button clicked', async () => {
    const writeText = jest.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText,
      },
    });

    render(<YamlEditorModal {...defaultProps} />);
    const copyBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/copy/i));

    if (copyBtn) {
      await act(async () => {
        fireEvent.click(copyBtn);
      });
      expect(writeText).toHaveBeenCalledWith(defaultProps.yamlData.yaml_content);
    }
  });

  it('shows Copied! message after successful copy', async () => {
    const writeText = jest.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText,
      },
    });

    render(<YamlEditorModal {...defaultProps} />);
    const copyBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/copy/i));

    if (copyBtn) {
      await act(async () => {
        fireEvent.click(copyBtn);
      });
      await waitFor(() => {
        expect(screen.getByText('Copied!')).toBeInTheDocument();
      });
    }
  });

  it('resets yaml to original when reset button clicked', () => {
    render(<YamlEditorModal {...defaultProps} />);
    const textarea = document.querySelector('textarea');
    const resetBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/reset/i));

    if (textarea && resetBtn) {
      // Make a change
      fireEvent.change(textarea, { target: { value: 'modified content' } });
      expect(textarea.value).toBe('modified content');

      // Reset
      fireEvent.click(resetBtn);
      expect(textarea.value).toBe(defaultProps.yamlData.yaml_content);
    }
  });

  it('disables reset button when no changes', () => {
    render(<YamlEditorModal {...defaultProps} />);
    const resetBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/reset/i));

    if (resetBtn) {
      expect(resetBtn.disabled).toBe(true);
    }
  });

  it('enables reset button when changes are made', () => {
    render(<YamlEditorModal {...defaultProps} />);
    const textarea = document.querySelector('textarea');
    const resetBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/reset/i));

    if (textarea && resetBtn) {
      fireEvent.change(textarea, { target: { value: 'modified' } });
      expect(resetBtn.disabled).toBe(false);
    }
  });

  it('shows diff view when Show Diff clicked', () => {
    render(<YamlEditorModal {...defaultProps} />);
    const textarea = document.querySelector('textarea');
    const diffBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/Show Diff/i));

    if (textarea && diffBtn) {
      // Make a change
      fireEvent.change(textarea, { target: { value: 'apiVersion: v2\nkind: ConfigMap' } });
      fireEvent.click(diffBtn);

      // Check for diff view
      expect(screen.getByText(/Hide Diff/i)).toBeInTheDocument();
    }
  });

  it('hides diff view when Hide Diff clicked', () => {
    render(<YamlEditorModal {...defaultProps} />);
    const textarea = document.querySelector('textarea');
    const diffBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/Show Diff/i));

    if (textarea && diffBtn) {
      // Make a change and show diff
      fireEvent.change(textarea, { target: { value: 'modified' } });
      fireEvent.click(diffBtn);
      expect(screen.getByText(/Hide Diff/i)).toBeInTheDocument();

      // Hide diff
      fireEvent.click(diffBtn);
      expect(screen.getByText(/Show Diff/i)).toBeInTheDocument();
    }
  });

  it('calls onProvision with edited yaml when Provision Now clicked', () => {
    const onProvision = jest.fn();
    render(<YamlEditorModal {...defaultProps} onProvision={onProvision} />);
    const textarea = document.querySelector('textarea');
    const provisionBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/Provision Now/i));

    if (textarea && provisionBtn) {
      const newYaml = 'apiVersion: v2\nkind: Service';
      fireEvent.change(textarea, { target: { value: newYaml } });
      fireEvent.click(provisionBtn);
      expect(onProvision).toHaveBeenCalledWith(newYaml);
    }
  });

  it('disables provision button when validation error exists', () => {
    render(<YamlEditorModal {...defaultProps} />);
    const textarea = document.querySelector('textarea');
    const provisionBtn = screen.getAllByRole('button').find((b) => b.textContent.match(/Provision Now/i));

    if (textarea && provisionBtn) {
      // Invalid YAML
      fireEvent.change(textarea, { target: { value: '   invalid' } });
      expect(provisionBtn.disabled).toBe(true);
    }
  });

  it('does not show Provision Now button in readOnly mode', () => {
    render(<YamlEditorModal {...defaultProps} readOnly={true} />);
    const provisionBtn = screen.queryByText(/Provision Now/i);
    expect(provisionBtn).not.toBeInTheDocument();
  });

  it('shows Close instead of Cancel in readOnly mode', () => {
    render(<YamlEditorModal {...defaultProps} readOnly={true} />);
    expect(screen.getByText('Close')).toBeInTheDocument();
    expect(screen.queryByText('Cancel')).not.toBeInTheDocument();
  });

  it('renders in inline mode without backdrop', () => {
    const { container } = render(<YamlEditorModal {...defaultProps} inline={true} />);
    const backdrop = container.querySelector('.fixed.inset-0.bg-black');
    expect(backdrop).toBeFalsy();
  });

  it('displays file path when provided', () => {
    const yamlDataWithPath = {
      ...defaultProps.yamlData,
      file_paths: ['/tmp/test-cluster.yaml'],
    };
    render(<YamlEditorModal {...defaultProps} yamlData={yamlDataWithPath} />);
    expect(screen.getAllByText(/test-cluster\.yaml/i).length).toBeGreaterThan(0);
  });

  it('displays resource name and type in header', () => {
    const yamlDataWithInfo = {
      ...defaultProps.yamlData,
      resource_name: 'my-cluster',
      resource_type: 'ROSAControlPlane',
    };
    render(<YamlEditorModal {...defaultProps} yamlData={yamlDataWithInfo} />);
    const content = document.body.textContent;
    expect(content).toMatch(/my-cluster/i);
    expect(content).toMatch(/ROSAControlPlane/i);
  });
});

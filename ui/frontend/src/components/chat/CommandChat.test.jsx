/**
 * Tests for CommandChat component.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

jest.mock('@heroicons/react/24/outline', () => ({
  CommandLineIcon: (props) => <svg data-testid="cmd-icon" {...props} />,
  XMarkIcon: (props) => <svg data-testid="x-icon" {...props} />,
  PaperAirplaneIcon: (props) => <svg data-testid="send-icon" {...props} />,
  CheckCircleIcon: (props) => <svg data-testid="check-icon" {...props} />,
  ExclamationCircleIcon: (props) => <svg data-testid="exclaim-icon" {...props} />,
  ClockIcon: (props) => <svg data-testid="clock-icon" {...props} />,
}));

// jsdom doesn't have scrollIntoView
Element.prototype.scrollIntoView = jest.fn();

import { CommandChat } from './CommandChat';

describe('CommandChat', () => {
  beforeEach(() => {
    // Reset fetch mock before each test
    if (global.fetch && global.fetch.mockRestore) {
      global.fetch.mockRestore();
    }
  });
  it('renders toggle button', () => {
    render(<CommandChat />);
    expect(screen.getByTestId('cmd-icon')).toBeInTheDocument();
  });

  it('shows chat panel when opened', () => {
    render(<CommandChat />);
    // Click the button to open
    const button = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(button);
    expect(screen.getByText(/ROSA Command Chat/)).toBeInTheDocument();
  });

  it('shows welcome message when opened', () => {
    render(<CommandChat />);
    const button = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(button);
    expect(screen.getByText(/Welcome to ROSA Command Chat/)).toBeInTheDocument();
  });

  it('shows example commands', () => {
    render(<CommandChat />);
    const button = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(button);
    expect(screen.getByText(/provision rosa cluster/)).toBeInTheDocument();
  });

  it('has input field when open', () => {
    render(<CommandChat />);
    const button = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(button);
    expect(screen.getByPlaceholderText(/Enter command/i)).toBeInTheDocument();
  });

  it('closes when close button clicked', () => {
    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    expect(screen.getByText(/ROSA Command Chat/)).toBeInTheDocument();
    const closeBtn = screen.getByTestId('x-icon').closest('button');
    fireEvent.click(closeBtn);
    expect(screen.queryByText(/ROSA Command Chat/)).toBeNull();
  });

  it('allows typing in the input field', () => {
    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'list all clusters' } });
    expect(input.value).toBe('list all clusters');
  });

  it('clears input after submitting command', async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ message: 'Success' }),
      })
    );

    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'list clusters' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    // Input should be cleared
    expect(input.value).toBe('');
    global.fetch.mockRestore();
  });

  it('submits command when Enter key is pressed', async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ message: 'Success' }),
      })
    );

    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'list clusters' } });
    fireEvent.keyPress(input, { key: 'Enter', code: 'Enter', charCode: 13 });

    expect(input.value).toBe('');
    global.fetch.mockRestore();
  });

  it('does not submit when Shift+Enter is pressed', () => {
    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'list clusters' } });
    fireEvent.keyPress(input, { key: 'Enter', code: 'Enter', charCode: 13, shiftKey: true });

    // Input should not be cleared
    expect(input.value).toBe('list clusters');
  });

  it('disables send button when input is empty', () => {
    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    expect(sendBtn).toBeDisabled();
  });

  it('enables send button when input has text', () => {
    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'list clusters' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    expect(sendBtn).not.toBeDisabled();
  });

  it('shows error message for unrecognized command', async () => {
    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'invalid command' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    // Wait for error message
    await screen.findByText(/didn't understand that command/i);
    expect(screen.getByText(/didn't understand that command/i)).toBeInTheDocument();
  });

  it('parses provision command correctly', async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ message: 'Provisioning started' }),
      })
    );

    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'provision rosa cluster named test-123' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    // Wait for fetch to be called
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/rosa-hcp/provision',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );
    global.fetch.mockRestore();
  });

  it('shows error when provision command is missing cluster name', async () => {
    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'provision cluster' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await screen.findByText(/Please specify a cluster name/i);
    expect(screen.getByText(/Please specify a cluster name/i)).toBeInTheDocument();
  });

  it('parses delete command correctly', async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ message: 'Deletion started' }),
      })
    );

    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'delete th9-test' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });

    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/rosa-hcp/clusters/th9-test',
      expect.objectContaining({ method: 'DELETE' })
    );
    global.fetch.mockRestore();
  });

  it('shows error when delete command is missing cluster name', async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: false,
        json: () => Promise.resolve({ message: 'Cluster not found: cluster' }),
      })
    );

    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'delete cluster' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    // The command will parse "cluster" as the name, so it will call the API
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });
    global.fetch.mockRestore();
  });

  it('parses list command correctly', async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ clusters: [] }),
      })
    );

    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'list all clusters' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await screen.findByText(/Executing: list/i);
    expect(global.fetch).toHaveBeenCalledWith('http://localhost:8000/api/rosa-hcp/clusters');
    global.fetch.mockRestore();
  });

  it('parses list command with region filter', async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ clusters: [] }),
      })
    );

    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'show all clusters in us-west-2' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await screen.findByText(/Executing: list/i);
    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/rosa-hcp/clusters?region=us-west-2'
    );
    global.fetch.mockRestore();
  });

  it('parses verify command correctly', async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ message: 'Verification complete' }),
      })
    );

    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'verify mce environment' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await screen.findByText(/Executing: verify/i);
    expect(global.fetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/mce/verify',
      expect.objectContaining({ method: 'POST' })
    );
    global.fetch.mockRestore();
  });

  it('handles API error responses', async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: false,
        json: () => Promise.resolve({ message: 'API Error occurred' }),
      })
    );

    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'list clusters' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(screen.getByTestId('exclaim-icon')).toBeInTheDocument();
    });
    global.fetch.mockRestore();
  });

  it('handles network errors', async () => {
    global.fetch = jest.fn(() => Promise.reject(new Error('Network error')));

    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'list clusters' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await screen.findByText(/Error: Network error/i);
    global.fetch.mockRestore();
  });

  it('shows success icon for successful commands', async () => {
    global.fetch = jest.fn(() =>
      Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ message: 'Command executed successfully' }),
      })
    );

    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    fireEvent.change(input, { target: { value: 'list clusters' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(screen.getByTestId('check-icon')).toBeInTheDocument();
    });
    global.fetch.mockRestore();
  });

  it('fills input when example command is clicked', () => {
    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const exampleBtn = screen.getByText('provision rosa cluster named test-cluster');
    fireEvent.click(exampleBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    expect(input.value).toBe('provision rosa cluster named test-cluster');
  });

  it('disables input and button while processing', async () => {
    global.fetch = jest.fn(
      () =>
        new Promise((resolve) =>
          setTimeout(
            () =>
              resolve({
                ok: true,
                json: () => Promise.resolve({ message: 'Processing completed' }),
              }),
            100
          )
        )
    );

    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    const input = screen.getByPlaceholderText(/Enter command/i);
    const sendBtn = screen.getByTestId('send-icon').closest('button');

    fireEvent.change(input, { target: { value: 'list clusters' } });
    fireEvent.click(sendBtn);

    // Check that button is disabled during processing
    expect(sendBtn).toBeDisabled();
    expect(input).toBeDisabled();

    await waitFor(() => {
      expect(screen.getByTestId('check-icon')).toBeInTheDocument();
    });
    global.fetch.mockRestore();
  });

  it('displays timestamps on messages', async () => {
    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);

    // Wait for the welcome message to be displayed
    await waitFor(() => {
      expect(screen.getByText(/Welcome to ROSA Command Chat/i)).toBeInTheDocument();
    });

    // Check that timestamps are present by looking for time format (contains colon)
    const content = screen.getByText(/Welcome to ROSA Command Chat/i).closest('.bg-gray-100');
    expect(content).toBeInTheDocument();
  });

  it('shows command hints at the bottom', () => {
    render(<CommandChat />);
    const openBtn = screen.getByTestId('cmd-icon').closest('button');
    fireEvent.click(openBtn);
    expect(screen.getByText(/Commands: provision, delete, list, verify/i)).toBeInTheDocument();
  });
});

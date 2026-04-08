/**
 * Tests for AIAssistantChat component.
 */

import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

jest.mock('@heroicons/react/24/outline', () => ({
  XMarkIcon: (props) => <svg data-testid="x-icon" {...props} />,
  PaperAirplaneIcon: (props) => <svg data-testid="send-icon" {...props} />,
  SparklesIcon: (props) => <svg data-testid="sparkles-icon" {...props} />,
}));

const mockFetch = jest.fn();
global.fetch = mockFetch;

// jsdom doesn't have scrollIntoView
Element.prototype.scrollIntoView = jest.fn();

import { AIAssistantChat } from './AIAssistantChat';

beforeEach(() => {
  mockFetch.mockReset();
});

describe('AIAssistantChat', () => {
  it('renders toggle button in non-inline mode', () => {
    render(<AIAssistantChat />);
    expect(screen.getByTestId('sparkles-icon')).toBeInTheDocument();
  });

  it('shows chat when opened', () => {
    render(<AIAssistantChat />);
    const button = screen.getByTestId('sparkles-icon').closest('button');
    fireEvent.click(button);
    expect(screen.getByText(/CAPA cluster assistant/)).toBeInTheDocument();
  });

  it('renders inline mode directly', () => {
    render(<AIAssistantChat inline={true} />);
    expect(screen.getByText(/CAPA cluster assistant/)).toBeInTheDocument();
  });

  it('renders with minikube theme', () => {
    render(<AIAssistantChat inline={true} theme="minikube" />);
    expect(screen.getByText(/CAPA cluster assistant/)).toBeInTheDocument();
  });

  it('renders with main theme', () => {
    render(<AIAssistantChat inline={true} theme="main" />);
    expect(screen.getByText(/CAPA cluster assistant/)).toBeInTheDocument();
  });

  it('has input field', () => {
    render(<AIAssistantChat inline={true} />);
    expect(screen.getByPlaceholderText(/Ask me anything/i)).toBeInTheDocument();
  });

  it('closes when close button clicked in non-inline mode', () => {
    render(<AIAssistantChat />);
    const openBtn = screen.getByTestId('sparkles-icon').closest('button');
    fireEvent.click(openBtn);
    expect(screen.getByText(/CAPA cluster assistant/)).toBeInTheDocument();
    const closeBtn = screen.getByTestId('x-icon').closest('button');
    fireEvent.click(closeBtn);
    expect(screen.queryByText(/CAPA cluster assistant/)).toBeNull();
  });

  it('allows typing in the input field', () => {
    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'What is ROSA?' } });
    expect(input.value).toBe('What is ROSA?');
  });

  it('clears input after sending message', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [] }),
    });
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ response: 'ROSA is Red Hat OpenShift Service on AWS' }),
    });

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'What is ROSA?' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    expect(input.value).toBe('');
  });

  it('submits message when Enter key is pressed', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [] }),
    });
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ response: 'AI response' }),
    });

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'Help me' } });
    fireEvent.keyPress(input, { key: 'Enter', code: 'Enter', charCode: 13 });

    expect(input.value).toBe('');
  });

  it('does not submit when Shift+Enter is pressed', () => {
    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'Help me' } });
    fireEvent.keyPress(input, { key: 'Enter', code: 'Enter', charCode: 13, shiftKey: true });

    expect(input.value).toBe('Help me');
  });

  it('disables send button when input is empty', () => {
    render(<AIAssistantChat inline={true} />);
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    expect(sendBtn).toBeDisabled();
  });

  it('enables send button when input has text', () => {
    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'Help' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    expect(sendBtn).not.toBeDisabled();
  });

  it('displays welcome message on initial render', () => {
    render(<AIAssistantChat inline={true} />);
    expect(
      screen.getByText(
        /I'm your CAPA cluster assistant. I can help you understand cluster status/i
      )
    ).toBeInTheDocument();
  });

  it('sends message with cluster context', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [{ name: 'test-cluster', status: 'ready' }] }),
    });
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ response: 'You have 1 cluster running' }),
    });

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'What clusters are running?' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await screen.findByText(/You have 1 cluster running/i);

    // Check that API was called with context
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/ai-assistant/chat',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: expect.stringContaining('What clusters are running?'),
      })
    );
  });

  it('displays AI response in chat', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [] }),
    });
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ response: 'This is an AI response' }),
    });

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'Help' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await screen.findByText(/This is an AI response/i);
    expect(screen.getByText(/This is an AI response/i)).toBeInTheDocument();
  });

  it('shows loading indicator while waiting for response', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [] }),
    });
    mockFetch.mockImplementationOnce(
      () =>
        new Promise((resolve) =>
          setTimeout(() => resolve({ json: () => Promise.resolve({ response: 'Done' }) }), 100)
        )
    );

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'Help' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    // Loading dots should be visible
    const loadingDots = document.querySelectorAll('.animate-bounce');
    expect(loadingDots.length).toBeGreaterThan(0);

    await screen.findByText(/Done/i);
  });

  it('handles API error gracefully', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [] }),
    });
    mockFetch.mockRejectedValueOnce(new Error('API Error'));

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'Help' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await screen.findByText(/Sorry, I encountered an error/i);
    expect(screen.getByText(/Sorry, I encountered an error/i)).toBeInTheDocument();
  });

  it('displays error message in red styling', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [] }),
    });
    mockFetch.mockRejectedValueOnce(new Error('API Error'));

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'Help' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    const errorMsg = await screen.findByText(/Sorry, I encountered an error/i);
    const errorDiv = errorMsg.closest('div');
    expect(errorDiv.className).toContain('bg-red-50');
  });

  it('disables input and send button while loading', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [] }),
    });
    mockFetch.mockImplementationOnce(
      () =>
        new Promise((resolve) =>
          setTimeout(() => resolve({ json: () => Promise.resolve({ response: 'Done' }) }), 100)
        )
    );

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    const sendBtn = screen.getByTestId('send-icon').closest('button');

    fireEvent.change(input, { target: { value: 'Help' } });
    fireEvent.click(sendBtn);

    expect(sendBtn).toBeDisabled();

    await screen.findByText(/Done/i);
  });

  it('shows quick action buttons', () => {
    render(<AIAssistantChat inline={true} />);
    expect(screen.getByText('What clusters are running?')).toBeInTheDocument();
    expect(screen.getByText('Troubleshoot failed cluster')).toBeInTheDocument();
    expect(screen.getByText('Explain ROSA HCP')).toBeInTheDocument();
    expect(screen.getByText('How to provision cluster?')).toBeInTheDocument();
  });

  it('fills input when quick action is clicked', () => {
    render(<AIAssistantChat inline={true} />);
    const quickBtn = screen.getByText('What clusters are running?');
    fireEvent.click(quickBtn);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    expect(input.value).toBe('What clusters are running?');
  });

  it('displays suggestions from AI response', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [] }),
    });
    mockFetch.mockResolvedValueOnce({
      json: () =>
        Promise.resolve({
          response: 'Here are some options',
          suggestions: ['Check cluster logs', 'Restart cluster'],
        }),
    });

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'Help' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await screen.findByText(/Here are some options/i);
    expect(screen.getByText('Check cluster logs')).toBeInTheDocument();
    expect(screen.getByText('Restart cluster')).toBeInTheDocument();
  });

  it('fills input when suggestion is clicked', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [] }),
    });
    mockFetch.mockResolvedValueOnce({
      json: () =>
        Promise.resolve({
          response: 'Options',
          suggestions: ['Check logs'],
        }),
    });

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'Help' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    const suggestion = await screen.findByText('Check logs');
    fireEvent.click(suggestion);

    expect(input.value).toBe('Check logs');
  });

  it('displays timestamps on messages', () => {
    render(<AIAssistantChat inline={true} />);
    const timestamps = screen.getAllByText(/\d{1,2}:\d{2}:\d{2}/);
    expect(timestamps.length).toBeGreaterThan(0);
  });

  it('displays user messages on the right side', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [] }),
    });
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ response: 'AI response' }),
    });

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'My question' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await screen.findByText(/My question/i);
    const userMsg = screen.getByText(/My question/i).closest('.flex');
    expect(userMsg.className).toContain('justify-end');
  });

  it('displays assistant messages on the left side', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [] }),
    });
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ response: 'AI response' }),
    });

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'Help' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    const aiMsg = await screen.findByText(/AI response/i);
    const msgContainer = aiMsg.closest('.flex');
    expect(msgContainer.className).toContain('justify-start');
  });

  it('includes message history in context (last 5 messages)', async () => {
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ clusters: [] }),
    });
    mockFetch.mockResolvedValueOnce({
      json: () => Promise.resolve({ response: 'Response 1' }),
    });

    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    fireEvent.change(input, { target: { value: 'First message' } });
    const sendBtn = screen.getByTestId('send-icon').closest('button');
    fireEvent.click(sendBtn);

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    // The second API call should include history
    expect(mockFetch).toHaveBeenCalledWith(
      'http://localhost:8000/api/ai-assistant/chat',
      expect.objectContaining({
        body: expect.stringContaining('history'),
      })
    );
  });

  it('does not show close button in inline mode', () => {
    render(<AIAssistantChat inline={true} />);
    expect(screen.queryByTestId('x-icon')).toBeNull();
  });

  it('shows floating button in non-inline mode when closed', () => {
    render(<AIAssistantChat />);
    expect(screen.getByTestId('sparkles-icon')).toBeInTheDocument();
  });

  it('renders with purple theme for minikube', () => {
    render(<AIAssistantChat inline={true} theme="minikube" />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    expect(input.className).toContain('focus:ring-purple-500');
  });

  it('renders with gray theme for main', () => {
    render(<AIAssistantChat inline={true} theme="main" />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    expect(input.className).toContain('focus:ring-gray-500');
  });

  it('renders with blue theme for mce (default)', () => {
    render(<AIAssistantChat inline={true} />);
    const input = screen.getByPlaceholderText(/Ask me anything/i);
    expect(input.className).toContain('focus:ring-blue-500');
  });
});

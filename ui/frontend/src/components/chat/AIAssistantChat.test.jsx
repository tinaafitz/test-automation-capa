/**
 * Tests for AIAssistantChat component.
 */

import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';

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
});

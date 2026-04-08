/**
 * Tests for PresentationMode page component.
 */

import React from 'react';
import { render, screen, fireEvent, act } from '@testing-library/react';

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
}));

jest.mock('@heroicons/react/24/outline', () => ({
  ChevronLeftIcon: (props) => <svg data-testid="chevron-left" {...props} />,
  ChevronRightIcon: (props) => <svg data-testid="chevron-right" {...props} />,
  PlayIcon: (props) => <svg data-testid="play-icon" {...props} />,
  XMarkIcon: (props) => <svg data-testid="x-mark" {...props} />,
}));

import PresentationMode from './PresentationMode';

describe('PresentationMode', () => {
  it('renders without crashing', () => {
    render(<PresentationMode />);
    expect(document.body).toBeTruthy();
  });

  it('renders the first slide title', () => {
    render(<PresentationMode />);
    expect(screen.getAllByText(/CAPA Automation Framework/i).length).toBeGreaterThan(0);
  });

  it('shows navigation controls', () => {
    render(<PresentationMode />);
    // Should have next/prev or navigation buttons
    const buttons = screen.getAllByRole('button');
    expect(buttons.length).toBeGreaterThan(0);
  });

  it('renders slide counter', () => {
    render(<PresentationMode />);
    // Should show something like "1 / N"
    expect(screen.getByText(/1\s*\/\s*\d+/)).toBeInTheDocument();
  });
});

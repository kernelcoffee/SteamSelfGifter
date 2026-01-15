import { describe, it, expect } from 'vitest';
import { render, screen } from '@/test/utils';
import { Sidebar } from './Sidebar';

describe('Sidebar', () => {
  it('should render all navigation links', () => {
    render(<Sidebar />);

    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Giveaways')).toBeInTheDocument();
    expect(screen.getByText('Wins')).toBeInTheDocument();
    expect(screen.getByText('History')).toBeInTheDocument();
    expect(screen.getByText('Analytics')).toBeInTheDocument();
    expect(screen.getByText('Settings')).toBeInTheDocument();
    expect(screen.getByText('Logs')).toBeInTheDocument();
  });

  it('should have correct link destinations', () => {
    render(<Sidebar />);

    expect(screen.getByText('Dashboard').closest('a')).toHaveAttribute('href', '/dashboard');
    expect(screen.getByText('Giveaways').closest('a')).toHaveAttribute('href', '/giveaways');
    expect(screen.getByText('Wins').closest('a')).toHaveAttribute('href', '/wins');
    expect(screen.getByText('History').closest('a')).toHaveAttribute('href', '/history');
    expect(screen.getByText('Analytics').closest('a')).toHaveAttribute('href', '/analytics');
    expect(screen.getByText('Settings').closest('a')).toHaveAttribute('href', '/settings');
    expect(screen.getByText('Logs').closest('a')).toHaveAttribute('href', '/logs');
  });

  it('should render navigation as a list', () => {
    render(<Sidebar />);

    const nav = screen.getByRole('navigation');
    expect(nav).toBeInTheDocument();

    const listItems = screen.getAllByRole('listitem');
    expect(listItems).toHaveLength(7);
  });
});

import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@/test/utils';
import { Notifications } from './Notifications';
import { useUIStore } from '@/stores/uiStore';

describe('Notifications', () => {
  beforeEach(() => {
    // Reset store
    useUIStore.setState({ notifications: [] });
  });

  it('should not render when there are no notifications', () => {
    const { container } = render(<Notifications />);

    expect(container.firstChild).toBeNull();
  });

  it('should render a success notification', () => {
    useUIStore.setState({
      notifications: [
        { id: '1', type: 'success', message: 'Success message' },
      ],
    });

    render(<Notifications />);

    expect(screen.getByText('Success message')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveClass('bg-green-50');
  });

  it('should render an error notification', () => {
    useUIStore.setState({
      notifications: [
        { id: '1', type: 'error', message: 'Error message' },
      ],
    });

    render(<Notifications />);

    expect(screen.getByText('Error message')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveClass('bg-red-50');
  });

  it('should render an info notification', () => {
    useUIStore.setState({
      notifications: [
        { id: '1', type: 'info', message: 'Info message' },
      ],
    });

    render(<Notifications />);

    expect(screen.getByText('Info message')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveClass('bg-blue-50');
  });

  it('should render a warning notification', () => {
    useUIStore.setState({
      notifications: [
        { id: '1', type: 'warning', message: 'Warning message' },
      ],
    });

    render(<Notifications />);

    expect(screen.getByText('Warning message')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveClass('bg-yellow-50');
  });

  it('should render multiple notifications', () => {
    useUIStore.setState({
      notifications: [
        { id: '1', type: 'success', message: 'First' },
        { id: '2', type: 'error', message: 'Second' },
        { id: '3', type: 'info', message: 'Third' },
      ],
    });

    render(<Notifications />);

    expect(screen.getByText('First')).toBeInTheDocument();
    expect(screen.getByText('Second')).toBeInTheDocument();
    expect(screen.getByText('Third')).toBeInTheDocument();
  });

  it('should dismiss notification when close button is clicked', () => {
    useUIStore.setState({
      notifications: [
        { id: 'test-id', type: 'success', message: 'Dismissable' },
      ],
    });

    render(<Notifications />);

    const dismissButton = screen.getByRole('button', { name: /dismiss/i });
    fireEvent.click(dismissButton);

    expect(useUIStore.getState().notifications).toHaveLength(0);
  });
});

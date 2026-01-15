import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@/test/utils';
import { Toggle } from './Toggle';

describe('Toggle', () => {
  it('should render with label', () => {
    render(<Toggle label="Enable Feature" checked={false} onChange={() => {}} />);

    // Label text appears in both sr-only span and visible label
    expect(screen.getByLabelText('Enable Feature')).toBeInTheDocument();
  });

  it('should render as switch role', () => {
    render(<Toggle label="Feature" checked={false} onChange={() => {}} />);

    expect(screen.getByRole('switch')).toBeInTheDocument();
  });

  it('should show checked state', () => {
    render(<Toggle label="Feature" checked={true} onChange={() => {}} />);

    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'true');
  });

  it('should show unchecked state', () => {
    render(<Toggle label="Feature" checked={false} onChange={() => {}} />);

    expect(screen.getByRole('switch')).toHaveAttribute('aria-checked', 'false');
  });

  it('should call onChange when clicked', () => {
    const handleChange = vi.fn();
    render(<Toggle label="Feature" checked={false} onChange={handleChange} />);

    fireEvent.click(screen.getByRole('switch'));

    expect(handleChange).toHaveBeenCalledWith(true);
  });

  it('should toggle from true to false', () => {
    const handleChange = vi.fn();
    render(<Toggle label="Feature" checked={true} onChange={handleChange} />);

    fireEvent.click(screen.getByRole('switch'));

    expect(handleChange).toHaveBeenCalledWith(false);
  });

  it('should call onChange when label is clicked', () => {
    const handleChange = vi.fn();
    render(<Toggle label="Feature" checked={false} onChange={handleChange} />);

    // Click the visible label (not the sr-only span)
    fireEvent.click(screen.getByRole('switch').parentElement!.querySelector('label')!);

    expect(handleChange).toHaveBeenCalledWith(true);
  });

  describe('disabled state', () => {
    it('should be disabled when disabled prop is true', () => {
      render(<Toggle label="Feature" checked={false} onChange={() => {}} disabled />);

      expect(screen.getByRole('switch')).toBeDisabled();
    });

    it('should not call onChange when disabled', () => {
      const handleChange = vi.fn();
      render(<Toggle label="Feature" checked={false} onChange={handleChange} disabled />);

      fireEvent.click(screen.getByRole('switch'));

      expect(handleChange).not.toHaveBeenCalled();
    });
  });

  describe('description', () => {
    it('should render description', () => {
      render(
        <Toggle
          label="Feature"
          checked={false}
          onChange={() => {}}
          description="This enables the feature"
        />
      );

      expect(screen.getByText('This enables the feature')).toBeInTheDocument();
    });
  });

  it('should have correct styling when checked', () => {
    render(<Toggle label="Feature" checked={true} onChange={() => {}} />);

    expect(screen.getByRole('switch')).toHaveClass('bg-primary-light');
  });

  it('should have correct styling when unchecked', () => {
    render(<Toggle label="Feature" checked={false} onChange={() => {}} />);

    expect(screen.getByRole('switch')).toHaveClass('bg-gray-200');
  });
});

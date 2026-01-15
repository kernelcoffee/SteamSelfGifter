import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@/test/utils';
import { Input } from './Input';

describe('Input', () => {
  it('should render an input', () => {
    render(<Input />);

    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('should render with label', () => {
    render(<Input label="Email" />);

    expect(screen.getByLabelText('Email')).toBeInTheDocument();
  });

  it('should render with placeholder', () => {
    render(<Input placeholder="Enter text" />);

    expect(screen.getByPlaceholderText('Enter text')).toBeInTheDocument();
  });

  it('should handle value changes', () => {
    const handleChange = vi.fn();
    render(<Input onChange={handleChange} />);

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'test' } });

    expect(handleChange).toHaveBeenCalled();
  });

  describe('error state', () => {
    it('should show error message', () => {
      render(<Input label="Email" error="Email is required" />);

      expect(screen.getByRole('alert')).toHaveTextContent('Email is required');
    });

    it('should have error styling', () => {
      render(<Input error="Error" />);

      expect(screen.getByRole('textbox')).toHaveClass('border-error-light');
    });

    it('should set aria-invalid', () => {
      render(<Input error="Error" />);

      expect(screen.getByRole('textbox')).toHaveAttribute('aria-invalid', 'true');
    });
  });

  describe('helper text', () => {
    it('should show helper text', () => {
      render(<Input helperText="Enter your email address" />);

      expect(screen.getByText('Enter your email address')).toBeInTheDocument();
    });

    it('should hide helper text when error is shown', () => {
      render(<Input helperText="Helper" error="Error" />);

      expect(screen.queryByText('Helper')).not.toBeInTheDocument();
      expect(screen.getByText('Error')).toBeInTheDocument();
    });
  });

  describe('disabled state', () => {
    it('should be disabled when disabled prop is true', () => {
      render(<Input disabled />);

      expect(screen.getByRole('textbox')).toBeDisabled();
    });
  });

  describe('types', () => {
    it('should render password input', () => {
      render(<Input type="password" label="Password" />);

      expect(screen.getByLabelText('Password')).toHaveAttribute('type', 'password');
    });

    it('should render number input', () => {
      render(<Input type="number" label="Amount" />);

      expect(screen.getByLabelText('Amount')).toHaveAttribute('type', 'number');
    });
  });

  it('should accept custom className', () => {
    render(<Input className="custom-class" />);

    expect(screen.getByRole('textbox')).toHaveClass('custom-class');
  });

  it('should generate id from label', () => {
    render(<Input label="User Name" />);

    const input = screen.getByRole('textbox');
    expect(input).toHaveAttribute('id', 'user-name');
  });

  it('should use provided id', () => {
    render(<Input id="custom-id" label="Label" />);

    const input = screen.getByRole('textbox');
    expect(input).toHaveAttribute('id', 'custom-id');
  });
});

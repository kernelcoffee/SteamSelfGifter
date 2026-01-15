import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@/test/utils';
import { Button } from './Button';
import { Plus, Trash } from 'lucide-react';

describe('Button', () => {
  it('should render with text', () => {
    render(<Button>Click me</Button>);

    expect(screen.getByRole('button', { name: /click me/i })).toBeInTheDocument();
  });

  it('should call onClick when clicked', () => {
    const handleClick = vi.fn();
    render(<Button onClick={handleClick}>Click me</Button>);

    fireEvent.click(screen.getByRole('button'));

    expect(handleClick).toHaveBeenCalledOnce();
  });

  describe('variants', () => {
    it('should render primary variant by default', () => {
      render(<Button>Primary</Button>);

      const button = screen.getByRole('button');
      expect(button).toHaveClass('bg-primary-light');
    });

    it('should render secondary variant', () => {
      render(<Button variant="secondary">Secondary</Button>);

      const button = screen.getByRole('button');
      expect(button).toHaveClass('bg-gray-200');
    });

    it('should render danger variant', () => {
      render(<Button variant="danger">Danger</Button>);

      const button = screen.getByRole('button');
      expect(button).toHaveClass('bg-error-light');
    });

    it('should render ghost variant', () => {
      render(<Button variant="ghost">Ghost</Button>);

      const button = screen.getByRole('button');
      expect(button).toHaveClass('bg-transparent');
    });
  });

  describe('sizes', () => {
    it('should render medium size by default', () => {
      render(<Button>Medium</Button>);

      const button = screen.getByRole('button');
      expect(button).toHaveClass('px-4', 'py-2');
    });

    it('should render small size', () => {
      render(<Button size="sm">Small</Button>);

      const button = screen.getByRole('button');
      expect(button).toHaveClass('px-3', 'py-1.5');
    });

    it('should render large size', () => {
      render(<Button size="lg">Large</Button>);

      const button = screen.getByRole('button');
      expect(button).toHaveClass('px-6', 'py-3');
    });
  });

  describe('icon', () => {
    it('should render with left icon by default', () => {
      render(<Button icon={Plus}>Add</Button>);

      expect(screen.getByRole('button')).toBeInTheDocument();
      // Icon is rendered as SVG
      expect(screen.getByRole('button').querySelector('svg')).toBeInTheDocument();
    });

    it('should render with right icon', () => {
      render(<Button icon={Trash} iconPosition="right">Delete</Button>);

      expect(screen.getByRole('button').querySelector('svg')).toBeInTheDocument();
    });
  });

  describe('loading state', () => {
    it('should show loading spinner when isLoading', () => {
      render(<Button isLoading>Loading</Button>);

      const button = screen.getByRole('button');
      expect(button).toBeDisabled();
      // Loader2 icon has animate-spin class
      expect(button.querySelector('.animate-spin')).toBeInTheDocument();
    });

    it('should be disabled when loading', () => {
      render(<Button isLoading>Loading</Button>);

      expect(screen.getByRole('button')).toBeDisabled();
    });

    it('should not call onClick when loading', () => {
      const handleClick = vi.fn();
      render(<Button isLoading onClick={handleClick}>Loading</Button>);

      fireEvent.click(screen.getByRole('button'));

      expect(handleClick).not.toHaveBeenCalled();
    });
  });

  describe('disabled state', () => {
    it('should be disabled when disabled prop is true', () => {
      render(<Button disabled>Disabled</Button>);

      expect(screen.getByRole('button')).toBeDisabled();
    });

    it('should not call onClick when disabled', () => {
      const handleClick = vi.fn();
      render(<Button disabled onClick={handleClick}>Disabled</Button>);

      fireEvent.click(screen.getByRole('button'));

      expect(handleClick).not.toHaveBeenCalled();
    });
  });

  describe('fullWidth', () => {
    it('should be full width when fullWidth is true', () => {
      render(<Button fullWidth>Full Width</Button>);

      expect(screen.getByRole('button')).toHaveClass('w-full');
    });
  });

  describe('custom className', () => {
    it('should accept custom className', () => {
      render(<Button className="custom-class">Custom</Button>);

      expect(screen.getByRole('button')).toHaveClass('custom-class');
    });
  });
});

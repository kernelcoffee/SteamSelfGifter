import { describe, it, expect } from 'vitest';
import { render, screen } from '@/test/utils';
import { Badge } from './Badge';

describe('Badge', () => {
  it('should render with text', () => {
    render(<Badge>Active</Badge>);

    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  describe('variants', () => {
    it('should render default variant by default', () => {
      render(<Badge>Default</Badge>);

      expect(screen.getByText('Default')).toHaveClass('bg-gray-100');
    });

    it('should render success variant', () => {
      render(<Badge variant="success">Success</Badge>);

      expect(screen.getByText('Success')).toHaveClass('bg-green-100');
    });

    it('should render warning variant', () => {
      render(<Badge variant="warning">Warning</Badge>);

      expect(screen.getByText('Warning')).toHaveClass('bg-yellow-100');
    });

    it('should render error variant', () => {
      render(<Badge variant="error">Error</Badge>);

      expect(screen.getByText('Error')).toHaveClass('bg-red-100');
    });

    it('should render info variant', () => {
      render(<Badge variant="info">Info</Badge>);

      expect(screen.getByText('Info')).toHaveClass('bg-blue-100');
    });
  });

  describe('sizes', () => {
    it('should render medium size by default', () => {
      render(<Badge>Medium</Badge>);

      expect(screen.getByText('Medium')).toHaveClass('text-sm');
    });

    it('should render small size', () => {
      render(<Badge size="sm">Small</Badge>);

      expect(screen.getByText('Small')).toHaveClass('text-xs');
    });
  });

  it('should accept custom className', () => {
    render(<Badge className="custom-class">Badge</Badge>);

    expect(screen.getByText('Badge')).toHaveClass('custom-class');
  });

  it('should have rounded-full class', () => {
    render(<Badge>Rounded</Badge>);

    expect(screen.getByText('Rounded')).toHaveClass('rounded-full');
  });

  it('should have dark mode styles', () => {
    render(<Badge variant="success">Dark</Badge>);

    expect(screen.getByText('Dark')).toHaveClass('dark:bg-green-900/30');
  });
});

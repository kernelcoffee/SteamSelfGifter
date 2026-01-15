import { describe, it, expect } from 'vitest';
import { render, screen } from '@/test/utils';
import { Card } from './Card';

describe('Card', () => {
  it('should render children', () => {
    render(<Card>Card content</Card>);

    expect(screen.getByText('Card content')).toBeInTheDocument();
  });

  it('should render with title', () => {
    render(<Card title="Card Title">Content</Card>);

    expect(screen.getByText('Card Title')).toBeInTheDocument();
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('Card Title');
  });

  it('should render actions', () => {
    render(
      <Card title="Title" actions={<button>Action</button>}>
        Content
      </Card>
    );

    expect(screen.getByRole('button', { name: /action/i })).toBeInTheDocument();
  });

  it('should render actions without title', () => {
    render(
      <Card actions={<button>Action</button>}>
        Content
      </Card>
    );

    expect(screen.getByRole('button', { name: /action/i })).toBeInTheDocument();
  });

  describe('padding', () => {
    it('should have medium padding by default', () => {
      const { container } = render(<Card>Content</Card>);

      // The content div should have p-4 class
      expect(container.querySelector('.p-4')).toBeInTheDocument();
    });

    it('should have no padding when padding is none', () => {
      const { container } = render(<Card padding="none">Content</Card>);

      expect(container.querySelector('.p-4')).not.toBeInTheDocument();
      expect(container.querySelector('.p-3')).not.toBeInTheDocument();
      expect(container.querySelector('.p-6')).not.toBeInTheDocument();
    });

    it('should have small padding when padding is sm', () => {
      const { container } = render(<Card padding="sm">Content</Card>);

      expect(container.querySelector('.p-3')).toBeInTheDocument();
    });

    it('should have large padding when padding is lg', () => {
      const { container } = render(<Card padding="lg">Content</Card>);

      expect(container.querySelector('.p-6')).toBeInTheDocument();
    });
  });

  it('should accept custom className', () => {
    const { container } = render(<Card className="custom-class">Content</Card>);

    expect(container.firstChild).toHaveClass('custom-class');
  });

  it('should have dark mode styles', () => {
    const { container } = render(<Card>Content</Card>);

    expect(container.firstChild).toHaveClass('dark:bg-surface-dark');
  });
});

import { describe, it, expect } from 'vitest';
import { render, screen } from '@/test/utils';
import { Spinner, Loading, Skeleton, CardSkeleton } from './Loading';

describe('Spinner', () => {
  it('should render a spinner', () => {
    const { container } = render(<Spinner />);

    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('should accept custom className', () => {
    const { container } = render(<Spinner className="custom-class" />);

    expect(container.querySelector('.custom-class')).toBeInTheDocument();
  });
});

describe('Loading', () => {
  it('should render a spinner', () => {
    const { container } = render(<Loading />);

    expect(container.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('should render with text', () => {
    render(<Loading text="Loading..." />);

    expect(screen.getByText('Loading...')).toBeInTheDocument();
  });

  it('should render without text by default', () => {
    render(<Loading />);

    expect(screen.queryByText('Loading...')).not.toBeInTheDocument();
  });

  describe('sizes', () => {
    it('should render medium size by default', () => {
      render(<Loading text="Loading" />);

      expect(screen.getByText('Loading')).toHaveClass('text-sm');
    });

    it('should render small size', () => {
      render(<Loading size="sm" text="Loading" />);

      expect(screen.getByText('Loading')).toHaveClass('text-xs');
    });

    it('should render large size', () => {
      render(<Loading size="lg" text="Loading" />);

      expect(screen.getByText('Loading')).toHaveClass('text-base');
    });
  });

  describe('fullScreen', () => {
    it('should not be full screen by default', () => {
      const { container } = render(<Loading />);

      expect(container.querySelector('.fixed')).not.toBeInTheDocument();
    });

    it('should be full screen when fullScreen is true', () => {
      const { container } = render(<Loading fullScreen />);

      expect(container.querySelector('.fixed')).toBeInTheDocument();
      expect(container.querySelector('.inset-0')).toBeInTheDocument();
    });
  });

  it('should accept custom className', () => {
    const { container } = render(<Loading className="custom-class" />);

    expect(container.querySelector('.custom-class')).toBeInTheDocument();
  });
});

describe('Skeleton', () => {
  it('should render a skeleton', () => {
    const { container } = render(<Skeleton />);

    expect(container.querySelector('.animate-pulse')).toBeInTheDocument();
  });

  it('should accept custom className', () => {
    const { container } = render(<Skeleton className="h-4 w-32" />);

    expect(container.querySelector('.h-4')).toBeInTheDocument();
    expect(container.querySelector('.w-32')).toBeInTheDocument();
  });

  it('should have rounded corners', () => {
    const { container } = render(<Skeleton />);

    expect(container.querySelector('.rounded')).toBeInTheDocument();
  });
});

describe('CardSkeleton', () => {
  it('should render multiple skeleton lines', () => {
    const { container } = render(<CardSkeleton />);

    const skeletons = container.querySelectorAll('.animate-pulse');
    expect(skeletons.length).toBe(3);
  });

  it('should have card styling', () => {
    const { container } = render(<CardSkeleton />);

    expect(container.querySelector('.rounded-lg')).toBeInTheDocument();
    expect(container.querySelector('.border')).toBeInTheDocument();
  });
});

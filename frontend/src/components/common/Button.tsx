import { ButtonHTMLAttributes, forwardRef } from 'react';
import { LucideIcon, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';

type ButtonVariant = 'primary' | 'secondary' | 'danger' | 'ghost';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  icon?: LucideIcon;
  iconPosition?: 'left' | 'right';
  isLoading?: boolean;
  fullWidth?: boolean;
}

const variantStyles: Record<ButtonVariant, string> = {
  primary: 'bg-primary-light dark:bg-primary-dark text-white hover:opacity-90',
  secondary: 'bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-gray-100 hover:bg-gray-300 dark:hover:bg-gray-600',
  danger: 'bg-error-light dark:bg-error-dark text-white hover:opacity-90',
  ghost: 'bg-transparent text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800',
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: 'px-3 py-1.5 text-sm',
  md: 'px-4 py-2 text-base',
  lg: 'px-6 py-3 text-lg',
};

const iconSizes: Record<ButtonSize, number> = {
  sm: 14,
  md: 18,
  lg: 22,
};

/**
 * Button component with variants, sizes, and loading state
 *
 * @example
 * <Button variant="primary" onClick={handleClick}>Save</Button>
 * <Button variant="danger" icon={Trash} isLoading={isDeleting}>Delete</Button>
 */
export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      variant = 'primary',
      size = 'md',
      icon: Icon,
      iconPosition = 'left',
      isLoading = false,
      fullWidth = false,
      disabled,
      className,
      children,
      ...props
    },
    ref
  ) => {
    const isDisabled = disabled || isLoading;

    return (
      <button
        ref={ref}
        disabled={isDisabled}
        className={clsx(
          // Base styles
          'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors',
          'focus:outline-none focus:ring-2 focus:ring-primary-light dark:focus:ring-primary-dark focus:ring-offset-2',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          // Variant and size
          variantStyles[variant],
          sizeStyles[size],
          // Full width
          fullWidth && 'w-full',
          // Custom classes
          className
        )}
        {...props}
      >
        {/* Loading spinner or left icon */}
        {isLoading ? (
          <Loader2 size={iconSizes[size]} className="animate-spin" />
        ) : (
          Icon && iconPosition === 'left' && <Icon size={iconSizes[size]} />
        )}

        {/* Button text */}
        {children}

        {/* Right icon (not shown when loading) */}
        {!isLoading && Icon && iconPosition === 'right' && (
          <Icon size={iconSizes[size]} />
        )}
      </button>
    );
  }
);

Button.displayName = 'Button';

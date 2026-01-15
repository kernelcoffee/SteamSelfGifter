import { clsx } from 'clsx';

interface ToggleProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  description?: string;
}

/**
 * Toggle switch component for boolean settings
 *
 * @example
 * <Toggle
 *   label="Enable DLC"
 *   checked={dlcEnabled}
 *   onChange={setDlcEnabled}
 * />
 */
export function Toggle({
  label,
  checked,
  onChange,
  disabled = false,
  description,
}: ToggleProps) {
  const id = label.toLowerCase().replace(/\s+/g, '-');

  return (
    <div className="flex items-start gap-3">
      {/* Toggle switch */}
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={clsx(
          'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out',
          'focus:outline-none focus:ring-2 focus:ring-primary-light dark:focus:ring-primary-dark focus:ring-offset-2',
          'disabled:opacity-50 disabled:cursor-not-allowed',
          checked
            ? 'bg-primary-light dark:bg-primary-dark'
            : 'bg-gray-200 dark:bg-gray-700'
        )}
      >
        <span className="sr-only">{label}</span>
        <span
          className={clsx(
            'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out',
            checked ? 'translate-x-5' : 'translate-x-0'
          )}
        />
      </button>

      {/* Label and description */}
      <div className="flex flex-col">
        <label
          htmlFor={id}
          className={clsx(
            'text-sm font-medium',
            disabled
              ? 'text-gray-400 dark:text-gray-500'
              : 'text-gray-900 dark:text-gray-100 cursor-pointer'
          )}
          onClick={() => !disabled && onChange(!checked)}
        >
          {label}
        </label>
        {description && (
          <p className="text-sm text-gray-500 dark:text-gray-400">{description}</p>
        )}
      </div>
    </div>
  );
}

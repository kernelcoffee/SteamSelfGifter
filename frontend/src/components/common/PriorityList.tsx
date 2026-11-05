import { useId, useLayoutEffect, useRef, useState, type DragEvent } from 'react';
import { ArrowDown, ArrowUp, GripVertical, Info, Plus, Trash2 } from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from './Badge';
import { Button } from './Button';
import { Input } from './Input';
import type {
  AutojoinPriorityItem,
  AutojoinPriorityType,
  AutojoinPriorityTypeInfo,
  RegistryParam,
} from '@/types';
import { absentTypes, defaultItem, moveItem, priorityLabel } from '@/utils/autojoinPriorities';

interface PriorityListProps {
  /** The list in display (and entry) order. */
  items: AutojoinPriorityItem[];
  onChange: (items: AutojoinPriorityItem[]) => void;
  /** Priority types from the registry: labels, descriptions, exemption, bounds. */
  types: AutojoinPriorityTypeInfo[];
  /** Registry limit on the number of items. */
  maxItems: number;
  /** Registry bounds and default of the ending-soon threshold. */
  threshold: RegistryParam;
  /** Raw text of the ending-soon threshold field. */
  thresholdText: string;
  onThresholdTextChange: (text: string) => void;
  thresholdError?: string;
}

type MoveDirection = 'up' | 'down';

const ADD_SELECT = 'add:select';

/**
 * Reorderable list of auto-join priorities. Fully controlled: the parent owns
 * the items and the threshold text. Works by buttons alone (keyboard, touch)
 * and by HTML5 drag and drop with a pointer. Labels, the filter exemption
 * badge, the threshold bounds and the item cap all come from the registry.
 */
export function PriorityList({
  items,
  onChange,
  types,
  maxItems,
  threshold,
  thresholdText,
  onThresholdTextChange,
  thresholdError,
}: PriorityListProps) {
  const baseId = useId();
  const addSelectId = `${baseId}-add`;
  const fullNoteId = `${baseId}-full`;

  // Source row of a drag in progress; a ref because it never affects render.
  const dragFrom = useRef<number | null>(null);
  const [dragSource, setDragSource] = useState<number | null>(null);
  const [dragOver, setDragOver] = useState<number | null>(null);
  const [announcement, setAnnouncement] = useState('');
  const [addChoice, setAddChoice] = useState<AutojoinPriorityType | null>(null);

  // Row buttons by `${type}:${role}`, used to keep focus on a live control.
  const controls = useRef(new Map<string, HTMLElement>());
  // Control to focus once the change that caused it has been committed: the
  // control may be disabled, or not mounted yet, when the button is pressed.
  const pendingFocus = useRef<string | null>(null);
  const addSelect = useRef<HTMLSelectElement>(null);
  const registerControl = (key: string) => (node: HTMLElement | null) => {
    if (!node) {
      controls.current.delete(key);
      return;
    }
    controls.current.set(key, node);
  };
  // Runs after every commit, once the DOM reflects the new order and the
  // disabled states; it only moves focus and never sets state.
  useLayoutEffect(() => {
    const key = pendingFocus.current;
    if (key === null) return;
    pendingFocus.current = null;
    const node = key === ADD_SELECT ? addSelect.current : controls.current.get(key);
    node?.focus();
  });

  const absent = absentTypes(items, types);
  const isFull = absent.length === 0 || items.length >= maxItems;
  const fullReason =
    absent.length === 0
      ? 'All priority types are in the list'
      : `The list holds at most ${maxItems} priorities`;
  // The select's value is derived: the last choice while it is still
  // absent, otherwise the first absent type.
  const effectiveChoice =
    absent.find((t) => t.type === addChoice)?.type ?? absent[0]?.type ?? null;

  const labelOf = (type: AutojoinPriorityType) => priorityLabel(type, types);
  const position = (index: number) => `position ${index + 1} of ${items.length}`;

  const move = (index: number, direction: MoveDirection) => {
    const to = direction === 'up' ? index - 1 : index + 1;
    if (to < 0 || to >= items.length) return;
    const { type } = items[index];
    // Focus is re-applied after every move: React re-inserts the moved row's
    // node, which blurs it in a browser. The pressed button keeps focus while
    // it stays enabled; once the row reaches the end it moved to, that button
    // is disabled and focus goes to the row's other move button, which the
    // same render enables.
    const atEnd = to === 0 || to === items.length - 1;
    const opposite = direction === 'up' ? 'down' : 'up';
    pendingFocus.current = `${type}:${atEnd ? opposite : direction}`;
    onChange(moveItem(items, index, to));
    setAnnouncement(`${labelOf(type)} moved to ${position(to)}`);
  };

  const remove = (index: number) => {
    const { type } = items[index];
    const next = items[index + 1] ?? items[index - 1];
    pendingFocus.current = next ? `${next.type}:remove` : ADD_SELECT;
    onChange(items.filter((_, i) => i !== index));
    setAnnouncement(`${labelOf(type)} removed`);
  };

  const add = () => {
    if (isFull || effectiveChoice === null) return;
    const item = defaultItem(effectiveChoice, threshold.default);
    if (item.type === 'ending_soon') {
      onThresholdTextChange(String(item.threshold_minutes));
    }
    // The Add controls are disabled once the list is full; focus the new
    // row instead of letting focus drop to the page.
    if (absent.length === 1 || items.length + 1 >= maxItems) {
      pendingFocus.current = `${item.type}:remove`;
    }
    onChange([...items, item]);
    setAnnouncement(`${labelOf(effectiveChoice)} added at position ${items.length + 1} of ${items.length + 1}`);
  };

  const clearDrag = () => {
    dragFrom.current = null;
    setDragSource(null);
    setDragOver(null);
  };

  const onDragStart = (index: number) => (event: DragEvent<HTMLElement>) => {
    dragFrom.current = index;
    setDragSource(index);
    // Firefox only starts a drag that carries data.
    event.dataTransfer.setData('text/plain', items[index].type);
    event.dataTransfer.effectAllowed = 'move';
  };

  const onDragOver = (index: number) => (event: DragEvent<HTMLLIElement>) => {
    if (dragFrom.current === null) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    if (dragOver !== index) setDragOver(index);
  };

  const onDrop = (index: number) => (event: DragEvent<HTMLLIElement>) => {
    event.preventDefault();
    const from = dragFrom.current;
    clearDrag();
    if (from === null || from === index) return;
    const { type } = items[from];
    onChange(moveItem(items, from, index));
    setAnnouncement(`${labelOf(type)} moved to ${position(index)}`);
  };

  return (
    <div className="space-y-3">
      {items.length === 0 ? (
        <p className="flex items-start gap-2 text-sm text-gray-600 dark:text-gray-300">
          <Info size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
          <span>No priorities: every giveaway obeys the filters and is entered highest price first.</span>
        </p>
      ) : (
        <ol aria-label="Priority order" className="space-y-2">
          {items.map((item, index) => {
            const info = types.find((t) => t.type === item.type);
            const label = labelOf(item.type);
            const isTarget = dragOver === index && dragSource !== null && dragSource !== index;
            return (
              <li
                key={item.type}
                onDragOver={onDragOver(index)}
                onDrop={onDrop(index)}
                onDragLeave={() => {
                  if (dragOver === index) setDragOver(null);
                }}
                className={clsx(
                  'flex flex-wrap items-center gap-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-surface-dark p-3',
                  dragSource === index && 'opacity-50',
                  isTarget && 'ring-2 ring-primary-light dark:ring-primary-dark',
                  isTarget && dragSource !== null && dragSource > index && 'border-t-2 border-t-primary-light dark:border-t-primary-dark',
                  isTarget && dragSource !== null && dragSource < index && 'border-b-2 border-b-primary-light dark:border-b-primary-dark',
                )}
              >
                <span
                  draggable="true"
                  aria-hidden="true"
                  tabIndex={-1}
                  title="Drag to reorder"
                  onDragStart={onDragStart(index)}
                  onDragEnd={clearDrag}
                  className="cursor-grab text-gray-400 dark:text-gray-500 pointer-coarse:hidden"
                >
                  <GripVertical size={18} />
                </span>
                <span className="font-medium text-gray-900 dark:text-white">{index + 1}.</span>
                <div className="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1">
                  <span className="font-medium text-gray-900 dark:text-white">{label}</span>
                  {info && (
                    <span className="min-w-0 text-sm text-gray-500 dark:text-gray-400">
                      {info.description}
                    </span>
                  )}
                  {info && (
                    <Badge variant={info.exempt_from_filters ? 'info' : 'default'} size="sm">
                      {info.exempt_from_filters ? 'Skips the filters' : 'Obeys the filters'}
                    </Badge>
                  )}
                </div>
                <div className="ml-auto flex flex-wrap gap-2">
                  <Button
                    ref={registerControl(`${item.type}:up`)}
                    type="button"
                    variant="secondary"
                    size="sm"
                    icon={ArrowUp}
                    aria-label={`Move ${label} up`}
                    disabled={index === 0}
                    onClick={() => move(index, 'up')}
                  >
                    Move up
                  </Button>
                  <Button
                    ref={registerControl(`${item.type}:down`)}
                    type="button"
                    variant="secondary"
                    size="sm"
                    icon={ArrowDown}
                    aria-label={`Move ${label} down`}
                    disabled={index === items.length - 1}
                    onClick={() => move(index, 'down')}
                  >
                    Move down
                  </Button>
                  <Button
                    ref={registerControl(`${item.type}:remove`)}
                    type="button"
                    variant="secondary"
                    size="sm"
                    icon={Trash2}
                    aria-label={`Remove ${label}`}
                    onClick={() => remove(index)}
                  >
                    Remove
                  </Button>
                </div>
                {item.type === 'ending_soon' && (
                  // A full-basis wrapper gives the field its own line under
                  // the row at every width, so the buttons stay on the first
                  // line at the right edge like every other row; the inner
                  // div caps the field's width.
                  <div className="basis-full">
                    <div className="sm:w-56">
                      <Input
                        id={`${baseId}-threshold`}
                        label={`${label} threshold (minutes)`}
                        type="number"
                        inputMode="numeric"
                        min={threshold.min}
                        max={threshold.max}
                        value={thresholdText}
                        onChange={(e) => onThresholdTextChange(e.target.value)}
                        helperText={`${threshold.min} to ${threshold.max} minutes`}
                        error={thresholdError}
                      />
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}

      <div className="space-y-1">
        <label htmlFor={addSelectId} className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Add priority
        </label>
        <div className="flex flex-wrap gap-2">
          <select
            id={addSelectId}
            ref={addSelect}
            value={effectiveChoice ?? ''}
            disabled={isFull}
            aria-describedby={isFull ? fullNoteId : undefined}
            onChange={(e) => {
              const choice = absent.find((t) => t.type === e.target.value);
              if (choice) setAddChoice(choice.type);
            }}
            className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-gray-100 dark:[color-scheme:dark] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {absent.map((t) => (
              <option key={t.type} value={t.type}>
                {t.label}
              </option>
            ))}
          </select>
          <Button
            type="button"
            variant="secondary"
            icon={Plus}
            aria-label="Add the selected priority"
            disabled={isFull}
            aria-describedby={isFull ? fullNoteId : undefined}
            onClick={add}
          >
            Add
          </Button>
        </div>
        {isFull && (
          <p id={fullNoteId} className="text-sm text-gray-500 dark:text-gray-400">
            {fullReason}
          </p>
        )}
      </div>

      <p className="sr-only" aria-live="polite">
        {announcement}
      </p>
    </div>
  );
}

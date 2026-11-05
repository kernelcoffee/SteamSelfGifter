import { Ban, Check, Plus } from 'lucide-react';
import { clsx } from 'clsx';
import { Button, Input } from '@/components/common';
import { useGameGenres } from '@/hooks';
import {
  fullListReason,
  genreDraftError,
  genreKey,
  isOnList,
  overlappingGenres,
  pressGenre,
  type GenreDraftState,
  type GenreLimits,
  type GenreListName,
  type GenreLists,
} from '@/utils/genreLists';

interface GenreListsEditorProps {
  excluded: string[];
  included: string[];
  onChange: (lists: GenreLists) => void;
  /** Text typed in the Add a genre field, owned by the form so it can block Save. */
  draft: string;
  onDraftChange: (text: string) => void;
  draftTarget: GenreListName;
  onDraftTargetChange: (target: GenreListName) => void;
  draftState: GenreDraftState;
  /** Registry bounds: items per list and characters per genre. */
  limits: GenreLimits;
}

/** One row of the grid: a cached genre with its count, or a listed genre the cache does not know. */
interface GenreRow {
  name: string;
  count: number | null;
}

const BUTTON_TEXT: Record<GenreListName, string> = {
  excluded: 'Excluded',
  included: 'Included',
};

function joinNames(names: string[]): string {
  if (names.length <= 1) return names.join('');
  return `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}`;
}

/**
 * Rows in a fixed order: the cache's genres as the API returns them, then the
 * listed genres the cache does not know, in list order. Pressing a button never
 * reorders rows, so the control under the pointer stays where it is.
 */
function buildRows(cached: GenreRow[], lists: GenreLists): GenreRow[] {
  const seen = new Set(cached.map((row) => genreKey(row.name)));
  const rows = [...cached];
  for (const name of [...lists.excluded, ...lists.included]) {
    const key = genreKey(name);
    if (seen.has(key)) continue;
    seen.add(key);
    rows.push({ name, count: null });
  }
  return rows;
}

function rowName(row: GenreRow, cacheKnown: boolean): string {
  if (row.count !== null) return `${row.name} (${row.count} ${row.count === 1 ? 'game' : 'games'})`;
  return cacheKnown ? `${row.name} (not cached)` : row.name;
}

/**
 * Editor for both auto-join genre lists as one grid of genres, each with an
 * Excluded and an Included toggle; the buttons carry the state, nothing else
 * repeats it. A genre on both lists is legal: exclusion wins, and the row and
 * a note under the grid say so instead of moving it. Everything that appears
 * or disappears sits under the grid so the grid never shifts. Fully controlled;
 * the form owns the lists and the draft.
 */
export function GenreListsEditor({
  excluded,
  included,
  onChange,
  draft,
  onDraftChange,
  draftTarget,
  onDraftTargetChange,
  draftState,
  limits,
}: GenreListsEditorProps) {
  const genres = useGameGenres();
  const lists: GenreLists = { excluded, included };
  const isFull: Record<GenreListName, boolean> = {
    excluded: excluded.length >= limits.maxItems,
    included: included.length >= limits.maxItems,
  };
  const overlap = overlappingGenres(excluded, included);
  const overlapKeys = new Set(overlap.map(genreKey));
  const draftError = genreDraftError(draftState, draftTarget, limits);
  const cacheKnown = genres.isSuccess;
  const rows = buildRows(
    (genres.data ?? []).map(({ name, count }) => ({ name, count })),
    lists,
  );

  // Only a genre that can be added clears the field; otherwise the text and
  // its inline error stay so the user sees why nothing was added.
  const submitDraft = () => {
    if (draftState.status !== 'ready') return;
    onChange({ ...lists, [draftTarget]: [...lists[draftTarget], draftState.name] });
    onDraftChange('');
  };

  const toggleButton = (name: string, list: GenreListName) => {
    const pressed = isOnList(lists, name, list);
    const disabled = !pressed && isFull[list];
    return (
      <button
        type="button"
        aria-pressed={pressed}
        disabled={disabled}
        aria-describedby={disabled ? `${list}-genres-full` : undefined}
        title={disabled ? fullListReason(list, limits) : undefined}
        onClick={() => onChange(pressGenre(lists, name, list, limits))}
        className={clsx(
          'inline-flex w-24 shrink-0 items-center justify-center gap-1 rounded-md border px-2 py-1 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50',
          pressed && list === 'excluded' &&
            'border-red-300 bg-red-100 text-red-800 dark:border-red-800 dark:bg-red-900/30 dark:text-red-300',
          pressed && list === 'included' &&
            'border-green-300 bg-green-100 text-green-800 dark:border-green-800 dark:bg-green-900/30 dark:text-green-300',
          !pressed &&
            'border-gray-300 bg-white text-gray-500 hover:bg-gray-100 dark:border-gray-600 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700',
        )}
      >
        {/* The check mark shows the pressed state without relying on colour;
            the slot is always reserved so the label never moves. */}
        <span className="inline-flex w-3 shrink-0 justify-center">
          {pressed && <Check size={12} strokeWidth={3} aria-hidden="true" />}
        </span>
        {BUTTON_TEXT[list]}
      </button>
    );
  };

  const row = (item: GenreRow) => {
    const onBoth = overlapKeys.has(genreKey(item.name));
    return (
      <div
        key={genreKey(item.name)}
        role="group"
        aria-label={rowName(item, cacheKnown)}
        className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-gray-200 dark:border-gray-700 px-2 py-1"
      >
        {/* The name asks for 10rem; when the row is narrower than the name plus
            the controls (a phone), the controls wrap as one block under it and
            the name gets the full width instead of being cut to a few letters. */}
        <span
          className="min-w-0 grow basis-40 truncate text-sm text-gray-900 dark:text-white"
          title={item.name}
          data-testid="genre-name"
        >
          {item.name}
        </span>
        <div className="ml-auto flex shrink-0 items-center gap-2">
          <span
            className="w-8 shrink-0 text-right text-xs tabular-nums text-gray-500 dark:text-gray-400"
            title={
              item.count === null
                ? cacheKnown
                  ? 'Not in your game cache'
                  : 'Genre cache unavailable'
                : `${item.count} ${item.count === 1 ? 'game' : 'games'} in your cache`
            }
          >
            {item.count ?? '—'}
          </span>
          {/* Fixed slot so the buttons do not move when a genre lands on both lists */}
          <span className="inline-flex w-4 shrink-0 justify-center">
            {onBoth && (
              <Ban
                size={14}
                className="text-red-600 dark:text-red-400"
                aria-label="On both lists: exclusion wins, so never entered"
              />
            )}
          </span>
          {toggleButton(item.name, 'excluded')}
          {toggleButton(item.name, 'included')}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-3">
      <div>
        <p id="genres-heading" className="text-sm font-medium text-gray-900 dark:text-white">
          Genres
        </p>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Excluded: never enter a game with that genre. Included: while any genre is included, only
          enter games with at least one of them. Excluded wins over included.
        </p>
        <p className="text-xs tabular-nums text-gray-500 dark:text-gray-400">
          {excluded.length} excluded · {included.length} included
        </p>
      </div>

      {genres.isLoading ? (
        <p className="text-sm text-gray-500 dark:text-gray-400">Loading genres…</p>
      ) : (
        <>
          {genres.isError && (
            <p className="text-sm text-red-600 dark:text-red-400">
              Could not load the genre list; you can still type a genre below
            </p>
          )}
          {rows.length === 0 ? (
            !genres.isError && (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                No genres cached yet, genres appear as games are fetched from Steam
              </p>
            )
          ) : (
            <div
              role="group"
              aria-labelledby="genres-heading"
              className="grid grid-cols-1 gap-2 xl:grid-cols-2"
            >
              {rows.map(row)}
            </div>
          )}
        </>
      )}

      {/* Notes that come and go live under the grid so the grid never moves */}
      {(['excluded', 'included'] as const).map(
        (list) =>
          isFull[list] && (
            <p key={list} id={`${list}-genres-full`} className="text-sm text-yellow-700 dark:text-yellow-400">
              {fullListReason(list, limits)}
            </p>
          ),
      )}
      {overlap.length > 0 && (
        <p className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
          <Ban size={16} className="mt-0.5 shrink-0 text-red-600 dark:text-red-400" aria-hidden="true" />
          <span>
            {overlap.length === 1
              ? `${overlap[0]} is in both lists: exclusion wins, so it is never entered.`
              : `${joinNames(overlap)} are in both lists: exclusion wins, so they are never entered.`}
          </span>
        </p>
      )}
      {included.length > 0 && (
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Games with no genres cached yet are skipped while a genre is included.
        </p>
      )}

      {/* Manual add */}
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1 basis-48 max-w-sm">
          <Input
            label="Add a genre"
            placeholder="e.g. Sports"
            value={draft}
            error={draftError}
            onChange={(e) => onDraftChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                submitDraft();
              }
            }}
          />
        </div>
        <div>
          <label
            htmlFor="genre-add-target"
            className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
          >
            Add to list
          </label>
          <select
            id="genre-add-target"
            aria-label="Add to list"
            value={draftTarget}
            onChange={(e) => onDraftTargetChange(e.target.value === 'included' ? 'included' : 'excluded')}
            className="rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-sm text-gray-900 dark:text-gray-100 dark:[color-scheme:dark]"
          >
            <option value="excluded">Excluded</option>
            <option value="included">Included</option>
          </select>
        </div>
        <Button
          type="button"
          variant="secondary"
          icon={Plus}
          aria-label="Add genre"
          className="mt-6 shrink-0"
          disabled={draftState.status !== 'ready'}
          onClick={submitDraft}
        >
          Add
        </Button>
      </div>
    </div>
  );
}

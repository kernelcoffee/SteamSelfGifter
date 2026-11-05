/*
 * Pure helpers for the two auto-join genre lists (excluded and included).
 * Matching mirrors the backend normaliser: trim, ASCII-only case folding,
 * code-point length. The bounds come from the registry's limits.
 */

export type GenreListName = 'excluded' | 'included';

export interface GenreLists {
  excluded: string[];
  included: string[];
}

export interface GenreLimits {
  maxItems: number;
  maxLength: number;
}

/**
 * Key the backend dedupes and matches on: ASCII-only lowercasing, like
 * SQLite's `lower()` and `core.text.ascii_lower` ("É" stays "É", so
 * "Éducation" and "éducation" are two distinct genres).
 */
export function genreKey(genre: string): string {
  return genre.replace(/[A-Z]/g, (letter) => letter.toLowerCase());
}

/** Length the backend checks: code points after strip, not UTF-16 units. */
export function genreLength(genre: string): number {
  return Array.from(genre).length;
}

export type GenreDraftState =
  | { status: 'empty' }
  | { status: 'tooLong'; name: string }
  | { status: 'duplicate'; name: string; existing: string }
  | { status: 'full'; name: string }
  | { status: 'ready'; name: string };

/**
 * Whether the typed genre can be added to the target list, and if not, why.
 * Duplicates are checked against the target list only: the same genre on the
 * other list is legal (exclusion wins) and shows as an overlap.
 */
export function checkGenreDraft(
  draft: string,
  target: string[],
  limits: GenreLimits,
): GenreDraftState {
  const name = draft.trim();
  if (!name) return { status: 'empty' };
  if (genreLength(name) > limits.maxLength) return { status: 'tooLong', name };
  const key = genreKey(name);
  const existing = target.find((genre) => genreKey(genre) === key);
  if (existing !== undefined) return { status: 'duplicate', name, existing };
  if (target.length >= limits.maxItems) return { status: 'full', name };
  return { status: 'ready', name };
}

/** Why a pending genre draft blocks saving, or undefined when it does not. */
export function genreDraftSaveBlockedReason(
  state: GenreDraftState,
  target: GenreListName,
): string | undefined {
  switch (state.status) {
    case 'empty':
      return undefined;
    case 'ready':
      return `Press Add to put "${state.name}" on the ${target} list, or clear the field, to save`;
    case 'duplicate':
      return `"${state.existing}" is already on the ${target} list; clear the Add a genre field to save`;
    case 'tooLong':
      return 'Shorten or clear the genre in the Add a genre field to save';
    case 'full':
      return `The ${target} list is full; clear the Add a genre field to save`;
  }
}

/** Inline error under the Add a genre field, naming the registry bounds. */
export function genreDraftError(
  state: GenreDraftState,
  target: GenreListName,
  limits: GenreLimits,
): string | undefined {
  switch (state.status) {
    case 'tooLong':
      return `Genre names are limited to ${limits.maxLength} characters`;
    case 'duplicate':
      return `${state.existing} is already in the ${target} list`;
    case 'full':
      return fullListReason(target, limits);
    case 'empty':
    case 'ready':
      return undefined;
  }
}

/** Visible reason a list cannot take another genre. */
export function fullListReason(target: GenreListName, limits: GenreLimits): string {
  return `The ${target} list is full (${limits.maxItems} genres)`;
}

/** Included genres that are also excluded (matched by genreKey), in included order. */
export function overlappingGenres(excluded: string[], included: string[]): string[] {
  const excludedKeys = new Set(excluded.map(genreKey));
  return included.filter((genre) => excludedKeys.has(genreKey(genre)));
}

function hasGenre(list: string[], name: string): boolean {
  const key = genreKey(name);
  return list.some((genre) => genreKey(genre) === key);
}

function withGenre(list: string[], name: string): string[] {
  return hasGenre(list, name) ? list : [...list, name];
}

function withoutGenre(list: string[], name: string): string[] {
  const key = genreKey(name);
  return list.filter((genre) => genreKey(genre) !== key);
}

export type GenreState = 'neutral' | GenreListName;

/**
 * Put a genre in exactly one state: neutral removes it from both lists; a
 * list state adds it there (keeping an existing spelling and position) and
 * removes it from the other list.
 */
export function setGenreState(lists: GenreLists, name: string, state: GenreState): GenreLists {
  switch (state) {
    case 'neutral':
      return {
        excluded: withoutGenre(lists.excluded, name),
        included: withoutGenre(lists.included, name),
      };
    case 'excluded':
      return {
        excluded: withGenre(lists.excluded, name),
        included: withoutGenre(lists.included, name),
      };
    case 'included':
      return {
        excluded: withoutGenre(lists.excluded, name),
        included: withGenre(lists.included, name),
      };
  }
}

/**
 * A press on a picker button: the active list's button takes the genre out
 * of that list only (back to neutral, or to the other list it was also on);
 * the inactive one moves it there. A press that would overfill the target
 * list changes nothing (the button is disabled with a reason).
 */
export function pressGenre(
  lists: GenreLists,
  name: string,
  target: GenreListName,
  limits: GenreLimits,
): GenreLists {
  if (hasGenre(lists[target], name)) {
    return target === 'excluded'
      ? { excluded: withoutGenre(lists.excluded, name), included: lists.included }
      : { excluded: lists.excluded, included: withoutGenre(lists.included, name) };
  }
  if (lists[target].length >= limits.maxItems) return lists;
  return setGenreState(lists, name, target);
}

/** Whether a genre is on the given list (by genreKey). */
export function isOnList(lists: GenreLists, name: string, list: GenreListName): boolean {
  return hasGenre(lists[list], name);
}

import { describe, it, expect } from 'vitest';
import {
  checkGenreDraft,
  fullListReason,
  genreDraftError,
  genreDraftSaveBlockedReason,
  genreKey,
  genreLength,
  isOnList,
  overlappingGenres,
  pressGenre,
  setGenreState,
  type GenreLists,
} from './genreLists';

const limits = { maxItems: 50, maxLength: 64 };
const many = (n: number) => Array.from({ length: n }, (_, i) => `Genre ${i}`);

describe('genreKey and genreLength', () => {
  it('folds ASCII letters only, like the backend', () => {
    expect(genreKey('Action RPG')).toBe('action rpg');
    expect(genreKey('Éducation')).toBe('Éducation');
    expect(genreKey('Éducation')).not.toBe(genreKey('éducation'));
  });

  it('counts code points, not UTF-16 units', () => {
    expect(genreLength('🎮🎮')).toBe(2);
    expect(genreLength('abc')).toBe(3);
  });
});

describe('checkGenreDraft', () => {
  it('is empty for a blank or whitespace draft', () => {
    expect(checkGenreDraft('', [], limits)).toEqual({ status: 'empty' });
    expect(checkGenreDraft('   ', [], limits)).toEqual({ status: 'empty' });
  });

  it('is ready with the trimmed name', () => {
    expect(checkGenreDraft('  Sports ', [], limits)).toEqual({ status: 'ready', name: 'Sports' });
  });

  it('accepts exactly the maximum length and rejects one more', () => {
    expect(checkGenreDraft('a'.repeat(64), [], limits).status).toBe('ready');
    expect(checkGenreDraft('a'.repeat(65), [], limits)).toEqual({
      status: 'tooLong',
      name: 'a'.repeat(65),
    });
    expect(checkGenreDraft('🎮'.repeat(33), [], limits).status).toBe('ready');
  });

  it('refuses an ASCII case variant already on the target list, naming it', () => {
    expect(checkGenreDraft('action', ['Action'], limits)).toEqual({
      status: 'duplicate',
      name: 'action',
      existing: 'Action',
    });
  });

  it('accepts a non-ASCII case variant as a distinct genre', () => {
    expect(checkGenreDraft('éducation', ['Éducation'], limits).status).toBe('ready');
  });

  it('is full at the registry maximum', () => {
    expect(checkGenreDraft('New', many(50), limits)).toEqual({ status: 'full', name: 'New' });
    expect(checkGenreDraft('New', many(49), limits).status).toBe('ready');
  });

  it('uses the limits it is given', () => {
    expect(checkGenreDraft('abcd', [], { maxItems: 1, maxLength: 3 }).status).toBe('tooLong');
    expect(checkGenreDraft('abc', ['x'], { maxItems: 1, maxLength: 3 }).status).toBe('full');
  });
});

describe('save-blocked reasons and inline errors', () => {
  it('names the target list', () => {
    expect(genreDraftSaveBlockedReason({ status: 'empty' }, 'included')).toBeUndefined();
    expect(genreDraftSaveBlockedReason({ status: 'ready', name: 'RPG' }, 'included')).toBe(
      'Press Add to put "RPG" on the included list, or clear the field, to save',
    );
    expect(
      genreDraftSaveBlockedReason({ status: 'duplicate', name: 'action', existing: 'Action' }, 'excluded'),
    ).toBe('"Action" is already on the excluded list; clear the Add a genre field to save');
    expect(genreDraftSaveBlockedReason({ status: 'tooLong', name: 'x' }, 'excluded')).toBe(
      'Shorten or clear the genre in the Add a genre field to save',
    );
    expect(genreDraftSaveBlockedReason({ status: 'full', name: 'x' }, 'included')).toBe(
      'The included list is full; clear the Add a genre field to save',
    );
  });

  it('names the registry bounds inline', () => {
    expect(genreDraftError({ status: 'tooLong', name: 'x' }, 'excluded', limits)).toBe(
      'Genre names are limited to 64 characters',
    );
    expect(
      genreDraftError({ status: 'duplicate', name: 'action', existing: 'Action' }, 'excluded', limits),
    ).toBe('Action is already in the excluded list');
    expect(genreDraftError({ status: 'full', name: 'x' }, 'included', limits)).toBe(
      'The included list is full (50 genres)',
    );
    expect(genreDraftError({ status: 'ready', name: 'x' }, 'included', limits)).toBeUndefined();
    expect(genreDraftError({ status: 'empty' }, 'included', limits)).toBeUndefined();
    expect(fullListReason('excluded', { maxItems: 7, maxLength: 1 })).toBe(
      'The excluded list is full (7 genres)',
    );
  });
});

describe('overlappingGenres', () => {
  it('lists included genres also excluded, by ASCII key, in included order', () => {
    expect(overlappingGenres(['action', 'Horror'], ['RPG', 'Horror', 'Action'])).toEqual([
      'Horror',
      'Action',
    ]);
    expect(overlappingGenres([], ['RPG'])).toEqual([]);
  });
});

describe('setGenreState', () => {
  const lists: GenreLists = { excluded: ['Action'], included: ['RPG'] };

  it('moves a genre to the other list', () => {
    expect(setGenreState(lists, 'Action', 'included')).toEqual({
      excluded: [],
      included: ['RPG', 'Action'],
    });
    expect(setGenreState(lists, 'rpg', 'excluded')).toEqual({
      excluded: ['Action', 'rpg'],
      included: [],
    });
  });

  it('keeps an existing spelling and position on the target list', () => {
    expect(setGenreState({ excluded: ['A', 'Action', 'B'], included: ['action'] }, 'ACTION', 'excluded')).toEqual({
      excluded: ['A', 'Action', 'B'],
      included: [],
    });
  });

  it('neutral removes the genre from both lists', () => {
    expect(setGenreState({ excluded: ['Action'], included: ['action'] }, 'Action', 'neutral')).toEqual({
      excluded: [],
      included: [],
    });
  });
});

describe('pressGenre', () => {
  it('moves a neutral or other-list genre into the pressed list', () => {
    expect(pressGenre({ excluded: [], included: [] }, 'Action', 'excluded', limits)).toEqual({
      excluded: ['Action'],
      included: [],
    });
    expect(pressGenre({ excluded: ['Action'], included: [] }, 'Action', 'included', limits)).toEqual({
      excluded: [],
      included: ['Action'],
    });
  });

  it('pressing the active list returns the genre to neutral', () => {
    expect(pressGenre({ excluded: [], included: ['Action'] }, 'Action', 'included', limits)).toEqual({
      excluded: [],
      included: [],
    });
    expect(pressGenre({ excluded: ['Action'], included: [] }, 'Action', 'excluded', limits)).toEqual({
      excluded: [],
      included: [],
    });
  });

  it('on a genre in both lists, takes it out of the pressed list only', () => {
    const both = { excluded: ['Action'], included: ['Action'] };
    expect(pressGenre(both, 'Action', 'included', limits)).toEqual({
      excluded: ['Action'],
      included: [],
    });
    expect(pressGenre(both, 'Action', 'excluded', limits)).toEqual({
      excluded: [],
      included: ['Action'],
    });
  });

  it('changes nothing when the target list is full', () => {
    const full = { excluded: many(50), included: ['Action'] };
    expect(pressGenre(full, 'Action', 'excluded', limits)).toBe(full);
  });

  it('isOnList matches by ASCII key', () => {
    expect(isOnList({ excluded: ['Action'], included: [] }, 'ACTION', 'excluded')).toBe(true);
    expect(isOnList({ excluded: ['Action'], included: [] }, 'Action', 'included')).toBe(false);
  });
});

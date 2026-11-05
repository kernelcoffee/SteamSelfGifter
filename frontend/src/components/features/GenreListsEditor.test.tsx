import { describe, it, expect, vi, beforeEach } from 'vitest';
import { useState } from 'react';
import { render, screen, within, userEvent } from '@/test/utils';
import { GenreListsEditor } from './GenreListsEditor';
import { api } from '@/services/api';
import { checkGenreDraft, type GenreListName, type GenreLists } from '@/utils/genreLists';
import type { GenreCount } from '@/types';

vi.mock('@/services/api', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    getGameGenres: vi.fn(),
  },
}));

const mockApi = vi.mocked(api);

const genres: GenreCount[] = [
  { name: 'Action', count: 12 },
  { name: 'Indie', count: 9 },
  { name: 'Sports', count: 1 },
];

const limits = { maxItems: 50, maxLength: 64 };

function Host({
  initial = { excluded: [], included: [] },
  onChange = () => {},
  hostLimits = limits,
}: {
  initial?: GenreLists;
  onChange?: (lists: GenreLists) => void;
  hostLimits?: typeof limits;
}) {
  const [lists, setLists] = useState(initial);
  const [draft, setDraft] = useState('');
  const [target, setTarget] = useState<GenreListName>('excluded');
  return (
    <GenreListsEditor
      excluded={lists.excluded}
      included={lists.included}
      onChange={(next) => {
        setLists(next);
        onChange(next);
      }}
      draft={draft}
      onDraftChange={setDraft}
      draftTarget={target}
      onDraftTargetChange={setTarget}
      draftState={checkGenreDraft(draft, lists[target], hostLimits)}
      limits={hostLimits}
    />
  );
}

function mockGenres(list: GenreCount[] = genres) {
  mockApi.getGameGenres.mockResolvedValue({ success: true, data: { genres: list } });
}

async function row(name: string) {
  return screen.findByRole('group', { name });
}

function toggles(group: HTMLElement) {
  return {
    excluded: within(group).getByRole('button', { name: 'Excluded' }),
    included: within(group).getByRole('button', { name: 'Included' }),
  };
}

describe('GenreListsEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGenres();
  });

  it('renders every cached genre once as a row with its count and two unpressed toggles', async () => {
    render(<Host />);

    const action = await row('Action (12 games)');
    expect(within(action).getByText('Action')).toBeInTheDocument();
    expect(within(action).getByText('12')).toBeInTheDocument();
    expect(toggles(action).excluded).toHaveAttribute('aria-pressed', 'false');
    expect(toggles(action).included).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByRole('group', { name: 'Sports (1 game)' })).toBeInTheDocument();
    const grid = screen.getByRole('group', { name: 'Genres' });
    expect(within(grid).getAllByRole('group')).toHaveLength(3);
    expect(screen.getByText('0 excluded · 0 included')).toBeInTheDocument();
    // The state lives in the buttons only: no state word, no chip lists.
    expect(screen.queryByText('Neutral')).not.toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Excluded genres' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Remove / })).not.toBeInTheDocument();
  });

  it('pressing Included moves a genre out of the excluded list', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Host initial={{ excluded: ['Action'], included: [] }} onChange={onChange} />);

    const action = await row('Action (12 games)');
    expect(toggles(action).excluded).toHaveAttribute('aria-pressed', 'true');
    await user.click(toggles(action).included);

    expect(onChange).toHaveBeenLastCalledWith({ excluded: [], included: ['Action'] });
    expect(toggles(action).included).toHaveAttribute('aria-pressed', 'true');
    expect(toggles(action).excluded).toHaveAttribute('aria-pressed', 'false');
    expect(screen.getByText('0 excluded · 1 included')).toBeInTheDocument();
  });

  it('marks the pressed toggle with a check mark, so the state never rests on colour alone', async () => {
    const user = userEvent.setup();
    render(<Host initial={{ excluded: ['Action'], included: [] }} />);

    const action = await row('Action (12 games)');
    const indie = await row('Indie (9 games)');
    // Same visible word either way; only the pressed one carries the mark.
    expect(toggles(action).excluded).toHaveTextContent('Excluded');
    expect(toggles(action).excluded.querySelector('svg')).not.toBeNull();
    expect(toggles(action).included.querySelector('svg')).toBeNull();
    expect(toggles(indie).excluded.querySelector('svg')).toBeNull();
    expect(toggles(indie).included.querySelector('svg')).toBeNull();

    await user.click(toggles(action).included);

    expect(toggles(action).excluded.querySelector('svg')).toBeNull();
    expect(toggles(action).included.querySelector('svg')).not.toBeNull();
  });

  it('lets the controls wrap as one block under the name instead of squeezing it', async () => {
    render(<Host />);

    const action = await row('Action (12 games)');
    expect(action).toHaveClass('flex', 'flex-wrap');
    const name = within(action).getByTestId('genre-name');
    expect(name).toHaveTextContent('Action');
    expect(name).toHaveClass('grow', 'basis-40', 'min-w-0', 'truncate');
    // Count, both-lists slot and both toggles move together.
    const block = toggles(action).excluded.parentElement;
    expect(block).toBe(toggles(action).included.parentElement);
    expect(block).toHaveClass('ml-auto', 'shrink-0');
    expect(block).toContainElement(within(action).getByTitle('12 games in your cache'));
  });

  it('pressing the active toggle again returns the genre to neutral', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Host initial={{ excluded: [], included: ['Action'] }} onChange={onChange} />);

    const action = await row('Action (12 games)');
    await user.click(toggles(action).included);

    expect(onChange).toHaveBeenLastCalledWith({ excluded: [], included: [] });
    expect(toggles(action).included).toHaveAttribute('aria-pressed', 'false');
    expect(toggles(action).excluded).toHaveAttribute('aria-pressed', 'false');
  });

  it('keeps the same elements in the same place when a toggle is pressed', async () => {
    const user = userEvent.setup();
    render(<Host initial={{ excluded: ['Indie'], included: [] }} />);

    const action = await row('Action (12 games)');
    const controls = () => Array.from(action.querySelectorAll('span, button, div'));
    const before = controls();
    const { excluded, included } = toggles(action);
    const gridBefore = within(screen.getByRole('group', { name: 'Genres' }))
      .getAllByRole('group')
      .map((g) => g.getAttribute('aria-label'));

    await user.click(excluded);
    await user.click(included);

    // Same DOM nodes, same order: nothing was inserted, removed or reordered.
    expect(controls()).toEqual(before);
    expect(toggles(action).excluded).toBe(excluded);
    expect(toggles(action).included).toBe(included);
    expect(
      within(screen.getByRole('group', { name: 'Genres' }))
        .getAllByRole('group')
        .map((g) => g.getAttribute('aria-label')),
    ).toEqual(gridBefore);
  });

  it('adds a typed genre to the list chosen next to the field, by button or Enter, as a row', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Host onChange={onChange} />);
    await row('Action (12 games)');

    await user.selectOptions(screen.getByRole('combobox', { name: 'Add to list' }), 'included');
    await user.type(screen.getByLabelText('Add a genre'), 'RPG');
    await user.click(screen.getByRole('button', { name: 'Add genre' }));
    expect(onChange).toHaveBeenLastCalledWith({ excluded: [], included: ['RPG'] });
    expect(screen.getByLabelText('Add a genre')).toHaveValue('');
    const rpg = screen.getByRole('group', { name: 'RPG (not cached)' });
    expect(toggles(rpg).included).toHaveAttribute('aria-pressed', 'true');
    expect(within(rpg).getByTitle('Not in your game cache')).toHaveTextContent('—');

    await user.selectOptions(screen.getByRole('combobox', { name: 'Add to list' }), 'excluded');
    await user.type(screen.getByLabelText('Add a genre'), 'Racing{Enter}');
    expect(onChange).toHaveBeenLastCalledWith({ excluded: ['Racing'], included: ['RPG'] });
    // Uncached rows follow the cached ones in list order.
    const names = within(screen.getByRole('group', { name: 'Genres' }))
      .getAllByRole('group')
      .map((g) => g.getAttribute('aria-label'));
    expect(names).toEqual([
      'Action (12 games)',
      'Indie (9 games)',
      'Sports (1 game)',
      'Racing (not cached)',
      'RPG (not cached)',
    ]);
  });

  it('removes an uncached genre row once it is on no list', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Host initial={{ excluded: ['Action'], included: ['RPG'] }} onChange={onChange} />);
    await row('Action (12 games)');

    const rpg = screen.getByRole('group', { name: 'RPG (not cached)' });
    await user.click(toggles(rpg).included);
    expect(onChange).toHaveBeenLastCalledWith({ excluded: ['Action'], included: [] });
    expect(screen.queryByRole('group', { name: 'RPG (not cached)' })).not.toBeInTheDocument();

    const action = screen.getByRole('group', { name: 'Action (12 games)' });
    await user.click(toggles(action).excluded);
    expect(onChange).toHaveBeenLastCalledWith({ excluded: [], included: [] });
    expect(action).toBeInTheDocument();
  });

  it('refuses a duplicate on the target list with a reason and keeps the text', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Host initial={{ excluded: ['Action'], included: [] }} onChange={onChange} />);
    await row('Action (12 games)');

    await user.type(screen.getByLabelText('Add a genre'), 'action');

    expect(screen.getByRole('alert')).toHaveTextContent('Action is already in the excluded list');
    expect(screen.getByRole('button', { name: 'Add genre' })).toBeDisabled();
    await user.keyboard('{Enter}');
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByLabelText('Add a genre')).toHaveValue('action');
  });

  it('allows the same genre on the other list and explains that exclusion wins', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Host initial={{ excluded: ['Action'], included: [] }} onChange={onChange} />);
    await row('Action (12 games)');

    await user.selectOptions(screen.getByRole('combobox', { name: 'Add to list' }), 'included');
    await user.type(screen.getByLabelText('Add a genre'), 'Action{Enter}');

    expect(onChange).toHaveBeenLastCalledWith({ excluded: ['Action'], included: ['Action'] });
    expect(
      screen.getByText('Action is in both lists: exclusion wins, so it is never entered.'),
    ).toBeInTheDocument();
    const action = screen.getByRole('group', { name: 'Action (12 games)' });
    expect(toggles(action).excluded).toHaveAttribute('aria-pressed', 'true');
    expect(toggles(action).included).toHaveAttribute('aria-pressed', 'true');
    expect(
      within(action).getByLabelText('On both lists: exclusion wins, so never entered'),
    ).toBeInTheDocument();
    // Still one row for Action, not a second uncached one.
    expect(screen.getAllByRole('group', { name: /^Action/ })).toHaveLength(1);
  });

  it('names several overlapping genres in one sentence', async () => {
    render(<Host initial={{ excluded: ['Action', 'Indie'], included: ['Action', 'Indie', 'RPG'] }} />);
    await row('Action (12 games)');

    expect(
      screen.getByText('Action and Indie are in both lists: exclusion wins, so they are never entered.'),
    ).toBeInTheDocument();
  });

  it('refuses a name longer than the registry bound', async () => {
    const user = userEvent.setup();
    render(<Host />);
    await row('Action (12 games)');

    await user.type(screen.getByLabelText('Add a genre'), 'a'.repeat(65));

    expect(screen.getByRole('alert')).toHaveTextContent('Genre names are limited to 64 characters');
    expect(screen.getByRole('button', { name: 'Add genre' })).toBeDisabled();
  });

  it('disables the toggles of a full list with the reason naming the bound', async () => {
    const user = userEvent.setup();
    const full = Array.from({ length: 50 }, (_, i) => `Genre ${i}`);
    render(<Host initial={{ excluded: full, included: [] }} />);

    const action = await row('Action (12 games)');
    const exclude = toggles(action).excluded;
    expect(exclude).toBeDisabled();
    const reason = screen.getByText('The excluded list is full (50 genres)');
    expect(exclude).toHaveAttribute('aria-describedby', reason.id);
    expect(toggles(action).included).toBeEnabled();

    await user.type(screen.getByLabelText('Add a genre'), 'Racing');
    expect(screen.getByRole('alert')).toHaveTextContent('The excluded list is full (50 genres)');
  });

  it('uses the bounds it is given', async () => {
    const user = userEvent.setup();
    render(<Host hostLimits={{ maxItems: 1, maxLength: 5 }} initial={{ excluded: [], included: ['RPG'] }} />);
    await row('Action (12 games)');

    expect(screen.getByText('The included list is full (1 genres)')).toBeInTheDocument();
    await user.type(screen.getByLabelText('Add a genre'), 'Simulation');
    expect(screen.getByRole('alert')).toHaveTextContent('Genre names are limited to 5 characters');
  });

  it('notes that uncached genres are skipped only while a genre is included', async () => {
    const { unmount } = render(<Host initial={{ excluded: [], included: ['RPG'] }} />);
    await row('Action (12 games)');
    expect(
      screen.getByText('Games with no genres cached yet are skipped while a genre is included.'),
    ).toBeInTheDocument();
    unmount();

    render(<Host />);
    await row('Action (12 games)');
    expect(
      screen.queryByText('Games with no genres cached yet are skipped while a genre is included.'),
    ).not.toBeInTheDocument();
  });

  it('shows the loading, empty and error states of the genre cache', async () => {
    mockApi.getGameGenres.mockReturnValue(new Promise(() => {}));
    const first = render(<Host initial={{ excluded: ['Action'], included: [] }} />);
    expect(screen.getByText('Loading genres…')).toBeInTheDocument();
    expect(screen.queryByRole('group', { name: 'Genres' })).not.toBeInTheDocument();
    first.unmount();

    mockGenres([]);
    const second = render(<Host />);
    expect(
      await screen.findByText('No genres cached yet, genres appear as games are fetched from Steam'),
    ).toBeInTheDocument();
    second.unmount();

    mockGenres([]);
    const third = render(<Host initial={{ excluded: ['Action'], included: [] }} />);
    expect(await screen.findByRole('group', { name: 'Action (not cached)' })).toBeInTheDocument();
    expect(
      screen.queryByText('No genres cached yet, genres appear as games are fetched from Steam'),
    ).not.toBeInTheDocument();
    third.unmount();

    mockApi.getGameGenres.mockResolvedValue({ success: false, data: { genres: [] }, error: 'down' });
    render(<Host initial={{ excluded: ['Action'], included: [] }} />);
    expect(
      await screen.findByText('Could not load the genre list; you can still type a genre below'),
    ).toBeInTheDocument();
    // Listed genres still have a row so they can be un-pressed; the count is unknown.
    const action = screen.getByRole('group', { name: 'Action' });
    expect(within(action).getByTitle('Genre cache unavailable')).toHaveTextContent('—');
    expect(toggles(action).excluded).toHaveAttribute('aria-pressed', 'true');
  });

  it('truncates a long genre name and keeps the full text in its title', async () => {
    const long = 'A very long genre name that will not fit';
    render(<Host initial={{ excluded: [long], included: [] }} />);
    await row('Action (12 games)');

    expect(screen.getByTitle(long)).toHaveClass('truncate');
  });
});

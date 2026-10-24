import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, within } from '@/test/utils';
import { Giveaways } from './Giveaways';
import { api } from '@/services/api';
import { useGiveawayFiltersStore } from '@/stores/giveawayFiltersStore';
import type { Giveaway } from '@/types';

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

const baseGiveaway: Giveaway = {
  id: 1,
  code: 'AbC12',
  url: 'https://www.steamgifts.com/giveaway/AbC12/',
  game_name: 'Hollow Knight',
  game_id: 367520,
  price: 15,
  copies: 1,
  entries: 120,
  win_chance: 0.8,
  end_time: new Date(Date.now() + 3_600_000).toISOString(),
  discovered_at: '2026-01-01T00:00:00Z',
  entered_at: null,
  is_hidden: false,
  is_entered: false,
  is_wishlist: false,
  is_dlc: false,
  is_won: false,
  won_at: null,
  is_safe: true,
  safety_score: 95,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  game_thumbnail: null,
};

async function renderWith(over: Partial<Giveaway>) {
  mockApi.get.mockResolvedValue({
    success: true,
    data: { giveaways: [{ ...baseGiveaway, ...over }], count: 1 },
  });
  render(<Giveaways />);
  return screen.findByRole('heading', { name: 'Hollow Knight', level: 3 });
}

describe('Giveaways page: genre line on cards', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useGiveawayFiltersStore.getState().resetFilters();
  });

  it('shows the first three genres then +N, with the full list in the title', async () => {
    const heading = await renderWith({
      game_genres: ['Action', 'Indie', 'RPG', 'Strategy'],
    });

    const line = screen.getByTitle('Action, Indie, RPG, Strategy');
    expect(line).toHaveTextContent('Action, Indie, RPG +1');
    expect(heading.parentElement).toContainElement(line);
  });

  it('keeps the +N counter out of the truncated part so it stays visible', async () => {
    await renderWith({
      game_genres: ['Massively Multiplayer', 'Simulation', 'Strategy', 'Indie', 'RPG'],
    });

    const line = screen.getByTitle('Massively Multiplayer, Simulation, Strategy, Indie, RPG');
    const names = within(line).getByText('Massively Multiplayer, Simulation, Strategy');
    const counter = within(line).getByText('+2');
    expect(names).toHaveClass('truncate');
    expect(counter).toHaveClass('shrink-0');
    expect(counter).not.toHaveClass('truncate');
    expect(names).not.toContainElement(counter);
  });

  it('shows all genres without a counter when there are three or fewer', async () => {
    await renderWith({ game_genres: ['Animation & Modeling', 'Utilities'] });

    const line = screen.getByTitle('Animation & Modeling, Utilities');
    expect(line).toHaveTextContent(/^Animation & Modeling, Utilities$/);
  });

  it.each([
    ['null', null],
    ['an empty list', []],
    ['missing', undefined],
  ])('renders no genre line when game_genres is %s', async (_label, genres) => {
    const heading = await renderWith({ game_genres: genres });

    expect(heading.parentElement?.querySelector('p')).toBeNull();
  });
});

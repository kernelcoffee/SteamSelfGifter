import { describe, it, expect } from 'vitest';
import { render, screen } from '@/test/utils';
import { AutojoinDecisionLine } from './AutojoinDecisionLine';
import { makeGiveaway, testRegistry } from '@/test/fixtures';
import type { AutojoinKind } from '@/types';

const types = testRegistry.priority_types;

function iconClass(container: HTMLElement): string {
  return container.querySelector('svg')?.getAttribute('class') ?? '';
}

describe('AutojoinDecisionLine', () => {
  it('shows "Not evaluated yet" with the help icon when nothing is recorded', () => {
    const { container } = render(<AutojoinDecisionLine giveaway={makeGiveaway()} lens={false} />);

    expect(screen.getByText('Auto-join:')).toBeInTheDocument();
    expect(screen.getByText('Not evaluated yet; checked at the next cycle')).toBeInTheDocument();
    expect(iconClass(container)).toContain('lucide-circle-help');
    expect(screen.queryByText(/^Checked /)).not.toBeInTheDocument();
  });

  it.each<[AutojoinKind, string, string]>([
    ['gate', 'Hidden', 'lucide-ban'],
    ['filter', 'Review score 6 is below your minimum 7', 'lucide-funnel'],
    ['budget', 'Not entered last cycle: the 10 per cycle cap was reached', 'lucide-wallet'],
  ])('kind %s: icon %s and the server label as text', (kind, label, icon) => {
    const { container } = render(
      <AutojoinDecisionLine
        giveaway={makeGiveaway({
          eligibility_reason: 'x',
          eligibility_label: label,
          eligibility_kind: kind,
        })}
        lens={false}
      />,
    );

    expect(screen.getByText(label)).toBeInTheDocument();
    expect(iconClass(container)).toContain(icon);
    expect(iconClass(container)).not.toContain('lucide-clock');
  });

  it('stored enter outcome: the one-word term with lift and position in the tooltip', () => {
    const { container } = render(
      <AutojoinDecisionLine
        giveaway={makeGiveaway({
          eligibility_reason: 'eligible',
          eligibility_label: 'Joinable',
          eligibility_kind: 'enter',
          eligibility_detail: { priority: 'wishlist', rank: 0, lifted_by: 'wishlist' },
        })}
        lens={false}
        priorityTypes={types}
      />,
    );

    const term = screen.getByTitle('Joinable: Wishlist, filters skipped, 1st in your order');
    expect(term).toHaveTextContent('Joinable: Wishlist, filters skipped, 1st in your order');
    expect(iconClass(container)).toContain('lucide-circle-check');
    expect(screen.queryByText(/Will be entered/)).not.toBeInTheDocument();
  });

  it('lens: shows the live decision, not the stored one', () => {
    render(
      <AutojoinDecisionLine
        giveaway={makeGiveaway({
          eligibility_reason: 'score_below_min',
          eligibility_label: 'Review score 6 is below your minimum 7',
          eligibility_kind: 'filter',
          decision: {
            code: 'eligible',
            label: 'Joinable',
            detail: { priority: 'dlc', rank: 1, lifted_by: 'dlc' },
            priority: 'dlc',
            rank: 1,
            lifted_by: 'dlc',
          },
        })}
        lens
        priorityTypes={types}
      />,
    );

    expect(screen.getByTitle('Joinable: DLC, filters skipped, 2nd in your order')).toBeInTheDocument();
    expect(screen.queryByText('Review score 6 is below your minimum 7')).not.toBeInTheDocument();
  });

  it('shows how long ago a stored decision was checked, with the UTC time in the title', () => {
    const checked = new Date(Date.now() - 12 * 60_000).toISOString();
    render(
      <AutojoinDecisionLine
        giveaway={makeGiveaway({
          eligibility_reason: 'hidden',
          eligibility_label: 'Hidden',
          eligibility_kind: 'gate',
          eligibility_checked_at: checked,
        })}
        lens={false}
      />,
    );

    const age = screen.getByText('Checked 12 minutes ago');
    expect(age).toHaveAttribute('title', new Date(checked).toUTCString());
  });

  it('renders labels as text, never as HTML', () => {
    render(
      <AutojoinDecisionLine
        giveaway={makeGiveaway({
          eligibility_reason: 'genre_excluded',
          eligibility_label: '<img src=x onerror=alert(1)>',
          eligibility_kind: 'filter',
        })}
        lens={false}
      />,
    );
    expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeInTheDocument();
    expect(document.querySelector('img')).toBeNull();
  });
});

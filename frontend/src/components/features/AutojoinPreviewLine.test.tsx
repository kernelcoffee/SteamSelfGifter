import { describe, it, expect, vi } from 'vitest';
import { render, screen, within, userEvent } from '@/test/utils';
import { AutojoinPreviewLine } from './AutojoinPreviewLine';
import { makePreview, testRegistry } from '@/test/fixtures';
import { registryLabels } from '@/utils/autojoinPriorities';

const labels = registryLabels(testRegistry);

describe('AutojoinPreviewLine', () => {
  it('ready: count of pool and a breakdown with registry labels, largest first', () => {
    render(
      <AutojoinPreviewLine
        status="ready"
        data={makePreview({ count: 3, pool: 12, counts: { eligible: 3, hidden: 1, score_below_min: 8, mystery: 0 } })}
        labels={labels}
        isStale={false}
      />,
    );

    expect(screen.getByText('3 of 12 active giveaways would be entered next cycle')).toBeInTheDocument();
    const items = within(screen.getByRole('list', { name: 'Decisions by reason' }))
      .getAllByRole('listitem')
      .map((li) => li.textContent);
    expect(items).toEqual(['Review score below minimum: 8', 'Joinable: 3', 'Hidden: 1']);
    expect(
      screen.getByText(
        'Preview only: nothing is entered. The points budget and the per cycle cap apply at cycle time.',
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText('Updating…')).not.toBeInTheDocument();
  });

  it('shows an unknown code as the code itself', () => {
    render(
      <AutojoinPreviewLine status="ready" data={makePreview({ counts: { brand_new: 2 } })} labels={labels} isStale={false} />,
    );
    expect(screen.getByText('brand_new: 2')).toBeInTheDocument();
  });

  it('names the saved count only when it differs', () => {
    const { rerender } = render(
      <AutojoinPreviewLine status="ready" data={makePreview({ count: 5 })} savedCount={3} labels={labels} isStale={false} />,
    );
    expect(screen.getByText(/would be entered next cycle \(saved: 3\)/)).toBeInTheDocument();

    rerender(
      <AutojoinPreviewLine status="ready" data={makePreview({ count: 3 })} savedCount={3} labels={labels} isStale={false} />,
    );
    expect(screen.queryByText(/saved:/)).not.toBeInTheDocument();
  });

  it('warns when nothing would be entered', () => {
    render(
      <AutojoinPreviewLine status="ready" data={makePreview({ count: 0, pool: 1, counts: { hidden: 1 } })} labels={labels} isStale={false} />,
    );
    expect(screen.getByText('0 of 1 active giveaway would be entered next cycle')).toBeInTheDocument();
    expect(screen.getByText('Auto-join would enter nothing next cycle.')).toBeInTheDocument();
  });

  it('stale: keeps the previous numbers, dimmed, with Updating…', () => {
    const { container } = render(
      <AutojoinPreviewLine status="ready" data={makePreview()} labels={labels} isStale />,
    );
    expect(screen.getByText('3 of 12 active giveaways would be entered next cycle')).toBeInTheDocument();
    expect(screen.getByText('Updating…')).toBeInTheDocument();
    expect(container.querySelector('.opacity-60')).not.toBeNull();
  });

  it('paused: states the reason and no numbers', () => {
    render(
      <AutojoinPreviewLine
        status="paused"
        pausedReason="Enter a minimum review score from 0 to 10, or choose No minimum"
        data={makePreview()}
        labels={labels}
        isStale={false}
      />,
    );
    expect(
      screen.getByText('Preview paused: Enter a minimum review score from 0 to 10, or choose No minimum'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/would be entered/)).not.toBeInTheDocument();
  });

  it('loading without data: computing', () => {
    render(<AutojoinPreviewLine status="loading" labels={labels} isStale={false} />);
    expect(screen.getByText('Computing the preview…')).toBeInTheDocument();
  });

  it('error: the backend message and a working Retry, without the count', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(
      <AutojoinPreviewLine
        status="error"
        error="Database is locked"
        onRetry={onRetry}
        data={makePreview()}
        labels={labels}
        isStale={false}
      />,
    );

    expect(
      screen.getByText('Preview unavailable: Database is locked. Your changes can still be saved.'),
    ).toBeInTheDocument();
    expect(screen.queryByText(/would be entered/)).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('is a polite live region only when asked', () => {
    const { container, rerender } = render(
      <AutojoinPreviewLine status="loading" labels={labels} isStale={false} live />,
    );
    expect(container.querySelector('[aria-live="polite"]')).not.toBeNull();
    rerender(<AutojoinPreviewLine status="loading" labels={labels} isStale={false} />);
    expect(container.querySelector('[aria-live]')).toBeNull();
  });
});

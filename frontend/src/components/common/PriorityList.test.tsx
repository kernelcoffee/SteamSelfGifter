import { describe, it, expect, vi } from 'vitest';
import { useState } from 'react';
import { render, screen, within, fireEvent, userEvent } from '@/test/utils';
import { PriorityList } from './PriorityList';
import type { AutojoinPriorityItem, AutojoinPriorityTypeInfo } from '@/types';
import { testRegistry } from '@/test/fixtures';

const types = testRegistry.priority_types;
const threshold = { name: 'threshold_minutes', min: 5, max: 10080, default: 60 };

/** Stateful host so the controlled list behaves as in the form. */
function Host({
  initial,
  onChange = () => {},
  registryTypes = types,
  maxItems = 3,
  thresholdError,
}: {
  initial: AutojoinPriorityItem[];
  onChange?: (items: AutojoinPriorityItem[]) => void;
  registryTypes?: AutojoinPriorityTypeInfo[];
  maxItems?: number;
  thresholdError?: string;
}) {
  const [items, setItems] = useState(initial);
  const [text, setText] = useState('90');
  return (
    <>
      <PriorityList
        items={items}
        onChange={(next) => {
          setItems(next);
          onChange(next);
        }}
        types={registryTypes}
        maxItems={maxItems}
        threshold={threshold}
        thresholdText={text}
        onThresholdTextChange={setText}
        thresholdError={thresholdError}
      />
      <output data-testid="threshold-text">{text}</output>
    </>
  );
}

const ALL: AutojoinPriorityItem[] = [
  { type: 'wishlist' },
  { type: 'dlc' },
  { type: 'ending_soon', threshold_minutes: 90 },
];

function rowLabels() {
  return within(screen.getByRole('list', { name: 'Priority order' }))
    .getAllByRole('listitem')
    .map((li) => li.textContent ?? '');
}

describe('PriorityList', () => {
  it('renders one row per item in order with position, registry label and description', () => {
    render(<Host initial={[{ type: 'dlc' }, { type: 'wishlist' }]} />);

    const rows = within(screen.getByRole('list', { name: 'Priority order' })).getAllByRole('listitem');
    expect(rows).toHaveLength(2);
    expect(rows[0]).toHaveTextContent('1.');
    expect(rows[0]).toHaveTextContent('DLC');
    expect(rows[0]).toHaveTextContent('DLC for games you own, from the DLC listing');
    expect(rows[1]).toHaveTextContent('2.');
    expect(rows[1]).toHaveTextContent('Wishlist');
  });

  it('shows the fixed badge from the registry exemption flag', () => {
    render(<Host initial={ALL} />);
    const rows = within(screen.getByRole('list', { name: 'Priority order' })).getAllByRole('listitem');

    expect(within(rows[0]).getByText('Skips the filters')).toBeInTheDocument();
    expect(within(rows[1]).getByText('Skips the filters')).toBeInTheDocument();
    expect(within(rows[2]).getByText('Obeys the filters')).toBeInTheDocument();
  });

  it('follows the registry, not a client copy: a relabelled, non-exempt wishlist', () => {
    const custom = types.map((t) =>
      t.type === 'wishlist' ? { ...t, label: 'Wanted', exempt_from_filters: false } : t,
    );
    render(<Host initial={[{ type: 'wishlist' }]} registryTypes={custom} />);

    const row = within(screen.getByRole('list', { name: 'Priority order' })).getByRole('listitem');
    expect(row).toHaveTextContent('Wanted');
    expect(within(row).getByText('Obeys the filters')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Move Wanted up' })).toBeInTheDocument();
  });

  it('disables Move up on the first row and Move down on the last', () => {
    render(<Host initial={ALL} />);

    expect(screen.getByRole('button', { name: 'Move Wishlist up' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Move Wishlist down' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Move Ending soon down' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Move Ending soon up' })).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Move DLC up' })).toHaveTextContent('Move up');
  });

  it('moves and removes by keyboard, announcing each change', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Host initial={ALL} onChange={onChange} />);

    screen.getByRole('button', { name: 'Move DLC up' }).focus();
    await user.keyboard('{Enter}');
    expect(onChange).toHaveBeenLastCalledWith([
      { type: 'dlc' },
      { type: 'wishlist' },
      { type: 'ending_soon', threshold_minutes: 90 },
    ]);
    expect(rowLabels()[0]).toContain('DLC');
    expect(screen.getByText('DLC moved to position 1 of 3')).toBeInTheDocument();
    // Move up is now disabled on DLC; focus moved to its Move down button.
    expect(screen.getByRole('button', { name: 'Move DLC down' })).toHaveFocus();

    screen.getByRole('button', { name: 'Remove Wishlist' }).focus();
    await user.keyboard('{Enter}');
    expect(onChange).toHaveBeenLastCalledWith([
      { type: 'dlc' },
      { type: 'ending_soon', threshold_minutes: 90 },
    ]);
    expect(screen.getByText('Wishlist removed')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Remove Ending soon' })).toHaveFocus();
  });

  it('after removing the last row focuses the previous one, then the Add select', async () => {
    const user = userEvent.setup();
    render(<Host initial={[{ type: 'wishlist' }, { type: 'dlc' }]} />);

    await user.click(screen.getByRole('button', { name: 'Remove DLC' }));
    expect(screen.getByRole('button', { name: 'Remove Wishlist' })).toHaveFocus();

    await user.click(screen.getByRole('button', { name: 'Remove Wishlist' }));
    expect(screen.getByRole('combobox', { name: 'Add priority' })).toHaveFocus();
    expect(screen.queryByRole('list', { name: 'Priority order' })).not.toBeInTheDocument();
    expect(
      screen.getByText('No priorities: every giveaway obeys the filters and is entered highest price first.'),
    ).toBeInTheDocument();
  });

  it('with two rows, moving the last row up hands focus to its now-enabled Move down button', async () => {
    const user = userEvent.setup();
    render(<Host initial={[{ type: 'wishlist' }, { type: 'dlc' }]} />);

    await user.click(screen.getByRole('button', { name: 'Move DLC up' }));

    expect(rowLabels()[0]).toContain('DLC');
    expect(screen.getByRole('button', { name: 'Move DLC up' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Move DLC down' })).toHaveFocus();
  });

  it('with two rows, moving the first row down hands focus to its now-enabled Move up button', async () => {
    const user = userEvent.setup();
    render(<Host initial={[{ type: 'wishlist' }, { type: 'dlc' }]} />);

    await user.click(screen.getByRole('button', { name: 'Move Wishlist down' }));

    expect(rowLabels()[1]).toContain('Wishlist');
    expect(screen.getByRole('button', { name: 'Move Wishlist down' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Move Wishlist up' })).toHaveFocus();
  });

  it('with three rows, a move that stops short of an end keeps focus on the pressed button', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Host initial={ALL} onChange={onChange} />);
    // A browser blurs a focused node when it is moved in the DOM, which is
    // what React does to the moved row; jsdom does not, so mimic it here.
    const blurIfMoved = (node: Node) => {
      const active = document.activeElement;
      if (active instanceof HTMLElement && node.contains(active)) active.blur();
    };
    const insertBefore = Node.prototype.insertBefore;
    const appendChild = Node.prototype.appendChild;
    const spies = [
      vi.spyOn(Node.prototype, 'insertBefore').mockImplementation(function (this: Node, node, ref) {
        blurIfMoved(node);
        return insertBefore.call(this, node, ref);
      }),
      vi.spyOn(Node.prototype, 'appendChild').mockImplementation(function (this: Node, node) {
        blurIfMoved(node);
        return appendChild.call(this, node);
      }),
    ];
    try {
      const down = screen.getByRole('button', { name: 'Move Wishlist down' });
      down.focus();
      await user.keyboard('{Enter}');

      expect(onChange).toHaveBeenLastCalledWith([
        { type: 'dlc' },
        { type: 'wishlist' },
        { type: 'ending_soon', threshold_minutes: 90 },
      ]);
      expect(rowLabels()[1]).toContain('Wishlist');
      expect(down).toBeEnabled();
      expect(down).toHaveFocus();

      // The next move reaches the end: the pressed button is disabled and
      // focus goes to the row's other button.
      await user.keyboard('{Enter}');
      expect(rowLabels()[2]).toContain('Wishlist');
      expect(down).toBeDisabled();
      expect(screen.getByRole('button', { name: 'Move Wishlist up' })).toHaveFocus();
    } finally {
      spies.forEach((spy) => spy.mockRestore());
    }
  });

  it('removing the only row of a full list focuses the Add select once it is enabled again', async () => {
    const user = userEvent.setup();
    render(<Host initial={[{ type: 'wishlist' }]} maxItems={1} />);
    expect(screen.getByRole('combobox', { name: 'Add priority' })).toBeDisabled();

    await user.click(screen.getByRole('button', { name: 'Remove Wishlist' }));

    const select = screen.getByRole('combobox', { name: 'Add priority' });
    expect(select).toBeEnabled();
    expect(select).toHaveFocus();
  });

  it('gives the Add button a name of its own, distinct from the select and starting with its visible text', () => {
    render(<Host initial={[{ type: 'wishlist' }]} />);

    const add = screen.getByRole('button', { name: 'Add the selected priority' });
    expect(add).toHaveTextContent('Add');
    expect(screen.queryByRole('button', { name: 'Add priority' })).not.toBeInTheDocument();
    expect(screen.getByRole('combobox', { name: 'Add priority' })).toBeInTheDocument();
  });

  it('Add priority offers only absent types and adds the selected one', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Host initial={[{ type: 'wishlist' }]} onChange={onChange} />);

    const select = screen.getByRole('combobox', { name: 'Add priority' });
    const options = within(select).getAllByRole('option').map((o) => o.textContent);
    expect(options).toEqual(['DLC', 'Ending soon']);

    await user.selectOptions(select, 'ending_soon');
    await user.click(screen.getByRole('button', { name: 'Add the selected priority' }));

    expect(onChange).toHaveBeenLastCalledWith([
      { type: 'wishlist' },
      { type: 'ending_soon', threshold_minutes: 60 },
    ]);
    // The threshold draft starts at the registry default.
    expect(screen.getByTestId('threshold-text')).toHaveTextContent('60');
    expect(screen.getByLabelText('Ending soon threshold (minutes)')).toHaveValue(60);
    expect(screen.getByText('Ending soon added at position 2 of 2')).toBeInTheDocument();
    expect(within(select).getAllByRole('option').map((o) => o.textContent)).toEqual(['DLC']);
  });

  it('disables Add with a visible reason when every type is present, and focuses the new row', async () => {
    const user = userEvent.setup();
    render(<Host initial={[{ type: 'wishlist' }, { type: 'dlc' }]} />);

    await user.click(screen.getByRole('button', { name: 'Add the selected priority' }));

    const select = screen.getByRole('combobox', { name: 'Add priority' });
    const add = screen.getByRole('button', { name: 'Add the selected priority' });
    expect(select).toBeDisabled();
    expect(add).toBeDisabled();
    const note = screen.getByText('All priority types are in the list');
    expect(add).toHaveAttribute('aria-describedby', note.id);
    expect(screen.getByRole('button', { name: 'Remove Ending soon' })).toHaveFocus();
  });

  it('honours the registry maximum item count', () => {
    render(<Host initial={[{ type: 'wishlist' }]} maxItems={1} />);

    expect(screen.getByRole('button', { name: 'Add the selected priority' })).toBeDisabled();
    expect(screen.getByText('The list holds at most 1 priorities')).toBeInTheDocument();
  });

  it('shows the threshold input only on the ending-soon row, with registry bounds and the error', () => {
    render(<Host initial={ALL} thresholdError="Must be between 5 and 10080 minutes" />);

    const input = screen.getByLabelText('Ending soon threshold (minutes)');
    expect(input).toHaveValue(90);
    expect(input).toHaveAttribute('min', '5');
    expect(input).toHaveAttribute('max', '10080');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(screen.getByRole('alert')).toHaveTextContent('Must be between 5 and 10080 minutes');
    const rows = within(screen.getByRole('list', { name: 'Priority order' })).getAllByRole('listitem');
    expect(within(rows[2]).getByLabelText('Ending soon threshold (minutes)')).toBe(input);
    expect(within(rows[0]).queryByRole('spinbutton')).not.toBeInTheDocument();
  });

  it('reorders by drag and drop and ignores a drop on the source row', () => {
    const onChange = vi.fn();
    render(<Host initial={ALL} onChange={onChange} />);
    const rows = () =>
      within(screen.getByRole('list', { name: 'Priority order' })).getAllByRole('listitem');
    const handle = (row: HTMLElement) => row.querySelector('[draggable="true"]');
    const dataTransfer = { setData: vi.fn(), effectAllowed: '', dropEffect: '' };

    const source = handle(rows()[2]);
    expect(source).not.toBeNull();
    if (!source) return;
    expect(source).toHaveAttribute('aria-hidden', 'true');
    expect(source).toHaveAttribute('tabindex', '-1');

    fireEvent.dragStart(source, { dataTransfer });
    expect(dataTransfer.setData).toHaveBeenCalledWith('text/plain', 'ending_soon');
    expect(rows()[2]).toHaveClass('opacity-50');
    fireEvent.dragOver(rows()[0], { dataTransfer });
    expect(rows()[0]).toHaveClass('ring-2');
    fireEvent.drop(rows()[0], { dataTransfer });

    expect(onChange).toHaveBeenLastCalledWith([
      { type: 'ending_soon', threshold_minutes: 90 },
      { type: 'wishlist' },
      { type: 'dlc' },
    ]);
    expect(rows()[0]).not.toHaveClass('ring-2');
    expect(screen.getByText('Ending soon moved to position 1 of 3')).toBeInTheDocument();

    onChange.mockClear();
    const again = handle(rows()[1]);
    if (!again) return;
    fireEvent.dragStart(again, { dataTransfer });
    fireEvent.drop(rows()[1], { dataTransfer });
    expect(onChange).not.toHaveBeenCalled();
  });

  it('ignores a drop that did not start on a handle', () => {
    const onChange = vi.fn();
    render(<Host initial={ALL} onChange={onChange} />);
    const rows = within(screen.getByRole('list', { name: 'Priority order' })).getAllByRole('listitem');

    fireEvent.drop(rows[0], { dataTransfer: { setData: vi.fn() } });
    expect(onChange).not.toHaveBeenCalled();
  });
});

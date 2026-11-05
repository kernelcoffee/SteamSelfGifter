import { describe, it, expect } from 'vitest';
import { ordinal, parseBoundedInt } from './numbers';

describe('parseBoundedInt', () => {
  it.each([
    ['', null],
    ['   ', null],
    ['abc', null],
    ['1.5', null],
    ['-1', null],
    ['1e3', null],
  ])('rejects %j', (text, expected) => {
    expect(parseBoundedInt(text, 0)).toBe(expected);
  });

  it('parses 0 as 0, never as missing', () => {
    expect(parseBoundedInt('0', 0)).toBe(0);
  });

  it('trims surrounding spaces', () => {
    expect(parseBoundedInt(' 42 ', 0)).toBe(42);
  });

  it('applies the inclusive bounds', () => {
    expect(parseBoundedInt('4', 5, 10080)).toBeNull();
    expect(parseBoundedInt('5', 5, 10080)).toBe(5);
    expect(parseBoundedInt('10080', 5, 10080)).toBe(10080);
    expect(parseBoundedInt('10081', 5, 10080)).toBeNull();
  });

  it('has no upper bound when max is omitted', () => {
    expect(parseBoundedInt('1000000', 1)).toBe(1000000);
  });

  it('rejects integers beyond the safe range', () => {
    expect(parseBoundedInt('99999999999999999999', 0)).toBeNull();
  });
});

describe('ordinal', () => {
  it.each([
    [1, '1st'],
    [2, '2nd'],
    [3, '3rd'],
    [4, '4th'],
    [11, '11th'],
    [12, '12th'],
    [13, '13th'],
    [21, '21st'],
    [22, '22nd'],
    [23, '23rd'],
    [101, '101st'],
    [111, '111th'],
  ])('%i -> %s', (n, expected) => {
    expect(ordinal(n)).toBe(expected);
  });
});

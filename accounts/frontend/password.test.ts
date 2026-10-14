// The hint under «New password» while it is typed: how strong it looks (length and kinds of characters, not the
// account's email in it). Only a hint: the server's validators (allauth, Django's) decide, and their message goes
// under the field.
import { describe, expect, it } from 'vitest';

import { passwordStrength } from './password';

describe('passwordStrength', () => {
  it('is nothing to say before anything is typed', () => {
    expect(passwordStrength('', 'laura@example.com')).toBe('empty');
  });

  it('is too short under 8 characters', () => {
    expect(passwordStrength('Ab1!xyz', 'laura@example.com')).toBe('short');
  });

  it('is weak with one kind of character, or with the email in it', () => {
    expect(passwordStrength('abcdefghij', 'laura@example.com')).toBe('weak');
    expect(passwordStrength('12345678901', 'laura@example.com')).toBe('weak');
    expect(passwordStrength('Laura-2026!x', 'laura@example.com')).toBe('weak');
  });

  it('is fair with two or more kinds under 12 characters', () => {
    expect(passwordStrength('panadero7', 'laura@example.com')).toBe('fair');
    expect(passwordStrength('Pan-de-7x', 'laura@example.com')).toBe('fair');
  });

  it('is strong from 12 characters with three kinds, or from 16 with any', () => {
    expect(passwordStrength('Pan-de-centeno-26', 'laura@example.com')).toBe('strong');
    expect(passwordStrength('correcthorsebatterystaple', 'laura@example.com')).toBe('strong');
  });
});

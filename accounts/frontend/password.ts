// The hint under «New password» while it is typed (Account → Security): how strong it looks, from its length and
// the kinds of characters in it, and weak whenever the account's email (its part before the @) is inside. Only a
// hint, as Google's and GitHub's: the server's validators (allauth's and Django's) decide, and their message goes
// under the field.

export type PasswordStrength = 'empty' | 'short' | 'weak' | 'fair' | 'strong';

/** Django's `MinimumLengthValidator` default. */
const MIN_LENGTH = 8;

export function passwordStrength(password: string, email: string): PasswordStrength {
  if (!password) return 'empty';
  if (password.length < MIN_LENGTH) return 'short';
  const local = email.split('@')[0]?.toLowerCase() ?? '';
  if (local.length >= 3 && password.toLowerCase().includes(local)) return 'weak';
  const kinds = [/[a-z]/, /[A-Z]/, /\d/, /[^a-zA-Z\d]/].filter((kind) => kind.test(password)).length;
  if (password.length >= 16 || (password.length >= 12 && kinds >= 3)) return 'strong';
  return kinds >= 2 ? 'fair' : 'weak';
}

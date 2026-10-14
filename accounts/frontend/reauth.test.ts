// A command that gives access or destroys (delete the account, create an API key, move the email to another
// address) needs a recent sign-in (accounts/README.md, «Reautenticación»): the server answers 401
// `reauthentication_required` with the ways to confirm (`flows`, `providers`). `useReauthentication().guard` runs
// the command, asks the person to confirm when the server says so, and runs it once more.
import { ApiError, ReauthenticationRequiredError } from '@erplora/ui/sdk';
import { describe, expect, it, vi } from 'vitest';
import { nextTick } from 'vue';

import { reauthRequestOf, useReauthentication } from './reauth';

const required = (flows: unknown = ['reauthenticate'], providers: unknown = []) =>
  new ApiError(401, 'reauthentication_required', "Confirm it's you", undefined, { flows, providers });

describe('reauthRequestOf', () => {
  it('reads the ways to confirm from the 401', () => {
    expect(reauthRequestOf(required(['reauthenticate', 'provider_redirect'], ['google']))).toEqual({
      flows: ['reauthenticate', 'provider_redirect'],
      providers: ['google'],
    });
  });

  it('reads allauth.headless’s own 401 too (an account door: disconnecting Google)', () => {
    expect(reauthRequestOf(new ReauthenticationRequiredError(['reauthenticate', 'mfa_reauthenticate']))).toEqual({
      flows: ['reauthenticate', 'mfa_reauthenticate'],
      providers: [],
    });
  });

  it('is nothing for any other failure, and keeps only strings', () => {
    expect(reauthRequestOf(new ApiError(401, 'unauthorized', 'Sign in'))).toBeNull();
    expect(reauthRequestOf(new Error('x'))).toBeNull();
    expect(reauthRequestOf(required('nope', [1, 'google']))).toEqual({ flows: [], providers: ['google'] });
  });
});

describe('useReauthentication', () => {
  it('runs the command once when no confirmation is needed', async () => {
    const reauth = useReauthentication();
    const action = vi.fn(async () => 'done');
    await expect(reauth.guard(action)).resolves.toBe('done');
    expect(action).toHaveBeenCalledTimes(1);
    expect(reauth.request.value).toBeNull();
  });

  it('asks to confirm on the 401, and once confirmed runs the command again', async () => {
    const reauth = useReauthentication();
    const action = vi.fn().mockRejectedValueOnce(required(['reauthenticate'], [])).mockResolvedValueOnce('done');
    const running = reauth.guard(action);
    await nextTick();
    await Promise.resolve();
    expect(reauth.request.value).toEqual({ flows: ['reauthenticate'], providers: [] });
    reauth.confirmed();
    await expect(running).resolves.toBe('done');
    expect(action).toHaveBeenCalledTimes(2);
    expect(reauth.request.value).toBeNull();
  });

  it('gives up quietly when the person closes the confirmation', async () => {
    const reauth = useReauthentication();
    const action = vi.fn().mockRejectedValue(required());
    const running = reauth.guard(action);
    await Promise.resolve();
    await Promise.resolve();
    reauth.cancelled();
    await expect(running).resolves.toBeUndefined();
    expect(action).toHaveBeenCalledTimes(1);
  });

  it('lets any other failure through, untouched', async () => {
    const reauth = useReauthentication();
    const refused = new ApiError(409, 'accounts.owns_businesses', 'You own businesses');
    await expect(reauth.guard(() => Promise.reject(refused))).rejects.toBe(refused);
    expect(reauth.request.value).toBeNull();
  });
});

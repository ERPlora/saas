// What the session says of the account changed (its language in Account → Preferences, its name in Account → Profile):
// a page says so on the window and the entry, which owns the session the shell paints, reads `base.session.me` again
// (saas#292: the side menu the server translates stayed in the old language until a reload).
import { describe, expect, it, vi } from 'vitest';

import { onSessionChanged, SESSION_CHANGED, sessionChanged } from './session-changed';

describe('session-changed', () => {
  it('tells every listener on the window that the session changed', () => {
    const listener = vi.fn();
    const stop = onSessionChanged(listener);
    sessionChanged();
    expect(listener).toHaveBeenCalledTimes(1);
    stop();
  });

  it('stops telling a listener once it stops listening', () => {
    const listener = vi.fn();
    onSessionChanged(listener)();
    sessionChanged();
    expect(listener).not.toHaveBeenCalled();
  });

  it('is an event of its own on the target it is given', () => {
    const target = new EventTarget();
    const heard = vi.fn();
    target.addEventListener(SESSION_CHANGED, heard);
    const onWindow = vi.fn();
    const stop = onSessionChanged(onWindow);
    sessionChanged(target);
    expect(heard).toHaveBeenCalledTimes(1);
    expect(onWindow).not.toHaveBeenCalled();
    stop();
  });
});

import { describe, expect, it, vi } from 'vitest';
import { useAutosave } from './useAutosave';

describe('useAutosave', () => {
  it('queues a single flush and clears dirty after markSaved', async () => {
    vi.useFakeTimers();
    let count = 0;
    const autosave = useAutosave(async () => {
      count += 1;
      autosave.markSaved();
    }, 300);

    autosave.queue();
    autosave.queue();
    expect(autosave.dirty.value).toBe(true);
    expect(count).toBe(0);

    await vi.advanceTimersByTimeAsync(350);
    expect(count).toBe(1);
    expect(autosave.dirty.value).toBe(false);
    vi.useRealTimers();
  });

  it('does not flush during hydration silence window', async () => {
    vi.useFakeTimers();
    let count = 0;
    const autosave = useAutosave(async () => {
      count += 1;
    }, 100);

    autosave.beginHydration();
    autosave.queue();
    await vi.advanceTimersByTimeAsync(200);
    expect(count).toBe(0);

    autosave.endHydration(0);
    await vi.advanceTimersByTimeAsync(1);
    autosave.queue();
    await vi.runAllTimersAsync();
    expect(count).toBe(1);
    vi.useRealTimers();
  });
});

import { ref } from 'vue';

export function useAutosave(onFlush: () => Promise<void>, delayMs = 1200) {
  const dirty = ref(false);
  const hydrating = ref(false);
  let timer: number | null = null;
  let hydrationTimer: number | null = null;

  const clearTimer = () => {
    if (timer !== null) {
      window.clearTimeout(timer);
      timer = null;
    }
  };

  const cancel = () => {
    clearTimer();
    if (hydrationTimer !== null) {
      window.clearTimeout(hydrationTimer);
      hydrationTimer = null;
    }
  };

  const beginHydration = () => {
    hydrating.value = true;
    clearTimer();
  };

  const endHydration = (silentMs = 220) => {
    if (hydrationTimer !== null) {
      window.clearTimeout(hydrationTimer);
    }
    hydrationTimer = window.setTimeout(() => {
      hydrating.value = false;
      hydrationTimer = null;
    }, Math.max(0, silentMs));
  };

  const queue = () => {
    if (hydrating.value) {
      return;
    }
    dirty.value = true;
    clearTimer();
    timer = window.setTimeout(async () => {
      await onFlush();
    }, Math.max(150, delayMs));
  };

  const markSaved = () => {
    dirty.value = false;
  };

  return {
    dirty,
    hydrating,
    beginHydration,
    endHydration,
    queue,
    markSaved,
    cancel,
  };
}

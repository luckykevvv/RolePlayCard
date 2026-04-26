import { describe, expect, it } from 'vitest';
import { useBatchGenerationState } from './useBatchGeneration';

describe('useBatchGenerationState', () => {
  it('handles start pause resume and completion', () => {
    const batch = useBatchGenerationState();
    batch.start(12, 3);
    expect(batch.state.status).toBe('running');
    expect(batch.state.totalSegments).toBe(12);
    expect(batch.state.currentSegment).toBe(3);

    batch.pause();
    expect(batch.state.status).toBe('paused');

    batch.resume();
    expect(batch.state.status).toBe('running');

    batch.complete();
    expect(batch.state.status).toBe('completed');
    expect(batch.state.errorMessage).toBe('');
  });

  it('stores failure details and resets safely', () => {
    const batch = useBatchGenerationState();
    batch.start(8, 2);
    batch.fail(4, 'network error');
    expect(batch.state.status).toBe('failed');
    expect(batch.state.failedSegmentIndex).toBe(4);
    expect(batch.state.errorMessage).toBe('network error');

    batch.reset(5, 1);
    expect(batch.state.status).toBe('idle');
    expect(batch.state.totalSegments).toBe(5);
    expect(batch.state.currentSegment).toBe(1);
    expect(batch.state.failedSegmentIndex).toBeUndefined();
  });
});

import { reactive } from 'vue';
import type { BatchGenerationState } from '../../../shared/types.js';

function createDefaultState(): BatchGenerationState {
  return {
    status: 'idle',
    currentSegment: 0,
    totalSegments: 0,
    failedSegmentIndex: undefined,
    errorMessage: '',
  };
}

export function useBatchGenerationState() {
  const state = reactive<BatchGenerationState>(createDefaultState());

  const reset = (totalSegments = 0, currentSegment = 0) => {
    Object.assign(state, createDefaultState(), {
      totalSegments: Math.max(0, totalSegments),
      currentSegment: Math.max(0, currentSegment),
    });
  };

  const start = (totalSegments: number, currentSegment: number) => {
    Object.assign(state, {
      status: 'running' as const,
      totalSegments: Math.max(0, totalSegments),
      currentSegment: Math.max(0, currentSegment),
      failedSegmentIndex: undefined,
      errorMessage: '',
    });
  };

  const pause = () => {
    if (state.status === 'running') {
      state.status = 'paused';
    }
  };

  const resume = () => {
    if (state.status === 'paused' || state.status === 'failed') {
      state.status = 'running';
      state.errorMessage = '';
      state.failedSegmentIndex = undefined;
    }
  };

  const complete = () => {
    state.status = 'completed';
    state.failedSegmentIndex = undefined;
    state.errorMessage = '';
  };

  const fail = (segmentIndex: number, message: string) => {
    state.status = 'failed';
    state.failedSegmentIndex = Math.max(0, segmentIndex);
    state.errorMessage = message;
  };

  return {
    state,
    reset,
    start,
    pause,
    resume,
    complete,
    fail,
  };
}

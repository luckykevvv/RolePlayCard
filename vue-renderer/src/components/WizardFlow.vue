<script setup lang="ts">
import type {
  BatchGenerationState,
  SegmentChangeSet,
  SegmentInfo,
  SegmentReport,
} from '../../../shared/types.js';

const props = defineProps<{
  storyText: string;
  wizardStep: 'input' | 'segments' | 'review' | 'export';
  maxCharsPerSegment: number;
  chapterRegex: string;
  storySegments: SegmentInfo[];
  currentSegmentIndex: number;
  completedSegments: number;
  totalSegments: number;
  allSegmentsCompleted: boolean;
  storySegmentationMode: 'chapter' | 'hard_buffer';
  latestSegmentReport: SegmentReport | null;
  pendingChangeSet: SegmentChangeSet | null;
  pendingSegmentIndex: number | null;
  segmentPreviewBusy: boolean;
  segmentGenerateBusy: boolean;
  batchState: BatchGenerationState;
  reviewEachSegment: boolean;
}>();

const emit = defineEmits<{
  (event: 'update-story-text', value: string): void;
  (event: 'update-max-chars', value: number): void;
  (event: 'update-chapter-regex', value: string): void;
  (event: 'update-wizard-step', value: 'input' | 'segments' | 'review' | 'export'): void;
  (event: 'upload-story-text'): void;
  (event: 'preview-segments'): void;
  (event: 'generate-current'): void;
  (event: 'generate-next'): void;
  (event: 'choose-segment', value: number): void;
  (event: 'start-batch'): void;
  (event: 'pause-batch'): void;
  (event: 'resume-batch'): void;
  (event: 'retry-batch'): void;
  (event: 'apply-segment-review'): void;
  (event: 'skip-segment-review'): void;
  (event: 'update-review-each-segment', value: boolean): void;
}>();

const stepOrder: Array<{ key: 'input' | 'segments' | 'review' | 'export'; label: string }> = [
  { key: 'input', label: '1. 输入原文' },
  { key: 'segments', label: '2. 切分与生成' },
  { key: 'review', label: '3. 变更审阅' },
  { key: 'export', label: '4. 导出检查' },
];

const summarizeArray = (values: string[]) => (values.length ? values.join('、') : '无');
</script>

<template>
  <section class="content-grid">
    <div class="editor-column">
      <section class="card">
        <div class="panel-header">
          <h2>向导模式</h2>
          <span class="muted">创作效率优先</span>
        </div>
        <div class="inline-actions">
          <button
            v-for="step in stepOrder"
            :key="step.key"
            :class="['nav-button', { active: wizardStep === step.key }]"
            @click="emit('update-wizard-step', step.key)"
          >
            {{ step.label }}
          </button>
        </div>
      </section>

      <section class="card">
        <div class="panel-header">
          <h2>故事输入与切分</h2>
        </div>
        <div class="field">
          <label>小说全文</label>
          <textarea
            :value="storyText"
            rows="8"
            placeholder="粘贴长篇文本，或上传 txt。"
            @input="emit('update-story-text', ($event.target as HTMLTextAreaElement).value)"
          />
        </div>
        <div class="field-grid">
          <label>硬切分上限</label>
          <input
            :value="maxCharsPerSegment"
            type="number"
            min="500"
            step="100"
            @input="emit('update-max-chars', Number(($event.target as HTMLInputElement).value) || 20000)"
          />
          <label>章节识别正则</label>
          <textarea
            :value="chapterRegex"
            rows="3"
            @input="emit('update-chapter-regex', ($event.target as HTMLTextAreaElement).value)"
          />
        </div>
        <div class="inline-actions">
          <button @click="emit('upload-story-text')" :disabled="segmentPreviewBusy || segmentGenerateBusy">上传小说 txt</button>
          <button @click="emit('preview-segments')" :disabled="segmentPreviewBusy || segmentGenerateBusy">
            <span v-if="segmentPreviewBusy" class="loading-spinner loading-inline" />
            {{ segmentPreviewBusy ? '预览生成中...' : '生成分段预览' }}
          </button>
        </div>
        <p class="muted">切分策略：{{ storySegmentationMode === 'chapter' ? '章节优先' : '硬切分' }} · 进度 {{ completedSegments }} / {{ totalSegments }}</p>
      </section>

      <section class="card">
        <div class="panel-header">
          <h2>批量增量生成</h2>
        </div>
        <div class="inline-actions">
          <label class="muted" style="display: inline-flex; align-items: center; gap: 0.4rem;">
            <input
              class="checkbox"
              type="checkbox"
              :checked="reviewEachSegment"
              @change="emit('update-review-each-segment', ($event.target as HTMLInputElement).checked)"
            />
            每段生成后先审阅再合并
          </label>
          <button @click="emit('generate-current')" :disabled="segmentPreviewBusy || segmentGenerateBusy || storySegments.length === 0">
            生成当前段
          </button>
          <button @click="emit('generate-next')" :disabled="segmentPreviewBusy || segmentGenerateBusy || storySegments.length === 0 || allSegmentsCompleted">
            {{ allSegmentsCompleted ? '已完成全部分段' : '下一段增量更新' }}
          </button>
          <button @click="emit('start-batch')" :disabled="batchState.status === 'running' || storySegments.length === 0 || allSegmentsCompleted">
            一键跑到末段
          </button>
          <button @click="emit('pause-batch')" :disabled="batchState.status !== 'running'">暂停</button>
          <button @click="emit('resume-batch')" :disabled="batchState.status !== 'paused'">继续</button>
          <button @click="emit('retry-batch')" :disabled="batchState.status !== 'failed'">失败重试</button>
        </div>
        <p class="muted">
          批量状态：{{ batchState.status }} · 当前段 {{ batchState.currentSegment }} / {{ batchState.totalSegments }}
          <template v-if="batchState.errorMessage"> · 错误：{{ batchState.errorMessage }}</template>
        </p>
        <p v-if="latestSegmentReport" class="muted">
          最近一段：新增角色 {{ latestSegmentReport.newCharactersCount }}，新增地点 {{ latestSegmentReport.newLocationsCount }}，新增节点 {{ latestSegmentReport.newTimelineNodesCount }}。
        </p>
      </section>
    </div>

    <div class="side-column">
      <section class="card">
        <div class="panel-header">
          <h2>分段列表</h2>
        </div>
        <p v-if="storySegments.length === 0" class="muted">尚未生成分段预览。</p>
        <div v-else class="overview-list">
          <button
            v-for="segment in storySegments"
            :key="segment.segmentIndex"
            :class="['overview-item', { active: currentSegmentIndex === segment.segmentIndex }]"
            @click="emit('choose-segment', segment.segmentIndex)"
          >
            <strong>第 {{ segment.segmentIndex + 1 }} 段 · {{ segment.title }}</strong>
            <span class="overview-meta">字符 {{ segment.charCount }} · 区间 {{ segment.start }}-{{ segment.end }}</span>
            <span class="overview-meta">{{ segment.preview }}</span>
          </button>
        </div>
      </section>

      <section class="card">
        <div class="panel-header">
          <h2>变更审阅卡</h2>
        </div>
        <p v-if="pendingSegmentIndex !== null" class="muted">待审阅段落：第 {{ pendingSegmentIndex + 1 }} 段</p>
        <p v-if="!pendingChangeSet" class="muted">当前没有待审阅变更。</p>
        <template v-else>
          <div class="field">
            <label>角色</label>
            <p class="muted">新增：{{ summarizeArray(pendingChangeSet.characters.added) }}</p>
            <p class="muted">更新：{{ summarizeArray(pendingChangeSet.characters.updated) }}</p>
          </div>
          <div class="field">
            <label>地点</label>
            <p class="muted">新增：{{ summarizeArray(pendingChangeSet.locations.added) }}</p>
            <p class="muted">更新：{{ summarizeArray(pendingChangeSet.locations.updated) }}</p>
          </div>
          <div class="field">
            <label>时间线节点</label>
            <p class="muted">新增：{{ summarizeArray(pendingChangeSet.timelineNodes.added) }}</p>
            <p class="muted">更新：{{ summarizeArray(pendingChangeSet.timelineNodes.updated) }}</p>
          </div>
          <div class="inline-actions">
            <button @click="emit('apply-segment-review')">应用本段合并</button>
            <button @click="emit('skip-segment-review')">跳过本段合并</button>
          </div>
        </template>
      </section>
    </div>
  </section>
</template>

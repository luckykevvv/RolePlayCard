<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import ExpertEditor from './components/ExpertEditor.vue';
import SettingsPanel from './components/SettingsPanel.vue';
import WizardFlow from './components/WizardFlow.vue';
import { apiRequest, downloadBase64Png, imageSrcFromPath } from './composables/useApiClient';
import { useAutosave } from './composables/useAutosave';
import { useBatchGenerationState } from './composables/useBatchGeneration';
import type {
  AppSettings,
  BatchGenerationState,
  BuiltinPrefixPromptListResponse,
  BuiltinPrefixPromptOption,
  CharacterDefinition,
  CharacterDraft,
  DraftSummary,
  EditorMode,
  ExportCharacterCardResponse,
  GenerateCardFromStorySegmentResponse,
  GenerateCardFromStoryResponse,
  GenerateFieldRequest,
  ImportCharacterCardResponse,
  OrganizeTimelineResponse,
  OpeningInfo,
  SegmentInfo,
  SegmentChangeSet,
  SegmentReport,
  StorySegmentsPreviewResponse,
  TimelineInfo,
  TimelineNode,
  ProviderConfig,
  UploadImageResponse,
  WorldBookAdvancedOptions,
  WorldBookEntry,
} from '../../shared/types.js';

const SETTINGS_STORAGE_KEY = 'roleplaycard_settings_v2';
const LEGACY_SETTINGS_COOKIE_KEY = 'roleplaycard_settings';
const CLIENT_ID_STORAGE_KEY = 'roleplaycard_client_id_v1';
const DEFAULT_PROVIDER_TIMEOUT_MS = 45000;
const MIN_PROVIDER_TIMEOUT_MS = 1000;
const DEFAULT_CHAPTER_REGEX =
  '(?imx)^[ \\t]*(第[0-9零〇一二三四五六七八九十百千两]+[章节卷回篇集部幕][^\\n\\r]*|卷[0-9零〇一二三四五六七八九十百千两]+[^\\n\\r]*|幕[0-9零〇一二三四五六七八九十百千两]+[^\\n\\r]*|chapter[ \\t]+[0-9ivxlcdm]+[^\\n\\r]*|volume[ \\t]+[0-9ivxlcdm]+[^\\n\\r]*)[ \\t]*$';

function createStorySegmentationSettings(): AppSettings['storySegmentation'] {
  return {
    chapterRegex: DEFAULT_CHAPTER_REGEX,
    maxCharsPerSegment: 20000,
  };
}

function buildDefaultSettings(): AppSettings {
  return {
    textProvider: createProviderConfig(),
    imageProvider: createProviderConfig(),
    storySegmentation: createStorySegmentationSettings(),
    exportDirectory: '',
    recentDirectory: '',
  };
}

function clonePlain<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function mergeSettings(defaults: AppSettings, incoming: Partial<AppSettings> | null): AppSettings {
  if (!incoming) return defaults;
  const normalizeProvider = (_provider: unknown): ProviderConfig['provider'] => 'openai_compatible';
  return {
    ...defaults,
    ...incoming,
    textProvider: {
      ...defaults.textProvider,
      ...(incoming.textProvider ?? {}),
      provider: normalizeProvider(incoming.textProvider?.provider),
    },
    imageProvider: {
      ...defaults.imageProvider,
      ...(incoming.imageProvider ?? {}),
      provider: normalizeProvider(incoming.imageProvider?.provider),
    },
    storySegmentation: {
      ...defaults.storySegmentation,
      ...(incoming.storySegmentation ?? {}),
    },
  };
}

function getCookieValue(name: string): string | null {
  const encoded = `${encodeURIComponent(name)}=`;
  const parts = document.cookie.split(';');
  for (const part of parts) {
    const trimmed = part.trim();
    if (trimmed.startsWith(encoded)) {
      return decodeURIComponent(trimmed.slice(encoded.length));
    }
  }
  return null;
}

function setCookieValue(name: string, value: string, days = 365) {
  const maxAge = days * 24 * 60 * 60;
  document.cookie = `${encodeURIComponent(name)}=${encodeURIComponent(value)}; path=/; max-age=${maxAge}; SameSite=Lax`;
}

function clearLegacySettingsCookie() {
  setCookieValue(LEGACY_SETTINGS_COOKIE_KEY, '', 0);
}

function loadSettingsFromPersistence(): AppSettings {
  const defaults = buildDefaultSettings();
  const storageRaw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
  if (storageRaw) {
    try {
      const parsed = JSON.parse(storageRaw) as Partial<AppSettings>;
      return mergeSettings(defaults, parsed);
    } catch {
      window.localStorage.removeItem(SETTINGS_STORAGE_KEY);
    }
  }
  const raw = getCookieValue(LEGACY_SETTINGS_COOKIE_KEY);
  if (!raw) return defaults;
  try {
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    const merged = mergeSettings(defaults, parsed);
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(merged));
    clearLegacySettingsCookie();
    return merged;
  } catch {
    return defaults;
  }
}

function saveSettingsToPersistence(value: AppSettings) {
  window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(clonePlain(value)));
}

function createClientId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
  }
  return `${Date.now().toString(16)}-${Math.floor(Math.random() * Number.MAX_SAFE_INTEGER).toString(16)}`;
}

function loadClientId(): string {
  const raw = window.localStorage.getItem(CLIENT_ID_STORAGE_KEY)?.trim() ?? '';
  if (/^[A-Za-z0-9_-]{8,128}$/.test(raw)) {
    return raw;
  }
  const created = createClientId();
  window.localStorage.setItem(CLIENT_ID_STORAGE_KEY, created);
  return created;
}

const CLIENT_ID = loadClientId();

function draftScopedInit(init?: RequestInit): RequestInit {
  return {
    ...(init ?? {}),
    headers: {
      ...(init?.headers && typeof init.headers === 'object' && !Array.isArray(init.headers)
        ? (init.headers as Record<string, string>)
        : {}),
      'X-Client-Id': CLIENT_ID,
    },
  };
}

const nowIso = () => new Date().toISOString();
const createId = () => {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  if (typeof crypto !== 'undefined' && typeof crypto.getRandomValues === 'function') {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }
  const ts = Date.now().toString(16);
  const rand = Math.floor(Math.random() * Number.MAX_SAFE_INTEGER).toString(16);
  return `${ts}-${rand}`;
};
const splitKeywords = (text: string) =>
  text
    .split(/[,，\n]/)
    .map((item) => item.trim())
    .filter(Boolean);

const createProviderConfig = (): ProviderConfig => ({
  provider: 'openai_compatible',
  baseUrl: 'https://api.openai.com/v1',
  apiKey: '',
  model: '',
  timeoutMs: 45000,
  temperature: 0.8,
  enabled: true,
  prefixPrompt: '',
  prefixPromptMode: 'custom',
  builtinPrefixPromptModel: '',
});

const createAdvanced = (): WorldBookAdvancedOptions => ({
  insertionOrder: 200,
  triggerProbability: 100,
  insertionPosition: 'after_char',
  depth: 4,
});

const createCharacter = (): CharacterDefinition => ({
  id: createId(),
  enabled: true,
  triggerMode: 'keyword',
  isUserRole: false,
  name: '',
  triggerKeywords: [],
  age: '',
  appearance: '',
  personality: '',
  speakingStyle: '',
  speakingExample: '',
  background: '',
  advanced: createAdvanced(),
});

const createWorldEntry = (): WorldBookEntry => ({
  id: createId(),
  enabled: true,
  triggerMode: 'keyword',
  title: '',
  keywords: [],
  content: '',
  advanced: createAdvanced(),
});

const createOpening = (index = 0): OpeningInfo => ({
  id: createId(),
  title: `首屏 ${index + 1}`,
  greeting: '',
  scenario: '',
  exampleDialogue: '',
  firstMessage: '',
});

const createTimelineNode = (parentId = ''): TimelineNode => ({
  id: createId(),
  parentId,
  title: '',
  timePoint: '',
  trigger: '',
  event: '',
  objective: '',
  conflict: '',
  outcome: '',
  nextHook: '',
});

const createTimeline = (): TimelineInfo => ({
  title: '剧情推进',
  enabled: false,
  triggerMode: 'always',
  keywords: ['剧情推进', '主线节点', '剧情走向'],
  timeBaseline: 'T0=当前主线时刻',
  timeFormat: 'T±<offset> | 时间描述',
  nodes: [],
});

type StoryGenerationStateDraft = NonNullable<CharacterDraft['storyGenerationState']>;
type WorkflowStateDraft = NonNullable<CharacterDraft['workflowState']>;
type BatchGenerationStateDraft = NonNullable<WorkflowStateDraft['batchGeneration']>;

const createStoryGenerationState = (): StoryGenerationStateDraft => ({
  totalSegments: 0,
  currentSegmentIndex: 0,
  segmentationMode: 'hard_buffer',
});

const createBatchGenerationState = (): BatchGenerationStateDraft => ({
  status: 'idle',
  currentSegment: 0,
  totalSegments: 0,
  failedSegmentIndex: undefined,
  errorMessage: '',
});

const createWorkflowState = (): WorkflowStateDraft => ({
  editorMode: 'expert',
  wizardStep: 'input',
  batchGeneration: createBatchGenerationState(),
});

function ensureStoryGenerationState(value: CharacterDraft): CharacterDraft['storyGenerationState'] {
  const incoming = value.storyGenerationState;
  if (!incoming || typeof incoming !== 'object') {
    return undefined;
  }
  const totalSegments = Number.isFinite(Number(incoming.totalSegments))
    ? Math.max(0, Number(incoming.totalSegments))
    : 0;
  const currentSegmentIndex = Number.isFinite(Number(incoming.currentSegmentIndex))
    ? Math.max(0, Number(incoming.currentSegmentIndex))
    : 0;
  const segmentationMode =
    incoming.segmentationMode === 'chapter' || incoming.segmentationMode === 'hard_buffer'
      ? incoming.segmentationMode
      : 'hard_buffer';
  return {
    totalSegments,
    currentSegmentIndex: Math.min(currentSegmentIndex, totalSegments),
    segmentationMode,
  };
}

function ensureWorkflowState(value: CharacterDraft): CharacterDraft['workflowState'] {
  const incoming = value.workflowState;
  if (!incoming || typeof incoming !== 'object') {
    return createWorkflowState();
  }
  const editorMode = incoming.editorMode === 'wizard' || incoming.editorMode === 'expert'
    ? incoming.editorMode
    : 'expert';
  const wizardStep = incoming.wizardStep === 'input'
    || incoming.wizardStep === 'segments'
    || incoming.wizardStep === 'review'
    || incoming.wizardStep === 'export'
    ? incoming.wizardStep
    : 'input';
  const batch = incoming.batchGeneration && typeof incoming.batchGeneration === 'object'
    ? incoming.batchGeneration
    : createBatchGenerationState();
  const status = batch.status === 'idle'
    || batch.status === 'running'
    || batch.status === 'paused'
    || batch.status === 'completed'
    || batch.status === 'failed'
    ? batch.status
    : 'idle';
  const currentSegment = Number.isFinite(Number(batch.currentSegment))
    ? Math.max(0, Number(batch.currentSegment))
    : 0;
  const totalSegments = Number.isFinite(Number(batch.totalSegments))
    ? Math.max(0, Number(batch.totalSegments))
    : 0;
  const failedSegmentIndex = Number.isFinite(Number(batch.failedSegmentIndex))
    ? Math.max(0, Number(batch.failedSegmentIndex))
    : undefined;
  return {
    editorMode,
    wizardStep,
    batchGeneration: {
      status,
      currentSegment: Math.min(currentSegment, totalSegments || currentSegment),
      totalSegments,
      failedSegmentIndex,
      errorMessage: String(batch.errorMessage || ''),
    },
  };
}

function isBlankCharacter(character: CharacterDefinition): boolean {
  return !(
    character.name.trim() ||
    character.triggerKeywords.length ||
    character.age.trim() ||
    character.appearance.trim() ||
    character.personality.trim() ||
    character.speakingStyle.trim() ||
    character.speakingExample.trim() ||
    character.background.trim()
  );
}

function inferSourceType(value: CharacterDraft): CharacterDraft['sourceType'] {
  if (value.sourceType === 'external' || value.sourceType === 'roleplaycard') {
    return value.sourceType;
  }
  if (
    value.characters.length === 1 &&
    isBlankCharacter(value.characters[0]) &&
    value.worldBook.entries.length > 0
  ) {
    return 'external';
  }
  return 'roleplaycard';
}

function isBlankOpening(opening: OpeningInfo): boolean {
  return !(
    opening.greeting.trim()
    || opening.scenario.trim()
    || opening.exampleDialogue.trim()
    || opening.firstMessage.trim()
  );
}

function ensureOpenings(value: CharacterDraft): OpeningInfo[] {
  if (Array.isArray(value.openings) && value.openings.length > 0) {
    return value.openings.map((item, index) => ({
      ...createOpening(index),
      ...item,
      id: item.id || createId(),
      title: item.title?.trim() ? item.title : `首屏 ${index + 1}`,
    }));
  }
  if (value.opening) {
    return [
      {
        ...createOpening(0),
        ...value.opening,
        id: value.opening.id || createId(),
        title: value.opening.title?.trim() ? value.opening.title : '首屏 1',
      },
    ];
  }
  return [createOpening(0)];
}

function parseTimelineNodesFromWorldBookContent(content: string): TimelineNode[] {
  const rawText = String(content || '');
  if (!rawText) {
    return [];
  }
  let parsed: unknown = null;
  try {
    parsed = JSON.parse(rawText);
  } catch {
    parsed = null;
  }
  let rawNodes: unknown = [];
  if (parsed && typeof parsed === 'object') {
    const dict = parsed as Record<string, unknown>;
    if (Array.isArray(dict.nodes)) {
      rawNodes = dict.nodes;
    } else if (dict.plotProgression && typeof dict.plotProgression === 'object') {
      const progression = dict.plotProgression as Record<string, unknown>;
      if (Array.isArray(progression.nodes)) {
        rawNodes = progression.nodes;
      }
    }
  }
  if (!Array.isArray(rawNodes)) {
    return [];
  }
  return rawNodes
    .filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    .map((item) => ({
      id: typeof item.id === 'string' && item.id ? item.id : createId(),
      parentId: typeof item.parentId === 'string' ? item.parentId : '',
      title: String(item.title ?? item.name ?? item.stage ?? ''),
      timePoint: String(item.timePoint ?? item.time ?? item.timeline ?? ''),
      trigger: String(item.trigger ?? item.triggerCondition ?? item.condition ?? ''),
      event: String(item.event ?? item.keyEvent ?? item.summary ?? ''),
      objective: String(item.objective ?? item.goal ?? ''),
      conflict: String(item.conflict ?? item.obstacle ?? ''),
      outcome: String(item.outcome ?? item.result ?? ''),
      nextHook: String(item.nextHook ?? item.next ?? item.nextStep ?? ''),
    }));
}

function ensureTimeline(value: CharacterDraft): TimelineInfo {
  const timelineCandidate = value.timeline && typeof value.timeline === 'object' ? value.timeline : null;
  const timeline = {
    ...createTimeline(),
    ...(timelineCandidate ?? {}),
    triggerMode: 'always' as const,
  };
  const worldEntries = Array.isArray(value.worldBook?.entries) ? value.worldBook.entries : [];
  const legacyPlotEntry = worldEntries.find((entry) => entry?.title === '剧情推进');
  if ((!Array.isArray(timeline.nodes) || timeline.nodes.length === 0) && legacyPlotEntry?.content) {
    timeline.nodes = parseTimelineNodesFromWorldBookContent(legacyPlotEntry.content);
    timeline.enabled = Boolean(legacyPlotEntry.enabled);
    timeline.keywords = legacyPlotEntry.keywords?.length ? legacyPlotEntry.keywords : timeline.keywords;
  }
  if (!Array.isArray(timeline.nodes)) {
    timeline.nodes = [];
  }
  const normalizedNodes = timeline.nodes.map((item) => ({
    ...createTimelineNode(''),
    ...item,
    id: item.id || createId(),
    parentId: item.parentId || '',
  }));
  const validIds = new Set(normalizedNodes.map((item) => item.id));
  normalizedNodes.forEach((node) => {
    if (!node.parentId || node.parentId === node.id || !validIds.has(node.parentId)) {
      node.parentId = '';
    }
  });
  timeline.nodes = normalizedNodes;
  timeline.keywords = Array.isArray(timeline.keywords) ? timeline.keywords.filter(Boolean) : [];
  if (timeline.keywords.length === 0) {
    timeline.keywords = ['剧情推进', '主线节点', '剧情走向'];
  }
  timeline.title = timeline.title || '剧情推进';
  timeline.timeBaseline = String(timeline.timeBaseline || 'T0=当前主线时刻');
  timeline.timeFormat = String(timeline.timeFormat || 'T±<offset> | 时间描述');
  return timeline;
}

function normalizeTimelineInfo(value: Partial<TimelineInfo> | null | undefined): TimelineInfo {
  const timeline = {
    ...createTimeline(),
    ...(value ?? {}),
    triggerMode: 'always' as const,
  };
  if (!Array.isArray(timeline.nodes)) {
    timeline.nodes = [];
  }
  timeline.nodes = timeline.nodes.map((item) => ({
    ...createTimelineNode(''),
    ...item,
    id: item.id || createId(),
    parentId: item.parentId || '',
  }));
  const validIds = new Set(timeline.nodes.map((item) => item.id));
  timeline.nodes.forEach((node) => {
    if (!node.parentId || node.parentId === node.id || !validIds.has(node.parentId)) {
      node.parentId = '';
    }
  });
  timeline.keywords = Array.isArray(timeline.keywords) ? timeline.keywords.filter(Boolean) : [];
  if (timeline.keywords.length === 0) {
    timeline.keywords = ['剧情推进', '主线节点', '剧情走向'];
  }
  timeline.title = timeline.title || '剧情推进';
  timeline.timeBaseline = String(timeline.timeBaseline || 'T0=当前主线时刻');
  timeline.timeFormat = String(timeline.timeFormat || 'T±<offset> | 时间描述');
  return timeline;
}

const createDraft = (): CharacterDraft => ({
  id: createId(),
  version: 2,
  sourceType: 'roleplaycard',
  createdAt: nowIso(),
  updatedAt: nowIso(),
  card: {
    name: '',
    description: '',
  },
  characters: [createCharacter()],
  openings: [createOpening(0)],
  worldBook: {
    entries: [],
  },
  timeline: createTimeline(),
  illustration: {
    originalImagePath: '',
    generatedImagePath: '',
    exportImagePath: '',
    promptSnapshot: '',
    negativePrompt: '',
    stylePrompt: '',
  },
  storyGenerationState: undefined,
  workflowState: createWorkflowState(),
});

const settings = reactive<AppSettings>({
  textProvider: createProviderConfig(),
  imageProvider: createProviderConfig(),
  storySegmentation: createStorySegmentationSettings(),
  exportDirectory: '',
  recentDirectory: '',
});

const draft = reactive<CharacterDraft>(createDraft());
const drafts = ref<DraftSummary[]>([]);
const activeView = ref<'editor' | 'settings'>('editor');
const generalStatus = ref('准备就绪');
const autosaveStatus = ref('自动保存待机');
const appDataDir = ref('');
const aiBusyField = ref('');
const imagePromptBusy = ref(false);
const imageGenerateBusy = ref(false);
const autosaveSaving = ref(false);
const cardGenerateBusy = ref(false);
const segmentPreviewBusy = ref(false);
const segmentGenerateBusy = ref(false);
const testingTextProvider = ref(false);
const testingImageProvider = ref(false);
const loadingBuiltinPrefixPrompts = ref(false);
const textModelOptions = ref<string[]>([]);
const imageModelOptions = ref<string[]>([]);
const builtinPrefixPromptDir = ref('');
const builtinPrefixPromptOptions = ref<BuiltinPrefixPromptOption[]>([]);
const cardGenerateInput = ref('');
const storySegments = ref<SegmentInfo[]>([]);
const storySegmentationMode = ref<'chapter' | 'hard_buffer'>('hard_buffer');
const currentSegmentIndex = ref(0);
const latestSegmentReport = ref<SegmentReport | null>(null);
const pendingSegmentReview = ref<{
  segmentIndex: number;
  draft: CharacterDraft;
  report: SegmentReport;
  changeSet: SegmentChangeSet | null;
} | null>(null);
const selectedCharacterIndex = ref<number | null>(0);
const selectedOpeningIndex = ref<number | null>(0);
const selectedWorldEntryIndex = ref<number | null>(0);
const selectedTimelineNodeId = ref<string | null>(null);
const timelineOrganizeBusy = ref(false);
const timelineOrganizeProposal = ref<TimelineInfo | null>(null);
const timelineDragNodeId = ref<string | null>(null);
const timelineDragOverNodeId = ref<string | null>(null);
const autosaveEnabled = ref(true);
const importInputRef = ref<HTMLInputElement | null>(null);
const imageInputRef = ref<HTMLInputElement | null>(null);
const storyTextInputRef = ref<HTMLInputElement | null>(null);
const previewSeed = ref(Date.now());
const workflowEditorMode = ref<EditorMode>('expert');
const workflowWizardStep = ref<'input' | 'segments' | 'review' | 'export'>('input');
const { state: batchGenerationState, start: startBatchState, pause: pauseBatchState, resume: resumeBatchState, complete: completeBatchState, fail: failBatchState, reset: resetBatchState } = useBatchGenerationState();
const reviewEachSegment = ref(false);
const batchLoopRunning = ref(false);
const imagePreview = computed(
  () =>
    imageSrcFromPath(
      draft.illustration.generatedImagePath || draft.illustration.originalImagePath || '',
      previewSeed.value,
    ),
);
const effectiveCardName = computed(
  () => draft.card.name.trim() || draft.characters[0]?.name.trim() || '',
);
const primaryOpening = computed(() => {
  if (!draft.openings?.length) {
    draft.openings = [createOpening(0)];
  }
  return draft.openings[0];
});
const exportReady = computed(
  () => Boolean(effectiveCardName.value && primaryOpening.value.firstMessage.trim() && imagePreview.value),
);
const isExternalCard = computed(() => inferSourceType(draft) === 'external');
const aiBusy = computed(() =>
  Boolean(
    aiBusyField.value ||
      imagePromptBusy.value ||
      imageGenerateBusy.value ||
      cardGenerateBusy.value ||
      segmentPreviewBusy.value ||
      segmentGenerateBusy.value,
  ),
);
const maxCharsPerSegment = computed({
  get: () => settings.storySegmentation.maxCharsPerSegment,
  set: (value: number) => {
    const normalized = Math.max(500, Math.floor(Number(value) || 20000));
    settings.storySegmentation.maxCharsPerSegment = normalized;
  },
});
const segmentGenerationState = computed<StoryGenerationStateDraft>(() => {
  const state = ensureStoryGenerationState(draft);
  if (!state) {
    return createStoryGenerationState();
  }
  return {
    totalSegments: state.totalSegments,
    currentSegmentIndex: state.currentSegmentIndex,
    segmentationMode: state.segmentationMode,
  };
});
const completedSegments = computed(() => segmentGenerationState.value.currentSegmentIndex);
const totalSegments = computed(() => segmentGenerationState.value.totalSegments);
const allSegmentsCompleted = computed(
  () => totalSegments.value > 0 && completedSegments.value >= totalSegments.value,
);
const editorMode = computed<EditorMode>({
  get: () => workflowEditorMode.value,
  set: (value) => {
    workflowEditorMode.value = value;
    updateWorkflowState();
  },
});
const wizardStep = computed<'input' | 'segments' | 'review' | 'export'>({
  get: () => workflowWizardStep.value,
  set: (value) => {
    workflowWizardStep.value = value;
    updateWorkflowState();
  },
});
const validationReport = computed(() => {
  const items: string[] = [];
  if (!effectiveCardName.value) items.push('缺少角色卡名称（或至少一个角色名称）');
  if (!primaryOpening.value.firstMessage.trim()) items.push('缺少首条消息');
  if (!imagePreview.value) items.push('缺少导出图片');
  return items;
});

function buildTimelineRows(nodesInput: TimelineNode[]): Array<{ node: TimelineNode; depth: number }> {
  const nodes = Array.isArray(nodesInput) ? nodesInput : [];
  const byParent = new Map<string, TimelineNode[]>();
  const allIds = new Set(nodes.map((item) => item.id));
  for (const node of nodes) {
    const parentKey = node.parentId && allIds.has(node.parentId) ? node.parentId : '';
    const siblings = byParent.get(parentKey) ?? [];
    siblings.push(node);
    byParent.set(parentKey, siblings);
  }
  const rows: Array<{ node: TimelineNode; depth: number }> = [];
  const visited = new Set<string>();
  const walk = (parentId: string, depth: number) => {
    const children = byParent.get(parentId) ?? [];
    for (const child of children) {
      if (visited.has(child.id)) continue;
      visited.add(child.id);
      rows.push({ node: child, depth });
      walk(child.id, depth + 1);
    }
  };
  walk('', 0);
  for (const node of nodes) {
    if (visited.has(node.id)) continue;
    rows.push({ node, depth: 0 });
    walk(node.id, 1);
  }
  return rows;
}

const timelineRows = computed(() => buildTimelineRows(draft.timeline.nodes ?? []));
const timelineProposalRows = computed(() => buildTimelineRows(timelineOrganizeProposal.value?.nodes ?? []));

const timelineGraphNodeWidth = 172;
const timelineGraphNodeHeight = 58;

const timelineGraph = computed(() => {
  const rows = timelineRows.value;
  const nodeWidth = timelineGraphNodeWidth;
  const nodeHeight = timelineGraphNodeHeight;
  const gapX = 52;
  const gapY = 16;
  const padding = 18;

  if (rows.length === 0) {
    return {
      width: 0,
      height: 0,
      nodes: [] as Array<{
        id: string;
        x: number;
        y: number;
        title: string;
        subtitle: string;
      }>,
      edges: [] as Array<{
        id: string;
        d: string;
      }>,
    };
  }

  const maxDepth = rows.reduce((max, row) => Math.max(max, row.depth), 0);
  const width = padding * 2 + (maxDepth + 1) * nodeWidth + maxDepth * gapX;
  const height = padding * 2 + rows.length * nodeHeight + Math.max(0, rows.length - 1) * gapY;

  const nodes = rows.map((row, index) => {
    const x = padding + row.depth * (nodeWidth + gapX);
    const y = padding + index * (nodeHeight + gapY);
    const title = summarizeText(row.node.title || `节点 ${index + 1}`, 12);
    const subtitle = summarizeText(
      row.node.timePoint || row.node.event || row.node.trigger || '未设说明',
      14,
    );
    return {
      id: row.node.id,
      x,
      y,
      title,
      subtitle,
    };
  });

  const byId = new Map(nodes.map((node) => [node.id, node]));
  const edges: Array<{ id: string; d: string }> = [];
  rows.forEach((row) => {
    if (!row.node.parentId) return;
    const parent = byId.get(row.node.parentId);
    const child = byId.get(row.node.id);
    if (!parent || !child) return;
    const x1 = parent.x + nodeWidth;
    const y1 = parent.y + nodeHeight / 2;
    const x2 = child.x;
    const y2 = child.y + nodeHeight / 2;
    const cp1x = x1 + (x2 - x1) * 0.45;
    const cp2x = x1 + (x2 - x1) * 0.55;
    const d = `M ${x1} ${y1} C ${cp1x} ${y1}, ${cp2x} ${y2}, ${x2} ${y2}`;
    edges.push({ id: `${row.node.parentId}-${row.node.id}`, d });
  });

  return {
    width,
    height,
    nodes,
    edges,
  };
});

const timelineRootCount = computed(() => draft.timeline.nodes.filter((node) => !node.parentId).length);
const timelineProposalRootCount = computed(
  () => (timelineOrganizeProposal.value?.nodes ?? []).filter((node) => !node.parentId).length,
);

function timelineParentTitle(node: TimelineNode): string {
  if (!node.parentId) {
    return '';
  }
  const parent = draft.timeline.nodes.find((item) => item.id === node.parentId);
  if (!parent) {
    return '未命名父节点';
  }
  return parent.title || parent.timePoint || '未命名父节点';
}

function clearTimelineOrganizeProposal() {
  timelineOrganizeProposal.value = null;
}

let saveRequestSeq = 0;
let ignoreSaveBeforeSeq = 0;
const clearingData = ref(false);
const autosave = useAutosave(async () => {
  if (!autosaveEnabled.value || !autosave.dirty.value) return;
  await saveDraft(false, 'autosave');
}, 1200);

function setStatus(message: string, channel: 'general' | 'autosave' = 'general') {
  if (channel === 'autosave') {
    autosaveStatus.value = message;
    return;
  }
  generalStatus.value = message;
}

function syncWorkflowStateFromDraft() {
  const state = ensureWorkflowState(draft) ?? createWorkflowState();
  workflowEditorMode.value = state.editorMode;
  workflowWizardStep.value = state.wizardStep;
  resetBatchState(state.batchGeneration?.totalSegments ?? 0, state.batchGeneration?.currentSegment ?? 0);
  Object.assign(batchGenerationState, state.batchGeneration ?? createBatchGenerationState());
}

function updateWorkflowState() {
  draft.workflowState = {
    editorMode: workflowEditorMode.value,
    wizardStep: workflowWizardStep.value,
    batchGeneration: {
      status: batchGenerationState.status,
      currentSegment: batchGenerationState.currentSegment,
      totalSegments: batchGenerationState.totalSegments,
      failedSegmentIndex: batchGenerationState.failedSegmentIndex,
      errorMessage: batchGenerationState.errorMessage,
    } satisfies BatchGenerationState,
  };
}

function isProviderConfigured(config: ProviderConfig): boolean {
  return Boolean(config.baseUrl.trim() && config.apiKey.trim() && config.model.trim());
}

function normalizeTextPrefixPromptSettings() {
  if (settings.textProvider.prefixPromptMode !== 'builtin' && settings.textProvider.prefixPromptMode !== 'custom') {
    settings.textProvider.prefixPromptMode = 'custom';
  }
  if (typeof settings.textProvider.prefixPrompt !== 'string') {
    settings.textProvider.prefixPrompt = '';
  }
  if (typeof settings.textProvider.builtinPrefixPromptModel !== 'string') {
    settings.textProvider.builtinPrefixPromptModel = '';
  }
}

function normalizeProviderTimeoutSettings() {
  const normalizeTimeout = (value: unknown): number => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return DEFAULT_PROVIDER_TIMEOUT_MS;
    }
    return Math.max(MIN_PROVIDER_TIMEOUT_MS, Math.floor(numeric));
  };
  settings.textProvider.timeoutMs = normalizeTimeout(settings.textProvider.timeoutMs);
  settings.imageProvider.timeoutMs = normalizeTimeout(settings.imageProvider.timeoutMs);
}

function providerTimeoutMs(kind: 'text' | 'image'): number {
  const source = kind === 'text' ? settings.textProvider.timeoutMs : settings.imageProvider.timeoutMs;
  const numeric = Number(source);
  if (!Number.isFinite(numeric)) {
    return DEFAULT_PROVIDER_TIMEOUT_MS;
  }
  return Math.max(MIN_PROVIDER_TIMEOUT_MS, Math.floor(numeric));
}

function normalizeStorySegmentationSettings() {
  if (!settings.storySegmentation || typeof settings.storySegmentation !== 'object') {
    settings.storySegmentation = createStorySegmentationSettings();
    return;
  }
  if (typeof settings.storySegmentation.chapterRegex !== 'string' || !settings.storySegmentation.chapterRegex.trim()) {
    settings.storySegmentation.chapterRegex = DEFAULT_CHAPTER_REGEX;
  }
  const rawMaxChars = Number(settings.storySegmentation.maxCharsPerSegment);
  settings.storySegmentation.maxCharsPerSegment = Number.isFinite(rawMaxChars)
    ? Math.max(500, Math.floor(rawMaxChars))
    : 20000;
}

function ensureApiConfigured(kind: 'text' | 'image'): boolean {
  normalizeProviderTimeoutSettings();
  const target = kind === 'text' ? settings.textProvider : settings.imageProvider;
  if (isProviderConfigured(target)) {
    return true;
  }
  const label = kind === 'text' ? '文本' : '图像';
  const message = `未配置${label} API，请先在“设置”中填写 Base URL、API Key 和模型。`;
  setStatus(message);
  window.alert(message);
  activeView.value = 'settings';
  return false;
}

async function refreshDraftList() {
  const result = await apiRequest<DraftSummary[]>('/drafts', draftScopedInit());
  if (result.success && result.data) {
    drafts.value = result.data;
  }
}

async function loadSettings() {
  const defaults = buildDefaultSettings();
  const persisted = loadSettingsFromPersistence();
  Object.assign(settings, mergeSettings(defaults, persisted));
  normalizeProviderTimeoutSettings();
  normalizeTextPrefixPromptSettings();
  normalizeStorySegmentationSettings();
  saveSettingsToPersistence(settings);
}

async function saveSettings(message = '设置已保存') {
  normalizeProviderTimeoutSettings();
  normalizeTextPrefixPromptSettings();
  normalizeStorySegmentationSettings();
  saveSettingsToPersistence(settings);
  setStatus(message);
}

async function saveTextSettings() {
  await saveSettings('文本设置已保存');
}

async function saveImageSettings() {
  await saveSettings('图像设置已保存');
}

async function saveSegmentationSettings() {
  normalizeStorySegmentationSettings();
  await saveSettings('分段设置已保存');
}

type ProviderTestResponse = { provider: string; detail: string; models: string[] };

async function loadBuiltinPrefixPrompts() {
  loadingBuiltinPrefixPrompts.value = true;
  try {
    const result = await apiRequest<BuiltinPrefixPromptListResponse>('/settings/text/prefix-prompts');
    if (!result.success || !result.data) {
      setStatus(`读取内置破限提示词失败: ${result.message}`);
      return;
    }
    builtinPrefixPromptDir.value = result.data.directory;
    builtinPrefixPromptOptions.value = result.data.items ?? [];
    const selectedBuiltinModel = settings.textProvider.builtinPrefixPromptModel?.toLowerCase() ?? '';
    if (
      selectedBuiltinModel &&
      !builtinPrefixPromptOptions.value.some((item) => item.model.toLowerCase() === selectedBuiltinModel)
    ) {
      settings.textProvider.builtinPrefixPromptModel = '';
    }
  } finally {
    loadingBuiltinPrefixPrompts.value = false;
  }
}

async function testTextSettings() {
  testingTextProvider.value = true;
  setStatus('正在测试文本 Provider 并拉取模型列表...');
  try {
    const result = await apiRequest<ProviderTestResponse>('/settings/text/test', {
      method: 'POST',
      timeoutMs: providerTimeoutMs('text'),
      body: JSON.stringify({ settings: clonePlain(settings) }),
    });
    if (!result.success || !result.data) {
      setStatus(`文本连通性测试失败: ${result.message}`);
      return;
    }
    textModelOptions.value = result.data.models ?? [];
    if (textModelOptions.value.length > 0 && !textModelOptions.value.includes(settings.textProvider.model)) {
      settings.textProvider.model = textModelOptions.value[0];
    }
    if (textModelOptions.value.length === 0) {
      setStatus('文本连通性测试通过，但未拉取到模型列表。');
      return;
    }
    setStatus(`文本连通性测试通过，已拉取 ${textModelOptions.value.length} 个模型，请选择。`);
  } finally {
    testingTextProvider.value = false;
  }
}

async function testImageSettings() {
  testingImageProvider.value = true;
  setStatus('正在测试图像 Provider 并拉取模型列表...');
  try {
    const result = await apiRequest<ProviderTestResponse>('/settings/image/test', {
      method: 'POST',
      timeoutMs: providerTimeoutMs('image'),
      body: JSON.stringify({ settings: clonePlain(settings) }),
    });
    if (!result.success || !result.data) {
      setStatus(`图像连通性测试失败: ${result.message}`);
      return;
    }
    imageModelOptions.value = result.data.models ?? [];
    if (imageModelOptions.value.length > 0 && !imageModelOptions.value.includes(settings.imageProvider.model)) {
      settings.imageProvider.model = imageModelOptions.value[0];
    }
    if (imageModelOptions.value.length === 0) {
      setStatus('图像连通性测试通过，但未拉取到模型列表。');
      return;
    }
    setStatus(`图像连通性测试通过，已拉取 ${imageModelOptions.value.length} 个模型，请选择。`);
  } finally {
    testingImageProvider.value = false;
  }
}

function syncSelectionIndexes() {
  if (draft.characters.length === 0) {
    draft.characters = [createCharacter()];
  }
  if (!draft.openings?.length) {
    draft.openings = [createOpening(0)];
  }
  if (selectedCharacterIndex.value !== null) {
    selectedCharacterIndex.value = Math.min(selectedCharacterIndex.value, draft.characters.length - 1);
    selectedCharacterIndex.value = Math.max(0, selectedCharacterIndex.value);
    const selectedCharacter = draft.characters[selectedCharacterIndex.value];
    if (selectedCharacter && isBlankCharacter(selectedCharacter)) {
      const fallbackIndex = draft.characters.findIndex((item) => !isBlankCharacter(item));
      if (fallbackIndex >= 0) {
        selectedCharacterIndex.value = fallbackIndex;
      }
    }
  }
  if (selectedOpeningIndex.value !== null) {
    selectedOpeningIndex.value = Math.min(selectedOpeningIndex.value, draft.openings.length - 1);
    selectedOpeningIndex.value = Math.max(0, selectedOpeningIndex.value);
    const selectedOpening = draft.openings[selectedOpeningIndex.value];
    if (selectedOpening && isBlankOpening(selectedOpening)) {
      const fallbackIndex = draft.openings.findIndex((item) => !isBlankOpening(item));
      if (fallbackIndex >= 0) {
        selectedOpeningIndex.value = fallbackIndex;
      }
    }
  }
  if (selectedWorldEntryIndex.value !== null) {
    selectedWorldEntryIndex.value = Math.min(
      selectedWorldEntryIndex.value,
      Math.max(0, draft.worldBook.entries.length - 1),
    );
    selectedWorldEntryIndex.value = Math.max(0, selectedWorldEntryIndex.value);
  }
  if (selectedTimelineNodeId.value && !draft.timeline.nodes.some((item) => item.id === selectedTimelineNodeId.value)) {
    selectedTimelineNodeId.value = draft.timeline.nodes[0]?.id ?? null;
  }
}

function syncStoryGenerationStateFromDraft() {
  const state = ensureStoryGenerationState(draft);
  if (!state) {
    currentSegmentIndex.value = 0;
    batchGenerationState.currentSegment = 0;
    batchGenerationState.totalSegments = storySegments.value.length;
    updateWorkflowState();
    return;
  }
  storySegmentationMode.value = state.segmentationMode;
  currentSegmentIndex.value = Math.min(state.currentSegmentIndex, Math.max(0, storySegments.value.length - 1));
  batchGenerationState.currentSegment = state.currentSegmentIndex;
  batchGenerationState.totalSegments = Math.max(storySegments.value.length, state.totalSegments);
  updateWorkflowState();
}

function applyDraftPayload(payload: CharacterDraft) {
  autosave.beginHydration();
  const normalizedCharacters = (Array.isArray(payload.characters) ? payload.characters : [])
    .map((item) => ({
      ...createCharacter(),
      ...item,
      id: item.id || createId(),
      triggerKeywords: Array.isArray(item.triggerKeywords) ? item.triggerKeywords.filter(Boolean) : [],
      advanced: {
        ...createAdvanced(),
        ...(item.advanced ?? {}),
      },
      isUserRole: Boolean(item.isUserRole),
    }));
  if (normalizedCharacters.length === 0) {
    normalizedCharacters.push(createCharacter());
  }
  const firstUserRoleIndex = normalizedCharacters.findIndex((item) => item.isUserRole);
  if (firstUserRoleIndex >= 0) {
    normalizedCharacters.forEach((character, index) => {
      character.isUserRole = index === firstUserRoleIndex;
    });
  }
  const normalized = {
    ...payload,
    openings: ensureOpenings(payload),
    characters: normalizedCharacters,
    timeline: ensureTimeline(payload),
    storyGenerationState: ensureStoryGenerationState(payload),
    workflowState: ensureWorkflowState(payload),
    worldBook: {
      entries: (payload.worldBook?.entries ?? []).filter((entry) => entry.title !== '剧情推进'),
    },
  };
  Object.assign(draft, normalized);
  draft.sourceType = inferSourceType(draft);
  clearTimelineOrganizeProposal();
  syncSelectionIndexes();
  syncStoryGenerationStateFromDraft();
  syncWorkflowStateFromDraft();
  void nextTick(() => autosave.endHydration());
}

async function openDraft(draftId: string) {
  const result = await apiRequest<CharacterDraft>(`/drafts/${encodeURIComponent(draftId)}`, draftScopedInit());
  if (!result.success || !result.data) {
    setStatus(`打开草稿失败: ${result.message}`);
    return;
  }
  storySegments.value = [];
  latestSegmentReport.value = null;
  pendingSegmentReview.value = null;
  applyDraftPayload(result.data);
  selectedTimelineNodeId.value = result.data.timeline?.nodes?.[0]?.id ?? null;
  setStatus(`已打开草稿 ${result.data.card.name || result.data.id}`);
}

async function saveDraft(saveAs = false, source: 'manual' | 'autosave' = 'manual') {
  if (clearingData.value) {
    return;
  }
  if (source === 'autosave') {
    autosaveSaving.value = true;
    setStatus('自动保存中...', 'autosave');
  }
  const requestSeq = ++saveRequestSeq;
  updateWorkflowState();
  draft.updatedAt = nowIso();
  const request = clonePlain(draft);
  request.opening = request.openings?.[0] ?? createOpening(0);
  try {
    const result = await apiRequest<CharacterDraft>('/drafts', {
      ...draftScopedInit({
        method: 'POST',
        body: JSON.stringify({ draft: request, saveAs }),
      }),
    });
    if (requestSeq < ignoreSaveBeforeSeq || clearingData.value) {
      return;
    }
    if (!result.success || !result.data) {
      setStatus(`保存草稿失败: ${result.message}`, source === 'autosave' ? 'autosave' : 'general');
      return;
    }
    applyDraftPayload(result.data);
    autosave.markSaved();
    await refreshDraftList();
    if (source === 'autosave') {
      setStatus('草稿已自动保存', 'autosave');
      return;
    }
    setStatus(saveAs ? '草稿已另存' : '草稿已保存');
  } finally {
    if (source === 'autosave') {
      autosaveSaving.value = false;
    }
  }
}

async function clearAllStoredData() {
  const confirmed = window.confirm('确认清空当前浏览器用户的草稿吗？此操作无法恢复。');
  if (!confirmed) return;
  clearingData.value = true;
  autosaveSaving.value = false;
  ignoreSaveBeforeSeq = saveRequestSeq + 1;
  autosaveEnabled.value = false;
  autosave.cancel();
  setStatus('正在清空当前用户草稿...');
  const result = await apiRequest<{ removedItems: number }>('/drafts/clear', {
    ...draftScopedInit({
      method: 'POST',
    }),
  });
  if (!result.success || !result.data) {
    clearingData.value = false;
    autosaveEnabled.value = true;
    autosaveStatus.value = '自动保存待机';
    setStatus(`清空失败: ${result.message}`);
    return;
  }
  applyDraftPayload(createDraft());
  resetSegmentProgressState();
  await refreshDraftList();
  Object.assign(settings, buildDefaultSettings());
  window.localStorage.removeItem(SETTINGS_STORAGE_KEY);
  clearLegacySettingsCookie();
  previewSeed.value = Date.now();
  selectedCharacterIndex.value = 0;
  selectedOpeningIndex.value = 0;
  selectedWorldEntryIndex.value = 0;
  selectedTimelineNodeId.value = null;
  window.setTimeout(() => {
    clearingData.value = false;
    autosaveEnabled.value = true;
    autosaveStatus.value = '自动保存待机';
    autosave.markSaved();
  }, 0);
  setStatus(`已清空当前用户草稿（删除 ${result.data.removedItems} 项）`);
}

function queueAutosave() {
  if (clearingData.value || !autosaveEnabled.value) return;
  autosave.queue();
}

async function runFieldAI(
  field: string,
  mode: GenerateFieldRequest['mode'],
  currentValue: string,
  apply: (value: string) => void,
) {
  if (!ensureApiConfigured('text')) {
    return;
  }
  aiBusyField.value = field;
  setStatus(`正在为 ${field} 生成内容...`);
  try {
    const generated = await requestAIField(field, mode, currentValue);
    if (generated === null) {
      return;
    }
    apply(generated);
    setStatus(`${field} 已更新`);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    setStatus(`AI 生成失败: ${detail}`);
  } finally {
    aiBusyField.value = '';
  }
}

async function requestAIField(field: string, mode: GenerateFieldRequest['mode'], userInput: string): Promise<string | null> {
    const result = await apiRequest<{ field: string; result: string; promptPreview: string }>('/ai/field', {
      method: 'POST',
      timeoutMs: providerTimeoutMs('text'),
      body: JSON.stringify({
        field,
        mode,
      userInput,
      draft: clonePlain(draft),
      settings: clonePlain(settings),
    }),
  });
  if (!result.success || !result.data) {
    setStatus(`AI 生成失败: ${result.message}`);
    return null;
  }
  return result.data.result;
}

function updateStoryGenerationState(
  total: number,
  current: number,
  mode: 'chapter' | 'hard_buffer',
) {
  const normalizedTotal = Math.max(0, total);
  const normalizedCurrent = Math.max(0, Math.min(current, total));
  draft.storyGenerationState = {
    totalSegments: normalizedTotal,
    currentSegmentIndex: normalizedCurrent,
    segmentationMode: mode,
  };
  batchGenerationState.totalSegments = normalizedTotal;
  batchGenerationState.currentSegment = normalizedCurrent;
  updateWorkflowState();
}

function resetSegmentProgressState() {
  draft.storyGenerationState = undefined;
  storySegments.value = [];
  currentSegmentIndex.value = 0;
  latestSegmentReport.value = null;
  pendingSegmentReview.value = null;
  resetBatchState(0, 0);
  updateWorkflowState();
}

function segmentTextByInfo(segment: SegmentInfo): string {
  const text = cardGenerateInput.value;
  const start = Math.max(0, segment.start);
  const end = Math.max(start, segment.end);
  return text.slice(start, end);
}

function chooseSegment(index: number) {
  if (index < 0 || index >= storySegments.value.length) {
    return;
  }
  currentSegmentIndex.value = index;
  batchGenerationState.currentSegment = index;
  updateWorkflowState();
}

async function previewStorySegments() {
  if (!cardGenerateInput.value.trim()) {
    setStatus('请先输入长篇小说全文，再生成分段预览。');
    return;
  }
  const normalizedMaxChars = Math.max(500, Math.floor(Number(maxCharsPerSegment.value) || 20000));
  settings.storySegmentation.maxCharsPerSegment = normalizedMaxChars;
  segmentPreviewBusy.value = true;
  latestSegmentReport.value = null;
  setStatus('正在生成分段预览...');
  try {
    const result = await apiRequest<StorySegmentsPreviewResponse>('/ai/story-segments/preview', {
      method: 'POST',
      body: JSON.stringify({
        storyText: cardGenerateInput.value,
        maxCharsPerSegment: normalizedMaxChars,
        chapterRegex: settings.storySegmentation.chapterRegex,
        settings: clonePlain(settings),
      }),
    });
    if (!result.success || !result.data) {
      setStatus(`分段预览失败: ${result.message}`);
      return;
    }
    storySegments.value = result.data.segments ?? [];
    storySegmentationMode.value = result.data.segmentationMode;
    settings.storySegmentation.chapterRegex = result.data.chapterRegex || settings.storySegmentation.chapterRegex;
    settings.storySegmentation.maxCharsPerSegment = result.data.maxCharsPerSegment;
    const restoredIndex = Math.min(
      segmentGenerationState.value.currentSegmentIndex,
      Math.max(0, storySegments.value.length - 1),
    );
    currentSegmentIndex.value = restoredIndex;
    updateStoryGenerationState(storySegments.value.length, segmentGenerationState.value.currentSegmentIndex, result.data.segmentationMode);
    resetBatchState(storySegments.value.length, restoredIndex);
    pendingSegmentReview.value = null;
    wizardStep.value = 'segments';
    setStatus(
      `分段预览完成：共 ${storySegments.value.length} 段，切分策略 ${result.data.segmentationMode === 'chapter' ? '章节优先' : '硬切分'}。`,
    );
  } finally {
    segmentPreviewBusy.value = false;
  }
}

async function generateStorySegment(index: number, options?: { deferApply?: boolean }): Promise<boolean> {
  if (!ensureApiConfigured('text')) return false;
  if (!storySegments.value.length) {
    setStatus('请先生成分段预览。');
    return false;
  }
  const segment = storySegments.value[index];
  if (!segment) {
    setStatus('当前段不存在，请重新生成分段预览。');
    return false;
  }
  const segmentText = segmentTextByInfo(segment);
  if (!segmentText.trim()) {
    setStatus('当前段文本为空，请检查原文后重试。');
    return false;
  }
  segmentGenerateBusy.value = true;
  batchGenerationState.currentSegment = index;
  updateWorkflowState();
  setStatus(`正在增量生成第 ${index + 1} 段...`);
  try {
    const result = await apiRequest<GenerateCardFromStorySegmentResponse>('/ai/card-from-story-segment', {
      method: 'POST',
      timeoutMs: providerTimeoutMs('text'),
      body: JSON.stringify({
        draft: clonePlain(draft),
        segmentText,
        segmentIndex: index,
        totalSegments: storySegments.value.length,
        settings: clonePlain(settings),
      }),
    });
    if (!result.success || !result.data) {
      setStatus(`分段增量生成失败: ${result.message}`);
      return false;
    }
    latestSegmentReport.value = result.data.segmentReport;
    const deferApply = Boolean(options?.deferApply);
    if (deferApply) {
      pendingSegmentReview.value = {
        segmentIndex: index,
        draft: clonePlain(result.data.draft),
        report: result.data.segmentReport,
        changeSet: result.data.changeSet ?? null,
      };
      wizardStep.value = 'review';
      pauseBatchState();
      updateWorkflowState();
      setStatus(`第 ${index + 1} 段已生成，等待审阅（可应用或跳过）。`);
      return true;
    }
    pendingSegmentReview.value = null;
    applyDraftPayload(result.data.draft);
    const state = ensureStoryGenerationState(result.data.draft) ?? createStoryGenerationState();
    batchGenerationState.currentSegment = state.currentSegmentIndex;
    updateWorkflowState();
    currentSegmentIndex.value = Math.min(state.currentSegmentIndex, Math.max(0, storySegments.value.length - 1));
    setStatus(
      `第 ${index + 1} 段增量完成：新增角色 ${result.data.segmentReport.newCharactersCount}，新增地点 ${result.data.segmentReport.newLocationsCount}。`,
    );
    return true;
  } finally {
    segmentGenerateBusy.value = false;
  }
}

async function generateCurrentSegment() {
  if (!storySegments.value.length) {
    setStatus('请先生成分段预览。');
    return;
  }
  await generateStorySegment(currentSegmentIndex.value, { deferApply: editorMode.value === 'wizard' });
}

async function generateNextSegment() {
  if (!storySegments.value.length) {
    setStatus('请先生成分段预览。');
    return;
  }
  if (allSegmentsCompleted.value) {
    setStatus('所有分段已生成完成。');
    return;
  }
  const nextIndex = Math.min(segmentGenerationState.value.currentSegmentIndex, storySegments.value.length - 1);
  currentSegmentIndex.value = nextIndex;
  await generateStorySegment(nextIndex, { deferApply: editorMode.value === 'wizard' });
}

function applyPendingSegmentReview() {
  const pending = pendingSegmentReview.value;
  if (!pending) {
    setStatus('当前没有可应用的审阅结果。');
    return;
  }
  latestSegmentReport.value = pending.report;
  applyDraftPayload(pending.draft);
  pendingSegmentReview.value = null;
  wizardStep.value = 'segments';
  setStatus(`已应用第 ${pending.segmentIndex + 1} 段的合并结果。`);
}

function skipPendingSegmentReview() {
  const pending = pendingSegmentReview.value;
  if (!pending) {
    setStatus('当前没有可跳过的审阅结果。');
    return;
  }
  const state = ensureStoryGenerationState(pending.draft) ?? createStoryGenerationState();
  updateStoryGenerationState(
    storySegments.value.length,
    state.currentSegmentIndex,
    state.segmentationMode,
  );
  currentSegmentIndex.value = Math.min(state.currentSegmentIndex, Math.max(0, storySegments.value.length - 1));
  latestSegmentReport.value = pending.report;
  pendingSegmentReview.value = null;
  wizardStep.value = 'segments';
  setStatus(`已跳过第 ${pending.segmentIndex + 1} 段合并，并推进到下一段。`);
}

async function runBatchGenerationLoop() {
  if (batchLoopRunning.value) return;
  batchLoopRunning.value = true;
  try {
    while (batchGenerationState.status === 'running') {
      if (!storySegments.value.length) {
        completeBatchState();
        updateWorkflowState();
        return;
      }
      if (pendingSegmentReview.value) {
        return;
      }
      const nextIndex = Math.min(segmentGenerationState.value.currentSegmentIndex, storySegments.value.length - 1);
      if (nextIndex < 0 || allSegmentsCompleted.value) {
        completeBatchState();
        updateWorkflowState();
        setStatus('批量生成完成，已到最后一段。');
        return;
      }
      currentSegmentIndex.value = nextIndex;
      const ok = await generateStorySegment(nextIndex, { deferApply: reviewEachSegment.value });
      if (!ok) {
        failBatchState(nextIndex, generalStatus.value || '分段生成失败');
        updateWorkflowState();
        return;
      }
      if (reviewEachSegment.value) {
        pauseBatchState();
        updateWorkflowState();
        return;
      }
      const generatedState = ensureStoryGenerationState(draft) ?? createStoryGenerationState();
      batchGenerationState.currentSegment = generatedState.currentSegmentIndex;
      if (generatedState.currentSegmentIndex >= storySegments.value.length) {
        completeBatchState();
        updateWorkflowState();
        setStatus('批量生成完成，已到最后一段。');
        return;
      }
    }
  } finally {
    batchLoopRunning.value = false;
  }
}

function startBatchGeneration() {
  if (!storySegments.value.length) {
    setStatus('请先生成分段预览。');
    return;
  }
  if (allSegmentsCompleted.value) {
    setStatus('所有分段已生成完成。');
    return;
  }
  const nextIndex = Math.min(segmentGenerationState.value.currentSegmentIndex, storySegments.value.length - 1);
  startBatchState(storySegments.value.length, nextIndex);
  wizardStep.value = 'segments';
  updateWorkflowState();
  void runBatchGenerationLoop();
}

function pauseBatchGeneration() {
  pauseBatchState();
  updateWorkflowState();
  setStatus('已暂停批量生成。');
}

function resumeBatchGeneration() {
  if (pendingSegmentReview.value) {
    setStatus('请先处理当前段的变更审阅卡。');
    return;
  }
  resumeBatchState();
  updateWorkflowState();
  setStatus('继续批量生成...');
  void runBatchGenerationLoop();
}

function retryBatchGeneration() {
  const failedIndex = batchGenerationState.failedSegmentIndex ?? currentSegmentIndex.value;
  currentSegmentIndex.value = Math.max(0, failedIndex);
  startBatchState(storySegments.value.length, currentSegmentIndex.value);
  updateWorkflowState();
  setStatus(`重试第 ${currentSegmentIndex.value + 1} 段...`);
  void runBatchGenerationLoop();
}

async function generateCardFromInput() {
  if (!ensureApiConfigured('text')) return;
  if (!cardGenerateInput.value.trim()) {
    setStatus('请先输入短篇小说全文，再执行一键生成。');
    return;
  }
  cardGenerateBusy.value = true;
  setStatus('正在根据短篇小说解析角色、地点与剧情时间线...');
  try {
    const result = await apiRequest<GenerateCardFromStoryResponse>('/ai/card-from-story', {
      method: 'POST',
      timeoutMs: providerTimeoutMs('text'),
      body: JSON.stringify({
        draft: clonePlain(draft),
        storyText: cardGenerateInput.value,
        settings: clonePlain(settings),
      }),
    });
    if (!result.success || !result.data) {
      setStatus(`角色卡一键生成失败: ${result.message}`);
      return;
    }
    applyDraftPayload(result.data.draft);
    selectedCharacterIndex.value = 0;
    selectedOpeningIndex.value = 0;
    selectedWorldEntryIndex.value = 0;
    selectedTimelineNodeId.value = result.data.draft.timeline?.nodes?.[0]?.id ?? null;
    const characterCount = result.data.draft.characters.length;
    const locationCount = result.data.draft.worldBook.entries.length;
    resetSegmentProgressState();
    wizardStep.value = 'export';
    setStatus(`角色卡一键生成完成：角色 ${characterCount} 个，地点条目 ${locationCount} 条。`);
  } finally {
    cardGenerateBusy.value = false;
  }
}

function addCharacter() {
  draft.characters.push(createCharacter());
  selectedCharacterIndex.value = draft.characters.length - 1;
}

function removeCharacter(index: number) {
  if (draft.characters.length === 1) {
    setStatus('至少保留一个角色。');
    return;
  }
  draft.characters.splice(index, 1);
  if (selectedCharacterIndex.value === null) return;
  if (selectedCharacterIndex.value === index) {
    selectedCharacterIndex.value = Math.min(index, draft.characters.length - 1);
    return;
  }
  if (selectedCharacterIndex.value > index) {
    selectedCharacterIndex.value -= 1;
  }
}

function selectCharacter(index: number) {
  selectedCharacterIndex.value = selectedCharacterIndex.value === index ? null : index;
}

function addOpening() {
  draft.openings.push(createOpening(draft.openings.length));
  selectedOpeningIndex.value = draft.openings.length - 1;
}

function removeOpening(index: number) {
  if (draft.openings.length === 1) {
    setStatus('至少保留一个首屏信息。');
    return;
  }
  draft.openings.splice(index, 1);
  draft.openings.forEach((item, idx) => {
    if (!item.title.trim() || item.title.startsWith('首屏 ')) {
      item.title = `首屏 ${idx + 1}`;
    }
  });
  if (selectedOpeningIndex.value === null) return;
  if (selectedOpeningIndex.value === index) {
    selectedOpeningIndex.value = Math.min(index, draft.openings.length - 1);
    return;
  }
  if (selectedOpeningIndex.value > index) {
    selectedOpeningIndex.value -= 1;
  }
}

function selectOpening(index: number) {
  selectedOpeningIndex.value = selectedOpeningIndex.value === index ? null : index;
}

function addWorldEntry() {
  draft.worldBook.entries.push(createWorldEntry());
  selectedWorldEntryIndex.value = draft.worldBook.entries.length - 1;
}

function removeWorldEntry(index: number) {
  draft.worldBook.entries.splice(index, 1);
  if (selectedWorldEntryIndex.value === null) return;
  if (draft.worldBook.entries.length === 0) {
    selectedWorldEntryIndex.value = null;
    return;
  }
  if (selectedWorldEntryIndex.value === index) {
    selectedWorldEntryIndex.value = Math.min(index, draft.worldBook.entries.length - 1);
    return;
  }
  if (selectedWorldEntryIndex.value > index) {
    selectedWorldEntryIndex.value -= 1;
  }
}

function selectWorldEntry(index: number) {
  selectedWorldEntryIndex.value = selectedWorldEntryIndex.value === index ? null : index;
}

function setCharacterKeywords(index: number, text: string) {
  draft.characters[index].triggerKeywords = splitKeywords(text);
}

function setCharacterUserRole(index: number, enabled: boolean) {
  if (!enabled) {
    draft.characters[index].isUserRole = false;
    return;
  }
  draft.characters.forEach((character, currentIndex) => {
    character.isUserRole = currentIndex === index;
  });
}

function setWorldEntryKeywords(index: number, text: string) {
  draft.worldBook.entries[index].keywords = splitKeywords(text);
}

function setTimelineKeywords(text: string) {
  draft.timeline.keywords = splitKeywords(text);
  clearTimelineOrganizeProposal();
}

function addTimelineRootNode() {
  const node = createTimelineNode('');
  draft.timeline.nodes.push(node);
  selectedTimelineNodeId.value = node.id;
  clearTimelineOrganizeProposal();
}

function addTimelineChildNode(parentId: string) {
  const node = createTimelineNode(parentId);
  draft.timeline.nodes.push(node);
  selectedTimelineNodeId.value = node.id;
  clearTimelineOrganizeProposal();
}

function selectTimelineNode(nodeId: string) {
  selectedTimelineNodeId.value = selectedTimelineNodeId.value === nodeId ? null : nodeId;
}

function collectTimelineDescendantIds(nodeId: string, nodesSnapshot: TimelineNode[] = draft.timeline.nodes): Set<string> {
  const result = new Set<string>();
  const stack = [nodeId];
  while (stack.length > 0) {
    const current = stack.pop() as string;
    for (const node of nodesSnapshot) {
      if (node.parentId !== current || result.has(node.id)) continue;
      result.add(node.id);
      stack.push(node.id);
    }
  }
  return result;
}

function timelineParentCandidates(nodeId: string): TimelineNode[] {
  const excluded = collectTimelineDescendantIds(nodeId);
  excluded.add(nodeId);
  return draft.timeline.nodes.filter((node) => !excluded.has(node.id));
}

function collectTimelineSubtreeNodes(nodeId: string, nodesSnapshot: TimelineNode[] = draft.timeline.nodes): TimelineNode[] {
  const ids = collectTimelineDescendantIds(nodeId, nodesSnapshot);
  ids.add(nodeId);
  return nodesSnapshot.filter((node) => ids.has(node.id));
}

function subtreeLastIndex(nodeId: string, nodesSnapshot: TimelineNode[]): number {
  const ids = collectTimelineDescendantIds(nodeId, nodesSnapshot);
  ids.add(nodeId);
  let last = -1;
  nodesSnapshot.forEach((node, index) => {
    if (ids.has(node.id)) {
      last = index;
    }
  });
  return last;
}

function moveTimelineSubtree(nodeId: string, parentId: string): boolean {
  const source = draft.timeline.nodes.find((item) => item.id === nodeId);
  if (!source) return false;
  const nextParent = parentId.trim();
  const candidates = timelineParentCandidates(nodeId);
  if (nextParent && !candidates.some((item) => item.id === nextParent)) {
    return false;
  }
  const snapshot = [...draft.timeline.nodes];
  const moving = collectTimelineSubtreeNodes(nodeId, snapshot);
  if (moving.length === 0) {
    return false;
  }
  const movingIds = new Set(moving.map((item) => item.id));
  const remaining = snapshot.filter((item) => !movingIds.has(item.id));
  moving[0].parentId = nextParent;

  let insertAt = remaining.length;
  if (nextParent) {
    const lastIndex = subtreeLastIndex(nextParent, remaining);
    insertAt = lastIndex >= 0 ? lastIndex + 1 : remaining.length;
  }
  draft.timeline.nodes = [
    ...remaining.slice(0, insertAt),
    ...moving,
    ...remaining.slice(insertAt),
  ];
  clearTimelineOrganizeProposal();
  return true;
}

function setTimelineNodeParent(nodeId: string, parentId: string) {
  const applied = moveTimelineSubtree(nodeId, parentId);
  if (!applied && !parentId.trim()) {
    const node = draft.timeline.nodes.find((item) => item.id === nodeId);
    if (node) {
      node.parentId = '';
      clearTimelineOrganizeProposal();
    }
  }
}

function moveTimelineNode(nodeId: string, direction: -1 | 1) {
  const index = draft.timeline.nodes.findIndex((item) => item.id === nodeId);
  if (index < 0) return;
  const subtree = collectTimelineSubtreeNodes(nodeId);
  const subtreeIds = new Set(subtree.map((item) => item.id));
  const remaining = draft.timeline.nodes.filter((item) => !subtreeIds.has(item.id));
  const currentStart = draft.timeline.nodes.findIndex((item) => item.id === subtree[0]?.id);
  const targetIndexRaw = currentStart + direction;
  let insertAt = Math.max(0, Math.min(remaining.length, targetIndexRaw));
  if (direction > 0 && insertAt < remaining.length) {
    insertAt += 1;
  }
  draft.timeline.nodes = [
    ...remaining.slice(0, insertAt),
    ...subtree,
    ...remaining.slice(insertAt),
  ];
  clearTimelineOrganizeProposal();
}

function onTimelineDragStart(nodeId: string, event: DragEvent) {
  timelineDragNodeId.value = nodeId;
  timelineDragOverNodeId.value = null;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', nodeId);
  }
}

function onTimelineDragEnd() {
  timelineDragNodeId.value = null;
  timelineDragOverNodeId.value = null;
}

function onTimelineDragOverNode(nodeId: string, event: DragEvent) {
  if (!timelineDragNodeId.value || timelineDragNodeId.value === nodeId) return;
  event.preventDefault();
  timelineDragOverNodeId.value = nodeId;
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'move';
  }
}

function onTimelineDropOnNode(nodeId: string, event: DragEvent) {
  event.preventDefault();
  const dragNodeId = timelineDragNodeId.value;
  onTimelineDragEnd();
  if (!dragNodeId || dragNodeId === nodeId) return;
  moveTimelineSubtree(dragNodeId, nodeId);
}

function onTimelineDropToRoot(event: DragEvent) {
  event.preventDefault();
  const dragNodeId = timelineDragNodeId.value;
  onTimelineDragEnd();
  if (!dragNodeId) return;
  moveTimelineSubtree(dragNodeId, '');
}

function cancelTimelineDragHover() {
  timelineDragOverNodeId.value = null;
}

function removeTimelineNode(nodeId: string) {
  const removeIds = collectTimelineDescendantIds(nodeId);
  removeIds.add(nodeId);
  draft.timeline.nodes = draft.timeline.nodes.filter((node) => !removeIds.has(node.id));
  clearTimelineOrganizeProposal();
  if (selectedTimelineNodeId.value && removeIds.has(selectedTimelineNodeId.value)) {
    selectedTimelineNodeId.value = draft.timeline.nodes[0]?.id ?? null;
  }
}

async function organizeTimelineWithAI() {
  if (!ensureApiConfigured('text')) return;
  if (!draft.timeline.nodes.length) {
    setStatus('当前没有时间线节点可整理。');
    return;
  }
  timelineOrganizeBusy.value = true;
  setStatus('正在生成时间线整理提案...');
  try {
    const result = await apiRequest<OrganizeTimelineResponse>('/ai/timeline/organize', {
      method: 'POST',
      timeoutMs: providerTimeoutMs('text'),
      body: JSON.stringify({
        draft: clonePlain(draft),
        settings: clonePlain(settings),
      }),
    });
    if (!result.success || !result.data) {
      setStatus(`时间线整理失败: ${result.message}`);
      return;
    }
    timelineOrganizeProposal.value = normalizeTimelineInfo(result.data.proposalTimeline);
    const summary = result.data.summary;
    setStatus(
      `已生成整理提案：节点 ${summary.nodeCountBefore} -> ${summary.nodeCountAfter}，根节点 ${summary.rootCountAfter}。`,
    );
  } finally {
    timelineOrganizeBusy.value = false;
  }
}

function applyTimelineOrganizeProposal() {
  if (!timelineOrganizeProposal.value) return;
  draft.timeline = normalizeTimelineInfo(clonePlain(timelineOrganizeProposal.value));
  selectedTimelineNodeId.value = draft.timeline.nodes[0]?.id ?? null;
  timelineOrganizeProposal.value = null;
  setStatus('已应用时间线整理提案。');
}

function discardTimelineOrganizeProposal() {
  if (!timelineOrganizeProposal.value) return;
  timelineOrganizeProposal.value = null;
  setStatus('已忽略时间线整理提案。');
}

function summarizeText(text: string, max = 40): string {
  const compact = text.trim().replace(/\s+/g, ' ');
  if (!compact) return '（空）';
  return compact.length > max ? `${compact.slice(0, max)}...` : compact;
}

async function pickImage() {
  imageInputRef.value?.click();
}

async function importCard() {
  setStatus('请选择要导入的角色卡文件...');
  importInputRef.value?.click();
}

function pickStoryText() {
  setStatus('请选择短篇小说 txt 文本...');
  storyTextInputRef.value?.click();
}

async function performImport(file: File) {
  try {
    const formData = new FormData();
    formData.append('file', file);
    setStatus(`正在导入角色卡: ${file.name}`);
    const result = await apiRequest<ImportCharacterCardResponse>('/card/import-file', {
      method: 'POST',
      body: formData,
    });
    if (!result.success || !result.data) {
      setStatus(`导入失败: ${result.message}`);
      return;
    }
    applyDraftPayload({ ...result.data.draft, sourceType: result.data.sourceType });
    selectedCharacterIndex.value = 0;
    selectedOpeningIndex.value = 0;
    selectedWorldEntryIndex.value = 0;
    selectedTimelineNodeId.value = result.data.draft.timeline?.nodes?.[0]?.id ?? null;
    previewSeed.value = Date.now();
    await refreshDraftList();
    setStatus(`导入成功：条目 ${result.data.draft.worldBook.entries.length} 条，图片路径已更新`);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    setStatus(`导入异常: ${detail}`);
  }
}

async function onImportInputChange(event: Event) {
  try {
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];
    target.value = '';
    if (!file) {
      setStatus('未选择导入文件');
      return;
    }

    await performImport(file);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    setStatus(`读取文件失败: ${detail}`);
  }
}

async function onImageInputChange(event: Event) {
  try {
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];
    target.value = '';
    if (!file) {
      setStatus('未选择图片');
      return;
    }
    const formData = new FormData();
    formData.append('file', file);
    setStatus(`正在上传图片: ${file.name}`);
    const result = await apiRequest<UploadImageResponse>('/files/upload-image', {
      method: 'POST',
      body: formData,
    });
    if (!result.success || !result.data) {
      setStatus(`图片上传失败: ${result.message}`);
      return;
    }
    draft.illustration.originalImagePath = result.data.path;
    draft.illustration.generatedImagePath = '';
    draft.illustration.exportImagePath = result.data.path;
    previewSeed.value = Date.now();
    setStatus('已加载角色图片');
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    setStatus(`图片上传异常: ${detail}`);
  }
}

async function onStoryTextInputChange(event: Event) {
  try {
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];
    target.value = '';
    if (!file) {
      setStatus('未选择 txt 文件');
      return;
    }
    if (!file.name.toLowerCase().endsWith('.txt')) {
      setStatus('仅支持上传 .txt 文件');
      return;
    }
    const rawText = await file.text();
    const content = rawText.replace(/^\uFEFF/, '');
    if (!content.trim()) {
      setStatus('txt 文件内容为空');
      return;
    }
    cardGenerateInput.value = content;
    resetSegmentProgressState();
    setStatus(`已加载小说文本: ${file.name}`);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    setStatus(`读取 txt 文件失败: ${detail}`);
  }
}

async function generateImagePrompt() {
  imagePromptBusy.value = true;
  setStatus('正在生成绘图提示词...');
  try {
    const result = await apiRequest<{ prompt: string; negativePrompt: string }>('/ai/image-prompt', {
      method: 'POST',
      body: JSON.stringify({ draft: clonePlain(draft) }),
    });
    if (!result.success || !result.data) {
      setStatus(`提示词生成失败: ${result.message}`);
      return;
    }
    draft.illustration.promptSnapshot = result.data.prompt;
    draft.illustration.negativePrompt = result.data.negativePrompt;
    setStatus('绘图提示词已生成');
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    setStatus(`提示词生成失败: ${detail}`);
  } finally {
    imagePromptBusy.value = false;
  }
}

async function generateImage() {
  if (!ensureApiConfigured('image')) {
    return;
  }
  imageGenerateBusy.value = true;
  setStatus('正在生成角色图...');
  try {
    const result = await apiRequest<{ imagePath: string; prompt: string }>('/ai/image', {
      method: 'POST',
      timeoutMs: providerTimeoutMs('image'),
      body: JSON.stringify({
        draft: clonePlain(draft),
        prompt: draft.illustration.promptSnapshot,
        negativePrompt: draft.illustration.negativePrompt,
        settings: clonePlain(settings),
      }),
    });
    if (!result.success || !result.data) {
      setStatus(`角色图生成失败: ${result.message}`);
      return;
    }
    draft.illustration.generatedImagePath = result.data.imagePath;
    draft.illustration.exportImagePath = result.data.imagePath;
    previewSeed.value = Date.now();
    setStatus('角色图已生成');
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    setStatus(`角色图生成失败: ${detail}`);
  } finally {
    imageGenerateBusy.value = false;
  }
}

async function exportCard() {
  setStatus('正在导出 TavernAI PNG...');
  const result = await apiRequest<ExportCharacterCardResponse>('/card/export-download', {
    method: 'POST',
    body: JSON.stringify({
      draft: { ...clonePlain(draft), opening: clonePlain(primaryOpening.value) },
      imagePath: draft.illustration.exportImagePath,
    }),
  });
  if (!result.success || !result.data) {
    setStatus(`导出失败: ${result.message}`);
    return;
  }
  downloadBase64Png(result.data.filename, result.data.imageBase64);
  setStatus(`导出成功: ${result.data.filename}`);
}

function resetDraft() {
  applyDraftPayload(createDraft());
  resetSegmentProgressState();
  selectedCharacterIndex.value = 0;
  selectedOpeningIndex.value = 0;
  selectedWorldEntryIndex.value = 0;
  selectedTimelineNodeId.value = null;
  setStatus('已新建草稿');
}

watch(
  draft,
  () => {
    if (autosave.hydrating.value) return;
    if (!autosaveEnabled.value) return;
    queueAutosave();
  },
  { deep: true },
);

onMounted(async () => {
  autosave.beginHydration();
  syncWorkflowStateFromDraft();
  await loadSettings();
  await loadBuiltinPrefixPrompts();
  if (!isProviderConfigured(settings.textProvider) || !isProviderConfigured(settings.imageProvider)) {
    const message = '未配置 API：请到“设置”里分别填写文本与图像的 Base URL、API Key 和模型。';
    setStatus(message);
    window.alert(message);
  }
  appDataDir.value = 'Web 模式（草稿保存在后端应用目录，设置保存在浏览器 localStorage）';
  await refreshDraftList();
  if (drafts.value[0]) {
    await openDraft(drafts.value[0].id);
  } else {
    await saveDraft(false);
  }
  autosave.markSaved();
  autosave.endHydration(320);
});
</script>

<template>
  <div class="app-shell">
    <input
      ref="imageInputRef"
      class="hidden-input"
      type="file"
      accept=".png,.jpg,.jpeg,.webp"
      @change="onImageInputChange"
    />
    <input
      ref="importInputRef"
      class="hidden-input"
      type="file"
      accept=".png,.json"
      @change="onImportInputChange"
    />
    <input
      ref="storyTextInputRef"
      class="hidden-input"
      type="file"
      accept=".txt,text/plain"
      @change="onStoryTextInputChange"
    />
    <aside class="sidebar">
      <div>
        <p class="eyebrow">RolePlayCard</p>
        <h1>短篇小说角色卡生成器</h1>
        <p class="muted">从故事文本自动生成可游玩角色卡（角色、地点、时间线）</p>
      </div>

      <div class="nav-group">
        <button
          :class="['nav-button', { active: activeView === 'editor' }]"
          @click="activeView = 'editor'"
        >
          编辑器
        </button>
        <button
          :class="['nav-button', { active: activeView === 'settings' }]"
          @click="activeView = 'settings'"
        >
          设置
        </button>
      </div>

      <div class="draft-panel">
        <div class="panel-header">
          <h2>草稿</h2>
          <button @click="resetDraft">新建</button>
        </div>
        <div class="inline-actions">
          <button @click="saveDraft(false)">保存</button>
          <button @click="saveDraft(true)">另存为</button>
          <button @click="importCard">导入卡</button>
          <button @click="clearAllStoredData">清空存储</button>
        </div>
        <div class="draft-list">
          <button
            v-for="item in drafts"
            :key="item.id"
            class="draft-item"
            @click="openDraft(item.id)"
          >
            <strong>{{ item.name || '未命名角色卡' }}</strong>
            <span>{{ new Date(item.updatedAt).toLocaleString() }}</span>
          </button>
        </div>
      </div>
    </aside>

    <main class="main-panel">
      <header class="topbar">
        <div>
          <p class="status">
            <span v-if="aiBusy" class="loading-spinner loading-inline" />
            <strong>其他操作:</strong>
            {{ generalStatus }}
          </p>
          <p class="status">
            <span v-if="autosaveSaving" class="loading-spinner loading-inline" />
            <strong>自动保存:</strong>
            {{ autosaveStatus }}
          </p>
          <p class="muted">数据目录: {{ appDataDir }}</p>
        </div>
        <div class="topbar-actions">
          <button :class="['nav-button', { active: editorMode === 'wizard' }]" @click="editorMode = 'wizard'">向导模式</button>
          <button :class="['nav-button', { active: editorMode === 'expert' }]" @click="editorMode = 'expert'">专家模式</button>
          <button @click="saveDraft(false)">立即保存</button>
          <button @click="exportCard" :disabled="!exportReady">导出 TavernAI PNG</button>
        </div>
      </header>

      <WizardFlow
        v-if="activeView === 'editor' && editorMode === 'wizard'"
        :story-text="cardGenerateInput"
        :wizard-step="wizardStep"
        :max-chars-per-segment="maxCharsPerSegment"
        :chapter-regex="settings.storySegmentation.chapterRegex"
        :story-segments="storySegments"
        :current-segment-index="currentSegmentIndex"
        :completed-segments="completedSegments"
        :total-segments="totalSegments"
        :all-segments-completed="allSegmentsCompleted"
        :story-segmentation-mode="storySegmentationMode"
        :latest-segment-report="latestSegmentReport"
        :pending-change-set="pendingSegmentReview?.changeSet ?? null"
        :pending-segment-index="pendingSegmentReview?.segmentIndex ?? null"
        :segment-preview-busy="segmentPreviewBusy"
        :segment-generate-busy="segmentGenerateBusy"
        :batch-state="batchGenerationState"
        :review-each-segment="reviewEachSegment"
        @update-story-text="cardGenerateInput = $event"
        @update-max-chars="maxCharsPerSegment = $event"
        @update-chapter-regex="settings.storySegmentation.chapterRegex = $event"
        @update-wizard-step="wizardStep = $event"
        @upload-story-text="pickStoryText"
        @preview-segments="previewStorySegments"
        @generate-current="generateCurrentSegment"
        @generate-next="generateNextSegment"
        @choose-segment="chooseSegment"
        @start-batch="startBatchGeneration"
        @pause-batch="pauseBatchGeneration"
        @resume-batch="resumeBatchGeneration"
        @retry-batch="retryBatchGeneration"
        @apply-segment-review="applyPendingSegmentReview"
        @skip-segment-review="skipPendingSegmentReview"
        @update-review-each-segment="reviewEachSegment = $event"
      />

      <ExpertEditor v-else-if="activeView === 'editor'">
        <div class="editor-column">
          <section class="card">
            <div class="panel-header">
              <h2>小说生成</h2>
            </div>
            <p class="muted">短篇可一键生成；长篇推荐使用“分段预览 -> 当前段生成 -> 下一段增量更新”的手动流程。</p>
            <div class="field">
              <label for="cardGenerateInput">小说全文</label>
              <textarea
                id="cardGenerateInput"
                v-model="cardGenerateInput"
                rows="7"
                placeholder="粘贴小说全文，或上传 txt。建议包含角色、地点、关键事件与时间推进。"
              />
              <div class="inline-actions">
                <button @click="pickStoryText" :disabled="cardGenerateBusy || segmentPreviewBusy || segmentGenerateBusy">上传小说 txt</button>
                <button @click="generateCardFromInput" :disabled="cardGenerateBusy">
                  <span v-if="cardGenerateBusy" class="loading-spinner loading-inline" />
                  {{ cardGenerateBusy ? '生成中...' : '根据短篇小说生成角色卡' }}
                </button>
              </div>
            </div>
            <div class="nested-card">
              <div class="panel-header">
                <h3>长篇分段增量模式（默认手动）</h3>
              </div>
              <div class="field-grid">
                <label>硬切分上限（字符）</label>
                <input v-model.number="maxCharsPerSegment" type="number" min="500" step="100" />
                <label>切分策略</label>
                <input :value="storySegmentationMode === 'chapter' ? 'chapter（章节优先）' : 'hard_buffer（硬切分）'" readonly />
                <label>当前进度</label>
                <input :value="`已完成 ${completedSegments} / ${totalSegments}`" readonly />
              </div>
              <div class="field">
                <label>章节识别正则（可改）</label>
                <textarea
                  v-model="settings.storySegmentation.chapterRegex"
                  rows="4"
                  placeholder="默认已包含：第X章/卷/回/篇/集/部/幕、卷X、幕X、Chapter X、Volume X"
                />
              </div>
              <div class="inline-actions">
                <button @click="previewStorySegments" :disabled="segmentPreviewBusy || segmentGenerateBusy">
                  <span v-if="segmentPreviewBusy" class="loading-spinner loading-inline" />
                  {{ segmentPreviewBusy ? '预览生成中...' : '生成分段预览' }}
                </button>
                <button
                  @click="generateCurrentSegment"
                  :disabled="segmentPreviewBusy || segmentGenerateBusy || storySegments.length === 0"
                >
                  <span v-if="segmentGenerateBusy" class="loading-spinner loading-inline" />
                  {{ segmentGenerateBusy ? '生成中...' : '生成当前段' }}
                </button>
                <button
                  @click="generateNextSegment"
                  :disabled="segmentPreviewBusy || segmentGenerateBusy || storySegments.length === 0 || allSegmentsCompleted"
                >
                  {{ allSegmentsCompleted ? '已完成全部分段' : '下一段增量更新' }}
                </button>
              </div>
              <p v-if="latestSegmentReport" class="muted">
                最近一段报告：新增角色 {{ latestSegmentReport.newCharactersCount }}，新增地点 {{ latestSegmentReport.newLocationsCount }}，新增节点 {{ latestSegmentReport.newTimelineNodesCount }}，冲突忽略 {{ latestSegmentReport.ignoredConflictCount }}。
              </p>
              <p v-if="storySegments.length === 0" class="muted">尚未生成分段预览。</p>
              <div v-else class="overview-list">
                <button
                  v-for="segment in storySegments"
                  :key="segment.segmentIndex"
                  :class="['overview-item', { active: currentSegmentIndex === segment.segmentIndex }]"
                  @click="chooseSegment(segment.segmentIndex)"
                >
                  <strong>第 {{ segment.segmentIndex + 1 }} 段 · {{ segment.title }}</strong>
                  <span class="overview-meta">字符 {{ segment.charCount }} · 区间 {{ segment.start }}-{{ segment.end }}</span>
                  <span class="overview-meta">{{ segment.preview }}</span>
                </button>
              </div>
            </div>
          </section>

          <section class="card">
            <div class="panel-header">
              <h2>角色卡信息</h2>
            </div>
            <div class="field">
              <label for="cardName">角色卡名称</label>
              <input
                id="cardName"
                v-model="draft.card.name"
                placeholder="例如：霓虹城调查局"
              />
            </div>
            <div class="field">
              <label for="cardDescription">角色卡描述</label>
              <textarea
                id="cardDescription"
                v-model="draft.card.description"
                rows="4"
                placeholder="描述这个角色卡的世界观、玩法和风格"
              />
              <div class="inline-actions">
                <button
                  @click="runFieldAI('card.description', 'generate', draft.card.description, (v) => (draft.card.description = v))"
                  :disabled="aiBusyField === 'card.description'"
                >
                  <span v-if="aiBusyField === 'card.description'" class="loading-spinner loading-inline" />
                  {{ aiBusyField === 'card.description' ? '生成中...' : 'AI 生成' }}
                </button>
                <button
                  @click="runFieldAI('card.description', 'rewrite', draft.card.description, (v) => (draft.card.description = v))"
                  :disabled="aiBusyField === 'card.description'"
                >
                  <span v-if="aiBusyField === 'card.description'" class="loading-spinner loading-inline" />
                  {{ aiBusyField === 'card.description' ? '改写中...' : 'AI 改写' }}
                </button>
              </div>
            </div>
          </section>

          <section class="card">
            <div class="panel-header">
              <h2>角色列表</h2>
              <button v-if="!isExternalCard" @click="addCharacter">添加角色</button>
            </div>
            <p v-if="isExternalCard" class="muted">
              外部卡模式：角色栏已收起，角色相关条目统一在“世界书条目”中编辑。
            </p>
            <template v-else>
              <div class="overview-list">
                <div
                  v-for="(character, index) in draft.characters"
                  :key="character.id"
                  class="overview-row"
                >
                  <button
                    :class="['overview-item', { active: selectedCharacterIndex === index }]"
                    @click="selectCharacter(index)"
                  >
                    <strong>{{ character.name || `角色 ${index + 1}` }}</strong>
                    <span class="overview-meta">
                      {{ character.isUserRole ? '玩家扮演' : 'NPC' }} ·
                      {{ character.triggerMode === 'always' ? '蓝灯' : '绿灯' }} · 关键词 {{ character.triggerKeywords.length }} 个
                    </span>
                  </button>
                  <div v-if="selectedCharacterIndex === index" class="nested-card">
                    <div class="panel-header">
                      <h3>角色详情</h3>
                      <button @click="removeCharacter(index)">删除当前角色</button>
                    </div>
                    <div class="field-grid">
                      <label>启用</label>
                      <input v-model="character.enabled" type="checkbox" class="checkbox" />
                      <label>蓝灯/绿灯</label>
                      <select v-model="character.triggerMode">
                        <option value="always">蓝灯（永久触发）</option>
                        <option value="keyword">绿灯（关键词触发）</option>
                      </select>
                      <label>玩家扮演（导出替换为 user）</label>
                      <input
                        :checked="character.isUserRole"
                        type="checkbox"
                        class="checkbox"
                        @change="setCharacterUserRole(index, ($event.target as HTMLInputElement).checked)"
                      />
                    </div>

                    <div class="field">
                      <label>姓名</label>
                      <input v-model="character.name" />
                    </div>

                    <div class="field">
                      <label>触发关键词（逗号分隔）</label>
                      <input
                        :value="character.triggerKeywords.join(', ')"
                        @input="setCharacterKeywords(index, ($event.target as HTMLInputElement).value)"
                      />
                      <div class="inline-actions">
                        <button
                          @click="runFieldAI(`characters.${index}.triggerKeywords`, 'generate', character.triggerKeywords.join(', '), (v) => setCharacterKeywords(index, v))"
                          :disabled="aiBusyField === `characters.${index}.triggerKeywords`"
                        >
                          <span v-if="aiBusyField === `characters.${index}.triggerKeywords`" class="loading-spinner loading-inline" />
                          {{ aiBusyField === `characters.${index}.triggerKeywords` ? '生成中...' : 'AI 生成' }}
                        </button>
                        <button
                          @click="runFieldAI(`characters.${index}.triggerKeywords`, 'rewrite', character.triggerKeywords.join(', '), (v) => setCharacterKeywords(index, v))"
                          :disabled="aiBusyField === `characters.${index}.triggerKeywords`"
                        >
                          <span v-if="aiBusyField === `characters.${index}.triggerKeywords`" class="loading-spinner loading-inline" />
                          {{ aiBusyField === `characters.${index}.triggerKeywords` ? '改写中...' : 'AI 改写' }}
                        </button>
                      </div>
                    </div>

                    <div class="field">
                      <label>年龄</label>
                      <input v-model="character.age" />
                    </div>

                    <div class="field">
                      <label>说话方式</label>
                      <input v-model="character.speakingStyle" />
                      <div class="inline-actions">
                        <button
                          @click="runFieldAI(`characters.${index}.speakingStyle`, 'generate', character.speakingStyle, (v) => (character.speakingStyle = v))"
                          :disabled="aiBusyField === `characters.${index}.speakingStyle`"
                        >
                          <span v-if="aiBusyField === `characters.${index}.speakingStyle`" class="loading-spinner loading-inline" />
                          {{ aiBusyField === `characters.${index}.speakingStyle` ? '生成中...' : 'AI 生成' }}
                        </button>
                        <button
                          @click="runFieldAI(`characters.${index}.speakingStyle`, 'rewrite', character.speakingStyle, (v) => (character.speakingStyle = v))"
                          :disabled="aiBusyField === `characters.${index}.speakingStyle`"
                        >
                          <span v-if="aiBusyField === `characters.${index}.speakingStyle`" class="loading-spinner loading-inline" />
                          {{ aiBusyField === `characters.${index}.speakingStyle` ? '改写中...' : 'AI 改写' }}
                        </button>
                      </div>
                    </div>

                    <div class="field">
                      <label>外貌</label>
                      <textarea v-model="character.appearance" rows="3" />
                      <div class="inline-actions">
                        <button
                          @click="runFieldAI(`characters.${index}.appearance`, 'generate', character.appearance, (v) => (character.appearance = v))"
                          :disabled="aiBusyField === `characters.${index}.appearance`"
                        >
                          <span v-if="aiBusyField === `characters.${index}.appearance`" class="loading-spinner loading-inline" />
                          {{ aiBusyField === `characters.${index}.appearance` ? '生成中...' : 'AI 生成' }}
                        </button>
                        <button
                          @click="runFieldAI(`characters.${index}.appearance`, 'rewrite', character.appearance, (v) => (character.appearance = v))"
                          :disabled="aiBusyField === `characters.${index}.appearance`"
                        >
                          <span v-if="aiBusyField === `characters.${index}.appearance`" class="loading-spinner loading-inline" />
                          {{ aiBusyField === `characters.${index}.appearance` ? '改写中...' : 'AI 改写' }}
                        </button>
                      </div>
                    </div>
                    <div class="field">
                      <label>性格</label>
                      <textarea v-model="character.personality" rows="3" />
                      <div class="inline-actions">
                        <button
                          @click="runFieldAI(`characters.${index}.personality`, 'generate', character.personality, (v) => (character.personality = v))"
                          :disabled="aiBusyField === `characters.${index}.personality`"
                        >
                          <span v-if="aiBusyField === `characters.${index}.personality`" class="loading-spinner loading-inline" />
                          {{ aiBusyField === `characters.${index}.personality` ? '生成中...' : 'AI 生成' }}
                        </button>
                        <button
                          @click="runFieldAI(`characters.${index}.personality`, 'rewrite', character.personality, (v) => (character.personality = v))"
                          :disabled="aiBusyField === `characters.${index}.personality`"
                        >
                          <span v-if="aiBusyField === `characters.${index}.personality`" class="loading-spinner loading-inline" />
                          {{ aiBusyField === `characters.${index}.personality` ? '改写中...' : 'AI 改写' }}
                        </button>
                      </div>
                    </div>
                    <div class="field">
                      <label>说话示例</label>
                      <textarea v-model="character.speakingExample" rows="3" />
                      <div class="inline-actions">
                        <button
                          @click="runFieldAI(`characters.${index}.speakingExample`, 'generate', character.speakingExample, (v) => (character.speakingExample = v))"
                          :disabled="aiBusyField === `characters.${index}.speakingExample`"
                        >
                          <span v-if="aiBusyField === `characters.${index}.speakingExample`" class="loading-spinner loading-inline" />
                          {{ aiBusyField === `characters.${index}.speakingExample` ? '生成中...' : 'AI 生成' }}
                        </button>
                        <button
                          @click="runFieldAI(`characters.${index}.speakingExample`, 'rewrite', character.speakingExample, (v) => (character.speakingExample = v))"
                          :disabled="aiBusyField === `characters.${index}.speakingExample`"
                        >
                          <span v-if="aiBusyField === `characters.${index}.speakingExample`" class="loading-spinner loading-inline" />
                          {{ aiBusyField === `characters.${index}.speakingExample` ? '改写中...' : 'AI 改写' }}
                        </button>
                      </div>
                    </div>
                    <div class="field">
                      <label>背景</label>
                      <textarea v-model="character.background" rows="3" />
                      <div class="inline-actions">
                        <button
                          @click="runFieldAI(`characters.${index}.background`, 'generate', character.background, (v) => (character.background = v))"
                          :disabled="aiBusyField === `characters.${index}.background`"
                        >
                          <span v-if="aiBusyField === `characters.${index}.background`" class="loading-spinner loading-inline" />
                          {{ aiBusyField === `characters.${index}.background` ? '生成中...' : 'AI 生成' }}
                        </button>
                        <button
                          @click="runFieldAI(`characters.${index}.background`, 'rewrite', character.background, (v) => (character.background = v))"
                          :disabled="aiBusyField === `characters.${index}.background`"
                        >
                          <span v-if="aiBusyField === `characters.${index}.background`" class="loading-spinner loading-inline" />
                          {{ aiBusyField === `characters.${index}.background` ? '改写中...' : 'AI 改写' }}
                        </button>
                      </div>
                    </div>

                    <div class="field-grid">
                      <label>触发顺序</label>
                      <input v-model.number="character.advanced.insertionOrder" type="number" />
                      <label>触发概率 (%)</label>
                      <input v-model.number="character.advanced.triggerProbability" type="number" min="0" max="100" />
                      <label>插入位置</label>
                      <select v-model="character.advanced.insertionPosition">
                        <option value="after_char">角色定义之后</option>
                        <option value="before_char">角色定义之前</option>
                        <option value="before_example">示例消息之前</option>
                        <option value="after_example">示例消息之后</option>
                        <option value="top_an">A/N 顶部</option>
                        <option value="bottom_an">A/N 底部</option>
                        <option value="at_depth">@Depth</option>
                      </select>
                      <template v-if="character.advanced.insertionPosition === 'at_depth'">
                        <label>深度 (Depth)</label>
                        <input v-model.number="character.advanced.depth" type="number" min="0" />
                      </template>
                    </div>
                  </div>
                </div>
              </div>
            </template>
          </section>

          <section class="card">
            <div class="panel-header">
              <h2>首屏信息</h2>
              <button @click="addOpening">添加首屏</button>
            </div>
            <div class="overview-list">
              <div
                v-for="(opening, index) in draft.openings"
                :key="opening.id"
                class="overview-row"
              >
                <button
                  :class="['overview-item', { active: selectedOpeningIndex === index }]"
                  @click="selectOpening(index)"
                >
                  <strong>{{ opening.title || `首屏 ${index + 1}` }}</strong>
                  <span class="overview-meta">{{ summarizeText(opening.firstMessage, 64) }}</span>
                </button>
                <div v-if="selectedOpeningIndex === index" class="nested-card">
                  <div class="panel-header">
                    <h3>首屏详情</h3>
                    <button @click="removeOpening(index)">删除当前首屏</button>
                  </div>
                  <div class="field">
                    <label>标题</label>
                    <input v-model="opening.title" placeholder="例如：雨夜初遇" />
                  </div>
                  <div class="field">
                    <label>开场白</label>
                    <textarea v-model="opening.greeting" rows="2" />
                  </div>
                  <div class="field">
                    <label>场景</label>
                    <textarea v-model="opening.scenario" rows="3" />
                  </div>
                  <div class="field">
                    <label>示例对话</label>
                    <textarea v-model="opening.exampleDialogue" rows="4" />
                  </div>
                  <div class="field">
                    <label>首条消息</label>
                    <textarea v-model="opening.firstMessage" rows="5" />
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section class="card">
            <div class="panel-header">
              <h2>时间线（剧情推进）</h2>
              <div class="inline-actions">
                <button @click="addTimelineRootNode">添加根节点</button>
                <button @click="organizeTimelineWithAI" :disabled="timelineOrganizeBusy || draft.timeline.nodes.length === 0">
                  <span v-if="timelineOrganizeBusy" class="loading-spinner loading-inline" />
                  {{ timelineOrganizeBusy ? '整理中...' : '自动整理时间线（LLM）' }}
                </button>
              </div>
            </div>
            <p class="muted">时间线独立编辑，导出时会自动转换为世界书“剧情推进”条目。支持拖拽重挂父子结构。</p>
            <p class="muted">
              基准：{{ draft.timeline.timeBaseline || 'T0=当前主线时刻' }}
              · 格式：{{ draft.timeline.timeFormat || 'T±<offset> | 时间描述' }}
              · 根节点 {{ timelineRootCount }} 个
            </p>
            <div class="field-grid">
              <label>条目标题</label>
              <input v-model="draft.timeline.title" />
              <label>启用（蓝灯）</label>
              <input v-model="draft.timeline.enabled" type="checkbox" class="checkbox" />
              <label>关键词（逗号分隔）</label>
              <input
                :value="draft.timeline.keywords.join(', ')"
                @input="setTimelineKeywords(($event.target as HTMLInputElement).value)"
              />
            </div>
            <div v-if="timelineOrganizeProposal" class="nested-card">
              <div class="panel-header">
                <h3>时间线整理提案（可选）</h3>
              </div>
              <p class="muted">
                提案基准：{{ timelineOrganizeProposal.timeBaseline }} · 格式：{{ timelineOrganizeProposal.timeFormat }}
                · 节点 {{ timelineOrganizeProposal.nodes.length }} 个 · 根节点 {{ timelineProposalRootCount }} 个
              </p>
              <div class="inline-actions">
                <button class="primary" @click="applyTimelineOrganizeProposal">采用提案</button>
                <button @click="discardTimelineOrganizeProposal">保留当前时间线</button>
              </div>
              <div class="overview-list timeline-proposal-list">
                <div
                  v-for="(row, rowIndex) in timelineProposalRows"
                  :key="`proposal-${row.node.id}`"
                  class="overview-item timeline-item"
                  :style="{ paddingLeft: `${0.85 + row.depth * 1.1}rem` }"
                >
                  <strong>{{ row.node.title || `提案节点 ${rowIndex + 1}` }}</strong>
                  <span class="overview-meta">
                    {{
                      row.depth === 0
                        ? '根节点'
                        : `子节点 · 父节点: ${row.node.parentId || '（无）'}`
                    }}
                    · {{ row.node.timePoint || '未设时间点' }} · {{ summarizeText(row.node.event, 30) }}
                  </span>
                </div>
              </div>
            </div>
            <div v-if="timelineRows.length > 0" class="timeline-graph-wrap">
              <svg
                class="timeline-graph"
                :viewBox="`0 0 ${timelineGraph.width} ${timelineGraph.height}`"
                xmlns="http://www.w3.org/2000/svg"
                role="img"
                aria-label="时间线结构图"
              >
                <g>
                  <path
                    v-for="edge in timelineGraph.edges"
                    :key="edge.id"
                    :d="edge.d"
                    class="timeline-graph-edge"
                  />
                </g>
                <g>
                  <g
                    v-for="node in timelineGraph.nodes"
                    :key="node.id"
                    :class="['timeline-graph-node', { active: selectedTimelineNodeId === node.id }]"
                    @click="selectTimelineNode(node.id)"
                  >
                    <rect
                      :x="node.x"
                      :y="node.y"
                      :width="timelineGraphNodeWidth"
                      :height="timelineGraphNodeHeight"
                      rx="10"
                      ry="10"
                    />
                    <text :x="node.x + 10" :y="node.y + 24" class="timeline-graph-title">
                      {{ node.title }}
                    </text>
                    <text :x="node.x + 10" :y="node.y + 41" class="timeline-graph-subtitle">
                      {{ node.subtitle }}
                    </text>
                  </g>
                </g>
              </svg>
            </div>
            <div
              v-if="timelineRows.length > 0"
              class="timeline-drop-root"
              @dragover.prevent
              @drop="onTimelineDropToRoot($event)"
            >
              拖到这里可设为根节点（parentId 为空）
            </div>
            <div class="overview-list">
              <div
                v-for="(row, rowIndex) in timelineRows"
                :key="row.node.id"
                class="overview-row"
              >
                <button
                  :class="[
                    'overview-item',
                    'timeline-item',
                    {
                      active: selectedTimelineNodeId === row.node.id,
                      'timeline-item-drag-over': timelineDragOverNodeId === row.node.id,
                      'timeline-item-dragging': timelineDragNodeId === row.node.id,
                    },
                  ]"
                  :style="{ paddingLeft: `${0.85 + row.depth * 1.1}rem` }"
                  draggable="true"
                  @dragstart="onTimelineDragStart(row.node.id, $event)"
                  @dragend="onTimelineDragEnd"
                  @dragover="onTimelineDragOverNode(row.node.id, $event)"
                  @dragleave="cancelTimelineDragHover"
                  @drop="onTimelineDropOnNode(row.node.id, $event)"
                  @click="selectTimelineNode(row.node.id)"
                >
                  <span class="timeline-drag-handle" title="拖到其他节点可挂为其子节点">⋮⋮</span>
                  <strong>{{ row.node.title || `节点 ${rowIndex + 1}` }}</strong>
                  <span class="overview-meta">
                    {{
                      row.depth === 0
                        ? '根节点'
                        : `子节点 · 父节点: ${timelineParentTitle(row.node)}`
                    }}
                    · {{ row.node.timePoint || '未设时间点' }} · {{ summarizeText(row.node.event, 36) }}
                  </span>
                </button>
                <div v-if="selectedTimelineNodeId === row.node.id" class="nested-card">
                  <div class="panel-header">
                    <h3>时间线节点</h3>
                    <button @click="removeTimelineNode(row.node.id)">删除节点</button>
                  </div>
                  <div class="inline-actions">
                    <button @click="addTimelineChildNode(row.node.id)">添加子节点</button>
                    <span class="muted">拖动本节点到其他节点上，可调整父子从属；子节点会随主节点一起移动。</span>
                  </div>
                  <div class="field">
                    <label>节点标题</label>
                    <input v-model="row.node.title" />
                  </div>
                  <div class="field-grid">
                    <label>时间点/阶段</label>
                    <input v-model="row.node.timePoint" />
                    <label>父节点（变更会连同子树一起移动）</label>
                    <select
                      :value="row.node.parentId"
                      @change="setTimelineNodeParent(row.node.id, ($event.target as HTMLSelectElement).value)"
                    >
                      <option value="">（无）</option>
                      <option
                        v-for="candidate in timelineParentCandidates(row.node.id)"
                        :key="candidate.id"
                        :value="candidate.id"
                      >
                        {{ candidate.title || candidate.timePoint || candidate.id }}
                      </option>
                    </select>
                  </div>
                  <div class="field">
                    <label>触发条件</label>
                    <textarea v-model="row.node.trigger" rows="2" />
                  </div>
                  <div class="field">
                    <label>关键事件</label>
                    <textarea v-model="row.node.event" rows="3" />
                  </div>
                  <div class="field-grid">
                    <label>角色目标</label>
                    <textarea v-model="row.node.objective" rows="2" />
                    <label>主要冲突</label>
                    <textarea v-model="row.node.conflict" rows="2" />
                  </div>
                  <div class="field-grid">
                    <label>节点结果</label>
                    <textarea v-model="row.node.outcome" rows="2" />
                    <label>下一节点线索</label>
                    <textarea v-model="row.node.nextHook" rows="2" />
                  </div>
                </div>
              </div>
            </div>
            <p v-if="timelineRows.length === 0" class="muted">暂无时间线节点，点击“添加根节点”。</p>
          </section>

          <section class="card">
            <div class="panel-header">
              <h2>世界书条目</h2>
              <button @click="addWorldEntry">添加条目</button>
            </div>
            <div class="overview-list">
              <div
                v-for="(entry, index) in draft.worldBook.entries"
                :key="entry.id"
                class="overview-row"
              >
                <button
                  :class="['overview-item', { active: selectedWorldEntryIndex === index }]"
                  @click="selectWorldEntry(index)"
                >
                  <strong>{{ entry.title || `条目 ${index + 1}` }}</strong>
                  <span class="overview-meta">
                    {{ entry.triggerMode === 'always' ? '蓝灯' : '绿灯' }} · 关键词 {{ entry.keywords.length }} 个
                  </span>
                </button>
                <div v-if="selectedWorldEntryIndex === index" class="nested-card">
                  <div class="panel-header">
                    <h3>条目详情</h3>
                    <button @click="removeWorldEntry(index)">删除当前条目</button>
                  </div>
                  <div class="field-grid">
                    <label>启用</label>
                    <input v-model="entry.enabled" type="checkbox" class="checkbox" />
                    <label>蓝灯/绿灯</label>
                    <select v-model="entry.triggerMode">
                      <option value="always">蓝灯（永久触发）</option>
                      <option value="keyword">绿灯（关键词触发）</option>
                    </select>
                  </div>
                  <div class="field">
                    <label>条目标题</label>
                    <input v-model="entry.title" />
                  </div>
                  <div class="field">
                    <label>关键词（逗号分隔）</label>
                    <input
                      :value="entry.keywords.join(', ')"
                      @input="setWorldEntryKeywords(index, ($event.target as HTMLInputElement).value)"
                    />
                  </div>
                  <div class="field">
                    <label>条目内容</label>
                    <textarea v-model="entry.content" rows="4" />
                  </div>
                  <div class="field-grid">
                    <label>触发顺序</label>
                    <input v-model.number="entry.advanced.insertionOrder" type="number" />
                    <label>触发概率 (%)</label>
                    <input v-model.number="entry.advanced.triggerProbability" type="number" min="0" max="100" />
                    <label>插入位置</label>
                    <select v-model="entry.advanced.insertionPosition">
                      <option value="after_char">角色定义之后</option>
                      <option value="before_char">角色定义之前</option>
                      <option value="before_example">示例消息之前</option>
                      <option value="after_example">示例消息之后</option>
                      <option value="top_an">A/N 顶部</option>
                      <option value="bottom_an">A/N 底部</option>
                      <option value="at_depth">@Depth</option>
                    </select>
                    <template v-if="entry.advanced.insertionPosition === 'at_depth'">
                      <label>深度 (Depth)</label>
                      <input v-model.number="entry.advanced.depth" type="number" min="0" />
                    </template>
                  </div>
                </div>
              </div>
            </div>
            <p v-if="draft.worldBook.entries.length === 0" class="muted">暂无条目，点击“添加条目”。</p>
          </section>
        </div>

        <div class="side-column">
          <section class="card">
            <div class="panel-header">
              <h2>角色插图</h2>
            </div>
            <div class="image-box">
              <img
                v-if="imagePreview"
                :src="imagePreview"
                alt="角色图预览"
              />
              <p v-else>尚未选择角色图</p>
            </div>
            <div class="stack-actions">
              <button @click="pickImage">上传图片</button>
              <button @click="generateImagePrompt" :disabled="imagePromptBusy || imageGenerateBusy">
                <span v-if="imagePromptBusy" class="loading-spinner loading-inline" />
                {{ imagePromptBusy ? '提示词生成中...' : '生成绘图提示词' }}
              </button>
              <button @click="generateImage" :disabled="imagePromptBusy || imageGenerateBusy">
                <span v-if="imageGenerateBusy" class="loading-spinner loading-inline" />
                {{ imageGenerateBusy ? '生成图片中...' : '使用 AI 文生图' }}
              </button>
            </div>
            <div class="field">
              <label>画风偏好</label>
              <textarea
                v-model="draft.illustration.stylePrompt"
                rows="3"
                placeholder="例如：anime portrait, warm tone, cinematic lighting"
              />
            </div>
            <div class="field">
              <label>提示词</label>
              <textarea v-model="draft.illustration.promptSnapshot" rows="4" />
            </div>
            <div class="field">
              <label>负面提示词</label>
              <textarea v-model="draft.illustration.negativePrompt" rows="3" />
            </div>
          </section>

          <section class="card">
            <div class="panel-header">
              <h2>导出检查</h2>
            </div>
            <p v-if="validationReport.length === 0">导出条件满足</p>
            <ul v-else class="warning-list">
              <li v-for="issue in validationReport" :key="issue">{{ issue }}</li>
            </ul>
            <button
              class="primary"
              @click="exportCard"
              :disabled="!exportReady"
            >
              导出 TavernAI PNG
            </button>
          </section>

        </div>
      </ExpertEditor>

      <SettingsPanel
        v-else
        :settings="settings"
        :text-model-options="textModelOptions"
        :image-model-options="imageModelOptions"
        :builtin-prefix-prompt-dir="builtinPrefixPromptDir"
        :builtin-prefix-prompt-options="builtinPrefixPromptOptions"
        :loading-builtin-prefix-prompts="loadingBuiltinPrefixPrompts"
        :testing-text-provider="testingTextProvider"
        :testing-image-provider="testingImageProvider"
        @refresh-builtin-prefix-prompts="loadBuiltinPrefixPrompts"
        @save-text-settings="saveTextSettings"
        @test-text-settings="testTextSettings"
        @save-image-settings="saveImageSettings"
        @test-image-settings="testImageSettings"
        @save-segmentation-settings="saveSegmentationSettings"
      />
    </main>
  </div>
</template>

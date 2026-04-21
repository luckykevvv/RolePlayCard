<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import type {
  AppSettings,
  CharacterDefinition,
  CharacterDraft,
  DraftSummary,
  ExportCharacterCardResponse,
  GenerateFieldRequest,
  ProviderConfig,
  TaskResult,
  UploadImageResponse,
  WorldBookAdvancedOptions,
  WorldBookEntry,
} from '../../shared/types.js';

const API_BASE = '/api';
const SETTINGS_COOKIE_KEY = 'roleplaycard_settings';

function buildDefaultSettings(): AppSettings {
  return {
    textProvider: createProviderConfig(),
    imageProvider: createProviderConfig(),
    exportDirectory: '',
    recentDirectory: '',
  };
}

function clonePlain<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function mergeSettings(defaults: AppSettings, incoming: Partial<AppSettings> | null): AppSettings {
  if (!incoming) return defaults;
  return {
    ...defaults,
    ...incoming,
    textProvider: { ...defaults.textProvider, ...(incoming.textProvider ?? {}) },
    imageProvider: { ...defaults.imageProvider, ...(incoming.imageProvider ?? {}) },
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

function loadSettingsFromCookie(): AppSettings {
  const defaults = buildDefaultSettings();
  const raw = getCookieValue(SETTINGS_COOKIE_KEY);
  if (!raw) return defaults;
  try {
    const parsed = JSON.parse(raw) as Partial<AppSettings>;
    return mergeSettings(defaults, parsed);
  } catch {
    return defaults;
  }
}

async function apiRequest<T>(path: string, init?: RequestInit): Promise<TaskResult<T>> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(init?.headers ?? {}),
    },
  });
  let payload: TaskResult<T> | null = null;
  try {
    payload = (await response.json()) as TaskResult<T>;
  } catch {
    payload = null;
  }
  if (payload) return payload;
  return {
    success: false,
    error_code: 'invalid_response',
    message: `HTTP ${response.status}`,
    data: null,
  };
}

function imageSrcFromPath(pathValue: string, seed: number): string {
  if (!pathValue) return '';
  if (pathValue.startsWith('data:') || pathValue.startsWith('blob:') || pathValue.startsWith('http')) {
    return pathValue;
  }
  return `${API_BASE}/files/image?path=${encodeURIComponent(pathValue)}&t=${seed}`;
}

function downloadBase64Png(filename: string, imageBase64: string) {
  const binary = atob(imageBase64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i);
  }
  const blob = new Blob([bytes], { type: 'image/png' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

const nowIso = () => new Date().toISOString();
const splitKeywords = (text: string) =>
  text
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);

const createProviderConfig = (): ProviderConfig => ({
  provider: 'mock',
  baseUrl: 'https://api.openai.com/v1',
  apiKey: '',
  model: '',
  timeoutMs: 45000,
  temperature: 0.8,
  enabled: true,
});

const createAdvanced = (): WorldBookAdvancedOptions => ({
  insertionOrder: 200,
  triggerProbability: 100,
  insertionPosition: 'after_char',
  depth: 4,
});

const createCharacter = (): CharacterDefinition => ({
  id: crypto.randomUUID(),
  enabled: true,
  triggerMode: 'keyword',
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
  id: crypto.randomUUID(),
  enabled: true,
  triggerMode: 'keyword',
  title: '',
  keywords: [],
  content: '',
  advanced: createAdvanced(),
});

const createDraft = (): CharacterDraft => ({
  id: crypto.randomUUID(),
  version: 2,
  createdAt: nowIso(),
  updatedAt: nowIso(),
  card: {
    name: '',
    description: '',
  },
  characters: [createCharacter()],
  opening: {
    greeting: '',
    scenario: '',
    exampleDialogue: '',
    firstMessage: '',
  },
  worldBook: {
    entries: [],
  },
  illustration: {
    originalImagePath: '',
    generatedImagePath: '',
    exportImagePath: '',
    promptSnapshot: '',
    negativePrompt: '',
    stylePrompt: '',
  },
});

const settings = reactive<AppSettings>({
  textProvider: createProviderConfig(),
  imageProvider: createProviderConfig(),
  exportDirectory: '',
  recentDirectory: '',
});

const draft = reactive<CharacterDraft>(createDraft());
const drafts = ref<DraftSummary[]>([]);
const activeView = ref<'editor' | 'settings'>('editor');
const status = ref('准备就绪');
const appDataDir = ref('');
const aiBusyField = ref('');
const importInputRef = ref<HTMLInputElement | null>(null);
const imageInputRef = ref<HTMLInputElement | null>(null);
const previewSeed = ref(Date.now());
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
const exportReady = computed(
  () => Boolean(effectiveCardName.value && draft.opening.firstMessage.trim() && imagePreview.value),
);
const validationReport = computed(() => {
  const items: string[] = [];
  if (!effectiveCardName.value) items.push('缺少角色卡名称（或至少一个角色名称）');
  if (!draft.opening.firstMessage.trim()) items.push('缺少首条消息');
  if (!imagePreview.value) items.push('缺少导出图片');
  return items;
});

let autosaveTimer: number | null = null;

async function refreshDraftList() {
  const result = await apiRequest<DraftSummary[]>('/drafts');
  if (result.success && result.data) {
    drafts.value = result.data;
  }
}

async function loadSettings() {
  Object.assign(settings, loadSettingsFromCookie());
}

async function saveSettings() {
  setCookieValue(SETTINGS_COOKIE_KEY, JSON.stringify(clonePlain(settings)));
  status.value = '设置已保存到浏览器 Cookie';
}

async function testSettings() {
  status.value = '正在测试 Provider 配置...';
  const result = await apiRequest<Array<{ provider: string; ok: boolean; detail: string }>>('/settings/test', {
    method: 'POST',
    body: JSON.stringify({ settings: clonePlain(settings) }),
  });
  if (!result.success || !result.data) {
    status.value = `测试失败: ${result.message}`;
    return;
  }
  status.value = result.data.map((item) => `${item.provider}: ${item.detail}`).join(' | ');
}

async function openDraft(draftId: string) {
  const result = await apiRequest<CharacterDraft>(`/drafts/${encodeURIComponent(draftId)}`);
  if (!result.success || !result.data) {
    status.value = `打开草稿失败: ${result.message}`;
    return;
  }
  Object.assign(draft, result.data);
  status.value = `已打开草稿 ${result.data.card.name || result.data.id}`;
}

async function saveDraft(saveAs = false) {
  draft.updatedAt = nowIso();
  const request = clonePlain(draft);
  const result = await apiRequest<CharacterDraft>('/drafts', {
    method: 'POST',
    body: JSON.stringify({ draft: request, saveAs }),
  });
  if (!result.success || !result.data) {
    status.value = `保存草稿失败: ${result.message}`;
    return;
  }
  Object.assign(draft, result.data);
  await refreshDraftList();
  status.value = saveAs ? '草稿已另存' : '草稿已保存';
}

function queueAutosave() {
  if (autosaveTimer) {
    window.clearTimeout(autosaveTimer);
  }
  autosaveTimer = window.setTimeout(() => {
    void saveDraft(false);
  }, 1200);
}

async function runFieldAI(
  field: string,
  mode: GenerateFieldRequest['mode'],
  currentValue: string,
  apply: (value: string) => void,
) {
  aiBusyField.value = field;
  status.value = `正在为 ${field} 生成内容...`;
  const result = await apiRequest<{ field: string; result: string; promptPreview: string }>('/ai/field', {
    method: 'POST',
    body: JSON.stringify({
      field,
      mode,
      userInput: currentValue,
      draft: clonePlain(draft),
      settings: clonePlain(settings),
    }),
  });
  aiBusyField.value = '';
  if (!result.success || !result.data) {
    status.value = `AI 生成失败: ${result.message}`;
    return;
  }
  apply(result.data.result);
  status.value = `${field} 已更新`;
}

function addCharacter() {
  draft.characters.push(createCharacter());
}

function removeCharacter(index: number) {
  if (draft.characters.length === 1) {
    status.value = '至少保留一个角色。';
    return;
  }
  draft.characters.splice(index, 1);
}

function addWorldEntry() {
  draft.worldBook.entries.push(createWorldEntry());
}

function removeWorldEntry(index: number) {
  draft.worldBook.entries.splice(index, 1);
}

function setCharacterKeywords(index: number, text: string) {
  draft.characters[index].triggerKeywords = splitKeywords(text);
}

function setWorldEntryKeywords(index: number, text: string) {
  draft.worldBook.entries[index].keywords = splitKeywords(text);
}

async function pickImage() {
  imageInputRef.value?.click();
}

async function importCard() {
  status.value = '请选择要导入的角色卡文件...';
  importInputRef.value?.click();
}

async function performImport(file: File) {
  try {
    const formData = new FormData();
    formData.append('file', file);
    status.value = `正在导入角色卡: ${file.name}`;
    const result = await apiRequest<{ draft: CharacterDraft; sourcePath: string }>('/card/import-file', {
      method: 'POST',
      body: formData,
    });
    if (!result.success || !result.data) {
      status.value = `导入失败: ${result.message}`;
      return;
    }
    Object.assign(draft, result.data.draft);
    previewSeed.value = Date.now();
    await refreshDraftList();
    status.value = `导入成功：条目 ${result.data.draft.worldBook.entries.length} 条，图片路径已更新`;
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    status.value = `导入异常: ${detail}`;
  }
}

async function onImportInputChange(event: Event) {
  try {
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];
    target.value = '';
    if (!file) {
      status.value = '未选择导入文件';
      return;
    }

    await performImport(file);
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    status.value = `读取文件失败: ${detail}`;
  }
}

async function onImageInputChange(event: Event) {
  try {
    const target = event.target as HTMLInputElement;
    const file = target.files?.[0];
    target.value = '';
    if (!file) {
      status.value = '未选择图片';
      return;
    }
    const formData = new FormData();
    formData.append('file', file);
    status.value = `正在上传图片: ${file.name}`;
    const result = await apiRequest<UploadImageResponse>('/files/upload-image', {
      method: 'POST',
      body: formData,
    });
    if (!result.success || !result.data) {
      status.value = `图片上传失败: ${result.message}`;
      return;
    }
    draft.illustration.originalImagePath = result.data.path;
    draft.illustration.generatedImagePath = '';
    draft.illustration.exportImagePath = result.data.path;
    previewSeed.value = Date.now();
    status.value = '已加载角色图片';
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    status.value = `图片上传异常: ${detail}`;
  }
}

async function generateImagePrompt() {
  status.value = '正在生成绘图提示词...';
  const result = await apiRequest<{ prompt: string; negativePrompt: string }>('/ai/image-prompt', {
    method: 'POST',
    body: JSON.stringify({ draft: clonePlain(draft) }),
  });
  if (!result.success || !result.data) {
    status.value = `提示词生成失败: ${result.message}`;
    return;
  }
  draft.illustration.promptSnapshot = result.data.prompt;
  draft.illustration.negativePrompt = result.data.negativePrompt;
  status.value = '绘图提示词已生成';
}

async function generateImage() {
  status.value = '正在生成角色图...';
  const result = await apiRequest<{ imagePath: string; prompt: string }>('/ai/image', {
    method: 'POST',
    body: JSON.stringify({
      draft: clonePlain(draft),
      prompt: draft.illustration.promptSnapshot,
      negativePrompt: draft.illustration.negativePrompt,
      settings: clonePlain(settings),
    }),
  });
  if (!result.success || !result.data) {
    status.value = `角色图生成失败: ${result.message}`;
    return;
  }
  draft.illustration.generatedImagePath = result.data.imagePath;
  draft.illustration.exportImagePath = result.data.imagePath;
  previewSeed.value = Date.now();
  status.value = '角色图已生成';
}

async function exportCard() {
  status.value = '正在导出 TavernAI PNG...';
  const result = await apiRequest<ExportCharacterCardResponse>('/card/export-download', {
    method: 'POST',
    body: JSON.stringify({
      draft: clonePlain(draft),
      imagePath: draft.illustration.exportImagePath,
    }),
  });
  if (!result.success || !result.data) {
    status.value = `导出失败: ${result.message}`;
    return;
  }
  downloadBase64Png(result.data.filename, result.data.imageBase64);
  status.value = `导出成功: ${result.data.filename}`;
}

function resetDraft() {
  Object.assign(draft, createDraft());
  status.value = '已新建草稿';
}

watch(
  draft,
  () => {
    queueAutosave();
  },
  { deep: true },
);

onMounted(async () => {
  await loadSettings();
  appDataDir.value = 'Web 模式（设置保存在 Cookie）';
  await refreshDraftList();
  if (drafts.value[0]) {
    await openDraft(drafts.value[0].id);
  } else {
    await saveDraft(false);
  }
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
    <aside class="sidebar">
      <div>
        <p class="eyebrow">RolePlayCard</p>
        <h1>AI 角色卡创建器</h1>
        <p class="muted">Web 版：多角色 + 条目化世界书</p>
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
          <p class="status">{{ status }}</p>
          <p class="muted">数据目录: {{ appDataDir }}</p>
        </div>
        <div class="topbar-actions">
          <button @click="saveDraft(false)">立即保存</button>
          <button @click="exportCard" :disabled="!exportReady">导出 TavernAI PNG</button>
        </div>
      </header>

      <section v-if="activeView === 'editor'" class="content-grid">
        <div class="editor-column">
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
                  AI 生成
                </button>
                <button
                  @click="runFieldAI('card.description', 'rewrite', draft.card.description, (v) => (draft.card.description = v))"
                  :disabled="aiBusyField === 'card.description'"
                >
                  AI 改写
                </button>
              </div>
            </div>
          </section>

          <section class="card">
            <div class="panel-header">
              <h2>角色列表</h2>
              <button @click="addCharacter">添加角色</button>
            </div>
            <div
              v-for="(character, index) in draft.characters"
              :key="character.id"
              class="nested-card"
            >
              <div class="panel-header">
                <h3>角色 {{ index + 1 }}</h3>
                <button @click="removeCharacter(index)">删除</button>
              </div>
              <div class="field-grid">
                <label>启用</label>
                <input v-model="character.enabled" type="checkbox" class="checkbox" />
                <label>蓝灯/绿灯</label>
                <select v-model="character.triggerMode">
                  <option value="always">蓝灯（永久触发）</option>
                  <option value="keyword">绿灯（关键词触发）</option>
                </select>
              </div>

              <div class="field">
                <label>姓名</label>
                <input v-model="character.name" />
                <div class="inline-actions">
                  <button
                    @click="runFieldAI(`characters.${index}.name`, 'generate', character.name, (v) => (character.name = v))"
                    :disabled="aiBusyField === `characters.${index}.name`"
                  >
                    AI 生成
                  </button>
                  <button
                    @click="runFieldAI(`characters.${index}.name`, 'rewrite', character.name, (v) => (character.name = v))"
                    :disabled="aiBusyField === `characters.${index}.name`"
                  >
                    AI 改写
                  </button>
                </div>
              </div>

              <div class="field">
                <label>触发关键词（逗号分隔）</label>
                <input
                  :value="character.triggerKeywords.join(', ')"
                  @input="setCharacterKeywords(index, ($event.target as HTMLInputElement).value)"
                />
              </div>

              <div class="field-grid">
                <label>年龄</label>
                <input v-model="character.age" />
                <label>说话方式</label>
                <input v-model="character.speakingStyle" />
              </div>

              <div class="field">
                <label>外貌</label>
                <textarea v-model="character.appearance" rows="3" />
              </div>
              <div class="field">
                <label>性格</label>
                <textarea v-model="character.personality" rows="3" />
              </div>
              <div class="field">
                <label>说话示例</label>
                <textarea v-model="character.speakingExample" rows="3" />
              </div>
              <div class="field">
                <label>背景</label>
                <textarea v-model="character.background" rows="3" />
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
                <label>深度 (Depth)</label>
                <input v-model.number="character.advanced.depth" type="number" min="0" />
              </div>
            </div>
          </section>

          <section class="card">
            <div class="panel-header">
              <h2>首屏信息</h2>
            </div>
            <div class="field">
              <label>开场白</label>
              <textarea v-model="draft.opening.greeting" rows="2" />
            </div>
            <div class="field">
              <label>场景</label>
              <textarea v-model="draft.opening.scenario" rows="3" />
            </div>
            <div class="field">
              <label>示例对话</label>
              <textarea v-model="draft.opening.exampleDialogue" rows="4" />
            </div>
            <div class="field">
              <label>首条消息</label>
              <textarea v-model="draft.opening.firstMessage" rows="5" />
            </div>
          </section>

          <section class="card">
            <div class="panel-header">
              <h2>世界书条目</h2>
              <button @click="addWorldEntry">添加条目</button>
            </div>
            <div
              v-for="(entry, index) in draft.worldBook.entries"
              :key="entry.id"
              class="nested-card"
            >
              <div class="panel-header">
                <h3>条目 {{ index + 1 }}</h3>
                <button @click="removeWorldEntry(index)">删除</button>
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
                <label>深度 (Depth)</label>
                <input v-model.number="entry.advanced.depth" type="number" min="0" />
              </div>
            </div>
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
              <button @click="generateImagePrompt">生成绘图提示词</button>
              <button @click="generateImage">使用 AI 文生图</button>
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
      </section>

      <section v-else class="settings-layout">
        <section class="card">
          <div class="panel-header">
            <h2>文本 Provider</h2>
          </div>
          <div class="field-grid">
            <label>Provider</label>
            <select v-model="settings.textProvider.provider">
              <option value="mock">mock</option>
              <option value="openai_compatible">openai_compatible</option>
            </select>
            <label>Base URL</label>
            <input v-model="settings.textProvider.baseUrl" />
            <label>Model</label>
            <input v-model="settings.textProvider.model" />
            <label>API Key</label>
            <input v-model="settings.textProvider.apiKey" type="password" />
            <label>Temperature</label>
            <input v-model.number="settings.textProvider.temperature" type="number" step="0.1" />
          </div>
        </section>

        <section class="card">
          <div class="panel-header">
            <h2>图像 Provider</h2>
          </div>
          <div class="field-grid">
            <label>Provider</label>
            <select v-model="settings.imageProvider.provider">
              <option value="mock">mock</option>
              <option value="openai_compatible">openai_compatible</option>
            </select>
            <label>Base URL</label>
            <input v-model="settings.imageProvider.baseUrl" />
            <label>Model</label>
            <input v-model="settings.imageProvider.model" />
            <label>API Key</label>
            <input v-model="settings.imageProvider.apiKey" type="password" />
            <label>Timeout(ms)</label>
            <input v-model.number="settings.imageProvider.timeoutMs" type="number" />
          </div>
          <div class="inline-actions">
            <button @click="saveSettings">保存设置</button>
            <button @click="testSettings">连通性测试</button>
          </div>
        </section>
      </section>
    </main>
  </div>
</template>

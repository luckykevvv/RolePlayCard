<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import type {
  AppSettings,
  CharacterDraft,
  DraftSummary,
  GenerateFieldRequest,
  ProviderConfig,
} from '../../shared/types.js';

const nowIso = () => new Date().toISOString();
const createProviderConfig = (): ProviderConfig => ({
  provider: 'mock',
  baseUrl: 'https://api.openai.com/v1',
  apiKey: '',
  model: '',
  timeoutMs: 45000,
  temperature: 0.8,
  enabled: true,
});

const createDraft = (): CharacterDraft => ({
  id: crypto.randomUUID(),
  version: 1,
  createdAt: nowIso(),
  updatedAt: nowIso(),
  profile: {
    name: '',
    age: '',
    gender: '',
    appearance: '',
    personality: '',
    speakingStyle: '',
    background: '',
  },
  opening: {
    greeting: '',
    scenario: '',
    exampleDialogue: '',
    firstMessage: '',
  },
  worldBook: '',
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
const imagePreview = computed(
  () => draft.illustration.generatedImagePath || draft.illustration.originalImagePath || '',
);
const exportReady = computed(
  () => Boolean(draft.profile.name.trim() && draft.opening.firstMessage.trim() && imagePreview.value),
);
const validationReport = computed(() => {
  const items: string[] = [];
  if (!draft.profile.name.trim()) items.push('缺少角色姓名');
  if (!draft.opening.firstMessage.trim()) items.push('缺少首条消息');
  if (!imagePreview.value) items.push('缺少导出图片');
  return items;
});

let autosaveTimer: number | null = null;

async function refreshDraftList() {
  const result = await window.rolePlayCard.listDrafts();
  if (result.success && result.data) {
    drafts.value = result.data;
  }
}

async function loadSettings() {
  const result = await window.rolePlayCard.getSettings();
  if (result.success && result.data) {
    Object.assign(settings, result.data);
  }
}

async function saveSettings() {
  status.value = '正在保存设置...';
  const result = await window.rolePlayCard.saveSettings(structuredClone(settings));
  status.value = result.success ? '设置已保存' : `设置保存失败: ${result.message}`;
}

async function testSettings() {
  status.value = '正在测试 Provider 配置...';
  const result = await window.rolePlayCard.testSettings();
  if (!result.success || !result.data) {
    status.value = `测试失败: ${result.message}`;
    return;
  }
  status.value = result.data.map((item) => `${item.provider}: ${item.detail}`).join(' | ');
}

async function openDraft(draftId: string) {
  const result = await window.rolePlayCard.loadDraft(draftId);
  if (!result.success || !result.data) {
    status.value = `打开草稿失败: ${result.message}`;
    return;
  }
  Object.assign(draft, result.data);
  status.value = `已打开草稿 ${result.data.profile.name || result.data.id}`;
}

async function saveDraft(saveAs = false) {
  draft.updatedAt = nowIso();
  const request = structuredClone(draft);
  const result = saveAs
    ? await window.rolePlayCard.saveDraftAs(request)
    : await window.rolePlayCard.saveDraft(request);
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

function resolveFieldValue(field: string) {
  const [section, key] = field.split('.');
  if (section === 'profile') {
    return draft.profile[key as keyof CharacterDraft['profile']] ?? '';
  }
  if (section === 'opening') {
    return draft.opening[key as keyof CharacterDraft['opening']] ?? '';
  }
  if (section === 'illustration') {
    return draft.illustration[key as keyof CharacterDraft['illustration']] ?? '';
  }
  return '';
}

function applyFieldValue(field: string, value: string) {
  const [section, key] = field.split('.');
  if (section === 'profile') {
    draft.profile[key as keyof CharacterDraft['profile']] = value;
    return;
  }
  if (section === 'opening') {
    draft.opening[key as keyof CharacterDraft['opening']] = value;
    return;
  }
  if (section === 'illustration') {
    draft.illustration[key as keyof CharacterDraft['illustration']] = value;
  }
}

async function runFieldAI(field: string, mode: GenerateFieldRequest['mode']) {
  aiBusyField.value = field;
  status.value = `正在为 ${field} 生成内容...`;
  const result = await window.rolePlayCard.generateField({
    field,
    mode,
    userInput: resolveFieldValue(field),
    draft: structuredClone(draft),
  });
  aiBusyField.value = '';
  if (!result.success || !result.data) {
    status.value = `AI 生成失败: ${result.message}`;
    return;
  }
  applyFieldValue(field, result.data.result);
  status.value = `${field} 已更新`;
}

async function pickImage() {
  const result = await window.rolePlayCard.pickImage();
  if (!result.success || !result.data) {
    status.value = '未选择图片';
    return;
  }
  draft.illustration.originalImagePath = result.data.path;
  draft.illustration.exportImagePath = result.data.path;
  status.value = '已加载角色图片';
}

async function generateImagePrompt() {
  status.value = '正在生成绘图提示词...';
  const result = await window.rolePlayCard.generateImagePrompt(structuredClone(draft));
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
  const result = await window.rolePlayCard.generateImage({
    draft: structuredClone(draft),
    prompt: draft.illustration.promptSnapshot,
    negativePrompt: draft.illustration.negativePrompt,
  });
  if (!result.success || !result.data) {
    status.value = `角色图生成失败: ${result.message}`;
    return;
  }
  draft.illustration.generatedImagePath = result.data.imagePath;
  draft.illustration.exportImagePath = result.data.imagePath;
  status.value = '角色图已生成';
}

async function exportCard() {
  const saveDialog = await window.rolePlayCard.pickExportPath(draft.profile.name || 'character-card');
  if (!saveDialog.success || !saveDialog.data) {
    status.value = '导出已取消';
    return;
  }

  status.value = '正在导出 TavernAI PNG...';
  const result = await window.rolePlayCard.exportCard({
    draft: structuredClone(draft),
    imagePath: draft.illustration.exportImagePath,
    outputPath: saveDialog.data.path,
  });
  status.value = result.success ? `导出成功: ${saveDialog.data.path}` : `导出失败: ${result.message}`;
}

function resetDraft() {
  Object.assign(draft, createDraft());
  status.value = '已新建草稿';
}

watch(
  draft,
  () => {
    draft.updatedAt = nowIso();
    queueAutosave();
  },
  { deep: true },
);

onMounted(async () => {
  const [info] = await Promise.all([window.rolePlayCard.getAppInfo(), loadSettings(), refreshDraftList()]);
  appDataDir.value = info.appDataDir;
  if (drafts.value[0]) {
    await openDraft(drafts.value[0].id);
  } else {
    await saveDraft(false);
  }
});

const fieldGroups = [
  {
    title: '角色描述',
    fields: [
      ['profile.name', '姓名'],
      ['profile.age', '年龄'],
      ['profile.gender', '性别'],
      ['profile.appearance', '外貌'],
      ['profile.personality', '性格'],
      ['profile.speakingStyle', '说话风格'],
      ['profile.background', '背景'],
    ],
  },
  {
    title: '首屏信息',
    fields: [
      ['opening.greeting', '开场白'],
      ['opening.scenario', '场景'],
      ['opening.exampleDialogue', '示例对话'],
      ['opening.firstMessage', '首条消息'],
    ],
  },
];
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div>
        <p class="eyebrow">RolePlayCard</p>
        <h1>AI 角色卡创建器</h1>
        <p class="muted">本地 Electron + Python 工作流</p>
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
        <button @click="saveDraft(false)">保存</button>
        <button @click="saveDraft(true)">另存为</button>
        <div class="draft-list">
          <button
            v-for="item in drafts"
            :key="item.id"
            class="draft-item"
            @click="openDraft(item.id)"
          >
            <strong>{{ item.name || '未命名角色' }}</strong>
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
          <section
            v-for="group in fieldGroups"
            :key="group.title"
            class="card"
          >
            <div class="panel-header">
              <h2>{{ group.title }}</h2>
            </div>
            <div
              v-for="[field, label] in group.fields"
              :key="field"
              class="field"
            >
              <label :for="field">{{ label }}</label>
              <textarea
                :id="field"
                v-model="(draft as any)[field.split('.')[0]][field.split('.')[1]]"
                rows="3"
              />
              <div class="inline-actions">
                <button
                  @click="runFieldAI(field, 'generate')"
                  :disabled="aiBusyField === field"
                >
                  AI 生成
                </button>
                <button
                  @click="runFieldAI(field, 'rewrite')"
                  :disabled="aiBusyField === field"
                >
                  AI 改写
                </button>
              </div>
            </div>
          </section>

          <section class="card">
            <div class="panel-header">
              <h2>世界书</h2>
            </div>
            <textarea
              v-model="draft.worldBook"
              rows="8"
              placeholder="输入世界观、组织、设定规则等内容"
            />
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
                :src="`file://${imagePreview}`"
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
              <label for="stylePrompt">画风偏好</label>
              <textarea
                id="stylePrompt"
                v-model="draft.illustration.stylePrompt"
                rows="3"
                placeholder="例如：anime portrait, warm tone, cinematic lighting"
              />
            </div>
            <div class="field">
              <label for="promptSnapshot">提示词</label>
              <textarea
                id="promptSnapshot"
                v-model="draft.illustration.promptSnapshot"
                rows="5"
              />
            </div>
            <div class="field">
              <label for="negativePrompt">负面提示词</label>
              <textarea
                id="negativePrompt"
                v-model="draft.illustration.negativePrompt"
                rows="4"
              />
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

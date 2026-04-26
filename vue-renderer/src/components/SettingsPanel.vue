<script setup lang="ts">
import type { AppSettings, BuiltinPrefixPromptOption } from '../../../shared/types.js';

defineProps<{
  settings: AppSettings;
  textModelOptions: string[];
  imageModelOptions: string[];
  builtinPrefixPromptDir: string;
  builtinPrefixPromptOptions: BuiltinPrefixPromptOption[];
  loadingBuiltinPrefixPrompts: boolean;
  testingTextProvider: boolean;
  testingImageProvider: boolean;
}>();

const emit = defineEmits<{
  (event: 'refresh-builtin-prefix-prompts'): void;
  (event: 'save-text-settings'): void;
  (event: 'test-text-settings'): void;
  (event: 'save-image-settings'): void;
  (event: 'test-image-settings'): void;
  (event: 'save-segmentation-settings'): void;
}>();
</script>

<template>
  <section class="settings-layout">
    <section class="card">
      <div class="panel-header">
        <h2>文本 Provider</h2>
      </div>
      <div class="field-grid">
        <label>Provider</label>
        <select v-model="settings.textProvider.provider" disabled>
          <option value="openai_compatible">openai_compatible</option>
        </select>
        <label>Base URL</label>
        <input v-model="settings.textProvider.baseUrl" />
        <label>文本模型</label>
        <select v-if="textModelOptions.length > 0" v-model="settings.textProvider.model">
          <option
            v-for="model in textModelOptions"
            :key="model"
            :value="model"
          >
            {{ model }}
          </option>
        </select>
        <input v-else v-model="settings.textProvider.model" placeholder="先点连通性测试拉取模型列表" />
        <label>API Key</label>
        <input v-model="settings.textProvider.apiKey" type="password" />
        <label>Temperature</label>
        <input v-model.number="settings.textProvider.temperature" type="number" step="0.1" />
        <label>Timeout(ms)</label>
        <input v-model.number="settings.textProvider.timeoutMs" type="number" min="1000" step="1000" />
        <label>破限提示词来源</label>
        <select v-model="settings.textProvider.prefixPromptMode">
          <option value="custom">自定义输入</option>
          <option value="builtin">内置文件</option>
        </select>
      </div>
      <div v-if="settings.textProvider.prefixPromptMode === 'builtin'" class="field-grid">
        <label>内置目录</label>
        <input :value="builtinPrefixPromptDir || '未读取'" readonly />
        <label>内置模型文件</label>
        <select v-if="builtinPrefixPromptOptions.length > 0" v-model="settings.textProvider.builtinPrefixPromptModel">
          <option value="">跟随当前文本模型</option>
          <option
            v-for="item in builtinPrefixPromptOptions"
            :key="item.filename"
            :value="item.model"
          >
            {{ item.model }} ({{ item.filename }})
          </option>
        </select>
        <input v-else value="目录中暂无 .txt 文件" readonly />
      </div>
      <div class="field">
        <label>前置破限提示词</label>
        <textarea
          v-model="settings.textProvider.prefixPrompt"
          rows="5"
          :placeholder="
            settings.textProvider.prefixPromptMode === 'builtin'
              ? '内置文件未命中时，会回退到这里（可留空）'
              : '每次文本调用会自动拼接：前置破限提示词 + 正常提示词'
          "
        />
      </div>
      <p v-if="settings.textProvider.prefixPromptMode === 'builtin'" class="muted">
        内置文件按“模型名.txt”匹配；未命中时会回退到上面的自定义文本。
      </p>
      <div class="inline-actions">
        <button @click="emit('refresh-builtin-prefix-prompts')" :disabled="loadingBuiltinPrefixPrompts">
          <span v-if="loadingBuiltinPrefixPrompts" class="loading-spinner loading-inline" />
          {{ loadingBuiltinPrefixPrompts ? '刷新中...' : '刷新内置列表' }}
        </button>
        <button @click="emit('save-text-settings')">保存文本设置</button>
        <button @click="emit('test-text-settings')" :disabled="testingTextProvider">
          <span v-if="testingTextProvider" class="loading-spinner loading-inline" />
          {{ testingTextProvider ? '测试中...' : '文本连通性测试' }}
        </button>
      </div>
    </section>

    <section class="card">
      <div class="panel-header">
        <h2>图像 Provider</h2>
      </div>
      <div class="field-grid">
        <label>Provider</label>
        <select v-model="settings.imageProvider.provider" disabled>
          <option value="openai_compatible">openai_compatible</option>
        </select>
        <label>Base URL</label>
        <input v-model="settings.imageProvider.baseUrl" />
        <label>图像模型</label>
        <select v-if="imageModelOptions.length > 0" v-model="settings.imageProvider.model">
          <option
            v-for="model in imageModelOptions"
            :key="model"
            :value="model"
          >
            {{ model }}
          </option>
        </select>
        <input v-else v-model="settings.imageProvider.model" placeholder="先点连通性测试拉取模型列表" />
        <label>API Key</label>
        <input v-model="settings.imageProvider.apiKey" type="password" />
        <label>Timeout(ms)</label>
        <input v-model.number="settings.imageProvider.timeoutMs" type="number" min="1000" step="1000" />
      </div>
      <div class="inline-actions">
        <button @click="emit('save-image-settings')">保存图像设置</button>
        <button @click="emit('test-image-settings')" :disabled="testingImageProvider">
          <span v-if="testingImageProvider" class="loading-spinner loading-inline" />
          {{ testingImageProvider ? '测试中...' : '图像连通性测试' }}
        </button>
      </div>
    </section>

    <section class="card">
      <div class="panel-header">
        <h2>长篇分段设置</h2>
      </div>
      <div class="field-grid">
        <label>默认硬切分上限</label>
        <input v-model.number="settings.storySegmentation.maxCharsPerSegment" type="number" min="500" step="100" />
      </div>
      <div class="field">
        <label>默认章节识别正则</label>
        <textarea
          v-model="settings.storySegmentation.chapterRegex"
          rows="5"
          placeholder="分段预览时优先用该正则识别章节标题"
        />
      </div>
      <div class="inline-actions">
        <button @click="emit('save-segmentation-settings')">保存分段设置</button>
      </div>
    </section>
  </section>
</template>

import type {
  AppSettings,
  CharacterDraft,
  DraftSummary,
  ExportCharacterCardRequest,
  GenerateFieldRequest,
  GenerateFieldResponse,
  GenerateImageRequest,
  GenerateImageResponse,
  ImagePromptResponse,
  ProviderValidationResult,
  TaskResult,
} from '../../shared/types.js';

declare module '*.vue' {
  import type { DefineComponent } from 'vue';
  const component: DefineComponent<Record<string, never>, Record<string, never>, any>;
  export default component;
}

declare global {
  interface Window {
    rolePlayCard: {
      getAppInfo: () => Promise<{ appDataDir: string }>;
      getSettings: () => Promise<TaskResult<AppSettings>>;
      saveSettings: (settings: AppSettings) => Promise<TaskResult<AppSettings>>;
      testSettings: () => Promise<TaskResult<ProviderValidationResult[]>>;
      listDrafts: () => Promise<TaskResult<DraftSummary[]>>;
      loadDraft: (draftId: string) => Promise<TaskResult<CharacterDraft>>;
      saveDraft: (draft: CharacterDraft) => Promise<TaskResult<CharacterDraft>>;
      saveDraftAs: (draft: CharacterDraft) => Promise<TaskResult<CharacterDraft>>;
      generateField: (
        payload: GenerateFieldRequest,
      ) => Promise<TaskResult<GenerateFieldResponse>>;
      generateImagePrompt: (
        draft: CharacterDraft,
      ) => Promise<TaskResult<ImagePromptResponse>>;
      generateImage: (
        payload: GenerateImageRequest,
      ) => Promise<TaskResult<GenerateImageResponse>>;
      exportCard: (
        payload: ExportCharacterCardRequest,
      ) => Promise<TaskResult<{ outputPath: string }>>;
      pickImage: () => Promise<TaskResult<{ path: string }>>;
      pickExportPath: (suggestedName: string) => Promise<TaskResult<{ path: string }>>;
    };
  }
}

export {};

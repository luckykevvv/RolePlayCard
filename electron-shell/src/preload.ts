import { contextBridge, ipcRenderer } from 'electron';
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

const api = {
  getAppInfo: () => ipcRenderer.invoke('app.info') as Promise<{ appDataDir: string }>,
  getSettings: () => ipcRenderer.invoke('settings.get') as Promise<TaskResult<AppSettings>>,
  saveSettings: (settings: AppSettings) =>
    ipcRenderer.invoke('settings.set', settings) as Promise<TaskResult<AppSettings>>,
  testSettings: () =>
    ipcRenderer.invoke('settings.test') as Promise<TaskResult<ProviderValidationResult[]>>,
  listDrafts: () => ipcRenderer.invoke('draft.list') as Promise<TaskResult<DraftSummary[]>>,
  loadDraft: (draftId: string) =>
    ipcRenderer.invoke('draft.load', draftId) as Promise<TaskResult<CharacterDraft>>,
  saveDraft: (draft: CharacterDraft) =>
    ipcRenderer.invoke('draft.save', draft) as Promise<TaskResult<CharacterDraft>>,
  saveDraftAs: (draft: CharacterDraft) =>
    ipcRenderer.invoke('draft.saveAs', draft) as Promise<TaskResult<CharacterDraft>>,
  generateField: (payload: GenerateFieldRequest) =>
    ipcRenderer.invoke('ai.generateField', payload) as Promise<TaskResult<GenerateFieldResponse>>,
  generateImagePrompt: (draft: CharacterDraft) =>
    ipcRenderer.invoke('ai.generateImagePrompt', draft) as Promise<TaskResult<ImagePromptResponse>>,
  generateImage: (payload: GenerateImageRequest) =>
    ipcRenderer.invoke('ai.generateImage', payload) as Promise<TaskResult<GenerateImageResponse>>,
  exportCard: (payload: ExportCharacterCardRequest) =>
    ipcRenderer.invoke('card.export', payload) as Promise<TaskResult<{ outputPath: string }>>,
  pickImage: () => ipcRenderer.invoke('files.pickImage') as Promise<TaskResult<{ path: string }>>,
  pickExportPath: (suggestedName: string) =>
    ipcRenderer.invoke('files.pickExportPath', suggestedName) as Promise<TaskResult<{ path: string }>>,
};

contextBridge.exposeInMainWorld('rolePlayCard', api);

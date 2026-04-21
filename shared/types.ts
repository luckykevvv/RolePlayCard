export type ProviderKind = 'mock' | 'openai_compatible';

export interface ProviderConfig {
  provider: ProviderKind;
  baseUrl: string;
  apiKey: string;
  model: string;
  timeoutMs: number;
  temperature: number;
  enabled: boolean;
  extraHeaders?: Record<string, string>;
}

export interface AppSettings {
  textProvider: ProviderConfig;
  imageProvider: ProviderConfig;
  exportDirectory: string;
  recentDirectory: string;
}

export interface CharacterProfile {
  name: string;
  age: string;
  gender: string;
  appearance: string;
  personality: string;
  speakingStyle: string;
  background: string;
}

export interface OpeningInfo {
  greeting: string;
  scenario: string;
  exampleDialogue: string;
  firstMessage: string;
}

export interface IllustrationInfo {
  originalImagePath: string;
  generatedImagePath: string;
  exportImagePath: string;
  promptSnapshot: string;
  negativePrompt: string;
  stylePrompt: string;
}

export interface CharacterDraft {
  id: string;
  version: number;
  createdAt: string;
  updatedAt: string;
  profile: CharacterProfile;
  opening: OpeningInfo;
  worldBook: string;
  illustration: IllustrationInfo;
}

export interface DraftSummary {
  id: string;
  name: string;
  updatedAt: string;
}

export interface TaskResult<T> {
  success: boolean;
  error_code: string | null;
  message: string;
  data: T | null;
}

export interface GenerateFieldRequest {
  field: string;
  mode: 'generate' | 'rewrite';
  draft: CharacterDraft;
  userInput: string;
}

export interface GenerateFieldResponse {
  field: string;
  result: string;
  promptPreview: string;
}

export interface ImagePromptResponse {
  prompt: string;
  negativePrompt: string;
}

export interface GenerateImageRequest {
  draft: CharacterDraft;
  prompt: string;
  negativePrompt: string;
}

export interface GenerateImageResponse {
  imagePath: string;
  prompt: string;
}

export interface ExportCharacterCardRequest {
  draft: CharacterDraft;
  imagePath: string;
  outputPath: string;
}

export interface ProviderValidationResult {
  provider: ProviderKind;
  ok: boolean;
  detail: string;
}

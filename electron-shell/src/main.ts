import { app, BrowserWindow, dialog, ipcMain } from 'electron';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import type {
  AppSettings,
  CharacterDraft,
  ExportCharacterCardRequest,
  GenerateFieldRequest,
  GenerateImageRequest,
  TaskResult,
} from '../../shared/types.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
function resolveProjectRoot(startDir: string) {
  let currentDir = startDir;
  while (true) {
    const packageJson = path.join(currentDir, 'package.json');
    const pythonServer = path.join(currentDir, 'python-service', 'src', 'server.py');
    if (fs.existsSync(packageJson) && fs.existsSync(pythonServer)) {
      return currentDir;
    }

    const parentDir = path.dirname(currentDir);
    if (parentDir === currentDir) {
      throw new Error(`Unable to resolve project root from ${startDir}`);
    }
    currentDir = parentDir;
  }
}
const projectRoot = resolveProjectRoot(__dirname);
const pythonEntry = path.join(projectRoot, 'python-service', 'src', 'server.py');
const pythonPort = 8765;
let pythonProcess: ChildProcessWithoutNullStreams | null = null;

function createWindow() {
  const win = new BrowserWindow({
    width: 1480,
    height: 980,
    minWidth: 1180,
    minHeight: 800,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) {
    void win.loadURL(devUrl);
    win.webContents.openDevTools({ mode: 'detach' });
  } else {
    void win.loadFile(path.join(projectRoot, 'vue-renderer', 'dist', 'index.html'));
  }
}

function getPythonCommand() {
  if (process.platform === 'win32') {
    return 'python';
  }
  return 'python3';
}

async function waitForHealth(timeoutMs = 15000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const response = await fetch(`http://127.0.0.1:${pythonPort}/health`);
      if (response.ok) {
        return;
      }
    } catch {
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
  }
  throw new Error('Python service health check timed out.');
}

async function ensurePythonService() {
  if (pythonProcess && !pythonProcess.killed) {
    return;
  }

  const appDataDir = app.getPath('userData');
  pythonProcess = spawn(
    getPythonCommand(),
    [pythonEntry, '--host', '127.0.0.1', '--port', String(pythonPort), '--app-data', appDataDir],
    {
      cwd: projectRoot,
      stdio: 'pipe',
      env: { ...process.env, PYTHONUNBUFFERED: '1' },
    },
  );

  pythonProcess.stdout.on('data', (chunk) => {
    process.stdout.write(`[python-service] ${chunk}`);
  });

  pythonProcess.stderr.on('data', (chunk) => {
    process.stderr.write(`[python-service] ${chunk}`);
  });

  pythonProcess.on('exit', (code) => {
    pythonProcess = null;
    console.error(`Python service exited with code ${code ?? 'unknown'}.`);
  });

  await waitForHealth();
}

async function apiRequest<T>(pathname: string, init?: RequestInit): Promise<TaskResult<T>> {
  await ensurePythonService();
  const response = await fetch(`http://127.0.0.1:${pythonPort}${pathname}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(init?.headers ?? {}),
    },
  });
  return (await response.json()) as TaskResult<T>;
}

app.whenReady().then(async () => {
  await ensurePythonService();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (pythonProcess && !pythonProcess.killed) {
    pythonProcess.kill();
  }
});

ipcMain.handle('app.info', () => ({
  appDataDir: app.getPath('userData'),
}));

ipcMain.handle('settings.get', async () => apiRequest<AppSettings>('/settings'));
ipcMain.handle('settings.set', async (_event, settings: AppSettings) =>
  apiRequest<AppSettings>('/settings', {
    method: 'POST',
    body: JSON.stringify(settings),
  }),
);
ipcMain.handle('settings.test', async () =>
  apiRequest('/settings/test', {
    method: 'POST',
  }),
);

ipcMain.handle('draft.list', async () => apiRequest('/drafts'));
ipcMain.handle('draft.load', async (_event, draftId: string) => apiRequest(`/drafts/${draftId}`));
ipcMain.handle('draft.save', async (_event, draft: CharacterDraft) =>
  apiRequest('/drafts', {
    method: 'POST',
    body: JSON.stringify({ draft, saveAs: false }),
  }),
);
ipcMain.handle('draft.saveAs', async (_event, draft: CharacterDraft) =>
  apiRequest('/drafts', {
    method: 'POST',
    body: JSON.stringify({ draft, saveAs: true }),
  }),
);

ipcMain.handle('ai.generateField', async (_event, payload: GenerateFieldRequest) =>
  apiRequest('/ai/field', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
);
ipcMain.handle('ai.generateImagePrompt', async (_event, draft: CharacterDraft) =>
  apiRequest('/ai/image-prompt', {
    method: 'POST',
    body: JSON.stringify({ draft }),
  }),
);
ipcMain.handle('ai.generateImage', async (_event, payload: GenerateImageRequest) =>
  apiRequest('/ai/image', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
);
ipcMain.handle('card.export', async (_event, payload: ExportCharacterCardRequest) =>
  apiRequest('/card/export', {
    method: 'POST',
    body: JSON.stringify(payload),
  }),
);

ipcMain.handle('files.pickImage', async () => {
  const result = await dialog.showOpenDialog({
    properties: ['openFile'],
    filters: [{ name: 'Images', extensions: ['png', 'jpg', 'jpeg', 'webp'] }],
  });

  if (result.canceled || result.filePaths.length === 0) {
    return { success: false, error_code: 'cancelled', message: 'No image selected.', data: null };
  }

  return { success: true, error_code: null, message: 'OK', data: { path: result.filePaths[0] } };
});

ipcMain.handle('files.pickExportPath', async (_event, suggestedName: string) => {
  const result = await dialog.showSaveDialog({
    defaultPath: `${suggestedName || 'character-card'}.png`,
    filters: [{ name: 'PNG Image', extensions: ['png'] }],
  });

  if (result.canceled || !result.filePath) {
    return { success: false, error_code: 'cancelled', message: 'No export path selected.', data: null };
  }

  return { success: true, error_code: null, message: 'OK', data: { path: result.filePath } };
});

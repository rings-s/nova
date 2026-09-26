import os from 'node:os';
import path from 'node:path';
import { defineConfig } from '@playwright/test';

// Runs against the dev server `make dev` already has up, not a server of its
// own: the specs are written for http://localhost:5173 (the one origin the API
// accepts), and the in-memory mock API only answers under `vite dev`.
//
// Results go to the system temp directory. Vite watches this directory tree and
// full-reloads every open page when a file appears in it, including pages in
// the middle of a test.
export default defineConfig({
	testDir: 'src',
	testMatch: '**/*.e2e.{ts,js}',
	outputDir: path.join(os.tmpdir(), 'nova-playwright-results'),
	workers: 2,
	use: { baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173' }
});

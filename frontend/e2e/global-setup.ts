import { chromium, type FullConfig } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

/**
 * Logs the test admin in through the real UI once and persists the session
 * (localStorage, incl. the Supabase session) as a storage state all tests
 * reuse. Credentials come ONLY from the environment.
 */
export default async function globalSetup(config: FullConfig) {
  const email = process.env.CYBERGUARD_TEST_EMAIL;
  const pass = process.env.CYBERGUARD_TEST_PASS;
  if (!email || !pass) {
    throw new Error('CYBERGUARD_TEST_EMAIL and CYBERGUARD_TEST_PASS must be set in the environment');
  }
  const baseURL = config.projects[0]?.use?.baseURL ?? 'http://localhost:5173';

  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto(`${baseURL}/login`);
  await page.getByPlaceholder('••••••••').fill(pass);
  await page.locator('form').getByRole('button', { name: 'Sign In' }).click();
  await page.waitForURL('**/dashboard', { timeout: 30_000 });

  const stateDir = path.resolve(process.cwd(), 'e2e', '.auth');
  fs.mkdirSync(stateDir, { recursive: true });
  await page.context().storageState({ path: path.join(stateDir, 'state.json') });
  await browser.close();
}

import { expect, test, type Page } from '@playwright/test';
import path from 'node:path';

/**
 * CYBERGUARD post-theme browser E2E. Credentials come ONLY from the
 * environment (CYBERGUARD_TEST_EMAIL / CYBERGUARD_TEST_PASS). Any browser
 * console message of type "error" (or an uncaught page error) fails the test.
 */

const MEDIA_PATH = path.resolve(process.cwd(), '..', 'evidence', 'media', 'manipulated.png');

test.describe.configure({ mode: 'serial' });

/**
 * Log in through the UI. Each test gets a fresh context (Playwright default),
 * and the backend treats sessions per-login, so every authenticated test
 * establishes its own session.
 */
async function login(page: Page) {
  await page.goto('/login');
  await page.getByPlaceholder('••••••••').fill(process.env.CYBERGUARD_TEST_PASS!);
  await page.locator('form').getByRole('button', { name: 'Sign In' }).click();
  await page.waitForURL('**/dashboard');
}

async function trackConsoleErrors(page: Page): Promise<string[]> {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push(String(err)));
  return errors;
}

async function expectNoConsoleErrors(errors: string[]) {
  expect(errors, `browser console errors: ${errors.join(' | ')}`).toEqual([]);
}

const unauthenticated = { storageState: { cookies: [], origins: [] } } as const;

test.describe('landing (public)', () => {
  test.use(unauthenticated);

  test('a. landing renders; Sign Up / Login buttons route to login modes', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await page.goto('/');
    await expect(page.getByText('AI-Powered Cyber Threat, Phishing & Digital Impersonation')).toBeVisible();

    await page.getByRole('link', { name: /sign up/i }).first().click();
    await expect(page).toHaveURL(/\/login\?mode=signup/);
    await expect(page.locator('form').getByRole('button', { name: 'Create Account' })).toBeVisible();

    await page.goto('/');
    await page.getByRole('link', { name: /^login$/i }).first().click();
    await expect(page).toHaveURL(/\/login\?mode=signin/);
    await expectNoConsoleErrors(errors);
  });
});

test.describe('authenticated flows', () => {
  test('b. login as admin; dashboard renders six stat cards and a chart', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);

    for (const card of [
      /events analyzed/i,
      /threats detected/i,
      /phishing attempts/i,
      /impersonation attempts/i,
      /suspected deepfakes/i,
      /account takeover attempts/i,
    ]) {
      await expect(page.getByText(card).first()).toBeVisible();
    }
    await expect(page.locator('svg.recharts-surface').first()).toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test('c. phishing: malicious sample -> severity badge + explanation', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);
    await page.goto('/phishing');
    await page.getByRole('button', { name: 'Load Phishing Sample' }).click();
    await page.getByRole('button', { name: 'Analyze Email' }).click();
    await expect(page.getByText(/^(CRITICAL|HIGH)$/).first()).toBeVisible({ timeout: 280_000 });
    await expect(page.getByText('AI Explanation')).toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test('d. url: malicious sample -> severity badge + explanation', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);
    await page.goto('/url-analysis');
    await page.getByPlaceholder('https://suspicious-domain.example/login').fill('http://185.220.101.7/paypal-login/verify');
    await page.getByRole('button', { name: 'Analyze URL' }).click();
    await expect(page.getByText(/^(CRITICAL|HIGH)$/).first()).toBeVisible({ timeout: 280_000 });
    await expect(page.getByText('AI Explanation')).toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test('e. impersonation: fake-CEO sample -> high or critical', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);
    await page.goto('/impersonation');
    await page.getByRole('button', { name: 'Load Fake CEO Sample' }).click();
    await page.getByRole('button', { name: 'Analyze Message' }).click();
    await expect(page.getByText(/^(CRITICAL|HIGH)$/).first()).toBeVisible({ timeout: 280_000 });
    await expectNoConsoleErrors(errors);
  });

  test('f. deepfake: upload manipulated.png -> manipulation probability visible', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);
    await page.goto('/deepfake');
    await page.locator('input[type="file"]').setInputFiles(MEDIA_PATH);
    await page.getByRole('button', { name: 'Analyze Media' }).click();
    await expect(page.getByText(/manipulation probability/i).first()).toBeVisible({ timeout: 400_000 });
    await expectNoConsoleErrors(errors);
  });

  test('g. account takeover: pre-filled sample -> result visible', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);
    await page.goto('/account-takeover');
    await page.getByRole('button', { name: 'Analyze', exact: true }).click();
    await expect(page.getByText(/indicators — event/i).first()).toBeVisible({ timeout: 280_000 });
    await expectNoConsoleErrors(errors);
  });

  test('h. alerts: list non-empty; first alert opens with explanation and indicators', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);
    await page.goto('/alerts');
    const firstRow = page.locator('tbody tr').first();
    await expect(firstRow).toBeVisible();
    await firstRow.click();
    await page.waitForURL(/\/alerts\//);
    // Alert detail uses tabbed panels; Indicators is the default tab.
    await expect(page.getByText(/critical \(|high \(|medium \(|safe \(|low \(/i).first()).toBeVisible();
    await page.getByRole('button', { name: 'Explanation', exact: true }).click();
    await expect(page.locator('main p').filter({ hasText: /.{200,}/ }).first()).toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test('i. incident from alert detail; status change grows timeline', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);
    await page.goto('/alerts');
    const firstRow = page.locator('tbody tr').first();
    await expect(firstRow).toBeVisible();
    await firstRow.click();
    await page.waitForURL(/\/alerts\//);

    await page.getByRole('button', { name: 'Create Incident' }).click();
    await page.waitForURL(/\/incidents\//);

    const timelineItems = page.locator('div.relative.space-y-5 > div.relative');
    await expect(page.getByText('Incident Timeline')).toBeVisible();
    const before = await timelineItems.count();

    // Status transition button, e.g. "Start Investigation" (paired with Escalate).
    await page.getByRole('button', { name: /start investigation|mark contained|close incident/i }).click();
    await expect(timelineItems).toHaveCount(before + 1);
    await expectNoConsoleErrors(errors);
  });

  test('j. response actions: catalog visible; approval-gated execution recorded', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);
    await page.goto('/response-actions');
    await expect(page.getByText('Execute Action (Simulated)')).toBeVisible();

    // Wait for the catalog query to resolve (history rows may appear first,
    // so wait on the action dropdown itself rather than a table row).
    await expect(page.locator('select option').nth(1)).toBeAttached();

    // Pick an approval-required action from the dropdown.
    const options = page.locator('select option');
    const count = await options.count();
    let approvalLabel: string | null = null;
    for (let i = 0; i < count; i++) {
      const label = (await options.nth(i).textContent()) ?? '';
      if (label.includes('(approval required)')) {
        approvalLabel = label.trim();
        break;
      }
    }
    expect(approvalLabel, 'catalog must contain an approval-required action').not.toBeNull();
    await page.locator('select').selectOption({ label: approvalLabel! });
    await page.getByPlaceholder(/user@company\.com/).fill('e2e-target@company.com');

    // The execute button stays disabled until the approval box is checked.
    const executeButton = page.getByRole('button', { name: /execute/i }).last();
    await expect(executeButton).toBeDisabled();
    await page.getByRole('checkbox').check();
    await expect(executeButton).toBeEnabled();
    await executeButton.click();
    await expect(page.getByText(/executed \(simulated\)/i).first()).toBeVisible();
    await expect(page.locator('tbody tr', { hasText: 'e2e-target@company.com' }).first()).toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test('k. audit logs show recent entries', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);
    await page.goto('/audit-logs');
    await expect(page.locator('tbody tr').first()).toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test('l. admin users table visible for admin role', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);
    await page.goto('/admin/users');
    await expect(page.locator('tbody tr').first()).toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test('m. settings profile shows role ADMIN', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);
    await page.goto('/settings');
    await expect(page.getByText(/^admin$/i).first()).toBeVisible();
    await expectNoConsoleErrors(errors);
  });

  test('n. logout returns to public login', async ({ page }) => {
    const errors = await trackConsoleErrors(page);
    await login(page);
    await page.goto('/dashboard');
    // Wait out loading skeletons: while they animate, the dashboard content
    // layer can transiently cover the dropdown (pre-existing layering quirk).
    await page
      .locator('main .animate-pulse')
      .first()
      .waitFor({ state: 'detached', timeout: 30_000 })
      .catch(() => {});
    // The Topbar user chip is the last button in the header banner.
    await page.locator('header').getByRole('button').last().click();
    await page.getByRole('button', { name: 'Logout' }).click();
    await page.waitForURL(/\/(login)?$/);
    await expectNoConsoleErrors(errors);
  });
});

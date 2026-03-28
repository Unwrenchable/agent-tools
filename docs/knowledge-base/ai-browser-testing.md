# AI-Driven Browser Testing

This page documents the methodology for using AI agents to generate and execute browser-based tests from code changes, inspired by the [expect-cli](https://github.com/millionco/expect) pattern.

---

## Core Concept

Traditional E2E tests are written ahead of the feature and maintained as the product evolves. AI-driven browser testing inverts the loop: the agent **reads the diff first**, reasons about what behavior changed, generates a test plan in natural language, and then executes it against a live browser. Persistent Playwright specs are authored *after* a flow is validated — not before.

```
┌──────────────┐     ┌───────────────┐     ┌───────────────┐     ┌──────────────┐
│  git diff    │────▶│ AI test plan  │────▶│ Live browser  │────▶│ Pass / Fail  │
│ (what changed│     │ (natural lang)│     │ (Playwright)  │     │ + recording  │
└──────────────┘     └───────────────┘     └───────────────┘     └──────────────┘
```

---

## Workflow Stages

### 1. Diff Analysis

The agent runs `git diff` (or `git diff HEAD~1` for a committed change) and maps each changed line to its user-facing consequence:

| Code change | What to test in the browser |
|-------------|----------------------------|
| New route added | Navigation to that route succeeds |
| Form field added | Submitting with and without the field |
| API response shape changed | Data rendered correctly in the UI |
| Auth guard added | Unauthenticated redirect; authenticated access |
| CSS class renamed | Element still visible and styled correctly |

### 2. Test Plan Generation

The plan is written in plain numbered steps before any code is executed. Each step must have an observable outcome:

```
Step 1: Navigate to /signup
Step 2: Enter email "new@example.com" and password "Str0ng!"
Step 3: Click "Create account"
Step 4: Assert toast message "Account created" is visible
Step 5: Assert URL is /onboarding
```

The plan is reviewed and approved before execution. Ambiguous steps must be clarified.

### 3. Browser Execution (Playwright)

Playwright is the preferred execution engine. Key practices:

```typescript
// Prefer role/label/text selectors over CSS
await page.getByRole('button', { name: 'Sign in' }).click();
await page.getByLabel('Email').fill('user@example.com');

// Always await assertions
await expect(page).toHaveURL('/dashboard');
await expect(page.getByText('Welcome back')).toBeVisible();

// Capture evidence on failure
await page.screenshot({ path: 'test-results/failure.png' });
```

Session reuse (to avoid re-authenticating on every run):
```bash
# Record authenticated state once
npx playwright codegen --save-storage=auth.json https://app.example.com

# Reuse in tests
const context = await browser.newContext({ storageState: 'auth.json' });
```
> **Never commit `auth.json`** — add it to `.gitignore`.

### 4. CI Integration

- Exit `0` on full pass; exit `1` on any failure
- Store traces in `test-results/` — attach to CI artifacts for debugging
- Use `--retries=1` to filter out infrastructure flakiness from real regressions
- Use `--reporter=list` for clean CI output; HTML report locally

```yaml
# Example GitHub Actions step
- name: Run browser tests
  run: npx playwright test --reporter=list --retries=1
  env:
    BASE_URL: ${{ vars.STAGING_URL }}
```

### 5. Converting Flows to Persistent Tests

When a validated flow is worth keeping, convert it to a `*.spec.ts` file:

```typescript
// tests/e2e/auth.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Authentication', () => {
  test('redirects unauthenticated users to login', async ({ page }) => {
    await page.goto(process.env.BASE_URL + '/dashboard');
    await expect(page).toHaveURL(/\/login/);
  });

  test('successful sign-in reaches the dashboard', async ({ page }) => {
    await page.goto(process.env.BASE_URL + '/login');
    await page.getByLabel('Email').fill('user@example.com');
    await page.getByLabel('Password').fill('secret');
    await page.getByRole('button', { name: 'Sign in' }).click();
    await expect(page).toHaveURL(/\/dashboard/);
    await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  });
});
```

File layout:
```
tests/
  e2e/
    auth.spec.ts
    checkout.spec.ts
    onboarding.spec.ts
playwright.config.ts
```

---

## Tooling Quick Reference

| Tool | Purpose |
|------|---------|
| `npx playwright test` | Run the full Playwright suite |
| `npx playwright test --ui` | Open interactive UI mode (local debugging) |
| `npx playwright codegen <url>` | Record a session and generate a spec |
| `npx playwright show-report` | Open HTML report from the last run |
| `npx playwright show-trace <trace.zip>` | Step through a recorded trace |
| `npx expect-cli` | AI pipeline: diff → plan → browser (requires `expect-cli`) |
| `npx expect-cli -m "test login flow" -y` | Run a named test immediately in CI |

---

## When to Use AI-Driven vs. Authored Tests

| Scenario | Approach |
|----------|----------|
| Rapid validation of a new feature in a PR | AI-driven: diff → plan → browser |
| Critical, stable user journey (login, checkout) | Authored Playwright spec in `tests/e2e/` |
| Visual regression check after a CSS refactor | AI-driven with screenshot comparison |
| Regression suite run on every commit | Authored specs in CI |
| Exploratory testing of an unfamiliar codebase | AI-driven with `npx playwright codegen` |

---

## Agent Responsible

The **[Browser Test Engineer](../../.github/agents/browser-test-engineer.agent.md)** agent owns this workflow. It pairs with:

- **QA Engineer** for test strategy and coverage targets
- **Frontend Engineer** for accessible locator guidance (`data-testid`, ARIA roles)
- **DevOps Engineer** for CI pipeline configuration (display servers, sandboxing)

---

**Source**: Methodology derived from [millionco/expect](https://github.com/millionco/expect) — an open-source AI-driven browser test runner built on Playwright and Claude/Codex.

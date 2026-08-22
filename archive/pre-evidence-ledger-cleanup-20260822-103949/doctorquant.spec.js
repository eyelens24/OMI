const { test, expect } = require('@playwright/test');

async function loadDemo(page) {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('http://127.0.0.1:8000');
  await page.getByRole('button', { name: /run built-in test csv/i }).click();
  await expect(page.locator('#results')).toBeVisible({ timeout: 15000 });
  await expect(page.locator('#snapshotIdentity')).not.toHaveText(/^[-—]$/);
  return errors;
}

test('demo loads with a visible immutable snapshot and no page errors', async ({ page }) => {
  const errors = await loadDemo(page);
  expect(errors).toEqual([]);
});

test('selecting A then B then A restores the same snapshot and card flow', async ({ page }) => {
  const errors = await loadDemo(page);
  const markers = page.locator('.loss-marker');
  await expect(markers).toHaveCount(5);

  // Use late markers: early incident points honestly have fewer than 50 prior marks.
  const first = markers.nth(3);
  const second = markers.nth(4);
  await first.click();
  await expect(page.locator('#timelineStatus')).toContainText(/snapshot/, { timeout: 15000 });
  const snapshotA = await page.locator('#snapshotIdentity').textContent();
  const flowA = await page.locator('#branches').innerHTML();

  await second.click();
  await expect(page.locator('#timelineStatus')).toContainText(/snapshot/, { timeout: 15000 });
  const snapshotB = await page.locator('#snapshotIdentity').textContent();
  expect(snapshotB).not.toBe(snapshotA);

  await first.click();
  await expect(page.locator('#timelineStatus')).toContainText(/snapshot/, { timeout: 15000 });
  await expect(page.locator('#snapshotIdentity')).toHaveText(snapshotA);
  expect(await page.locator('#branches').innerHTML()).toBe(flowA);
  expect(errors).toEqual([]);
});

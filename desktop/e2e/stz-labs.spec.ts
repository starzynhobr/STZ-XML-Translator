import { expect, test } from '@playwright/test'

const headers = { Authorization: 'Bearer e2e-token' }

test('the STZ Labs pill opens the site, GitHub and Discord card', async ({ page }) => {
  await page.request.post('/api/xml/close', { headers })
  await page.request.post('/api/projects/close', { headers })
  await page.goto('/')
  const pill = page.getByRole('button', { name: /Labs/ })
  await pill.click()
  const card = page.getByRole('dialog', { name: 'STZ Labs' })
  await expect(card.getByRole('button', { name: /stzlabs\.com/ })).toBeVisible()
  await expect(card.getByRole('button', { name: 'GitHub' })).toBeVisible()
  await expect(card.getByRole('button', { name: 'Discord' })).toBeVisible()
  await page.screenshot({ path: test.info().outputPath('stz-labs.png') })
  await page.keyboard.press('Escape')
  await expect(card).toBeHidden()
})

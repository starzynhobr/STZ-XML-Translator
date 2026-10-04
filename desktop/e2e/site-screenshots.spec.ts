import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

// Real UI and local engine, isolated sample data; no provider calls or feedback sends.
test('captures the current interface for the project page', async ({ page }) => {
  const output = path.resolve(import.meta.dirname, '../../dist/site-screenshots/v160')
  fs.mkdirSync(output, { recursive: true })
  const headers = { Authorization: 'Bearer e2e-token' }
  await page.request.put('/api/settings', { headers, data: { locale: 'en_US', target: 'pt_BR', theme: 'dark', accent: 'amber' } })
  await page.request.post('/api/xml/open', { headers, data: { path: path.join(import.meta.dirname, '.tmp/files/items.xml') } })
  await page.request.post('/api/xml/load', { headers, data: { parent: 'item', targets: ['description'], contexts: ['name'] } })
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await expect(page.getByRole('searchbox')).toBeVisible()
  await page.screenshot({ path: path.join(output, 'workspace-dark.png') })
  await page.getByRole('button', { name: /Glossary: \d+ terms/ }).click()
  const glossary = page.getByRole('dialog', { name: 'Glossary', exact: true })
  await expect(glossary).toBeVisible()
  await page.getByLabel('Original term').fill('Ember Blade')
  await page.getByLabel('Must become').fill('Lâmina de Brasa')
  await glossary.getByRole('button', { name: 'Add term' }).click()
  await expect(glossary.getByText('Lâmina de Brasa', { exact: true })).toBeVisible()
  await page.screenshot({ path: path.join(output, 'glossary.png') })
  await page.keyboard.press('Escape')
  await page.getByTitle('Change fields').click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.screenshot({ path: path.join(output, 'xml-fields.png') })
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'Settings', exact: true }).click()
  await expect(page.getByLabel('App language')).toBeVisible()
  await page.screenshot({ path: path.join(output, 'settings.png') })
  await page.getByRole('button', { name: 'Light', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.getByRole('button', { name: 'Back to translation', exact: true }).click()
  await expect(page.getByRole('searchbox')).toBeVisible()
  await page.screenshot({ path: path.join(output, 'workspace-light.png') })
})

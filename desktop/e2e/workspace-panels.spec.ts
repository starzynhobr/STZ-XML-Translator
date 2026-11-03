import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const work = path.join(import.meta.dirname, '.tmp')
const visuals = path.join(work, 'visuals')
const headers = { Authorization: 'Bearer e2e-token' }

test.beforeEach(async ({ page }) => {
  fs.mkdirSync(visuals, { recursive: true })
  await page.request.put('/api/settings', { headers, data: { locale: 'pt_BR', target: 'pt_BR', theme: 'dark', accent: 'blue' } })
  await page.request.post('/api/xml/open', { headers, data: { path: path.join(work, 'files/items.xml') } })
  await page.request.post('/api/xml/load', { headers, data: { parent: 'item', targets: ['description'], contexts: ['name'] } })
  await page.goto('/')
  await expect(page.getByRole('searchbox')).toBeVisible()
})

test('glossary floats over the bench and preserves search and focus', async ({ page }) => {
  await page.setViewportSize({ width: 1728, height: 900 })
  await page.getByRole('searchbox').fill('short')
  const opener = page.getByRole('button', { name: /Glossário: \d+ termos/ })
  await opener.click()
  const panel = page.getByRole('dialog', { name: 'Glossário', exact: true })
  await expect(panel).toBeVisible()
  const bounds = (await panel.boundingBox())!
  expect(bounds.width).toBeLessThan(1100)
  expect(bounds.height).toBeLessThan(852)
  await page.screenshot({ path: path.join(visuals, 'glossary-floating.png') })
  await page.getByLabel('Termo original').fill('Golem')
  await page.getByLabel('Deve virar').fill('Golem de pedra')
  await panel.getByRole('button', { name: 'Adicionar termo' }).click()
  await expect(panel.getByText('Golem de pedra', { exact: true })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(panel).toBeHidden()
  await expect(page.getByRole('searchbox')).toHaveValue('short')
  await expect(opener).toBeFocused()
})

test('dropdowns use themed options and keyboard navigation; search has one focus border', async ({ page }) => {
  const provider = page.getByRole('combobox', { name: 'Com', exact: true })
  await provider.focus()
  await page.keyboard.press('ArrowDown')
  const menu = page.getByRole('listbox', { name: 'Com', exact: true })
  await expect(menu).toBeVisible()
  const colors = await menu.evaluate((element) => ({
    actual: getComputedStyle(element).backgroundColor,
    expected: getComputedStyle(document.documentElement).getPropertyValue('--panel').trim(),
  }))
  expect(colors.actual).toBe('rgb(18, 21, 29)')
  expect(colors.expected).toBe('#12151d')
  await page.screenshot({ path: path.join(visuals, 'dropdown-themed.png') })
  await page.keyboard.press('Home')
  await page.keyboard.press('Enter')
  await expect(provider).toContainText('Gemini')
  await expect(menu).toBeHidden()
  await provider.click()
  await page.keyboard.press('Escape')
  await expect(menu).toBeHidden()
  await expect(provider).toBeFocused()

  const search = page.getByRole('searchbox')
  await search.focus()
  const outline = await search.evaluate((input) => ({
    inner: getComputedStyle(input).outlineStyle,
    outer: getComputedStyle(input.parentElement!).borderColor,
  }))
  expect(outline.inner).toBe('none')
  expect(outline.outer).toBe('rgb(124, 183, 255)')
})

test('XML selection stays compact, lists many tags and cancel restores the file', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 700 })
  const opener = page.getByTitle('Alterar campos')
  await opener.click()
  const panel = page.getByRole('dialog', { name: 'O que vamos traduzir?' })
  await expect(panel).toBeVisible()
  await expect(panel.getByRole('radiogroup', { name: 'description' }).getByRole('radio', { name: 'Traduzir' })).toHaveAttribute('aria-checked', 'true')
  await expect(page.getByText('Espere a operação em andamento terminar.', { exact: true })).toBeHidden()
  const bounds = (await panel.boundingBox())!
  expect(bounds.width).toBeLessThan(1024)
  expect(bounds.height).toBeLessThan(653)
  await page.screenshot({ path: path.join(visuals, 'xml-floating.png') })

  const many = path.join(work, 'files/many-tags.xml')
  fs.writeFileSync(many, `<root>${Array.from({ length: 12 }, (_, i) => `<tag${i}><text>One</text></tag${i}><tag${i}><text>Two</text></tag${i}>`).join('')}</root>`)
  page.once('dialog', (dialog) => void dialog.accept(many))
  await panel.getByRole('button', { name: 'Trocar arquivo', exact: true }).click()
  await expect(panel.getByText('many-tags.xml', { exact: true })).toBeVisible()
  // Twelve text tags, all suggested; the list scrolls inside the panel.
  const last = panel.getByRole('button', { name: 'Usar tag11' })
  await expect(last).toHaveAttribute('aria-pressed', 'true')
  await last.scrollIntoViewIfNeeded()
  await expect(last).toBeInViewport()
  expect((await panel.boundingBox())!.height).toBeLessThan(653)
  await page.keyboard.press('Escape')
  await expect(panel).toBeHidden()
  await expect(opener).toBeFocused()
  await expect(page.getByRole('button', { name: 'items.xml', exact: true })).toBeVisible()
  const response = await page.request.get('/api/state', { headers })
  const state = await response.json()
  expect(state.file.name).toBe('items.xml')
  expect(state.loaded).toBe(true)
  expect(state.total).toBe(4)
})

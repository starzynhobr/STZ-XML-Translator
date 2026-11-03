import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const work = path.join(import.meta.dirname, '.tmp')
const folder = path.join(work, 'project-files')

test.describe.configure({ mode: 'serial' })

function answerNextPrompt(page: Page, value: string) {
  page.once('dialog', (dialog) => void dialog.accept(value))
}

test('a project lists its XMLs, remembers the fields and shows progress', async ({ page }) => {
  fs.mkdirSync(folder, { recursive: true })
  fs.copyFileSync(path.join(work, 'files', 'items.xml'), path.join(folder, 'catalog.xml'))
  // The engine is shared across specs: start without the file an earlier test left open.
  const closed = await page.request.post('/api/xml/close', { headers: { Authorization: 'Bearer e2e-token' } })
  expect(closed.ok()).toBe(true)

  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Projetos', exact: true })).toBeVisible()

  await page.getByRole('button', { name: 'Novo projeto' }).click()
  answerNextPrompt(page, folder)
  await page.getByRole('button', { name: 'Selecionar pasta do jogo' }).click()
  await expect(page.getByText('· 1 arquivos')).toBeVisible()
  await page.getByLabel('Nome do projeto').fill('Jogo de teste')
  await page.getByRole('button', { name: 'Criar projeto' }).click()

  await expect(page.getByRole('heading', { name: 'Jogo de teste' })).toBeVisible()
  await page.getByRole('button', { name: /catalog\.xml/ }).click()

  await expect(page.getByRole('heading', { name: 'O que vamos traduzir?' })).toBeVisible()
  // The fields are suggested: one click loads them.
  await page.getByRole('button', { name: 'Carregar 8 entradas' }).click()

  const editor = page.getByRole('textbox', { name: 'Tradução' })
  await editor.fill('Uma espada curta.')
  await page.getByRole('button', { name: 'Voltar ao projeto Jogo de teste' }).click()

  await expect(page.getByRole('heading', { name: 'Jogo de teste' })).toBeVisible()
  await expect(page.getByText('1 de 8', { exact: true })).toBeVisible()
  await expect(page.getByRole('listitem').filter({ hasText: 'catalog.xml' })).toContainText('item')

  // The fields are remembered: continuing opens the file straight away.
  await page.getByRole('button', { name: 'Continuar catalog.xml' }).click()
  await expect(editor).toBeVisible()
})

test.afterAll(async ({ request }) => {
  await request.post('/api/projects/close', { headers: { Authorization: 'Bearer e2e-token' } })
})

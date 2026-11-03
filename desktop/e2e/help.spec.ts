import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const work = path.join(import.meta.dirname, '.tmp')
const headers = { Authorization: 'Bearer e2e-token' }

test.describe.configure({ mode: 'serial' })

test('help is searchable and goes back where it came from', async ({ page }) => {
  await page.request.post('/api/xml/close', { headers })
  await page.request.post('/api/projects/close', { headers })
  await page.goto('/')
  await page.getByRole('button', { name: 'Ajuda' }).click()
  await expect(page.getByRole('heading', { name: 'Ajuda', level: 1 })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Criar um projeto' })).toBeVisible()

  const search = page.getByRole('searchbox', { name: /Buscar na ajuda/ })
  await search.fill('cota')  // accents and case do not matter: also finds "Cota"
  await expect(page.getByRole('heading', { name: 'Erros de cota e limite' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Criar um projeto' })).toBeHidden()
  await search.fill('zzzz nada')
  await expect(page.getByText('Nada encontrado. Tente outras palavras.')).toBeVisible()

  await page.getByRole('button', { name: 'Voltar' }).click()
  await expect(page.getByRole('heading', { name: 'Projetos', exact: true })).toBeVisible()
})

test('translating the whole project asks first', async ({ page }) => {
  const game = path.join(work, 'Confirm Game')
  fs.mkdirSync(path.join(game, 'Confirm Game_Data'), { recursive: true })
  fs.copyFileSync(path.join(work, 'files', 'items.xml'), path.join(game, 'Confirm Game_Data', 'items.xml'))
  const project = await (await page.request.post('/api/projects', { headers, data: { folder: game, name: 'Confirm Game' } })).json()
  await page.request.post(`/api/projects/${project.id}/open`, { headers })
  await page.goto('/')

  await page.getByRole('button', { name: 'Traduzir projeto inteiro' }).click()
  const dialog = page.getByRole('dialog', { name: 'Traduzir o projeto inteiro?' })
  await expect(dialog).toContainText('1 arquivos')
  await dialog.getByRole('button', { name: 'Cancelar' }).click()
  await expect(dialog).toBeHidden()
  const state = await (await page.request.get('/api/state', { headers })).json()
  expect(state.job.status).toBe('idle')  // nothing started

  await page.request.post('/api/projects/close', { headers })
  await page.request.delete(`/api/projects/${project.id}`, { headers })
})

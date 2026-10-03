import { expect, test, type Page } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const work = path.join(import.meta.dirname, '.tmp')
const xmlPath = path.join(work, 'files', 'items.xml')
const outPath = path.join(work, 'files', 'items_pt.xml')
const configPath = path.join(work, 'data', 'config.json')

test.describe.configure({ mode: 'serial' })

/** Outside Tauri the app asks for paths with window.prompt; answer the next one. */
function answerNextPrompt(page: Page, value: string) {
  page.once('dialog', (dialog) => void dialog.accept(value))
}

const rows = (page: Page) => page.locator('section button[aria-current]')
const progress = (page: Page) => page.getByText(/\d+ confirmadas · \d+ a revisar · \d+ pendentes/)
const tagGroup = (page: Page, title: string) => page.getByText(title, { exact: true }).locator('xpath=ancestor::div[contains(@class,"flex-col")][1]')

test('opens a file, picks the fields and loads the entries', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Abra um arquivo XML' })).toBeVisible()

  answerNextPrompt(page, xmlPath)
  await page.getByRole('button', { name: 'Escolher arquivo' }).click()
  await expect(page.getByRole('heading', { name: 'O que vamos traduzir?' })).toBeVisible()
  await expect(page.getByLabel('Tag que se repete')).toContainText('item · 4 registros')

  // Nothing can be loaded before a field is chosen.
  await expect(page.getByRole('button', { name: 'Escolha um campo para traduzir' })).toBeDisabled()
  await tagGroup(page, 'Campos para traduzir').getByRole('button', { name: 'description' }).click()
  await tagGroup(page, 'Campos de contexto').getByRole('button', { name: 'name', exact: true }).click()

  await expect(page.getByText('4 registros · 4 textos para traduzir')).toBeVisible()
  const preview = page.getByRole('region', { name: 'Prévia' })
  await expect(preview).toContainText('<item id="1" rarity="rare">')
  await expect(preview).toContainText('A short sword.')

  await page.getByRole('button', { name: 'Carregar 4 entradas' }).click()
  await expect(rows(page)).toHaveCount(4)
  await expect(progress(page)).toHaveText('0 confirmadas · 0 a revisar · 4 pendentes')
  await expect(rows(page).first()).toContainText('Ember Blade')
})

test('translates one entry, confirms it and translates the rest', async ({ page }) => {
  await page.goto('/')
  await expect(rows(page)).toHaveCount(4)
  await page.locator('select[name=provider]').selectOption('Ollama (Local)')

  const editor = page.getByRole('textbox', { name: 'Tradução' })
  const inspector = page.getByRole('complementary')
  await inspector.getByRole('button', { name: 'Traduzir', exact: true }).click()
  await expect(editor).toHaveValue('[PT] A short sword.')
  await expect(progress(page)).toHaveText('0 confirmadas · 1 a revisar · 3 pendentes')

  await inspector.getByRole('button', { name: /Confirmar e avançar/ }).click()
  await expect(progress(page)).toHaveText('1 confirmadas · 0 a revisar · 3 pendentes')
  // Confirming moves on to the next entry.
  await expect(inspector.getByText('Entrada 2 de 4')).toBeVisible()

  await page.getByRole('button', { name: 'Traduzir 3 pendentes' }).click()
  await expect(page.getByRole('button', { name: 'Tudo traduzido' })).toBeDisabled()
  await expect(progress(page)).toHaveText('1 confirmadas · 3 a revisar · 0 pendentes')
  await expect(rows(page).nth(1)).toContainText('[PT] Blocks <b>fire</b>.')
})

test('filters, searches, edits and confirms with the keyboard', async ({ page }) => {
  await page.goto('/')
  await expect(rows(page)).toHaveCount(4)

  await page.getByRole('button', { name: /^A revisar/ }).click()
  await expect(rows(page)).toHaveCount(3)
  await page.getByRole('button', { name: /^Pendentes/ }).click()
  await expect(page.getByText('Nenhuma entrada aqui')).toBeVisible()
  await page.getByRole('button', { name: /^Todas/ }).click()

  await page.getByRole('searchbox').fill('hatchet')
  await expect(rows(page)).toHaveCount(1)
  await rows(page).first().click()
  await page.getByRole('searchbox').fill('')
  await expect(rows(page)).toHaveCount(4)

  const editor = page.getByRole('textbox', { name: 'Tradução' })
  await expect(editor).toHaveValue('[PT] A reliable tool.')
  await editor.fill('Uma ferramenta confiável.')
  await editor.press('Control+Enter')
  await expect(progress(page)).toHaveText('2 confirmadas · 2 a revisar · 0 pendentes')
  await expect(rows(page).nth(2)).toContainText('Uma ferramenta confiável.')
  await expect(rows(page).nth(2)).toContainText('Confirmado')
})

test('keeps a glossary for the target language', async ({ page }) => {
  await page.goto('/')
  // Portuguese starts from the glossary bundled with the app.
  const link = page.getByRole('button', { name: /Glossário: \d+ termos/ })
  const before = Number((await link.textContent())!.match(/\d+/)![0])
  await link.click()
  await expect(page.getByRole('heading', { name: 'Glossário' })).toBeVisible()
  await expect(page.getByText(/este é o de Português \(Brasil\)/)).toBeVisible()

  await page.getByLabel('Termo original').fill('sword')
  await page.getByLabel('Deve virar').fill('espada')
  await page.getByRole('button', { name: 'Adicionar termo' }).click()
  await expect(page.getByText(`${before + 1} termos · salvo automaticamente`)).toBeVisible()

  await page.getByRole('button', { name: 'Voltar à tradução' }).click()
  await expect(page.getByRole('button', { name: `Glossário: ${before + 1} termos` })).toBeVisible()
  // The inspector points out the term in the selected text.
  await rows(page).first().click()
  await expect(page.getByText('sword → espada')).toBeVisible()

  // Another target language has its own, empty glossary.
  await page.locator('select[name=target]').selectOption('es_ES')
  await expect(page.getByRole('button', { name: 'Glossário: 0 termos' })).toBeVisible()
  await page.locator('select[name=target]').selectOption('pt_BR')
  await expect(page.getByRole('button', { name: `Glossário: ${before + 1} termos` })).toBeVisible()
})

test('exports an XML where only the translated texts changed', async ({ page }) => {
  await page.goto('/')
  await expect(rows(page)).toHaveCount(4)
  answerNextPrompt(page, outPath)
  await page.getByRole('button', { name: 'Exportar XML' }).click()
  await expect(page.getByText('XML exportado.')).toBeVisible()

  const original = fs.readFileSync(xmlPath, 'utf8')
  const expected = original
    .replace('A short sword.', '[PT] A short sword.')
    .replace('Blocks <b>fire</b>.', '[PT] Blocks <b>fire</b>.')
    .replace('A reliable tool.', 'Uma ferramenta confiável.')
    .replace('The ink is still readable.', '[PT] The ink is still readable.')
  expect(fs.readFileSync(outPath, 'utf8')).toBe(expected)
})

test('settings: theme, language and an API key that is not stored in plain text', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Configurações' }).click()
  await expect(page.getByRole('heading', { name: 'Configurações' })).toBeVisible()

  await page.getByRole('button', { name: 'Claro' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.getByRole('button', { name: 'Âmbar' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-accent', 'amber')
  await page.getByRole('button', { name: 'Escuro' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')

  await page.getByLabel('Idioma do aplicativo').selectOption('en_US')
  await expect(page.getByRole('heading', { name: 'Settings' })).toBeVisible()
  await expect(page.locator('html')).toHaveAttribute('lang', 'en')
  await page.getByLabel('App language').selectOption('pt_BR')
  await expect(page.getByRole('heading', { name: 'Configurações' })).toBeVisible()

  const deepl = page.locator('div.border-t', { hasText: 'DeepL' }).first()
  await expect(deepl).toContainText('Sem chave')
  await deepl.getByRole('button', { name: 'Adicionar' }).click()
  await page.getByLabel('Chave de API de DeepL').fill('e2e-secret-key-42')
  await deepl.getByRole('button', { name: 'Salvar' }).click()
  await expect(deepl).toContainText('Chave salva')
  expect(fs.readFileSync(configPath, 'utf8')).not.toContain('e2e-secret-key-42')
})

test('a provider without a key explains itself instead of translating', async ({ page }) => {
  await page.goto('/')
  await expect(rows(page)).toHaveCount(4)
  await page.locator('select[name=provider]').selectOption('Microsoft Azure')
  await page.getByRole('complementary').getByRole('button', { name: 'Traduzir', exact: true }).click()
  await expect(page.getByText('Este provedor precisa de uma chave de API. Adicione em Configurações.')).toBeVisible()
  await page.locator('select[name=provider]').selectOption('Ollama (Local)')
})

test('a new version shows its release notes inside the app', async ({ page }) => {
  await page.route('**/api/state', async (route) => {
    const response = await route.fetch()
    const state = await response.json()
    state.update = {
      ...state.update,
      available: true,
      version: '9.9.9',
      notes: '## Novo\n- **Glossário** por idioma\n\n## Corrigido\n- Exportação preserva o arquivo',
    }
    await route.fulfill({ response, json: state })
  })
  await page.goto('/')
  const dialog = page.getByRole('dialog')
  await expect(dialog.getByRole('heading', { name: 'O que chegou na 9.9.9' })).toBeVisible()
  await expect(dialog.getByRole('heading', { name: 'Novo' })).toBeVisible()
  await expect(dialog.getByText('Glossário por idioma')).toBeVisible()
  await expect(dialog.getByText('Exportação preserva o arquivo')).toBeVisible()

  await dialog.getByRole('button', { name: 'Depois' }).click()
  await expect(dialog).toBeHidden()
  // Dismissed, it stays reachable from the footer.
  await page.getByRole('button', { name: 'Nova versão 9.9.9: ver novidades' }).click()
  await expect(dialog).toBeVisible()
})

test('going back to the fields keeps the current choice', async ({ page }) => {
  await page.goto('/')
  await page.getByTitle('Alterar campos').click()
  await expect(page.getByRole('heading', { name: 'O que vamos traduzir?' })).toBeVisible()
  await expect(tagGroup(page, 'Campos para traduzir').getByRole('button', { name: 'description' })).toHaveAttribute('aria-pressed', 'true')
  await expect(tagGroup(page, 'Campos de contexto').getByRole('button', { name: 'name', exact: true })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: 'Voltar à tradução' }).click()
  await expect(progress(page)).toHaveText('2 confirmadas · 2 a revisar · 0 pendentes')
})

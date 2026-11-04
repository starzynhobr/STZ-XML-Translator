import { expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

// Real UI and local engine with a made-up sample game; no provider calls or feedback sends.
const headers = { Authorization: 'Bearer e2e-token' }
const output = path.resolve(import.meta.dirname, '../../dist/site-screenshots/v170')
const game = path.join(import.meta.dirname, '.tmp', 'Ember Saga')
const xmls = path.join(game, 'Ember Saga_Data', 'XMLs')

const ITEMS = [
  ['Ember Blade', 'A short sword forged in dragon fire.', 'Lâmina de Brasa', 'Uma espada curta forjada no fogo de dragão.'],
  ['Frost Shield', 'Blocks <b>fire</b> damage for 3 turns.', 'Escudo de Gelo', 'Bloqueia dano de <b>fogo</b> por 3 turnos.'],
  ['Iron Hatchet', 'A reliable tool for any traveler.', 'Machadinha de Ferro', 'Uma ferramenta confiável para qualquer viajante.'],
  ['Old Map', 'The ink is still readable.', '', ''],
  ['Moonstone Ring', 'Restores {AMOUNT} mana at dawn.', '', ''],
  ['Healing Draught', 'Heals {AMOUNT} HP over time.', '', ''],
  ['Storm Bow', 'Arrows chain lightning to nearby foes.', '', ''],
  ['Wanderer Cloak', 'Grants stealth while standing still.', '', ''],
]

function writeGame() {
  fs.rmSync(game, { recursive: true, force: true })
  fs.mkdirSync(xmls, { recursive: true })
  fs.writeFileSync(path.join(game, 'Ember Saga.exe'), 'MZ')
  const items = ITEMS.map(([name, description], i) =>
    `  <item id="${i + 1}" rarity="common">\n    <name>${name}</name>\n    <description><![CDATA[${description}]]></description>\n    <icon>icons/item_${i + 1}.png</icon>\n  </item>`).join('\n')
  fs.writeFileSync(path.join(xmls, 'items.xml'), `<?xml version="1.0" encoding="UTF-8"?>\n<items>\n${items}\n</items>\n`)
  const quests = ['The Ashen Road', 'Whispers in the Mine', 'A Crown of Thorns'].map((title, i) =>
    `  <quest id="${i + 1}">\n    <title>${title}</title>\n    <summary>Speak with the elder in Hollow Vale.</summary>\n  </quest>`).join('\n')
  fs.writeFileSync(path.join(xmls, 'quests.xml'), `<?xml version="1.0" encoding="UTF-8"?>\n<quests>\n${quests}\n</quests>\n`)
  fs.writeFileSync(path.join(xmls, 'npcs.xml'), `<?xml version="1.0" encoding="UTF-8"?>\n<npcs>\n  <npc id="1">\n    <name>Elder Maren</name>\n    <greeting>Welcome, traveler. The road is dark tonight.</greeting>\n  </npc>\n</npcs>\n`)
}

test('captures the current interface for the project page', async ({ page }) => {
  fs.mkdirSync(output, { recursive: true })
  writeGame()
  await page.request.post('/api/xml/close', { headers })
  await page.request.post('/api/projects/close', { headers })
  await page.request.put('/api/settings', { headers, data: { locale: 'en_US', target: 'pt_BR', theme: 'dark', accent: 'amber' } })
  for (const old of (await (await page.request.get('/api/projects', { headers })).json()).projects) {
    if (old.name === 'Ember Saga') await page.request.delete(`/api/projects/${old.id}`, { headers })
  }
  const project = await (await page.request.post('/api/projects', { headers, data: { folder: game, name: 'Ember Saga' } })).json()
  await page.request.post(`/api/projects/${project.id}/open`, { headers })

  // Some progress: three items translated by hand.
  await page.request.post('/api/xml/open', { headers, data: { path: path.join(xmls, 'items.xml') } })
  await page.request.post('/api/xml/load', { headers, data: { parent: 'item', targets: ['name', 'description'], contexts: [] } })
  const { entries } = await (await page.request.get('/api/entries', { headers })).json()
  for (const [name, description, ptName, ptDescription] of ITEMS) {
    for (const [original, text] of [[name, ptName], [description, ptDescription]]) {
      const entry = entries.find((e: { original: string }) => e.original === original)
      if (entry && text) await page.request.post('/api/entries/edit', { headers, data: { id: entry.id, text } })
    }
  }
  await page.request.post('/api/xml/close', { headers })
  await page.request.post('/api/projects/close', { headers })

  await page.setViewportSize({ width: 1440, height: 900 })
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Projects', exact: true })).toBeVisible()
  await page.screenshot({ path: path.join(output, 'projects.png') })

  await page.getByRole('button', { name: /Labs/ }).click()
  await expect(page.getByRole('dialog', { name: 'STZ Labs' })).toBeVisible()
  await page.screenshot({ path: path.join(output, 'stz-labs.png') })
  await page.keyboard.press('Escape')

  await page.getByText('Ember Saga', { exact: true }).click()
  await expect(page.getByRole('button', { name: /quests\.xml/ })).toBeVisible()
  await page.screenshot({ path: path.join(output, 'project-files.png') })

  await page.getByRole('button', { name: /quests\.xml/ }).click()
  await expect(page.getByRole('button', { name: /^Load \d+ entries$/ })).toBeVisible()
  await page.screenshot({ path: path.join(output, 'field-selection.png') })
  await page.getByRole('button', { name: /^Load \d+ entries$/ }).click()
  await expect(page.getByRole('searchbox')).toBeVisible()
  await page.getByRole('button', { name: /Back to project Ember Saga/ }).click()

  await page.getByRole('listitem').filter({ hasText: 'items.xml' }).getByRole('button').first().click()
  await expect(page.getByRole('searchbox')).toBeVisible()
  await page.screenshot({ path: path.join(output, 'workspace-dark.png') })

  await page.getByRole('button', { name: 'Settings', exact: true }).click()
  await page.getByRole('button', { name: 'Light', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light')
  await page.getByRole('button', { name: 'Back to translation', exact: true }).click()
  await expect(page.getByRole('searchbox')).toBeVisible()
  await page.screenshot({ path: path.join(output, 'workspace-light.png') })
  await page.request.put('/api/settings', { headers, data: { theme: 'dark' } })
})

test.afterAll(async ({ request }) => {
  await request.post('/api/xml/close', { headers })
  await request.post('/api/projects/close', { headers })
})

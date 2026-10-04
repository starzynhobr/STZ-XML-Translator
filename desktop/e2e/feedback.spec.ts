import { expect, test } from '@playwright/test'

test('feedback keeps text on failure and uses the displayed limit', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Configurações' }).click()
  await page.getByRole('button', { name: 'Enviar feedback', exact: true }).click()
  const field = page.getByRole('textbox', { name: 'Enviar feedback', exact: true })
  await expect(field).toHaveAttribute('maxlength', '400')
  await field.fill('Teste do formulário sem envio externo.')
  await page.route('**/api/feedback', (route) => route.fulfill({
    status: 429, contentType: 'application/json', body: JSON.stringify({ error: 'feedback_rate_limited' }),
  }))
  await page.getByRole('button', { name: 'Enviar', exact: true }).click()
  await expect(page.getByText('Muitos envios seguidos. Tente de novo mais tarde.')).toBeVisible()
  await expect(field).toHaveValue('Teste do formulário sem envio externo.')
  await page.unroute('**/api/feedback')
  await page.route('**/api/feedback', (route) => route.fulfill({
    status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true }),
  }))
  await page.getByRole('button', { name: 'Enviar', exact: true }).click()
  await expect(field).not.toBeVisible()
})

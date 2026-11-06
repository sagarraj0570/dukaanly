import { Page, TestInfo, expect } from '@playwright/test'
import * as fs from 'fs'
import * as path from 'path'

export interface OverflowCheckResult {
  hasOverflow: boolean
  scrollWidth: number
  innerWidth: number
  offendingElements: string[]
}

export async function checkNoHorizontalOverflow(page: Page): Promise<OverflowCheckResult> {
  return await page.evaluate(() => {
    const scrollWidth = document.documentElement.scrollWidth
    const innerWidth = window.innerWidth
    const offending: string[] = []

    if (scrollWidth > innerWidth + 1) {
      // Find elements pushing the page wide
      const all = document.querySelectorAll('*')
      for (const el of Array.from(all)) {
        if (!(el instanceof HTMLElement)) continue
        // Ignore intentional scroll containers
        const style = window.getComputedStyle(el)
        if (style.overflowX === 'auto' || style.overflowX === 'scroll' || el.classList.contains('scroll-snap-x')) {
          continue
        }
        const rect = el.getBoundingClientRect()
        if (rect.right > innerWidth + 2 && rect.width > 0 && rect.height > 0) {
          const selector = el.tagName.toLowerCase() + 
            (el.id ? `#${el.id}` : '') + 
            (el.className ? `.${el.className.split(' ').slice(0, 2).join('.')}` : '')
          offending.push(`${selector} (right: ${Math.round(rect.right)}px > ${innerWidth}px)`)
          if (offending.length >= 5) break
        }
      }
    }

    return {
      hasOverflow: scrollWidth > innerWidth + 1,
      scrollWidth,
      innerWidth,
      offendingElements: offending,
    }
  })
}

export async function checkInputFontSizes(page: Page): Promise<{ selector: string; fontSize: number }[]> {
  return await page.evaluate(() => {
    const smallInputs: { selector: string; fontSize: number }[] = []
    const inputs = document.querySelectorAll('input:not([type="checkbox"]):not([type="radio"]), select, textarea')
    for (const el of Array.from(inputs)) {
      if (!(el instanceof HTMLElement)) continue
      const style = window.getComputedStyle(el)
      const size = parseFloat(style.fontSize)
      if (size < 15.5) {
        const selector = el.tagName.toLowerCase() + (el.id ? `#${el.id}` : '')
        smallInputs.push({ selector, fontSize: size })
      }
    }
    return smallInputs
  })
}

export async function checkTouchTargets(page: Page): Promise<string[]> {
  return await page.evaluate(() => {
    const offenders: string[] = []
    const clickables = document.querySelectorAll('button:not([disabled]), a[href], input[type="button"], input[type="submit"]')
    
    for (const el of Array.from(clickables)) {
      if (!(el instanceof HTMLElement)) continue
      // Skip hidden elements
      const style = window.getComputedStyle(el)
      if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') continue
      
      const rect = el.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) continue

      // Allowlist: inline breadcrumbs, copyright links, small legal notes, internal tag chips
      if (
        el.closest('nav[aria-label="Breadcrumb"]') || 
        el.closest('footer') || 
        el.classList.contains('allow-small-target') ||
        rect.width >= 40 && rect.height >= 40 // Allow slight border variance down to 40px
      ) {
        continue
      }

      if (rect.width < 36 || rect.height < 36) {
        const selector = el.tagName.toLowerCase() + 
          (el.id ? `#${el.id}` : '') + 
          (el.innerText ? ` ("${el.innerText.trim().slice(0, 15)}")` : '')
        offenders.push(`${selector} (${Math.round(rect.width)}x${Math.round(rect.height)}px)`)
        if (offenders.length >= 8) break
      }
    }
    return offenders
  })
}

export async function saveScreenshot(page: Page, testInfo: TestInfo, name: string) {
  const dir = path.join(process.cwd(), 'tests', 'responsive', 'artifacts')
  if (!fs.existsSync(dir)) {
    fs.mkdirSync(dir, { recursive: true })
  }
  const cleanProjectName = testInfo.project.name.replace(/[^a-zA-Z0-9_-]/g, '_')
  const filename = `${cleanProjectName}_${name}.png`
  await page.screenshot({ path: path.join(dir, filename), fullPage: true })
}

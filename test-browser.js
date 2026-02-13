#!/usr/bin/env node
/**
 * Browser test for treemap - loads page and verifies Voronoi renders
 */
const { chromium } = require('playwright');
const http = require('http');
const fs = require('fs');
const path = require('path');

const port = 3847;
const server = http.createServer((req, res) => {
  const file = req.url === '/' || req.url === '/treemap.html' ? 'treemap.html' : req.url.slice(1).split('?')[0];
  const f = path.join(__dirname, file);
  try {
    const data = fs.readFileSync(f);
    const ct = file.endsWith('.js') ? 'application/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html';
    res.writeHead(200, { 'Content-Type': ct });
    res.end(data);
  } catch {
    res.writeHead(404);
    res.end();
  }
});

(async () => {
  await new Promise(r => server.listen(port, r));
  
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage();
  
  const errors = [];
  page.on('pageerror', err => errors.push('Page error: ' + err.message));
  page.on('console', msg => {
    const t = msg.type();
    const text = msg.text();
    if (t === 'error' && !text.includes('favicon')) errors.push('Console: ' + text);
  });

  await page.goto(`http://localhost:${port}/`, { waitUntil: 'networkidle', timeout: 20000 });

  await page.waitForSelector('rect', { timeout: 5000 });

  const hasCells = await page.evaluate(() => document.querySelectorAll('rect').length);
  const hasLegend = await page.evaluate(() => document.querySelectorAll('.legend-item').length > 0);

  await browser.close();
  server.close();

  console.log('--- Browser Test ---');
  console.log('Treemap cells:', hasCells);
  console.log('Legend items:', hasLegend);
  if (errors.length) {
    console.log('Errors:', errors);
  }

  if (hasCells < 50) {
    console.error('Expected many cells, got', hasCells);
    process.exit(1);
  }
  if (!hasLegend) {
    console.error('Legend not populated');
    process.exit(1);
  }
  if (errors.length) {
    console.error('JS errors occurred');
    process.exit(1);
  }
  console.log('Browser test passed.');
  process.exit(0);
})().catch(err => {
  console.error('Test failed:', err.message);
  process.exit(1);
});

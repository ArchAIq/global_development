/**
 * Merge CDC_midbln.csv and CDC_IPO.csv, remove duplicates by brand_name,
 * and output JSON for treemap (companies by revenue)
 */
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname);
const midbln = fs.readFileSync(path.join(root, 'CDC_midbln.csv'), 'utf8');
const ipo = fs.readFileSync(path.join(root, 'CDC_IPO.csv'), 'utf8');
const cis = fs.readFileSync(path.join(root, 'CDC_CIS_100mln.csv'), 'utf8');

function parseCSV(text) {
  const lines = text.trim().split('\n');
  const header = lines[0].split(',');
  const rows = [];
  for (let i = 1; i < lines.length; i++) {
    const values = [];
    let current = '';
    let inQuotes = false;
    for (let j = 0; j < lines[i].length; j++) {
      const c = lines[i][j];
      if (c === '"') {
        inQuotes = !inQuotes;
      } else if (inQuotes) {
        current += c;
      } else if (c === ',') {
        values.push(current.trim());
        current = '';
      } else {
        current += c;
      }
    }
    values.push(current.trim());
    const row = {};
    header.forEach((h, idx) => row[h.trim()] = values[idx] || '');
    rows.push(row);
  }
  return rows;
}

function parseRevenue(val) {
  if (val == null || val === '') return NaN;
  const n = parseFloat(String(val).replace(/,/g, ''));
  return isNaN(n) ? NaN : n;
}

function normalizeName(name) {
  return (name || '')
    .trim()
    .replace(/\s*\([^)]+\)\s*$/g, '') // strip parenthetical suffixes like (CDL)
    .toLowerCase()
    .replace(/\s+/g, ' ');
}

const midblnRows = parseCSV(midbln);
const ipoRows = parseCSV(ipo);
const cisRows = parseCSV(cis);

const byKey = new Map();

function addRow(row) {
  const name = (row.brand_name || row.hq_office || '').trim();
  const key = normalizeName(name);
  const rev = parseRevenue(row.last_Y);
  if (!key) return;
  const existing = byKey.get(key);
  if (!existing) {
    byKey.set(key, { ...row, revenue: rev });
  } else {
    const existingRev = parseRevenue(existing.last_Y);
    if (rev > existingRev || (isNaN(existingRev) && !isNaN(rev))) {
      byKey.set(key, { ...row, revenue: rev });
    }
  }
}

midblnRows.forEach(addRow);
ipoRows.forEach(addRow);
cisRows.forEach(addRow);

const companies = Array.from(byKey.values())
  .filter(c => !isNaN(c.revenue) && c.revenue > 0)
  .sort((a, b) => b.revenue - a.revenue)
  .map(c => ({
    name: (c.brand_name || c.hq_office || '').trim(),
    revenue: c.revenue,
    country: c.country || '',
    ipo: (c.IPO || '').trim() || null,
  }));

const output = {
  companies,
  totalRevenue: companies.reduce((s, c) => s + c.revenue, 0),
};

fs.writeFileSync(
  path.join(root, 'companies-by-revenue.json'),
  JSON.stringify(output, null, 2),
  'utf8'
);

// Update embedded data in treemap.html
const treemapPath = path.join(root, 'treemap.html');
let treemapHtml = fs.readFileSync(treemapPath, 'utf8');
const dataJson = JSON.stringify({ companies: output.companies, totalRevenue: output.totalRevenue });
const dataRegex = /const data = \{[\s\S]*?\};/;
if (dataRegex.test(treemapHtml)) {
  treemapHtml = treemapHtml.replace(dataRegex, `const data = ${dataJson};`);
  fs.writeFileSync(treemapPath, treemapHtml, 'utf8');
  console.log('Updated treemap.html with new data.');
}

console.log(`Merged ${companies.length} companies (deduplicated). Total revenue: ${output.totalRevenue.toLocaleString()} M`);
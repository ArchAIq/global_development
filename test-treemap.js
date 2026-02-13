#!/usr/bin/env node
/**
 * Test treemap.html - verify data, structure, and basic functionality
 */
const fs = require('fs');
const path = require('path');

const htmlPath = path.join(__dirname, 'treemap.html');
const html = fs.readFileSync(htmlPath, 'utf8');

const errors = [];
let passed = 0;

// 1. Data is embedded and valid JSON
const dataStart = html.indexOf('const data = ');
const dataEnd = html.indexOf('};', dataStart) + 1;
const dataStr = dataStart >= 0 && dataEnd > dataStart ? html.slice(dataStart + 12, dataEnd) : '';
if (!dataStr) {
  errors.push('Could not find embedded data in HTML');
} else {
  try {
    const data = JSON.parse(dataStr);
    if (!data.companies || !Array.isArray(data.companies)) {
      errors.push('Data must have companies array');
    } else {
      const count = data.companies.length;
      if (count < 100) errors.push(`Expected ~142 companies, got ${count}`);
      else passed++;
      
      const sample = data.companies[0];
      if (!sample.name || typeof sample.revenue !== 'number' || !sample.country) {
        errors.push('Company objects need name, revenue, country');
      } else passed++;
    }
  } catch (e) {
    errors.push('Invalid data JSON: ' + e.message);
  }
}

// 2. Required scripts present
const scripts = ['d3.v7'];
const requiredScripts = ['d3.v7'];
requiredScripts.forEach(s => {
  if (html.includes(s)) passed++;
  else errors.push(`Missing script: ${s}`);
});

// 3. Traditional treemap
if (html.includes('d3.treemap')) passed++;
else errors.push('Missing d3.treemap');

// 4. Color scale and legend
if (html.includes('colorScale') && html.includes('legend')) passed++;
else errors.push('Missing colorScale or legend');

console.log('--- Treemap Test ---');
console.log(`Passed: ${passed}`);
if (errors.length) {
  console.log('Errors:');
  errors.forEach(e => console.log('  -', e));
  process.exit(1);
}
console.log('All checks passed.');
process.exit(0);

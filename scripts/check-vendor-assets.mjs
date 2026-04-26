import { readdir, readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const ROOT = process.cwd();
const problems = new Set();

const forbiddenTextPatterns = [
  'XMLHttpRequest',
  'xhr.open',
  'eval(',
  'fetch(',
  'importScripts(',
  '@import url(',
  'unpkg.com',
  'cdn.jsdelivr',
  'cdnjs.cloudflare',
  '__placeholder',
  'placeholder'
];

const leafletSignatures = ['L.Map', 'L.map', 'Leaflet', 'version:"1.9.4"', 'version: "1.9.4"'];
const markerClusterSignatures = ['MarkerClusterGroup', 'markerClusterGroup'];
const openingHoursSignatures = ['opening_hours'];

function resolvePath(relativePath) {
  return path.join(ROOT, relativePath);
}

function addProblem(message) {
  problems.add(message);
}

async function ensureFileExistsAndNotEmpty(relativePath) {
  const fullPath = resolvePath(relativePath);
  try {
    const info = await stat(fullPath);
    if (!info.isFile()) {
      addProblem(`${relativePath}: expected a file.`);
      return false;
    }
    if (info.size <= 0) {
      addProblem(`${relativePath}: file is empty (0 bytes).`);
      return false;
    }
    return true;
  } catch {
    addProblem(`${relativePath}: missing file.`);
    return false;
  }
}

async function readTextFile(relativePath) {
  return readFile(resolvePath(relativePath), 'utf8');
}

function checkForbiddenPatterns(relativePath, text) {
  for (const pattern of forbiddenTextPatterns) {
    if (text.includes(pattern)) {
      addProblem(`${relativePath}: contains forbidden pattern "${pattern}".`);
    }
  }
}

function checkSignatures(relativePath, text, signatures, description) {
  if (!signatures.some((signature) => text.includes(signature))) {
    addProblem(`${relativePath}: missing expected ${description} signature.`);
  }
}

async function checkTextFile(relativePath, { signatures = null, signatureName = '' } = {}) {
  const ok = await ensureFileExistsAndNotEmpty(relativePath);
  if (!ok) return;

  const text = await readTextFile(relativePath);
  checkForbiddenPatterns(relativePath, text);

  if (signatures) {
    checkSignatures(relativePath, text, signatures, signatureName);
  }
}

async function checkBinaryFile(relativePath) {
  await ensureFileExistsAndNotEmpty(relativePath);
}

async function detectFontReferences() {
  const cssPath = 'vendor/fontawesome/css/all.min.css';
  const ok = await ensureFileExistsAndNotEmpty(cssPath);
  if (!ok) return [];

  const cssText = await readTextFile(cssPath);
  checkForbiddenPatterns(cssPath, cssText);

  const matches = cssText.matchAll(/\.\.\/webfonts\/([^)"'?#]+\.(?:woff2?|ttf|eot|otf|svg))(?:[?#][^)"']*)?/gi);
  const referenced = [...new Set(Array.from(matches, (match) => match[1]))];

  if (!referenced.includes('fa-solid-900.woff2')) {
    addProblem(`${cssPath}: does not reference ../webfonts/fa-solid-900.woff2.`);
  }

  return referenced;
}

async function checkNoForbiddenPatternsInVendorTextFiles() {
  async function walk(currentDir) {
    const entries = await readdir(currentDir, { withFileTypes: true });
    for (const entry of entries) {
      const fullPath = path.join(currentDir, entry.name);
      if (entry.isDirectory()) {
        await walk(fullPath);
        continue;
      }

      const ext = path.extname(entry.name).toLowerCase();
      if (!['.js', '.mjs', '.cjs', '.css', '.txt', '.map'].includes(ext)) {
        continue;
      }

      const relativePath = path.relative(ROOT, fullPath).replaceAll(path.sep, '/');
      const text = await readFile(fullPath, 'utf8');
      checkForbiddenPatterns(relativePath, text);
    }
  }

  await walk(resolvePath('vendor'));
}

async function main() {
  await checkTextFile('vendor/leaflet/leaflet.js', {
    signatures: leafletSignatures,
    signatureName: 'Leaflet'
  });
  await checkTextFile('vendor/leaflet/leaflet.css');

  const leafletImages = [
    'vendor/leaflet/images/layers.png',
    'vendor/leaflet/images/layers-2x.png',
    'vendor/leaflet/images/marker-icon.png',
    'vendor/leaflet/images/marker-icon-2x.png',
    'vendor/leaflet/images/marker-shadow.png'
  ];
  for (const imagePath of leafletImages) {
    await checkBinaryFile(imagePath);
  }

  await checkTextFile('vendor/leaflet.markercluster/MarkerCluster.css');
  await checkTextFile('vendor/leaflet.markercluster/MarkerCluster.Default.css');
  await checkTextFile('vendor/leaflet.markercluster/leaflet.markercluster.js', {
    signatures: markerClusterSignatures,
    signatureName: 'MarkerCluster'
  });

  await checkTextFile('vendor/opening_hours/opening_hours.min.js', {
    signatures: openingHoursSignatures,
    signatureName: 'opening_hours'
  });

  const referencedFonts = await detectFontReferences();
  await checkBinaryFile('vendor/fontawesome/webfonts/fa-solid-900.woff2');
  for (const fontName of referencedFonts) {
    await checkBinaryFile(`vendor/fontawesome/webfonts/${fontName}`);
  }

  await checkNoForbiddenPatternsInVendorTextFiles();

  if (problems.size > 0) {
    console.error('Vendor asset check failed:');
    for (const problem of [...problems].sort()) {
      console.error(`- ${problem}`);
    }
    process.exit(1);
  }

  console.log('Vendor asset check passed.');
}

main().catch((error) => {
  console.error(`Vendor asset check failed: ${error.message}`);
  process.exit(1);
});

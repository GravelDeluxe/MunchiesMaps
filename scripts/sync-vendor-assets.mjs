import { copyFile, mkdir, readdir, readFile, stat } from 'node:fs/promises';
import path from 'node:path';
import process from 'node:process';

const ROOT = process.cwd();

function abs(...parts) {
  return path.join(ROOT, ...parts);
}

async function ensureSourceExists(relativePath) {
  const fullPath = abs(relativePath);
  try {
    const info = await stat(fullPath);
    if (!info.isFile() && !info.isDirectory()) {
      throw new Error(`Not a regular file or directory: ${relativePath}`);
    }
    return fullPath;
  } catch {
    throw new Error(`Missing vendor source: ${relativePath}\nRun npm install first.`);
  }
}

async function copyFileChecked(sourceRelativePath, targetRelativePath, copied) {
  const source = await ensureSourceExists(sourceRelativePath);
  const target = abs(targetRelativePath);
  await mkdir(path.dirname(target), { recursive: true });
  await copyFile(source, target);
  copied.push(`${sourceRelativePath} -> ${targetRelativePath}`);
}

async function collectFontReferences(fontAwesomeCssPath) {
  const cssSource = await readFile(fontAwesomeCssPath, 'utf8');
  const matches = cssSource.matchAll(/\.\.\/webfonts\/([^)"'?#]+\.(?:woff2?|ttf|eot|otf|svg))(?:[?#][^)"']*)?/gi);
  return [...new Set(Array.from(matches, (match) => match[1]))];
}

function isOpeningHoursTextValid(text) {
  const forbiddenPatterns = [
    'XMLHttpRequest',
    'xhr.open',
    'eval(',
    'cdn.jsdelivr',
    'unpkg.com',
    'cdnjs.cloudflare',
    '__placeholder',
    'placeholder'
  ];

  return text.includes('opening_hours') && !forbiddenPatterns.some((pattern) => text.includes(pattern));
}

async function isValidOpeningHoursAsset(fullPath) {
  try {
    const info = await stat(fullPath);
    if (!info.isFile() || info.size <= 0) return false;

    const text = await readFile(fullPath, 'utf8');
    return isOpeningHoursTextValid(text);
  } catch {
    return false;
  }
}

async function findOpeningHoursSource() {
  const candidateRelativePaths = [
    'node_modules/opening_hours/build/opening_hours.min.js',
    'node_modules/opening_hours/build/opening_hours.js',
    'node_modules/opening_hours/opening_hours.min.js',
    'node_modules/opening_hours/opening_hours.js',
    'node_modules/opening_hours/dist/opening_hours.min.js',
    'node_modules/opening_hours/dist/opening_hours.js'
  ];

  for (const candidate of candidateRelativePaths) {
    const fullPath = abs(candidate);
    if (await isValidOpeningHoursAsset(fullPath)) {
      return fullPath;
    }
  }

  const openingHoursRoot = abs('node_modules/opening_hours');
  try {
    const entries = await readdir(openingHoursRoot, { recursive: true, withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isFile()) continue;
      if (!/^opening_hours.*\.js$/i.test(entry.name)) continue;

      const candidate = path.join(entry.parentPath, entry.name);
      if (await isValidOpeningHoursAsset(candidate)) {
        return candidate;
      }
    }
  } catch {
    // opening_hours package may not exist in node_modules.
  }

  return null;
}

async function main() {
  const copied = [];

  await copyFileChecked('node_modules/leaflet/dist/leaflet.js', 'vendor/leaflet/leaflet.js', copied);
  await copyFileChecked('node_modules/leaflet/dist/leaflet.css', 'vendor/leaflet/leaflet.css', copied);

  const leafletImages = [
    'layers.png',
    'layers-2x.png',
    'marker-icon.png',
    'marker-icon-2x.png',
    'marker-shadow.png'
  ];

  for (const imageName of leafletImages) {
    await copyFileChecked(
      `node_modules/leaflet/dist/images/${imageName}`,
      `vendor/leaflet/images/${imageName}`,
      copied
    );
  }

  await copyFileChecked(
    'node_modules/leaflet.markercluster/dist/leaflet.markercluster.js',
    'vendor/leaflet.markercluster/leaflet.markercluster.js',
    copied
  );
  await copyFileChecked(
    'node_modules/leaflet.markercluster/dist/MarkerCluster.css',
    'vendor/leaflet.markercluster/MarkerCluster.css',
    copied
  );
  await copyFileChecked(
    'node_modules/leaflet.markercluster/dist/MarkerCluster.Default.css',
    'vendor/leaflet.markercluster/MarkerCluster.Default.css',
    copied
  );

  const openingHoursTargetRelativePath = 'vendor/opening_hours/opening_hours.min.js';
  const openingHoursTarget = abs(openingHoursTargetRelativePath);

  if (await isValidOpeningHoursAsset(openingHoursTarget)) {
    console.log('Keeping existing vendor/opening_hours/opening_hours.min.js');
  } else {
    const openingHoursSource = await findOpeningHoursSource();

    if (!openingHoursSource) {
      throw new Error(
        'No valid opening_hours source found. Existing vendor/opening_hours/opening_hours.min.js is missing or invalid.'
      );
    }

    await mkdir(abs('vendor/opening_hours'), { recursive: true });
    await copyFile(openingHoursSource, openingHoursTarget);
    copied.push(`${path.relative(ROOT, openingHoursSource)} -> ${openingHoursTargetRelativePath}`);
  }

  const fontAwesomeCssRelativePath = 'node_modules/@fortawesome/fontawesome-free/css/all.min.css';
  await copyFileChecked(fontAwesomeCssRelativePath, 'vendor/fontawesome/css/all.min.css', copied);

  const fontReferences = await collectFontReferences(abs(fontAwesomeCssRelativePath));

  if (!fontReferences.includes('fa-solid-900.woff2')) {
    throw new Error('Unexpected FontAwesome CSS: fa-solid-900.woff2 was not referenced in all.min.css');
  }

  for (const fontName of fontReferences) {
    await copyFileChecked(
      `node_modules/@fortawesome/fontawesome-free/webfonts/${fontName}`,
      `vendor/fontawesome/webfonts/${fontName}`,
      copied
    );
  }

  console.log('Synced vendor assets:');
  for (const file of copied) {
    console.log(`- ${file}`);
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});

import { copyFile, mkdir, readFile, stat } from 'node:fs/promises';
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

  const openingHoursCandidates = [
    'node_modules/opening_hours/build/opening_hours.min.js',
    'node_modules/opening_hours/opening_hours.min.js',
    'node_modules/opening_hours/dist/opening_hours.min.js'
  ];

  let openingHoursSource;
  for (const candidate of openingHoursCandidates) {
    try {
      openingHoursSource = await ensureSourceExists(candidate);
      break;
    } catch {
      // Try the next candidate.
    }
  }

  if (!openingHoursSource) {
    throw new Error(
      `Missing vendor source: ${openingHoursCandidates.join(' OR ')}\nRun npm install first.`
    );
  }

  await mkdir(abs('vendor/opening_hours'), { recursive: true });
  await copyFile(openingHoursSource, abs('vendor/opening_hours/opening_hours.min.js'));
  copied.push(`${path.relative(ROOT, openingHoursSource)} -> vendor/opening_hours/opening_hours.min.js`);

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

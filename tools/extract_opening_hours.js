#!/usr/bin/env node
"use strict";

const fs = require("fs");
const path = require("path");

const GEOJSON_ROOT = path.join(__dirname, "..", "resources", "geojson");
const OUTPUT_TXT = path.join(__dirname, "..", "resources", "opening_hours_unique.txt");
const OUTPUT_JSON = path.join(__dirname, "..", "resources", "opening_hours_unique.json");
const EXAMPLE_LIMIT = 10;

function normalizeOpeningHours(value) {
  if (typeof value !== "string") {
    return null;
  }

  let normalized = value.trim().replace(/\s+/g, " ");
  normalized = normalized.replace(/^opening_hours:\s*/i, "");
  normalized = normalized.trim().replace(/\s+/g, " ");

  if (!normalized) {
    return null;
  }

  return normalized;
}

async function walkDir(dirPath, files = []) {
  let entries;
  try {
    entries = await fs.promises.readdir(dirPath, { withFileTypes: true });
  } catch (error) {
    console.warn(`Warning: unable to read directory ${dirPath}: ${error.message}`);
    return files;
  }

  for (const entry of entries) {
    const fullPath = path.join(dirPath, entry.name);
    if (entry.isDirectory()) {
      await walkDir(fullPath, files);
    } else if (entry.isFile() && entry.name.toLowerCase().endsWith(".geojson")) {
      files.push(fullPath);
    }
  }

  return files;
}

async function processGeojson(filePath, counts) {
  let raw;
  try {
    raw = await fs.promises.readFile(filePath, "utf8");
  } catch (error) {
    console.warn(`Warning: unable to read file ${filePath}: ${error.message}`);
    return 0;
  }

  let data;
  try {
    data = JSON.parse(raw);
  } catch (error) {
    console.warn(`Warning: unable to parse JSON in ${filePath}: ${error.message}`);
    return 0;
  }

  if (!data || !Array.isArray(data.features)) {
    return 0;
  }

  let totalFound = 0;
  for (const feature of data.features) {
    const openingHours = feature?.properties?.opening_hours;
    const normalized = normalizeOpeningHours(openingHours);
    if (!normalized) {
      continue;
    }
    totalFound += 1;
    counts.set(normalized, (counts.get(normalized) || 0) + 1);
  }

  return totalFound;
}

async function main() {
  const counts = new Map();
  const geojsonFiles = await walkDir(GEOJSON_ROOT);

  let totalOccurrences = 0;
  for (const filePath of geojsonFiles) {
    totalOccurrences += await processGeojson(filePath, counts);
  }

  const unique = Array.from(counts.keys()).sort((a, b) => a.localeCompare(b));
  const top = Array.from(counts.entries())
    .map(([value, count]) => ({ value, count }))
    .sort((a, b) => (b.count - a.count) || a.value.localeCompare(b.value))
    .slice(0, 50);

  const outputJson = {
    unique,
    count_total: totalOccurrences,
    count_unique: unique.length,
    top,
  };

  try {
    await fs.promises.writeFile(OUTPUT_TXT, `${unique.join("\n")}\n`, "utf8");
    await fs.promises.writeFile(OUTPUT_JSON, `${JSON.stringify(outputJson, null, 2)}\n`, "utf8");
  } catch (error) {
    console.error(`Error: unable to write output files: ${error.message}`);
    process.exitCode = 1;
    return;
  }

  console.log("Opening hours extraction complete.");
  console.log(`GeoJSON files scanned: ${geojsonFiles.length}`);
  console.log(`Total occurrences: ${totalOccurrences}`);
  console.log(`Unique values: ${unique.length}`);
  console.log(`First ${Math.min(EXAMPLE_LIMIT, unique.length)} unique values:`);
  for (const value of unique.slice(0, EXAMPLE_LIMIT)) {
    console.log(`- ${value}`);
  }
}

main().catch((error) => {
  console.error(`Error: unexpected failure: ${error.message}`);
  process.exitCode = 1;
});

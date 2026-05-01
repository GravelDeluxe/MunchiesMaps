import assert from 'node:assert/strict';

const REGION_ORDER = {
  de: Array.from({ length: 16 }, (_, i) => `de-${i + 1}`),
  cz: Array.from({ length: 14 }, (_, i) => `cz-${i + 1}`),
  pl: Array.from({ length: 16 }, (_, i) => `pl-${String((i + 1) * 2).padStart(2, '0')}`)
};
const REGION_COUNTRIES = Object.keys(REGION_ORDER);
const COUNTRY_URL_ALIASES = { de: 'de', germany: 'de', cz: 'cz', czechia: 'cz', pl: 'pl', poland: 'pl' };
const URL_COUNTRY_TO_REGION_ORDER_KEY = {};
const URL_COUNTRY_ORDER = REGION_COUNTRIES.map((country) => country);
const normalizeUrlCountryToken = (value) => String(value || '').trim().toLowerCase().replace(/[_\s]+/g, '-');
const getRegionOrderKeyForUrlCountry = (urlCountry) => URL_COUNTRY_TO_REGION_ORDER_KEY[urlCountry] || urlCountry;
const canonicalUrlCountryCode = (value) => {
  const raw = normalizeUrlCountryToken(value);
  const alias = COUNTRY_URL_ALIASES[raw] || '';
  const key = getRegionOrderKeyForUrlCountry(alias);
  return Array.isArray(REGION_ORDER[key]) ? alias : '';
};
const getRegionOrder = (country) => REGION_ORDER[getRegionOrderKeyForUrlCountry(canonicalUrlCountryCode(country) || country)] || [];
const setEquals = (a, b) => a.size === b.size && [...a].every((v) => b.has(v));

function encodeActiveRegions(country, activeRegions) {
  const order = getRegionOrder(country);
  const bitString = order.map((id) => (activeRegions.has(id) ? '1' : '0')).join('');
  return parseInt(bitString, 2).toString(36);
}
function decodeActiveRegions(country, code) {
  const order = getRegionOrder(country);
  const value = parseInt(String(code), 36);
  if (!Number.isFinite(value)) return null;
  const bits = value.toString(2).padStart(order.length, '0');
  return new Set(order.filter((_, idx) => bits[idx] === '1'));
}
function parseRegionStateParam(value) {
  const result = {};
  for (const segment of String(value || '').split(';').map((s) => s.trim()).filter(Boolean)) {
    const [countryRaw, codeRaw] = segment.split(':');
    const country = canonicalUrlCountryCode(countryRaw);
    if (!country || !codeRaw) continue;
    const decoded = decodeActiveRegions(country, codeRaw);
    if (!(decoded instanceof Set)) continue;
    const existing = result[country];
    if (!(existing instanceof Set)) {
      result[country] = decoded;
      continue;
    }
    if (decoded.size === 0) continue;
    decoded.forEach((regionId) => existing.add(regionId));
  }
  return result;
}
function normalizeRegionStateByUrlCountry(stateByCountry) {
  const normalized = {};
  for (const [rawCountry, selection] of Object.entries(stateByCountry || {})) {
    const country = canonicalUrlCountryCode(rawCountry);
    if (!country || !(selection instanceof Set)) continue;
    if (!(normalized[country] instanceof Set)) normalized[country] = new Set();
    selection.forEach((regionId) => normalized[country].add(regionId));
  }
  return normalized;
}
function serializeRegionStateByCountry(stateByCountry) {
  const normalized = normalizeRegionStateByUrlCountry(stateByCountry);
  const parts = [];
  for (const country of URL_COUNTRY_ORDER) {
    const selection = normalized[country];
    if (!(selection instanceof Set) || selection.size === 0) continue;
    const encoded = encodeActiveRegions(country, selection);
    if (encoded !== '0') parts.push(`${country}:${encoded}`);
  }
  return parts.join(';');
}

const parsed = parseRegionStateParam('de:0;germany:8');
assert.equal(encodeActiveRegions('de', parsed.de), '8');

const serialized = serializeRegionStateByCountry({ de: new Set(), cz: new Set([REGION_ORDER.cz[0]]) });
assert.equal(serialized.startsWith('de:'), false);
assert.equal(serialized.includes('germany'), false);
assert.equal(serialized, `cz:${encodeActiveRegions('cz', new Set([REGION_ORDER.cz[0]]))}`);

assert.ok(parseRegionStateParam('de:8').de instanceof Set);

const roundTripSet = new Set([REGION_ORDER.de[12]]);
const roundTrip = parseRegionStateParam(serializeRegionStateByCountry({ de: roundTripSet }));
assert.ok(setEquals(roundTrip.de, roundTripSet));

const parsedAliases = parseRegionStateParam('cz:1o;pl:pa8;czechia:1o;germany:cnc;poland:pa8');
const serializedAliases = serializeRegionStateByCountry(parsedAliases);
assert.equal(serializedAliases.includes('czechia'), false);
assert.equal(serializedAliases.includes('germany'), false);
assert.equal(serializedAliases.includes('poland'), false);
assert.equal(serializedAliases.includes('cz:1o'), true);
assert.equal(serializedAliases.includes('de:cnc'), true);
assert.equal(serializedAliases.includes('pl:pa8'), true);

assert.equal(serializeRegionStateByCountry(parseRegionStateParam('de:0;germany:cnc')), 'de:cnc');
assert.equal(serializeRegionStateByCountry(parseRegionStateParam('germany:cnc;de:0')), 'de:cnc');
assert.equal(serializeRegionStateByCountry(parseRegionStateParam('pl:pa8;poland:pa8')), 'pl:pa8');
assert.equal(serializeRegionStateByCountry(parseRegionStateParam('cz:1o;czechia:1o')), 'cz:1o');

console.log('url-state smoke tests passed');

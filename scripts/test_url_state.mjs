import assert from 'node:assert/strict';

const REGION_ORDER = {
  de: Array.from({ length: 16 }, (_, i) => `de-${i + 1}`),
  cz: Array.from({ length: 14 }, (_, i) => `cz-${i + 1}`)
};
const REGION_COUNTRIES = Object.keys(REGION_ORDER);
const COUNTRY_CODE_ALIASES = { germany: 'de', czechia: 'cz' };

const normalizeTextToken = (value) => String(value || '').trim().toLowerCase().replace(/[_\s]+/g, '-');
const canonicalCountryCode = (value) => {
  const raw = normalizeTextToken(value);
  const alias = COUNTRY_CODE_ALIASES[raw] || raw;
  return Array.isArray(REGION_ORDER[alias]) ? alias : '';
};
const getRegionOrder = (country) => REGION_ORDER[country] || [];
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
    const country = canonicalCountryCode(countryRaw);
    if (!country || !codeRaw) continue;
    const decoded = decodeActiveRegions(country, codeRaw);
    if (!(decoded instanceof Set)) continue;
    const existing = result[country];
    if (!(existing instanceof Set) || (existing.size === 0 && decoded.size > 0)) result[country] = decoded;
  }
  return result;
}
function serializeRegionStateByCountry(stateByCountry) {
  const parts = [];
  for (const country of REGION_COUNTRIES) {
    const selection = stateByCountry[country];
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

console.log('url-state smoke tests passed');

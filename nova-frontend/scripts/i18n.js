/**
 * Translation checks.
 *
 *   node scripts/i18n.js check   every t()/tp()/m() string has an Arabic entry (CI)
 *   node scripts/i18n.js audit   English text still hard-coded in markup
 *
 * `check` reads the literal first argument of t('…'), m('…') and the plural
 * form of tp(n, '…', '…'), and looks it up in `src/lib/i18n/ar.js`. A dynamic
 * key (t(variable)) cannot be checked here; mark its possible values with m().
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { AR } from '../src/lib/i18n/ar.js';

const ROOT = new URL('../src', import.meta.url).pathname;

/** @param {string} dir @returns {string[]} */
function files(dir) {
	return readdirSync(dir).flatMap((name) => {
		const path = join(dir, name);
		if (statSync(path).isDirectory()) return path.endsWith('/i18n/ar') ? [] : files(path);
		// The dictionary itself, and the module whose comments show example calls.
		if (path.endsWith('/i18n/ar.js') || path.endsWith('/i18n/index.svelte.js')) return [];
		return /\.(svelte|js)$/.test(name) && !/\.(e2e|test|spec)\.js$/.test(name) ? [path] : [];
	});
}

// A JS string literal: '…', "…" or `…` without ${}.
const LITERAL = String.raw`('(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*"|\`(?:[^\`\\$]|\\.)*\`)`;
const CALLS = [
	new RegExp(String.raw`\b(?:t|m)\(\s*${LITERAL}`, 'g'),
	new RegExp(String.raw`\btp\(\s*[^,]+,\s*${LITERAL}\s*,\s*${LITERAL}`, 'g')
];

/** @param {string} literal */
function unquote(literal) {
	const body = literal.slice(1, -1);
	return body.replace(/\\(.)/g, (_, c) => ({ n: '\n', t: '\t' })[c] ?? c);
}

function check() {
	const missing = new Map();
	const used = new Set();
	for (const file of files(ROOT)) {
		const source = readFileSync(file, 'utf8');
		for (const [index, pattern] of CALLS.entries()) {
			for (const match of source.matchAll(pattern)) {
				const key = unquote(index === 0 ? match[1] : match[2]);
				used.add(key);
				if (!(key in AR)) {
					if (!missing.has(key)) missing.set(key, relative(ROOT, file));
				}
			}
		}
	}
	for (const [key, file] of missing) console.log(`missing  ${JSON.stringify(key)}  (${file})`);
	const unused = Object.keys(AR).filter((key) => !used.has(key) && !key.startsWith('error.'));
	if (process.argv.includes('--unused')) {
		for (const key of unused) console.log(`unused   ${JSON.stringify(key)}`);
	}
	console.log(`${used.size} messages, ${missing.size} without Arabic, ${unused.length} unused`);
	if (missing.size) process.exit(1);
}

const ATTRS =
	/\b(?:placeholder|label|title|aria-label|alt|description|subtitle|eyebrow|hint|what|question|message)="([^"{]*[A-Za-z]{2,}[^"{]*)"/g;

function audit() {
	let total = 0;
	for (const file of files(ROOT).filter((f) => f.endsWith('.svelte'))) {
		const source = readFileSync(file, 'utf8')
			.replace(/<script[\s\S]*?<\/script>/g, '')
			.replace(/<style[\s\S]*?<\/style>/g, '')
			.replace(/<!--[\s\S]*?-->/g, '')
			.replace(/<svg[\s\S]*?<\/svg>/g, '');
		const found = [];
		// Text between tags, with {expressions} removed.
		let withoutExpressions = source;
		for (let previous = ''; previous !== withoutExpressions;) {
			previous = withoutExpressions;
			withoutExpressions = withoutExpressions.replace(/\{[^{}]*\}/g, ' ');
		}
		for (const match of withoutExpressions.matchAll(/>([^<>]*)</g)) {
			const text = match[1].replace(/\s+/g, ' ').trim();
			if (
				/[A-Za-z]{2,}/.test(text) &&
				!/^(NOVA|SAR|— NOVA|English)$/.test(text) &&
				!text.includes('i18n-ignore')
			)
				found.push(text);
		}
		for (const match of source.matchAll(ATTRS)) found.push(`[attr] ${match[1]}`);
		if (found.length) {
			total += found.length;
			console.log(`\n${relative(ROOT, file)} (${found.length})`);
			for (const text of found.slice(0, 200)) console.log(`  ${text}`);
		}
	}
	console.log(`\n${total} hard-coded strings`);
}

if (process.argv[2] === 'audit') audit();
else check();

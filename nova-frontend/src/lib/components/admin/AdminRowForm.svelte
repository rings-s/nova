<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * A row's columns as inputs, for the console's direct edits (the API's
	 * `create_row` / `update_row`). Every value is edited as text and turned back
	 * into the column's JSON type on submit; numbers stay strings so a price
	 * keeps its exact decimals.
	 *
	 * Creating, a blank field takes the column's default. Editing, the primary
	 * key and `tenant_id` are left out (the API refuses to change them), a masked
	 * column starts blank because its value never reaches the page, and only the
	 * fields that changed are submitted.
	 */
	import Input from '$lib/components/ui/Input.svelte';
	import Select from '$lib/components/ui/Select.svelte';
	import Textarea from '$lib/components/ui/Textarea.svelte';

	/**
	 * @type {{
	 *   id: string,
	 *   columns: import('$lib/api/admin.js').AdminColumn[],
	 *   values?: Record<string, unknown>|null,
	 *   onsubmit: (values: Record<string, unknown>) => void
	 * }}
	 */
	let { id, columns, values = null, onsubmit } = $props();

	let creating = $derived(values === null);

	let fields = $derived(
		columns.filter(
			(column) =>
				column.writable && (creating || (!column.primary_key && column.name !== 'tenant_id'))
		)
	);

	/**
	 * @param {import('$lib/api/admin.js').AdminColumn} column
	 * @param {unknown} value
	 */
	function toText(column, value) {
		if (value === null || value === undefined || column.masked) return '';
		if (column.type === 'json') return JSON.stringify(value, null, 2);
		return String(value);
	}

	/** What each field held when the form opened. */
	function initialTexts() {
		return Object.fromEntries(
			columns.map((column) => [column.name, toText(column, values?.[column.name])])
		);
	}

	let initial = $derived(initialTexts());
	// Read once: the parent keys the form on the row, so it opens once per row.
	let drafts = $state(initialTexts());
	let problems = $state(/** @type {Record<string, string>} */ ({}));

	/** @param {import('$lib/api/admin.js').AdminColumn} column */
	function choices(column) {
		const blank = creating
			? column.required
				? []
				: [{ value: '', label: t('Default') }]
			: column.nullable
				? [{ value: '', label: t('Empty') }]
				: [];
		const options =
			column.type === 'boolean'
				? [
						{ value: 'true', label: t('Yes') },
						{ value: 'false', label: t('No') }
					]
				: column.choices.map((choice) => ({ value: choice, label: choice }));
		return [...blank, ...options];
	}

	/** @param {import('$lib/api/admin.js').AdminColumn} column */
	function hint(column) {
		const kind = column.references ? `${column.type} → ${column.references}` : column.type;
		if (creating) return column.required ? kind : `${kind} · ${t('blank for the default')}`;
		if (column.masked) return `${kind} · ${t('blank keeps the current value')}`;
		return column.nullable ? `${kind} · ${t('blank for empty')}` : kind;
	}

	/** @param {SubmitEvent} event */
	function submit(event) {
		event.preventDefault();
		/** @type {Record<string, unknown>} */
		const out = {};
		/** @type {Record<string, string>} */
		const found = {};
		for (const column of fields) {
			const text = drafts[column.name] ?? '';
			if (!creating && text === initial[column.name]) continue;
			if ((column.type === 'text' ? text : text.trim()) === '') {
				// Creating: the column's default. Editing: empty, but a secret is kept.
				if (!creating && !column.masked) out[column.name] = null;
				continue;
			}
			if (column.type === 'json') {
				try {
					out[column.name] = JSON.parse(text);
				} catch {
					found[column.name] = t('This isn’t valid JSON.');
				}
			} else if (column.type === 'boolean') {
				out[column.name] = text === 'true';
			} else {
				out[column.name] = column.type === 'text' ? text : text.trim();
			}
		}
		problems = found;
		if (Object.keys(found).length === 0) onsubmit(out);
	}
</script>

<form {id} class="grid gap-x-5 gap-y-4 sm:grid-cols-2" onsubmit={submit}>
	{#each fields as column (column.name)}
		{@const required = creating && column.required}
		{@const dir = column.type === 'text' ? 'auto' : 'ltr'}
		<div class={column.type === 'json' ? 'sm:col-span-2' : ''}>
			{#if column.type === 'boolean' || column.type === 'enum'}
				<Select
					label={column.name}
					hint={hint(column)}
					{required}
					options={choices(column)}
					dir="ltr"
					bind:value={drafts[column.name]}
				/>
			{:else if column.type === 'json'}
				<Textarea
					label={column.name}
					hint={hint(column)}
					error={problems[column.name] ?? null}
					{required}
					rows={6}
					class="font-mono text-xs"
					spellcheck="false"
					dir="ltr"
					bind:value={drafts[column.name]}
				/>
			{:else}
				<Input
					label={column.name}
					hint={hint(column)}
					{required}
					type={column.masked ? 'password' : column.type === 'date' ? 'date' : 'text'}
					autocomplete={column.masked ? 'new-password' : 'off'}
					inputmode={column.type === 'number' ? 'decimal' : undefined}
					placeholder={column.type === 'datetime'
						? '2026-01-31T09:30:00+03:00'
						: column.type === 'uuid'
							? '00000000-0000-0000-0000-000000000000'
							: null}
					maxlength={column.max_length ?? undefined}
					class={column.type === 'uuid' || column.type === 'datetime' ? 'font-mono' : ''}
					{dir}
					bind:value={drafts[column.name]}
				/>
			{/if}
		</div>
	{/each}
</form>

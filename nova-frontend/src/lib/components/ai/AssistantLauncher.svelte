<script>
	import { t } from '$lib/i18n/index.svelte.js';
	/**
	 * A floating "Ask the assistant" button that opens a chat with one agent.
	 *
	 * Two kinds:
	 * - a business's own receptionist (`tenantId` + `agent`), on its storefront;
	 * - the marketplace assistant (`marketplace`), which searches every listed
	 *   business and books at the one the customer picks.
	 *
	 * It asks first whether a model can answer and renders nothing otherwise:
	 * a chat that could only hand off is worse than no chat. The chat routes
	 * need a signed-in caller, so a visitor gets a sign-in prompt instead.
	 */
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { authStore } from '../../stores/auth.svelte.js';
	import { getMarketplaceAssistant, listAgents, sendMarketplaceMessage } from '../../api/ai.js';
	import Icon from '../ui/Icon.svelte';
	import Button from '../ui/Button.svelte';
	import ChatWidget from './ChatWidget.svelte';

	/**
	 * @type {{
	 *   title: string,
	 *   subtitle?: string|null,
	 *   intro?: string|null,
	 *   starters?: string[],
	 *   marketplace?: boolean,
	 *   tenantId?: string|null,
	 *   agent?: string,
	 *   businessId?: string|null,
	 *   referralToken?: string|null
	 * }}
	 */
	let {
		title,
		subtitle = null,
		intro = null,
		starters = [],
		marketplace = false,
		tenantId = null,
		agent = 'receptionist_agent',
		businessId = null,
		referralToken = null
	} = $props();

	let ready = $state(false);
	let open = $state(false);

	$effect(() => {
		if (!authStore.isAuthenticated) {
			// A visitor still sees the button; opening it asks them to sign in.
			ready = true;
			return;
		}
		if (!marketplace && !tenantId) {
			ready = false;
			return;
		}
		let cancelled = false;
		const check = marketplace
			? getMarketplaceAssistant().then((status) => status.inference_available)
			: listAgents(tenantId ?? '').then(
					(catalog) =>
						catalog.inference_available && catalog.agents.some((spec) => spec.name === agent)
				);
		check
			.then((ok) => {
				if (!cancelled) ready = ok;
			})
			.catch(() => {
				if (!cancelled) ready = false;
			});
		return () => {
			cancelled = true;
		};
	});

	/** @param {KeyboardEvent} event */
	function onkeydown(event) {
		if (event.key === 'Escape' && open) open = false;
	}

	/** @param {{ sessionId: string, message: string, locale: string, confirmHoldToken: string|null }} params */
	function sendToMarketplace(params) {
		return sendMarketplaceMessage(params);
	}

	let loginHref = $derived(
		`${resolve('/login')}?next=${encodeURIComponent(page.url.pathname + page.url.search)}`
	);
</script>

<svelte:window {onkeydown} />

{#if ready}
	<div class="fixed end-4 bottom-4 z-40 flex flex-col items-end gap-3 sm:end-6 sm:bottom-6">
		{#if open}
			<div class="w-[min(26rem,calc(100vw-2rem))] shadow-overlay" role="dialog" aria-label={title}>
				{#if authStore.isAuthenticated && authStore.principal?.kind === 'customer'}
					<ChatWidget
						{tenantId}
						{agent}
						{businessId}
						{referralToken}
						{title}
						{subtitle}
						{intro}
						{starters}
						send={marketplace ? sendToMarketplace : null}
						class="h-[min(38rem,calc(100dvh-7rem))]"
					/>
				{:else}
					<div class="rounded-card border border-line bg-surface p-5 shadow-card">
						<p class="font-semibold text-fg">{title}</p>
						<p class="mt-1 text-sm text-fg-secondary">
							{authStore.isAuthenticated
								? t('The assistant books for customer accounts. Sign in with one to use it.')
								: t('Sign in to let the assistant find a time and book it for you.')}
						</p>
						{#if !authStore.isAuthenticated}
							<div class="mt-4 grid grid-cols-2 gap-2">
								<Button variant="outline" href={`${resolve('/register')}?as=customer`}
									>{t('Create account')}</Button
								>
								<!-- eslint-disable-next-line svelte/no-navigation-without-resolve -->
								<Button href={loginHref}>{t('Sign in')}</Button>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		{/if}
		<button
			type="button"
			class="flex h-12 items-center gap-2 rounded-full bg-brand-600 px-4 text-sm font-semibold text-white shadow-raised focus-ring transition-transform duration-fast hover:scale-[1.03]"
			aria-expanded={open}
			onclick={() => (open = !open)}
		>
			<Icon name={open ? 'x' : 'sparkles'} class="size-5" />
			{open ? t('Close') : t('Ask the assistant')}
		</button>
	</div>
{/if}

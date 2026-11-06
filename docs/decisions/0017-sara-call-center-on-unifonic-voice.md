# 0017 — Sara, a Call-Center Agent on Unifonic Voice

## Status

Accepted — 2026-10-22. Amends ADR-0015: on a phone call, pressing 1 on the keypad stands in for the
chat's "Yes, book it" button. ADR-0011's rule that no agent confirms a booking still holds.

## Context

The owner asked for a call-center employee named Sara for the AI agents: a phone number a salon's
customers can ring, answered by NOVA's own agent rather than a third party's. Only the carrying of
the call is bought in. The constraints:

- The numbers must be Saudi (+966) and the provider licensed for voice in the Kingdom.
- NOVA keeps the brain: the same `AiChatService`, tools and domain rules as the chat agents, so
  nothing a phone call can do bypasses a rule the app enforces.
- Caller ID can be forged. A number is not an identity (docs/14 TM-01's lesson).
- The chat agents' model is a small local one (qwen3-1.7b on a CPU) that takes minutes per turn. A
  caller cannot wait that long.

## Decision

### Unifonic Voice carries the call, as webhook turns

Unifonic (Riyadh, CST-licensed, already the region's SMS/WhatsApp provider) runs a call as a loop
of webhooks. A number's inbound application fetches a URL we host; we answer with JSON (`say` this,
then listen at `responseUrl`); Unifonic recognises the caller's speech and POSTs the text, and any
keys pressed, to that URL; we answer with the next instruction. That loop is exactly NOVA's
turn-based `AiChatService.chat()`, so no media server, SIP trunk or streaming speech pipeline is
needed. The cost is walk-in-style turns: the caller cannot interrupt Sara, and she speaks with
Unifonic's built-in Arabic voice.

All of Unifonic's shapes are in one adapter (`integrations/voice/unifonic.py`, a `VoiceGateway`
protocol). Its documentation is behind a login, so the field names come from its public guides and
must be checked on a live account before go-live; a difference changes that file only.

### A new module, `call_center`, because a call has state

`ai_agents` owns no tables, and a call needs some: the line a number rings (`phone_lines`) and the
call itself (`voice_calls`: turns, outcome, verification, the last answer for a retried
delivery). Both are tenant-owned under forced RLS. `call_center` depends on `ai_agents`' service,
never the other way round. Sara is `call_center_agent` (alias `sara`) in the roster, marked
`voice_only`: the chat routes refuse her, and the voice path refuses every other agent.

### The links are the credentials

Unifonic sends no Authorization header to `responseUrl`, so each URL it is given is signed:

- a line's answer URL, `/webhooks/voice/{tenant_id}/lines/{line_id}.{hmac}`, keyed by a
  purpose-derived key and the line's `token_version` (rotating revokes it), with no expiry;
- each turn's URL, `/webhooks/voice/{tenant_id}/calls/{purpose token}`, naming the call and valid
  two hours.

The tenant is in the path. The router scopes the connection to it before reading anything, so a
genuine token under another tenant's id finds no call (RLS) and answers 404. No request path gains
a `bypass_tenant_scope`.

### The keypad decides, not the model

What a key means is decided in `call_center/domain.py`, and the model never sees a key:

- **1** books the time Sara is holding. The service reads the newest offer's hold token
  server-side (`confirm_latest_offer`), exactly as the app sends the button's. A spoken "yes" is
  text the model reads and is refused with `not_confirmed`, as in chat.
- **2** cancels the booking Sara offered to cancel (`request_cancellation` still only previews),
  for a verified caller only, through `BookingService.cancel` under the customer's policy.
- **A four-digit code** verifies the caller (below).

### Caller ID finds a customer; a code proves one

The caller's number finds the customer record to book for, or opens one, as reception would. That
is all it does. `list_my_bookings`, `get_booking_status`, `get_payment_status` and
`request_cancellation` refuse (`caller_not_verified`) until the caller types the code that
`verify_caller` has `call_center` send to the customer's WhatsApp. The code is four digits, valid
five minutes, three attempts, stored as an HMAC bound to the call, and never spoken, logged or
shown to the model. A reminder call rang the number on file, so it starts verified.

Separately, because a voice turn acts as a service principal, which sees every booking in the
tenant, the customer-service tools now also check that a booking named by id belongs to the
customer the call (or a staff member) acts for.

### Saudi dialect, not Modern Standard Arabic

Sara speaks the everyday Saudi dialect, never MSA. The prompt lists words to use and the MSA forms
to avoid, with an example reply. Every fixed phrase NOVA says without the model (the greeting,
"press 1", the code prompts, the reminder) is written in that dialect. All of them use the polite
plural (تبون، اضغطوا), which is courteous and fits any caller. Times are said the way a Saudi says
them, not read as digits: on a call, the tools hand the model `local_time` as "بكرة الساعة أربع ونص
العصر" (`app/core/spoken.py`), and the reminder call uses the same words. What the model writes
itself passes through `speakable` before either voice reads it: no markdown, links or emoji, and in
Arabic, times, riyals, percentages and amounts up to 9,999 in Saudi words ("150 SAR" → "مية وخمسين
ريال"). Dates, phone numbers and codes keep their digits.

### Her voice: Qwen3-TTS, Saudi fine-tune

The owner chose Qwen's text-to-speech models for Sara's voice. Qwen3-TTS (Apache-2.0, 0.6B and
1.7B, released January 2026) ships ten languages, and Arabic is not one of them. The voice is
therefore the community fine-tune `vadimbelsky/qwen3-TTS-KSA`: Qwen3-TTS-12Hz-1.7B-Base trained on
about 13,000 Saudi-dialect utterances. It has one baked-in speaker, `ksa_speaker`, and makes 24 kHz
or 8 kHz audio. Its authors say it is not production-ready, and that long passages can drift into
Arabic that sounds foreign. Sara's replies are at most two sentences.

NOVA does not load the model. It calls an OpenAI-compatible `POST /v1/audio/speech` server
(`integrations/voice/speech.py`, the `VOICE_TTS_*` settings). vLLM-Omni serves Qwen3-TTS that way on
a CUDA GPU, at 8000 Hz for the phone line.

> **Superseded in part by ADR-0018 (2026-10-23):** the server is NOVA's own `tts` compose service
> (`infra/tts`), which runs the fine-tune through its `qwen-tts` package and resamples to 8000 Hz,
> rather than vLLM-Omni. The request and everything after it are unchanged. Each reply's clip is kept in Redis under an HMAC of voice
and words, served at `GET /webhooks/voice/audio/{key}.wav`, and played by Unifonic (`play`). The
same words are generated once, until `VOICE_TTS_CACHE_SECONDS`. Speech runs after the router
commits, so no transaction waits on it. A clip is kept only if it is a mono PCM WAV at the rate
asked for (`wav_problem`): a server that ignored `sample_rate`, or answered an error with 200, would
otherwise be played as noise for an hour.

The model and the voice share one wait: `VOICE_TURN_BUDGET_SECONDS` (8) from Unifonic's request.
Speech gets what the model left, never more than `VOICE_TTS_TIMEOUT_SECONDS`; under half a second
left, it is not asked for at all. A clip made earlier is played whatever the time.

The voice never blocks a call. With no server, a failure, a reply slower than
`VOICE_TTS_TIMEOUT_SECONDS`, an English reply (the fine-tune speaks Arabic only), or a clip Redis
could not store (a link to it would be a 404, and silence), Unifonic reads the text in its own voice
instead.

Three things are unconfirmed:

- whether Unifonic's `play` takes a URL;
- whether vLLM-Omni exposes the fine-tune's baked speaker as a `voice` (moot since ADR-0018:
  `infra/tts` passes `voice` to `qwen-tts` as the speaker);
- whether `ksa_speaker` is a woman's voice, as Sara's should be.

If it is not, a female Saudi voice needs its own fine-tune of the Base model on recordings made
with the speaker's consent.

### A separate, fast model

`VOICE_AI_*` settings give Sara her own OpenAI-compatible endpoint (`openai_compatible` provider;
since 2026-10-24 a llama-server only, ADR-0018; since 2026-10-28 a vLLM server only, ADR-0019)
with a 6-second turn timeout, falling back to `AI_*`. A timeout makes Sara ask the caller to repeat
rather than drop the call. For PDPL, prefer a model hosted in the Kingdom; the choice is a
deployment one.

### Reminder calls

An hourly cron (`place_reminder_calls`) rings customers with a confirmed booking 2–24 hours ahead,
only with the new `customers.voice_consent` (PDPL, per channel, withheld by default), from the
business's own line, during 10:00–21:00 in the branch's timezone, within a daily cap per business,
and once per booking (a partial unique index). "Press 1 to keep it, 2 to talk to me."

The call is committed before it is dialled, so the customer's first keypress finds it. A dial that
certainly did not ring (no connection, or a 4xx) removes the call, and the next sweep tries again.
One that may have rung (a timeout after Unifonic had the request, or a 5xx) is kept and never
dialled again: ringing twice is worse than not learning Unifonic's call id.

### Hung-up calls

Unifonic posts nothing when a caller hangs up. Every reply carries a fresh turn link valid for
`CALL_LINK_TTL` (2 hours), so a call with no turn for that long can never go on. The hourly
`end_abandoned_calls` cron ends it at its last turn. It keeps whatever it achieved; a reminder that
never got a key press becomes `no_answer`.

### Retention

After `VOICE_CALL_RETENTION_DAYS` (90), the nightly `scrub_old_calls` cron clears a call's caller
number, Sara's last words, the retry key and any code digest (PDPL). The call stays, with its
outcome, turns, customer and booking, so the call log and its counts outlive the personal details.
Conversation memory expires from Redis after `AI_HISTORY_TTL_SECONDS`, and clips after
`VOICE_TTS_CACHE_SECONDS`. A follow-up Sara opened keeps the caller's number under `support`'s own
rules.

### Plans

Sara is the plan feature `ai_call_center`, on Studio and Chain. Every turn also counted as an AI
message (`BillingService.use_ai_message`), so a trial's ten messages covered a short call. Since
2026-10-24 only the owner's staff agents spend the trial's messages, and only on a turn a model
answered: anyone can ring a business, so a caller must not be able to use up its trial. A business
without the feature hears that it cannot take calls, and the call ends.

## Consequences

- A phone call can do what the receptionist and customer-service chat agents can, and nothing
  more: the same tools, the same domain rules, a keypress where the app has a button.
- The voice is Unifonic's, and callers take turns. A streaming pipeline (SIP into LiveKit or
  Asterisk, with Saudi-dialect speech-to-text and text-to-speech) would allow interruptions and a
  custom voice; this design keeps that possible by isolating the gateway.
- Handoff is a promised call back (`CallbackRequested` event, outcome `callback_requested`), not a
  live transfer, until Unifonic's transfer instruction is confirmed.
- Calls are never closed by a status webhook: a call that ends without a final turn stays
  `in_progress` in the log. A sweep can close them later.
- Until the WhatsApp template `call_verification_code` is approved, Sara cannot verify a caller and
  says a person will call back instead.
- A booking Sara makes is a `draft` until staff confirm it, and a caller cannot see a QR code. So
  after booking she sends the details (`booking_received`: time in the branch's clock, ticket link,
  "the business will confirm") on WhatsApp. A record she opened from a call has no WhatsApp
  consent, so she asks first, and pressing 3 records it as the customer's own. Caller ID can be
  forged, so that consent covers only the business's transactional messages to the number on file.

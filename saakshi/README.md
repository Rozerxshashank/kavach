# Saakshi साक्षी: proof of work, by voice

> 30 crore people in India work every day with no proof that they do.

Maids, masons, drivers and tailors are paid in cash or a UPI ping, with no payslip and no record. India's e-Shram
portal has registered over 300 million informal workers, but registration needs no proof of income, so it is an ID card
and not a work history. Without income proof, banks treat these workers as high-risk, and they borrow from
moneylenders at 30–60%.

**Saakshi ("witness") turns a worker's voice note into employer-confirmed proof of work and income, by phone, in
their own language.**

1. **The worker says it, in her own language.** She picks one of nine languages first (Hindi, English, Tamil, Telugu,
   Kannada, Malayalam, Marathi, Bengali, Gujarati), then just talks: no button to hold. *"Is mahine Mehta ji ke yahan
   kaam kiya, paune paanch hazaar mile."* One voice note can cover several homes.
2. **Saakshi reads it back.** Nothing is saved until the worker hears it in her language and says *"haan"*. Missing
   details, such as an employer's phone number or the month, are asked for one at a time.
3. **The employer is called.** A 20-second call in the employer's language. The employer can confirm, correct the
   figure, ask to be called later, or say no.
4. **The trust engine scores every record** with reasons anyone can read, and catches fraud patterns.
5. **The worker owns a Kaam Passport.** It is a signed, hash-chained work and income history with a QR code, shared
   on her terms: an income band for a landlord, the full history for a lender, work days for the welfare board.

Built for the Gnani.ai All-India Internship Challenge.

---

## Gnani AI models used, and what each one does

| Gnani model | API | What it does in Saakshi |
| --- | --- | --- |
| **Prisma** (`prisma-v2.5`, speech-to-text) | `POST api.vachana.ai/stt/v3` | **Saakshi's ears.** It transcribes workers' voice notes recorded in kitchens and on construction sites, and employers' replies on confirmation calls. It runs in nine Indian languages (each checked end to end), handles Hinglish, and phone numbers spoken in words ("nau aath double ek…"). It also transcribes the simulated employers' voices in the red-team. Clips longer than Prisma's 30-second limit are split at pauses. |
| **Timbre** (`timbre-v2.5`, text-to-speech) | `POST api.vachana.ai/api/v1/tts/inference` | **Saakshi's voice.** It reads every record back before saving, makes every confirmation call in the employer's language (and switches mid-call if they reply in another one), and reads the passport aloud for workers who can't read it. When a worker types instead of speaking, Timbre voices her line, so an employer can still hear "the worker". Simulated employers in the demo and red-team each have their own Timbre voice. |

The language models (Groq `gpt-oss-120b` / `gpt-oss-20b`) are the brain: they understand what people mean, answer
employers' questions, and translate Saakshi's lines into the seven languages beyond Hindi and English. **Everything spoken or
heard goes through Gnani.** Every amount, date and phone number the models propose is **re-derived
deterministically** from the speaker's own words (`backend/saakshi/numbers.py`) before it is read back or stored.

---

## A working product, at zero running cost

Saakshi runs for real users, not just on demo data:

- **Real accounts.** A worker signs up at `/start` with her phone number and a PIN. There's no SMS OTP, so no cost.
  PINs are hashed with PBKDF2, and sessions are signed tokens. Every worker endpoint checks the token.
  Set `SAAKSHI_ADMIN_KEY` to lock the operator desk; without it the server runs in open local mode.
- **Confirmation by WhatsApp link (free).** After she saves a record, the worker taps **WhatsApp**, which opens her
  own WhatsApp with a ready message to the employer. Because the message comes from a number the employer knows,
  it avoids the "is this a scam?" reaction a cold call gets. The employer opens the link, hears Saakshi explain the
  request (Timbre), and **confirms by speaking** (Prisma). The recording is kept as evidence. They can also tap,
  correct the amount, or say they don't know the worker. Each link can be answered only once.
- **Pay through UPI from the same page.** A standard `upi://pay` link opens the employer's own payment app with
  the worker's UPI ID, the amount and a note filled in. Saakshi never touches the money.
- **Two-sided payment proof.** No free API reports UPI payments, so Saakshi checks them like an auditor would. The
  employer gives the 12-digit UPI reference (UTR) from their receipt, and the worker pastes her bank's credit SMS.
  **Same UTR on both sides means the payment is proven.** One side alone is shown as *claimed*.
- **Real phone calls are optional.** The Twilio integration (below) stays available for workers or employers
  without smartphones.

## Talking like a person, not a form

- **Language first.** Sign-up starts with a choice of nine languages, in their own scripts. Everything after that is
  in that language: what Saakshi says, what Prisma listens for, the WhatsApp message to the employer, and the main
  screen. The worker or employer can switch at any time.
- **Hands-free, like a phone call.** After one tap to start, the mic stays open. Saakshi notices when you start and
  stop speaking (an adaptive noise floor, a natural-pause end of turn, and 400 ms of pre-roll so the first syllable
  isn't lost). **Talk over her to interrupt** (barge-in). What you say while she is thinking is kept and answered
  next, not dropped. Typing still works; focusing the box pauses the mic.
- **The brain answers real questions.** On a call, one model sees the whole conversation and every fact on record
  (the kind of work, the months on record, what the worker said when recording it, how Saakshi works). *"Vo mere
  yahan kya kaam karti hai?"* gets *"Sunita ji ghar ki saaf-safaai karti hain"*, not the claim read out again.
  *"Kab se?"* gets the months on record. Guards still apply: it can't vouch for a record, can't use a number that
  isn't on record, and can't get the payment direction backwards. If it tries, a scripted answer is used instead.

- **Specific, natural lines.** *"Sunita जी का कहना है कि उन्होंने आपके यहाँ घर की साफ़-सफ़ाई का काम किया, और आपने उन्हें मई से
  अक्टूबर तक हर महीने 3 हज़ार रुपये दिए। क्या यह सही है?"* (Sunita says she did housework for you, and you paid her ₹3,000 a month
  from May to October. Is that right?) It names the work type, groups consecutive months, and drops the year when it's
  the current year.
- **Real answers to real questions.** "What is this money for?", "Who are you?", "Will you share my number?" get a short,
  warm answer from the model, under three guards: every number in the answer must match the record, the answer must never
  vouch for the record ("yes it's correct") and must keep the payment direction right (employer → worker), and names are
  never respelled. If any guard fails, a scripted answer is used instead.
- **No robotic repetition.** After the claim has been said once, Saakshi asks briefly ("तो क्या यह सही है?", so is that
  right?) and varies its re-prompts.

## Built for real use

- **Withdraw a record** you got wrong. It stays in the tamper-evident chain, marked withdrawn, and drops out of the
  passport.
- **Delete my account.** This erases all records, recordings and share links, and requires the PIN again (DPDP Act).
- **Nine languages** for the worker, and separately for the employer on their confirmation page and calls. Lines
  Saakshi speaks are hand-written in Hindi and English; for the other seven they are translated once by the model,
  cached, and **rejected if any number changes** (Saakshi falls back to English rather than say a wrong amount).
- **Phone numbers are read back in full** before anything is saved, so a misheard digit is caught. In languages
  other than Hindi and English, Saakshi asks for the number one digit at a time (or typed), and the model only
  translates the spoken number words into English; the digits are computed in code (`langs.english_digits`),
  because models are unreliable at that arithmetic.
- **Forgot PIN:** a helper at a union, NGO or bank-mitra desk resets it from the witness desk.
- **Installable on phones** (web app manifest and icons): "Add to home screen" opens it full-screen like an app.
- **Resilient:**
  - Speech and model calls have hard time budgets.
  - Voice falls back to text.
  - A browser tab shares one live connection and resumes it after a drop.
  - Calls dropped by a restart end cleanly and are retried.
  - "Reset demo world" never touches real users' records.
- **Guided demo:** the `/demo` page lists five steps with tappable example lines, so you can run the whole flow
  without a microphone.

## Evidence levels

One trust score can't tell a lender what it needs to know, so every record carries an **evidence level**:

| Level | Meaning | What backs it |
| --- | --- | --- |
| **L0 Unverified** | Worker's statement, or any fraud signal | — |
| **L1 Employer confirmed** | The employer confirmed it | Recorded call, or a spoken confirmation on the link (a tap counts, but is marked weaker) |
| **L2 Payment proven** | Confirmed, and the money trail agrees | Employer's UTR matches the worker's bank SMS, or her SMS shows the employer as payer |
| **L3 Established** | Payment proven over time | L2, and the same employer has confirmed 3 or more months |

The worker's passport and the lender's verification page let the **verifier choose the level they require**
("count income from L2"), and every record shows which level it reached and why.

## The edge cases it handles

**Worker voice notes**
- Several employers in one note, split into separate records with separate calls.
- Indian money idioms: *paune paanch hazaar* (₹4,750), *saade teen sau* (₹350), *dhai lakh*, *dedh sau*, *35 sau*,
  `4.5k`, Devanagari digits.
- Relative dates: *parso*, *pichle hafte*, *is mahine*, *pichle mahine*, month names in Hindi and English, and a
  future month treated as last year's.
- Phone numbers said in words, including "double" and "triple".
- Corrections ("nahi, Gupta madam ke yahan teen hazaar") trigger a fresh read-back.
- Known employers are recognized by name. "Phone mat karna" (don't call them) records the entry as self-declared.
- Daily wage × days, partial payment, unpaid dues, payment in kind.

**Employer calls**
- Confirm, correct, deny (with one gentle re-check), partial confirmation.
- *"Kaun? Scam hai kya?"*: Saakshi never asks for money or OTPs and **plays the worker's own voice note**. A second
  time, it offers a verification code; a third time, it bows out politely.
- *"Kal shaam ko call karna"* (call me tomorrow evening) schedules a callback.
- *"Main unka beta hoon"* (I'm his son): asks for the employer, or accepts a household member's confirmation at lower
  weight.
- *"Dobara call mat karna"* (don't call again) is honored immediately.
- Language switching mid-call; silence and noise get a re-prompt, then a polite exit.
- **A contractor confirms a whole crew in one call:** *"sab sahi hai, bas Raju 3 din aaya"* (all correct, only Raju
  came 3 days) updates three records correctly.
- Rate limits and model outages never count against the employer.

**Trust and fraud**
- Mutual and circular vouching, where A says B employs her and B says C employs him, in a loop.
- Near-sequential phone numbers (SIMs bought together).
- An employer confirming from the worker's own device.
- A household vouching for an implausible number of workers.
- Wages far outside the band for the role, and sudden income jumps.
- UPI credit SMS evidence that matches a record.

**Passport**
- Records are hash-chained (editing a stored amount breaks the chain), and the summary is signed with HMAC.
- Scoped, expiring, revocable share links.
- Honest gaps: a "pending" or "self-declared" record never counts as verified income.
- **The construction welfare-board certificate** counts verified construction days over the last 12 months against the
  90-day BOCW registration requirement.

## Red team

`Witness desk → Red team` generates a population of honest workers and fraudsters, runs **every confirmation call
through the real call engine and classifier**, and measures what the trust engine catches. On our runs it caught
12 of 12 fraudulent records with 0 honest records wrongly flagged. That is a synthetic population, so it is not a
real-world accuracy claim.

---

## Run it

Requirements: Python 3.11+ with [uv](https://docs.astral.sh/uv/), and Node 18+.

```bash
cp .env.example .env          # add GNANI_API_KEY and GROQ_API_KEY (or keep them in ../.env)
./run.sh                      # http://localhost:8100   (PORT=9000 ./run.sh to change)
```

Real use: open **/start**, create a record, speak your work, and send the WhatsApp link to your employer.

Demo world (seeded workers use PIN `2468`): open **/demo**, click **Build demo world**, then:
1. On Sunita's phone, tap **Start**, then just talk (or type) about the work you did.
2. Say *haan* to save. A call appears on the witness desk.
3. Press **☎ Ring phone** and answer on the employer's phone. The line is open, so just talk (or use the quick replies). Or press
   **Let … answer** to hear a simulated employer.

### Try it on your own phone

Phone browsers only allow the microphone on HTTPS, so there's a phone-test mode that serves HTTPS on your WiFi:

```bash
cd backend && uv run uvicorn saakshi.server:app --port 8100     # the API
cd web && npm run dev:phone                                       # open <your-computer's-IP>:5175 on the phone
```

The `/demo` page shows a QR code for that address. Typing it without `https://` is fine: a small gateway redirects
plain HTTP to HTTPS. Your phone must be on the same WiFi. The certificate is made on your
computer, so the browser warns once; choose "continue". Links sent on WhatsApp from there use the same address, so an
employer's phone on the same WiFi can open them too. For use outside your WiFi, deploy behind a real domain, or a
Cloudflare Tunnel / ngrok URL, and set `SAAKSHI_PUBLIC_URL`.

Development:

```bash
cd backend && uv run uvicorn saakshi.server:app --reload --port 8100
cd web && npm install && npm run dev       # http://localhost:5174
```

Tests (offline, no API calls, 101 tests):

```bash
cd backend && uv run --group dev pytest -q
```

## Deploy

One container, one process. The data (SQLite, recordings and seven daily backups) lives in `/data`, so put a
persistent volume there.

Saakshi deploys together with Kavach, the red team and runtime Shield that protects it. From the project root
(the folder above this one):

```bash
cp .env.example .env    # fill it in: API keys, both domains, secrets, the harness key and Saakshi's Shield key
docker compose up -d --build
```

The root `docker-compose.yml` runs both apps behind Caddy, which gets free HTTPS certificates (the microphone needs
HTTPS). On a free VM (Oracle Cloud Always Free, Google Cloud e2-micro), `kavach.<vm-ip>.sslip.io` and
`saakshi.<vm-ip>.sslip.io` work without buying a domain. This folder's `Dockerfile` also runs on its own on any Docker
host that gives HTTPS and a volume. Health check: `GET /api/health`.

**Kavach Shield inside Saakshi.** With `KAVACH_SHIELD_URL` and `KAVACH_SHIELD_KEY` set, every employer call checks
each employer line with the Shield, asks it before confirming a record or recording an amount, and lets it check the
brain's own answers before they're spoken. The worker's other employers and their pay are registered as that call's
secrets. Each check has a 2-second budget; if Kavach is slow or down, the call carries on under Saakshi's own rules.

**Test harness.** With `SAAKSHI_HARNESS_KEY` set, Kavach can run sandboxed attack calls against the real call engine
(`/api/harness/*`). Sandbox worlds never appear anywhere else in the app and are deleted when the call closes.

What production mode does (the image sets `SAAKSHI_ENV=production`):
- It refuses to start without a real signing key, an operator key, an `https://` public URL and both API keys.
- Real people's data is private: a worker sees only her own record (her login), and operators see everything
  (`SAAKSHI_ADMIN_KEY`). Demo data (seeded workers, red-team runs) stays open, so visitors can try the whole product.
- Logins last 30 days, and a PIN reset logs out every old session. Five wrong PINs lock the number for 15 minutes.
- Each visitor is rate-limited, more tightly on login and on anything that uses Gnani or Groq. Uploads are capped
  at 6 MB and must be WAV. Responses carry a CSP, HSTS, no-referrer and frame-deny headers. The API docs and
  open CORS are off.

## Real phone lines (Twilio)

Saakshi works on real phone calls, not just in the browser. The same call engine and voice journal run over plain
phone lines, so **any phone works, including feature phones with no internet**.

- **Outbound:** "📞 Call real number" on the witness desk dials the employer. Saakshi speaks with Timbre, the
  employer's answer is recorded and transcribed by Prisma from 8 kHz phone audio (μ-law handled), and the
  conversation continues turn by turn until the record is settled.
- **Voicemail detection:** an answering machine is never spoken to; the call counts as "no answer" and is retried.
- **Silence and hang-ups:** silence gets a re-prompt; a mid-call hang-up keeps the records pending and retries later.
- **Inbound hotline:** a worker calls Saakshi's number and logs work by voice. An unknown number can register just by
  saying their name.
- **Security:** every webhook is checked against Twilio's `X-Twilio-Signature`, and forged requests get a 403.

To switch it on:

1. Create a Twilio account and buy (or use the trial) voice number. On a trial account, add the phones you'll call as
   *verified caller IDs*. Calling Indian numbers may require enabling India in Twilio's voice geo-permissions.
2. Expose the server publicly, for example `ngrok http 8100`, and copy the `https://…` address.
3. Fill `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` and `SAAKSHI_PUBLIC_URL` in `.env`, then restart.
4. In the Twilio console, set your number's **"A call comes in"** webhook to `POST {SAAKSHI_PUBLIC_URL}/tel/inbound`.

The nav shows **Phone line ●** once it's configured, and the demo page shows the hotline number. The whole flow was
tested with a local Twilio emulator: signed webhooks, μ-law phone recordings generated with Timbre, real Prisma and
LLM calls, voicemail, silence, a suspicious employer, a contractor's crew, a worker logging work by phone, and phone
registration.

## Layout

```
backend/saakshi/
  gnani.py      Timbre + Prisma clients (single-flight lock, retries, 30 s chunking)
  numbers.py    Indian number, money, date and spoken-phone parsing (deterministic)
  journal.py    worker voice journal: extract → verify → ask → read back → save
  calls.py      employer confirmation-call state machine (human or simulated, voice to voice)
  lines.py      every line Saakshi speaks, in Hindi and English
  langs.py      the nine languages: number-checked translation, spoken phone numbers
  trust.py      explainable confidence scores, fraud signals, ring detection, graph
  passport.py   Kaam Passport, signatures, scoped sharing, BOCW certificate, UPI SMS + UTR parsing
  accounts.py   phone + PIN accounts (PBKDF2), signed session tokens, UPI ID validation
  links.py      employer confirmation links: WhatsApp share, spoken confirmation, correct, deny
  payments.py   two-sided UPI payment proof (UTR from employer × bank SMS from worker)
  simulate.py   demo world + red-team simulator
  store.py      SQLite with hash-chained entries
  telephony.py  Twilio REST, webhook signatures, TwiML
  tel_routes.py phone-line webhooks: employer calls, worker hotline, phone registration
  server.py     FastAPI + SSE live updates
web/src/        React + TypeScript (Vite): demo, worker app, employer phone, witness desk, passport
```

## Limits, stated plainly

- Real phone calls need a Twilio account and a public URL (see above); without them, calls run in the browser.
  Twilio was chosen for its documented, testable webhooks; an Exotel adapter would follow the same interface.
- Gnani's API key allows one request at a time across all processes, so voice steps queue up under load. A
  production deployment needs a higher-concurrency plan.
- A spoken link confirmation proves a person said yes on that link. It doesn't prove who that person is; that's why
  payment proof (L2) and tenure (L3) exist.
- A lender has to choose to accept the passport. It is designed as *alternative data* alongside their own checks.
- Fraud signals reduce collusion; they cannot eliminate it. Every score shows its reasons so a human can judge.
- Wage bands are indicative and only flag outliers, never reject.

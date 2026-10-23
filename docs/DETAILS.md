# Details: HubSpot Form Spam Triage Agent

Everything that used to sit in the main README, kept here so the README stays short. Back to the [README](../README.md).

## Background

CAPTCHA and honeypots catch the obvious bots. What gets through looks real at first glance: a valid-looking email, a name typed as keyboard mash, a phone number of `1111111111`, the same "SEO backlinks" message from three addresses in two minutes. Those contacts still get created, still enrol in nurture and lead-routing workflows, and still count as conversions. Then someone in ops spends Friday cleaning them up by hand.

This agent reads a HubSpot form-submission or new-contact export, scores every row for spam risk from several small signals (no single signal decides), and sorts it into **clean**, **review** or **likely spam**, each with plain-English reasons. It gives you an import file that sets a `Spam triage status` property, so your workflows and reports can exclude quarantined contacts, and a short report that shows which forms are being hit and whether bots seem to be posting straight to the form's API address.

## Where each step runs (full version)

If you can create a repo but aren't sure where you actually *run* this, here's the whole flow in order:

1. **GitHub** is where the code lives. Copy it to your laptop with `git clone https://github.com/rubianaseem/hubspot-form-spam-triage-agent.git`, or click **Code → Download ZIP** and unzip it.
2. **HubSpot** is where you get the input. Export the form's submissions, or a contact view of recently created contacts, as a CSV (steps in [SETUP.md](../SETUP.md#4-use-your-real-hubspot-data)).
3. **Terminal** (Mac Terminal, or the terminal inside Cursor) is where you run the script on that CSV: `python agent.py --input your_export.csv` (see [Quick start](../README.md#-quick-start)).
4. **Claude is optional.** With no API key the agent uses its built-in rules. If you add an Anthropic API key to `.env`, Claude gives a second opinion and a short reviewer note on the rows the rules flagged. It still runs in the terminal. You don't open the Claude app or paste anything into a chat.
5. **You, then HubSpot.** Open `out/triage_report.md` and `out/triage.csv`, check the *review* rows and spot-check the *likely spam* ones, then import `out/hubspot_import.csv` back into HubSpot to set the spam properties. Finally add "Spam triage status is not likely_spam" to your lead workflows and conversion reports.

**The agent never writes to HubSpot and never deletes anything.** It only reads the CSV you give it and creates files on your computer. You decide what gets imported.

## Full feature list

- **A risk score, not a single rule:** disposable email domains, random-looking addresses, keyboard-mash names, the same text in first name, last name and company, fake phone numbers (`0000000`, `123456789`, too few digits), pitch-style messages and pasted links
- **Catches the coordinated stuff:** the same phone number or message coming from different emails, and bursts of submissions on one form inside a few minutes
- **Flags possible direct-to-API posts:** a submission with no page URL, when your real forms always record one, often means a bot is posting straight to the form's address and skipping your page-level CAPTCHA
- **Three buckets, with reasons:** *clean* flows on as normal, *review* gets a human look, *likely spam* gets quarantined. Every row says why
- **HubSpot-ready import:** `hubspot_import.csv` sets `Spam risk score`, `Spam triage status` and `Spam triage reasons` on each contact by Record ID
- **Report you can forward:** counts per bucket, which signals fired, which forms take the most spam, and what to change
- **Tunable in one place:** weights, thresholds, burst window and your target countries live in `agent.py` and `.env`
- **Works with no API key.** Claude is an upgrade, not a requirement, and any API error falls back to the rules

## The pain point: all quotes and sources

This one came from [r/hubspot](https://www.reddit.com/r/hubspot/comments/1vqpqyy/how_are_you_dealing_with_spam_form_submissions/) and the HubSpot Community. The spam that hurts isn't the obvious bot. It's the submission that passes the checks and lands in the CRM looking like a lead.

- *"CAPTCHA and honeypots help with obvious bots, but they dont catch legit-looking emails paired with junk names or phone numbers."* ([r/hubspot: How are you dealing with spam form submissions that look real but aren't?](https://www.reddit.com/r/hubspot/comments/1vqpqyy/how_are_you_dealing_with_spam_form_submissions/))
- *"...when we looked more closely at the contacts we found disposable emails, gibberish names and invalid phone numbers."* (a reply in the same thread)
- *"I wouldn't automatically delete a submission based on one signal. Give it a risk score..."* and *"Quarantine the questionable ones and review a sample for false positives."* (another reply in the same thread)
- *"The form already has HubSpot's built-in invisible reCAPTCHA enabled, and the submissions were correctly flagged as spam. However, they were still enrolling into workflows, which created operational noise and unnecessary processing."* ([HubSpot Community: Bots bypassing HubSpot form spam protection (reCAPTCHA v2)](https://community.hubspot.com/t/bots-bypassing-hubspot-form-spam-protection-recaptcha-v2-any-better-solutions/147301))
- *"Once a bot has the portal ID + form GUID, it can post directly to HubSpot and skip Webflow, page JS, WAF rules, and page-level CAPTCHA entirely."* ([HubSpot Community: Bots bypassing reCAPTCHA and submitting directly to HubSpot API](https://community.hubspot.com/t/bots-bypassing-recaptcha-and-submitting-directly-to-hubspot-api-via-non-hubspot-forms/147938))

I took the risk-score advice literally. One odd signal (a Gmail address, a short message) is normal for real buyers, so nothing here is excluded on one signal alone, and nothing is ever deleted. Several signals together push a row into quarantine, and the middle band goes to a human.

## Quick start (full)

```bash
git clone https://github.com/rubianaseem/hubspot-form-spam-triage-agent.git
cd hubspot-form-spam-triage-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python agent.py            # runs on the sample data, no API key needed
```

Use your own export:

```bash
python agent.py --input ~/Downloads/contact-us-submissions.csv --output out/oct
```

Optional: `cp .env.example .env` and add your `ANTHROPIC_API_KEY`. Set `TARGET_COUNTRIES` to the markets you sell into. Use `--no-llm` to force the rules even when a key is set. Full walkthrough in [SETUP.md](../SETUP.md).

## Full example output

On the included `sample_form_submissions.csv` (8 fictional submissions), with no API key:

```
Triaged 8 submissions from sample_form_submissions.csv (built-in rules, no API key)

ID       Score  Verdict      Top reason
50102      100  likely_spam  disposable email domain (mailinator.com)
50103      100  likely_spam  random-looking email address (jhgfdsa1993@)
50107       80  likely_spam  random-looking email address (a.k.r.t.y.u@)
50104       55  review       disposable email domain (yopmail.com)
50105        5  clean        free email and no company
50101        0  clean        no spam signals
50106        0  clean        no spam signals
50108        0  clean        no spam signals

Clean 4 | Review 1 | Likely spam 3
Files written to out/: triage.csv, hubspot_import.csv, triage_report.md
Nothing was deleted or sent to HubSpot.
```

Note row 50104: a normal-looking name and phone, but a disposable email, inside a burst, with no page URL. That's exactly the "looks real but isn't" case, so it goes to a human rather than straight to quarantine. Row 50105 is a real-looking buyer on Gmail with no company, and it stays clean.

`out/triage_report.md` adds the signals that fired, the forms taking the most spam, a table of rows to check, and next steps.

## 💷 Cost note

With no API key it costs nothing. With a key, Claude is only called for rows the rules flagged (*review* and *likely spam*), with one short prompt each, so a typical weekly export only sends a handful of rows. Check current pricing on Anthropic's site; I haven't put a number here because it depends on your model and volume.

## 🔁 Stack-swap table

| This repo uses | Swap for | What changes |
|---|---|---|
| HubSpot form or contact export (CSV) | Salesforce Web-to-Lead / Lead report, Marketo, Pardot, Webflow or Typeform export | Add your column names to `COLUMNS` in `agent.py` |
| CSV import back into HubSpot | Salesforce Data Import Wizard, Marketo list import | Map `Spam triage status` to a custom field there |
| Built-in disposable-domain list | A maintained open-source list, or an email verification API | Replace `DISPOSABLE_DOMAINS`, or add a lookup in `score_rows` |
| Anthropic Claude | Any LLM with a Python SDK | Edit `get_client` and `llm_second_opinion` |
| Run by hand in Terminal | n8n, a HubSpot custom code action, or a scheduled job | Call the same scoring on each new submission |

## 🛠 Customise for your stack

- **Your markets:** set `TARGET_COUNTRIES` in `.env` so out-of-market IPs add a small amount of risk (it's deliberately weak on its own).
- **Your thresholds:** `REVIEW_AT` and `SPAM_AT` in `.env`. Start strict on review and loose on spam, then tighten once you've reviewed a few weeks.
- **Your weights:** the `WEIGHTS` dictionary near the top of `agent.py`. If disposable emails are always junk for you, raise it.
- **Your spam phrases:** add what your forms actually receive to `SPAM_PHRASES`.
- **Forms without a page URL by design:** if you post submissions server-side, remove the `Page URL` column from the export (or the weight) so it isn't counted.

## 🧭 How this runs today (and what production would add)

**Today:** you export a CSV, run the script on your laptop, review the output, and import the result yourself. That's on purpose. It lets you see the false positives before anything changes in HubSpot.

**What production would add:**

- Scoring each submission as it arrives, from a HubSpot workflow webhook or custom code action, or an n8n flow, so quarantine happens before nurture or routing ever fires
- A real disposable-domain list and an email verification step, rather than the starter list here
- Routing public forms through an endpoint you control and forwarding clean submissions to a hidden HubSpot form, which is the structural fix the HubSpot Community thread describes for direct-to-API spam
- A feedback loop: track which quarantined contacts later replied or became pipeline, and retune the weights from that
- Logging every verdict and reason, so you can audit why a contact was excluded

---

MIT licensed. Sample data is fictional.

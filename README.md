# HubSpot Form Spam Triage Agent

**Keep fake form fills out of your workflows, your sales queue and your conversion reports, without deleting a single real lead.**

> Built by Rubia Naseem, GTM Engineer (12+ yrs CRM/RevOps, HubSpot & Salesforce).

---

## The pain point

The spam that hurts isn't the obvious bot. It's the submission that passes CAPTCHA and honeypots and lands in the CRM looking like a lead, then enrols in workflows and counts as a conversion. I took the community's advice literally: score risk from several signals, quarantine, and never delete on one signal alone.

- *"CAPTCHA and honeypots help with obvious bots, but they dont catch legit-looking emails paired with junk names or phone numbers."* ([r/hubspot: How are you dealing with spam form submissions that look real but aren't?](https://www.reddit.com/r/hubspot/comments/1vqpqyy/how_are_you_dealing_with_spam_form_submissions/))
- *"Once a bot has the portal ID + form GUID, it can post directly to HubSpot and skip Webflow, page JS, WAF rules, and page-level CAPTCHA entirely."* ([HubSpot Community: Bots bypassing reCAPTCHA and submitting directly to HubSpot API](https://community.hubspot.com/t/bots-bypassing-recaptcha-and-submitting-directly-to-hubspot-api-via-non-hubspot-forms/147938))

More quotes are in [docs/DETAILS.md](docs/DETAILS.md#the-pain-point-all-quotes-and-sources).

---

## What it does

- **Scores risk from small signals:** disposable or random-looking emails, keyboard-mash names, fake phone numbers, pitch-style messages and pasted links
- **Catches coordinated spam:** the same phone or message from different emails, and bursts of submissions on one form
- **Flags possible direct-to-API posts:** submissions with no page URL when your real forms always record one
- **Three buckets with reasons:** *clean*, *review* or *likely spam*, and every row says why
- **HubSpot-ready import:** `hubspot_import.csv` sets `Spam risk score`, `Spam triage status` and `Spam triage reasons` by Record ID
- **Works with no API key:** Claude only adds a second opinion if you set a key

---

## Where each step runs

1. **GitHub** holds the code. Clone it or click **Code → Download ZIP**.
2. **HubSpot** gives you the input: export the form's submissions or recently created contacts as a CSV.
3. **Terminal** is where you run it: `python agent.py --input your_export.csv`.
4. **Claude is optional.** With an Anthropic key it reviews the flagged rows; without one, the built-in rules do everything. It all stays in the terminal.
5. **You, then HubSpot.** Check the *review* rows, then import `out/hubspot_import.csv` and exclude "likely spam" from your workflows and reports.

**The agent never writes to HubSpot and never deletes anything.**

---

## Quick start

```bash
git clone https://github.com/rubianaseem/hubspot-form-spam-triage-agent.git
cd hubspot-form-spam-triage-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python agent.py            # runs on the sample data, no API key needed
```

Use your own export with `python agent.py --input ~/Downloads/contact-us-submissions.csv --output out/oct`.

---

## Example output

On the included `sample_form_submissions.csv` (8 fictional submissions), with no API key:

```
ID       Score  Verdict      Top reason
50102      100  likely_spam  disposable email domain (mailinator.com)
50103      100  likely_spam  random-looking email address (jhgfdsa1993@)
50107       80  likely_spam  random-looking email address (a.k.r.t.y.u@)
50104       55  review       disposable email domain (yopmail.com)
50105        5  clean        free email and no company

Clean 4 | Review 1 | Likely spam 3
Nothing was deleted or sent to HubSpot.
```

---

## More

- [SETUP.md](SETUP.md): API key, exporting your real HubSpot data, importing the result back, extending it, troubleshooting
- [docs/DETAILS.md](docs/DETAILS.md): all the pain-point quotes, full feature list and example output, cost note, stack-swap table, customising, and how this runs today vs production

MIT licensed. Sample data is fictional.

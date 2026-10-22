# Setup guide

Everything here runs on your own computer. The agent reads a CSV and writes files to `out/`. It never connects to HubSpot or deletes anything.

## 1. Get the code and a virtual environment

```bash
git clone https://github.com/rubianaseem/hubspot-form-spam-triage-agent.git
cd hubspot-form-spam-triage-agent
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

A virtual environment (`.venv`) keeps this project's packages separate from the rest of your machine. Run `source .venv/bin/activate` again each time you open a new terminal.

## 2. Sample run (no API key)

```bash
python agent.py
```

You should see 8 submissions scored: 4 clean, 1 review and 3 likely spam. Open `out/triage_report.md` to read the report.

## 3. Optional: add an Anthropic API key

```bash
cp .env.example .env
```

Open `.env` and paste your key after `ANTHROPIC_API_KEY=`. Run `python agent.py` again: the summary line will say "Claude + rules", and the reviewer notes in `out/triage.csv` will have `claude` as their source. Claude only gives a second opinion. If it disagrees with the rules, the note says so and the rules verdict is kept, so results stay predictable. Use `--no-llm` to switch Claude off for a run.

Never commit `.env`. It's already in `.gitignore`.

## 4. Use your real HubSpot data

**Option A, one form's submissions:**
1. In HubSpot go to **Marketing → Forms** and open the form.
2. Open its submissions and export them as CSV.

**Option B, recently created contacts (all forms):**
1. Go to **CRM → Contacts** and filter on *Create date* in the last 7 days.
2. Add the columns the agent reads: Email, First Name, Last Name, Phone Number, Company Name, Message (if you have it), Recent Conversion, IP Country, and a page URL property such as *First Page Seen*.
3. Export the view as CSV. Keep the *Record ID* column, because the import uses it.

Then run:

```bash
python agent.py --input ~/Downloads/your_export.csv --output out/this-week
```

Columns are matched by name, and both HubSpot export names and simple names (`email`, `first_name`) work. Missing optional columns just mean that signal is skipped.

## 5. Import the result back into HubSpot

1. Create three contact properties once: **Spam risk score** (number), **Spam triage status** (dropdown: clean, review, likely_spam), **Spam triage reasons** (multi-line text).
2. **CRM → Contacts → Import → File from computer → One file → One object → Contacts.**
3. Upload `out/hubspot_import.csv`, match *Record ID* to *Record ID*, and map the three columns to the new properties. Choose to update existing contacts only.
4. In your lead routing, nurture and notification workflows, add the filter *Spam triage status is not likely_spam*. Do the same in conversion reports.

Review the *review* rows before importing, and change their status in the CSV if you disagree. Delete nothing until you've watched a few weeks of results.

## 6. Extend it with an AI coding tool

Open the folder in Cursor, Claude Code, Codex CLI or Grok and ask for a change in plain words. Some prompts that work well:

- "Add a signal that flags submissions where the email domain doesn't match the company website column."
- "Load disposable domains from a text file called `disposable_domains.txt` instead of the set in agent.py."
- "Add a `--since` flag that only scores rows submitted after a given date."
- "Turn the scoring into a function I can call from an n8n Code node or a HubSpot custom code action."

Ask the tool to run `python agent.py` afterwards to confirm the sample still works.

## 7. Troubleshooting

| Problem | Fix |
|---|---|
| `No Email column found` | Your export uses another header. Add it to `COLUMNS["email"]` in `agent.py`. |
| Every row gets `no_page_url` | Your export has a page URL column that's empty for everyone. Remove that column or set its weight to 0. |
| Too many real leads in *review* | Raise `REVIEW_AT` in `.env`, or lower the weight of the signal that keeps firing (see the report). |
| `anthropic not available` | Run `pip install -r requirements.txt` inside the activated venv. The agent keeps working on rules either way. |
| `Claude call failed` | Check the key and model name in `.env`. That row falls back to the template note. |
| Strange characters in names | Save the export as UTF-8 CSV. |

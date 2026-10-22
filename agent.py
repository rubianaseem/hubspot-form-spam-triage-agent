#!/usr/bin/env python3
"""HubSpot Form Spam Triage Agent.

Reads a HubSpot form-submission (or new-contact) export, scores every row for
spam risk from several weak signals, and sorts it into clean / review / likely
spam with plain-English reasons. It never deletes anything: it writes files you
review, plus an import file that sets two custom properties so your workflows
and reports can exclude quarantined contacts.

Runs with no API key (built-in rules). If ANTHROPIC_API_KEY is set, Claude adds
a second opinion on the rows the rules can't settle.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

try:  # optional
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # noqa: BLE001
    pass

DEFAULT_MODEL = "claude-sonnet-5-5"

# A starter list. Swap in a maintained list (see SETUP.md) for real use.
DISPOSABLE_DOMAINS = {
    "mailinator.com", "yopmail.com", "guerrillamail.com", "10minutemail.com",
    "tempmail.com", "temp-mail.org", "trashmail.com", "sharklasers.com",
    "getnada.com", "dispostable.com", "maildrop.cc", "throwawaymail.com",
}
FREE_DOMAINS = {
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "aol.com",
    "icloud.com", "proton.me", "protonmail.com", "live.com", "gmx.com",
}
SPAM_PHRASES = [
    "seo", "backlink", "guaranteed", "click here", "10x leads", "crypto",
    "casino", "loan", "rank your site", "first page of google", "viagra",
    "web design services", "increase traffic",
]

# Column names we accept, first match wins. HubSpot export names come first.
COLUMNS = {
    "id": ["Record ID", "record_id", "Contact ID", "id"],
    "submitted_at": ["Conversion date", "Create Date", "submitted_at", "Submitted at"],
    "form": ["Form name", "Recent Conversion", "form_name", "Form"],
    "email": ["Email", "email"],
    "first": ["First Name", "firstname", "first_name"],
    "last": ["Last Name", "lastname", "last_name"],
    "phone": ["Phone Number", "phone", "Phone"],
    "company": ["Company Name", "company", "Company"],
    "message": ["Message", "message", "Comments"],
    "page_url": ["Page URL", "page_url", "First Page Seen", "Conversion page"],
    "country": ["IP Country", "Country", "country"],
    "utm_source": ["UTM Source", "utm_source", "Original Source Drill-Down 1"],
}

# Weights are points out of 100. Tune them in one place.
WEIGHTS = {
    "disposable_email": 30,
    "random_email": 15,
    "gibberish_name": 25,
    "repeated_name": 10,
    "invalid_phone": 15,
    "spam_message": 30,
    "link_in_message": 10,
    "duplicate_details": 20,
    "burst": 10,
    "no_page_url": 15,
    "free_email_no_company": 5,
    "off_target_country": 5,
}

VOWELS = set("aeiouy")


# ---------------------------------------------------------------- helpers
def pick(row: dict, key: str) -> str:
    for name in COLUMNS[key]:
        if name in row and row[name] is not None:
            return str(row[name]).strip()
    return ""


def parse_time(value: str):
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(value[:19], fmt)
        except ValueError:
            continue
    return None


def looks_gibberish(word: str) -> bool:
    """A name with no vowels, a long consonant run, or digits in it."""
    w = re.sub(r"[^a-z0-9]", "", word.lower())
    if len(w) < 4:
        return False
    if any(ch.isdigit() for ch in w):
        return True
    if not (set(w) & VOWELS):
        return True
    return bool(re.search(r"[^aeiouy0-9]{5,}", w))


def looks_random_local_part(local: str) -> bool:
    core = re.sub(r"[._\-+]", "", local.lower())
    if len(core) < 6:
        return False
    if re.search(r"[^aeiouy0-9]{6,}", core):
        return True
    # lots of single letters split by dots, e.g. a.k.r.t.y.u
    parts = [p for p in re.split(r"[._]", local) if p]
    return len(parts) >= 4 and all(len(p) == 1 for p in parts)


def phone_problem(phone: str) -> str:
    if not phone:
        return ""
    if re.search(r"[a-zA-Z]", phone):
        return "letters in the phone number"
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 8:
        return f"only {len(digits)} digits"
    if len(set(digits)) == 1:
        return "the same digit repeated"
    if digits in "01234567890123456789" or digits in "98765432109876543210":
        return "a counting sequence (1234...)"
    return ""


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


# ---------------------------------------------------------------- scoring
def score_rows(rows: list[dict], cfg: dict) -> list[dict]:
    phones = defaultdict(set)
    messages = defaultdict(set)
    for r in rows:
        digits = re.sub(r"\D", "", r["phone"])
        if len(digits) >= 7:
            phones[digits].add(r["email"].lower())
        if len(r["message"]) >= 25:
            messages[norm(r["message"])].add(r["email"].lower())

    # bursts: N+ submissions on the same form inside the window
    burst_ids = set()
    by_form = defaultdict(list)
    for r in rows:
        if r["_ts"]:
            by_form[r["form"]].append(r)
    window = timedelta(minutes=cfg["burst_minutes"])
    for form_rows in by_form.values():
        form_rows.sort(key=lambda x: x["_ts"])
        for i, r in enumerate(form_rows):
            group = [x for x in form_rows[i:] if x["_ts"] - r["_ts"] <= window]
            if len(group) >= cfg["burst_count"]:
                burst_ids.update(x["id"] for x in group)

    out = []
    for r in rows:
        hits: list[tuple[str, str]] = []
        email = r["email"].lower()
        local, _, domain = email.partition("@")

        if domain in DISPOSABLE_DOMAINS:
            hits.append(("disposable_email", f"disposable email domain ({domain})"))
        if local and looks_random_local_part(local):
            hits.append(("random_email", f"random-looking email address ({local}@)"))
        bad_names = [n for n in (r["first"], r["last"]) if looks_gibberish(n)]
        if bad_names:
            hits.append(("gibberish_name", "name looks like keyboard mash (" + ", ".join(bad_names) + ")"))
        names = [n.lower() for n in (r["first"], r["last"], r["company"]) if n]
        if len(names) >= 2 and len(set(names)) < len(names):
            hits.append(("repeated_name", "same text in first name, last name or company"))
        problem = phone_problem(r["phone"])
        if problem:
            hits.append(("invalid_phone", f"phone number has {problem}"))
        msg = r["message"].lower()
        found = [p for p in SPAM_PHRASES if re.search(r"\b" + re.escape(p) + r"\b", msg)]
        if found or (len(r["message"]) > 20 and r["message"].upper() == r["message"] and re.search(r"[A-Z]", r["message"])):
            label = ", ".join(found[:3]) if found else "all capitals"
            hits.append(("spam_message", f"message reads like a pitch ({label})"))
        if re.search(r"https?://|www\.", msg):
            hits.append(("link_in_message", "link pasted in the message"))
        digits = re.sub(r"\D", "", r["phone"])
        if (len(digits) >= 7 and len(phones[digits]) > 1) or (
            len(r["message"]) >= 25 and len(messages[norm(r["message"])]) > 1
        ):
            hits.append(("duplicate_details", "same phone or message used by a different email"))
        if r["id"] in burst_ids:
            hits.append(("burst", f"{cfg['burst_count']}+ submissions on this form within {cfg['burst_minutes']} min"))
        if cfg["has_page_url_col"] and not r["page_url"]:
            hits.append(("no_page_url", "no page URL recorded, possibly posted straight to the Forms API"))
        if domain in FREE_DOMAINS and not r["company"]:
            hits.append(("free_email_no_company", "free email and no company"))
        if cfg["targets"] and r["country"] and r["country"].lower() not in cfg["targets"]:
            hits.append(("off_target_country", f"IP country outside your markets ({r['country']})"))

        score = min(100, sum(WEIGHTS[k] for k, _ in hits))
        if score >= cfg["spam_at"]:
            verdict = "likely_spam"
        elif score >= cfg["review_at"]:
            verdict = "review"
        else:
            verdict = "clean"
        out.append({**r, "score": score, "verdict": verdict, "signals": [k for k, _ in hits], "reasons": [t for _, t in hits]})
    return out


# ---------------------------------------------------------------- notes
def template_note(r: dict) -> str:
    if r["verdict"] == "clean":
        return "No strong spam signals. Let it flow to sales as normal."
    top = "; ".join(r["reasons"][:3])
    if r["verdict"] == "likely_spam":
        return f"Quarantine: {top}. Keep it out of workflows and reports; don't delete until you've spot-checked a sample."
    return f"Check by hand: {top}. Could be a real person with sloppy data, so look before you exclude."


def get_client():
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic  # noqa: WPS433

        return anthropic.Anthropic()
    except Exception as exc:  # noqa: BLE001
        print(f"  (anthropic not available: {exc}. Using built-in rules.)")
        return None


def llm_second_opinion(client, model: str, r: dict):
    prompt = (
        "You help a marketing ops team triage HubSpot form submissions. "
        "Given this submission and the rule-based signals, reply with JSON only: "
        '{"verdict": "clean"|"review"|"likely_spam", "note": "<one sentence for the reviewer>"}. '
        "Be careful: a real buyer can have a Gmail address or a short message.\n\n"
        + json.dumps({k: r[k] for k in ("form", "email", "first", "last", "phone", "company", "message", "page_url", "country")})
        + "\nSignals: " + "; ".join(r["reasons"])
    )
    try:
        resp = client.messages.create(model=model, max_tokens=200, messages=[{"role": "user", "content": prompt}])
        text = resp.content[0].text
        data = json.loads(text[text.find("{"): text.rfind("}") + 1])
        if data.get("verdict") in {"clean", "review", "likely_spam"}:
            return data["verdict"], str(data.get("note", "")).strip()
    except Exception as exc:  # noqa: BLE001
        print(f"  (Claude call failed for {r['id']}: {exc}. Using the template note.)")
    return None


# ---------------------------------------------------------------- outputs
def write_outputs(rows: list[dict], outdir: Path, source: str, used_llm: bool) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    with open(outdir / "triage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Record ID", "Email", "Form name", "Spam risk score", "Verdict", "Reasons", "Reviewer note", "Note source"])
        for r in rows:
            w.writerow([r["id"], r["email"], r["form"], r["score"], r["verdict"], " | ".join(r["reasons"]), r["note"], r["note_source"]])

    with open(outdir / "hubspot_import.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Record ID", "Email", "Spam risk score", "Spam triage status", "Spam triage reasons"])
        for r in rows:
            w.writerow([r["id"], r["email"], r["score"], r["verdict"], "; ".join(r["reasons"])])

    counts = Counter(r["verdict"] for r in rows)
    sig = Counter(s for r in rows if r["verdict"] != "clean" for s in r["signals"])
    no_url = sum(1 for r in rows if "no_page_url" in r["signals"])
    forms = Counter(r["form"] for r in rows if r["verdict"] == "likely_spam")
    lines = [
        "# Form spam triage report",
        "",
        f"Source file: `{source}`. Rows: {len(rows)}. Notes by: {'Claude second opinion on review/spam rows' if used_llm else 'built-in rules (no API key)'}.",
        "",
        f"- Clean: {counts.get('clean', 0)}",
        f"- Review by hand: {counts.get('review', 0)}",
        f"- Likely spam (quarantine): {counts.get('likely_spam', 0)}",
        "",
        "## Signals behind the flagged rows",
        "",
    ]
    lines += [f"- `{k}`: {v} row(s)" for k, v in sig.most_common()] or ["- none"]
    lines += ["", "## Forms taking the most spam", ""]
    lines += [f"- {k}: {v}" for k, v in forms.most_common()] or ["- none"]
    lines += ["", "## Rows to look at", "", "| Record ID | Email | Score | Verdict | Note |", "|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda x: -x["score"]):
        if r["verdict"] != "clean":
            lines.append(f"| {r['id']} | {r['email']} | {r['score']} | {r['verdict']} | {r['note'].replace('|', '/')} |")
    lines += ["", "## What to do next", ""]
    lines.append("1. Spot-check the *likely_spam* rows. Nothing has been deleted.")
    lines.append("2. Import `hubspot_import.csv` to set `Spam triage status` on these contacts (see SETUP.md).")
    lines.append("3. Add `Spam triage status is not likely_spam` to the enrolment triggers of your lead workflows and to your conversion reports.")
    if no_url:
        lines.append(
            f"4. {no_url} row(s) have no page URL. If your real forms always record one, bots may be posting straight to the form's API address. "
            "Archiving that form and publishing a new one changes the address; check the workflows and reports that use it first."
        )
    (outdir / "triage_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description="Score HubSpot form submissions for spam risk.")
    ap.add_argument("--input", default="sample_form_submissions.csv")
    ap.add_argument("--output", default="out")
    ap.add_argument("--no-llm", action="store_true", help="use the built-in rules even if a key is set")
    args = ap.parse_args()

    path = Path(args.input)
    if not path.exists():
        print(f"Can't find {path}. Pass --input with your export.")
        return 1
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        raw = list(reader)
        headers = reader.fieldnames or []
    if not raw:
        print("The file has no rows.")
        return 1
    if not any(h in headers for h in COLUMNS["email"]):
        print(f"No Email column found. Columns seen: {', '.join(headers)}")
        return 1

    targets = {c.strip().lower() for c in os.environ.get("TARGET_COUNTRIES", "").split(",") if c.strip()}
    cfg = {
        "review_at": int(os.environ.get("REVIEW_AT", 30)),
        "spam_at": int(os.environ.get("SPAM_AT", 60)),
        "burst_count": int(os.environ.get("BURST_COUNT", 3)),
        "burst_minutes": int(os.environ.get("BURST_MINUTES", 10)),
        "targets": targets,
        "has_page_url_col": any(h in headers for h in COLUMNS["page_url"]),
    }

    rows = []
    for i, row in enumerate(raw, start=1):
        r = {k: pick(row, k) for k in COLUMNS}
        r["id"] = r["id"] or f"row-{i}"
        r["_ts"] = parse_time(r["submitted_at"]) if r["submitted_at"] else None
        rows.append(r)

    scored = score_rows(rows, cfg)
    client = None if args.no_llm else get_client()
    model = os.environ.get("ANTHROPIC_MODEL", DEFAULT_MODEL)
    used_llm = False
    for r in scored:
        r["note"], r["note_source"] = template_note(r), "rules"
        if client and r["verdict"] != "clean":
            res = llm_second_opinion(client, model, r)
            if res:
                llm_verdict, note = res
                used_llm = True
                r["note_source"] = "claude"
                r["note"] = note or r["note"]
                if llm_verdict != r["verdict"]:
                    r["note"] += f" (Claude suggests {llm_verdict}; rules said {r['verdict']}. Rules verdict kept.)"

    outdir = Path(args.output)
    write_outputs(scored, outdir, str(path), used_llm)

    print(f"\nTriaged {len(scored)} submissions from {path} ({'Claude + rules' if used_llm else 'built-in rules, no API key'})\n")
    print(f"{'ID':<8} {'Score':>5}  {'Verdict':<12} Top reason")
    for r in sorted(scored, key=lambda x: -x["score"]):
        reason = r["reasons"][0] if r["reasons"] else "no spam signals"
        print(f"{r['id']:<8} {r['score']:>5}  {r['verdict']:<12} {reason}")
    c = Counter(r["verdict"] for r in scored)
    print(f"\nClean {c.get('clean', 0)} | Review {c.get('review', 0)} | Likely spam {c.get('likely_spam', 0)}")
    print(f"Files written to {outdir}/: triage.csv, hubspot_import.csv, triage_report.md")
    print("Nothing was deleted or sent to HubSpot.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

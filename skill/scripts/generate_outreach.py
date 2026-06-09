#!/usr/bin/env python3
import argparse
import json
import sys


def choose_contact(dossier):
    emails = dossier.get("emails") or []
    if emails:
        return emails[0]
    pages = dossier.get("contact_pages") or []
    if pages:
        return pages[0]
    socials = dossier.get("social_links") or []
    if socials:
        return socials[0]
    return None


def likely_pain(summary, offer):
    text = (summary or "").lower()
    if any(word in text for word in ["logistics", "transport", "delivery"]):
        return "keeping qualification, routing, and follow-up consistent across time-sensitive inbound demand"
    if any(word in text for word in ["construction", "build", "project"]):
        return "keeping project communication and document-heavy follow-up from becoming fragmented"
    if any(word in text for word in ["legal", "finance", "accounting", "compliance"]):
        return "maintaining consistent client follow-up in document-heavy, high-trust workflows"
    return f"keeping inbound qualification and follow-up more consistent around {offer}"


def clean_clue(summary, company):
    if not summary:
        return f"I reviewed {company}'s public company information"
    clue = summary.split(".")[0].strip()
    clue = " ".join(clue.split())
    if not clue:
        return f"I reviewed {company}'s public company information"
    lowered = clue.lower()
    banned_starts = (
        "hi ",
        "hello ",
        "dear ",
        "best,",
        "regards,",
        "sincerely",
        "click here",
        "buy now",
    )
    if lowered.startswith(banned_starts):
        return f"I reviewed {company}'s public company information"
    return clue[:180]


def first_sentence(text):
    if not text:
        return ""
    line = text.split("\n", 1)[0].strip()
    return line[0].lower() + line[1:] if len(line) > 1 else line.lower()


def draft(dossier, offer, cta):
    company = dossier.get("company", "your company")
    summary = (dossier.get("summary") or "").strip()
    clue = clean_clue(summary, company)
    pain = likely_pain(summary, offer)
    contact = choose_contact(dossier)
    subject = f"Idea for {company}'s outreach flow"
    body = (
        f"Hi {company} team,\n\n"
        f"I noticed {first_sentence(clue)}. "
        f"That often points to a need for {pain}.\n\n"
        f"I work on {offer} for teams that want outreach to stay relevant, structured, and easier to hand off internally.\n\n"
        f"If useful, I can send a short tailored teardown for {company} and where this could help. {cta}\n\n"
        f"Best,\nMikhail"
    )
    return {
        "company": company,
        "target_contact": contact,
        "subject": subject,
        "body": body,
    }


def main():
    ap = argparse.ArgumentParser(description="Generate a restrained outreach draft from a reviewed dossier.")
    ap.add_argument("dossier_json", help="Path to the reviewed dossier JSON")
    ap.add_argument("--offer", required=True, help="Short description of the service or offer")
    ap.add_argument("--cta", default="Would a 10-minute intro next week be useful?", help="Single clear call to action")
    args = ap.parse_args()

    with open(args.dossier_json, encoding="utf-8") as fh:
        dossier = json.load(fh)
    json.dump(draft(dossier, args.offer, args.cta), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

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
        return "operational coordination, compliance, and response time"
    if any(word in text for word in ["construction", "build", "project"]):
        return "project visibility, document flow, and client communication"
    if any(word in text for word in ["legal", "finance", "accounting", "compliance"]):
        return "keeping up with fast-moving client and document-heavy workflows"
    return f"making repetitive business workflows more consistent and less manual around {offer}"


def draft(dossier, offer, cta):
    company = dossier.get("company", "your company")
    summary = dossier.get("summary") or ""
    clue = summary.split(".")[0].strip() if summary else f"I looked up {company}"
    pain = likely_pain(summary, offer)
    contact = choose_contact(dossier)
    body = (
        f"Hi {company} team,\n\n"
        f"I looked at your company and noticed this: {clue}. "
        f"That usually means extra pressure around {pain}.\n\n"
        f"I help teams simplify that with {offer} — especially where quick response, cleaner handoffs, and better client-facing communication matter.\n\n"
        f"If useful, I can send a short tailored breakdown or a concrete example for {company}. {cta}\n\n"
        f"Best,\nMikhail"
    )
    return {
        "company": company,
        "target_contact": contact,
        "subject": f"A practical idea for {company}",
        "body": body,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dossier_json")
    ap.add_argument("--offer", required=True)
    ap.add_argument("--cta", default="Would a 10-minute intro next week be useful?")
    args = ap.parse_args()

    dossier = json.load(open(args.dossier_json, encoding="utf-8"))
    json.dump(draft(dossier, args.offer, args.cta), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()

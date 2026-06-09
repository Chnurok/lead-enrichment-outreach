# Lead dossier schema

## Core fields

```json
{
  "company": "string",
  "region": "string|null",
  "query": "string",
  "primary_domain": "string|null",
  "website_title": "string|null",
  "site_verification": {
    "verified": true,
    "score": 0.0,
    "title": "string|null",
    "reason": "string|null"
  },
  "summary": "string|null",
  "summary_source": {
    "source_url": "string|null",
    "source_type": "page|serp|null"
  },
  "emails": ["string"],
  "email_sources": {
    "email@example.com": {
      "source_url": "string|null",
      "source_type": "page|mailto|jsonld|null"
    }
  },
  "best_contact_email": "string|null",
  "best_contact_source": {
    "source_url": "string|null",
    "source_type": "page|mailto|jsonld|null"
  },
  "phones": ["string"],
  "phone_sources": {
    "+1 555 123 4567": {
      "source_url": "string|null",
      "source_type": "page|tel|jsonld|null"
    }
  },
  "contact_pages": ["string"],
  "social_links": ["string"],
  "snippets": ["string"],
  "trust_signals": {
    "has_domain": true,
    "has_summary": true,
    "email_count": 0,
    "phone_count": 0,
    "warning_count": 0,
    "warning_penalty": 0.0,
    "site_verified": true,
    "site_verification_score": 0.0,
    "best_contact": {
      "present": true,
      "official": true,
      "strong": false,
      "weak": false,
      "tier": "official_strong|official_weak|external|unknown|null"
    }
  },
  "confidence": 0.0,
  "warnings": ["string"]
}
```

## Notes

- `summary` should stay short and factual.
- `summary_source`, `email_sources`, and `phone_sources` are there for reviewability.
- `site_verification` explains whether the likely official site was strongly matched.
- `trust_signals` explain why the final confidence is high or low.
- `warnings` should explain ambiguity, weak contacts, or poor evidence.
- Keep `snippets` short; they are evidence, not a dump.

## Contact ranking intuition

1. Strong role-based or direct email on the likely official domain
2. General inbox on the likely official domain
3. Weak official-domain email (`press@`, `privacy@`, `careers@`, etc.)
4. Contact page only
5. Social profile only
6. External email not clearly tied to the likely official domain

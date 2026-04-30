# Lead dossier schema

## Minimal fields

```json
{
  "company": "string",
  "region": "string|null",
  "query": "string",
  "primary_domain": "string|null",
  "website_title": "string|null",
  "summary": "string|null",
  "emails": ["string"],
  "phones": ["string"],
  "contact_pages": ["string"],
  "social_links": ["string"],
  "snippets": ["string"],
  "confidence": 0.0,
  "warnings": ["string"]
}
```

## Notes

- `summary` should be short and factual.
- `confidence` is a heuristic 0..1.
- `warnings` should explain missing data, ambiguity, or weak matches.
- Keep `snippets` short; they are evidence, not a dump.

## Contact ranking

1. Named employee email on official domain
2. Role-based email on official domain
3. General inbox on official domain
4. Contact form page
5. Social profile only

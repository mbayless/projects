# PHI / PII Scanner

A secure app that finds protected health information (PHI) and personal data (PII) across many file types and links, lets a person validate every finding by hand, shows metrics, and exports a redacted copy. It runs entirely on your own computer.

```bash
pip install -r requirements.txt
streamlit run app.py
```

## What it does

1. **Scan** — upload JSON, text, CSV/TSV, Excel (.xlsx) or Word (.docx) files, paste links for the app to open, or paste text directly. Each source is turned into text and scanned.
2. **Validate** — every finding is shown in a table with its type, category, value, a confidence bar and the surrounding context. Set each one to *confirmed* or *false positive*. This manual step is the heart of the tool: the detectors propose, a person decides.
3. **Metrics** — totals, how much has been reviewed, and breakdowns by category, by type (with average confidence) and by source, plus a **HIPAA 18 Safe Harbor coverage** table showing findings per identifier.
4. **Export** — download the **finding** report as `finding.csv` or `finding.json` (every finding and your decision, or only the confirmed ones), and a redacted copy of the text with confirmed items labelled, masked or removed.

## What it detects

All 18 HIPAA Safe Harbor identifiers plus common PII and financial data (21 detectors):

- Names, street addresses, ZIP codes, dates, phone and fax numbers, email addresses
- Social Security numbers, medical record numbers, health-plan/member IDs, account and routing numbers
- Driver's licenses, passports, vehicle VINs, device/serial numbers, URLs, IP addresses
- NPI provider IDs, ICD-10 diagnosis codes, ages over 89, and credit/debit cards

Formats with a checksum (SSN, credit card, NPI) are validated so false positives are rare. Identifiers 16 and 17 (biometrics and full-face photos) can't be found in text — the coverage table flags them for manual review.

## Security

- Everything runs locally. Files are read into memory and scanned there; nothing is uploaded.
- The only network request the app ever makes is fetching a link you explicitly paste on the Scan tab.
- The redacted export never contains the confirmed values; the finding report does, so store it carefully.
- This tool supports a HIPAA Safe Harbor review; it does not replace a compliance program or legal sign-off.

## Files

`app.py` is the interface, `detectors.py` holds the detectors and the HIPAA-18 map (edit it to add your own patterns), `extractors.py` turns each format into text, and `sample/` has synthetic (fake) files to try it on.

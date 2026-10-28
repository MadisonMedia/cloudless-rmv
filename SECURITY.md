# Security

* This repository contains **no API key**. Every user needs their own RMV Open Data key
  (<https://www.rmv.de/s/de/rmv-open-data>).
* The key is stored only in your Home Assistant config entry. It is redacted from
  diagnostics and never written to logs by this integration.
* **Never** paste your key, a HAR file or an unredacted log into an issue. The RMV API
  receives the key as a URL parameter (`accessId=…`), so raw URLs contain it.
* If you published a key by accident: request a new one from the RMV and treat the old one as burned.
* Report vulnerabilities privately via GitHub “Report a vulnerability” (Security tab).

# Test fixtures

`prothomalo-bn.xml`, `bdnews24-bn.xml`, `bdnews24-en.xml` and `prothomalo-en-empty.xml` are **real feed
snapshots** downloaded from the publishers on 2026-10-23 (the Prothom Alo English feed was genuinely
empty at that moment). They are kept only so tests can run offline; do not redistribute them.

Synthetic feeds used for edge cases (malformed XML, missing fields, odd timestamps) are built inside
the tests themselves and are clearly marked as synthetic there.

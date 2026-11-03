"""P2-003 supplementary sources: FAQs, enforcement releases, Amendment Directions, withdrawn circulars.

Each source has an adapter module with ``discover()``, ``fetch()`` and ``parse()``.
Everything network-facing goes through :mod:`src.supplementary.common`, which
reuses the P1 scraper's session, retry policy and payload conventions.
Linking (:mod:`.linking`) is direction-level only; paragraph mapping comes from
the hand-alignment sheet (:mod:`.alignment`). No LLM or embedding model is used.
"""

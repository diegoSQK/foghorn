"""Mailing-list ingest (Phase 8 stage 1): deterministic email → draft parsing
and the IMAP poller that feeds the review queue. No LLM anywhere — unparsed
fields stay None and the reviewer fills them in the Inbox UI."""

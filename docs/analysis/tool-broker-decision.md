# Progressive tool disclosure (a "tool broker") — decided against

**Status:** closed unbuilt, 2026-07-25 (#27 part 4, after #2 and #11).
Reopen with a measurement; see the last section.

`ToolBase` documented a broker for years without one existing:

```
tier:   "core" = always sent to the LLM, "extended" = on demand via the tool broker
intent: Broker group ... Used by request_tools(intent=...) to load tool groups.
```

`request_tools()` was never written. This records why it stays that way, so the
question is not reopened on intuition alone.

## What it would have saved

Measured against a live Writer session on 0.12.1:

| what the client receives | tools | tokens |
|---|---|---|
| today, after document-type filtering | 94 | 17,107 |
| a `tier = "core"` opening set | 17 | 3,540 (21%) |
| the existing `minimal` preset | 8 | 1,821 (11%) |

About 13,500 tokens off a session opening — real, and **already obtainable**
through a custom endpoint, which yields a smaller set than the broker's core
tier, with no new machinery and no extra round trip.

So the saving is not what a broker uniquely offers. Not having to configure
anything is.

## Why that is not worth it here

**It reintroduces #24 by design.** #24 was filed because clients cached a tool
list and never learned Calc tools had appeared; the reporter's words were that
it "looks as if Nelson simply *lacks* spreadsheet support". A broker hides most
tools behind a request step on purpose. A model that does not realise it should
ask lands on exactly that conclusion — this time as intended behaviour rather
than a bug.

**The premise is contradicted by the evidence we have.** #2 reports a model
failing to choose the right tool *while the tool was visible and
unambiguously named*. Requiring it to first infer a capability might exist,
then request the group, then call the tool, is a harder task than picking from
a list. MCP offers no standard affordance for requesting more tools, so it
would be a custom tool competing for attention with the ones it gates.

**The metadata that would drive it is unvalidated.** The `tier = "core"` tags
come from the same abandoned pass as the `intent` tags replaced in #27 part 3:
22 tools carry one, nothing ever read them, and only 17 appear in a Writer
session. Choosing what a model sees first from an unreviewed list is not a
foundation.

## What was done instead (#27 parts 1–3, shipped in 0.12.0)

- the `initialize` instructions now spend their budget on decisions — start at
  `doc_list_open`, do not reach for `doc_create` when the document exists, call
  `nav_outline` before editing — rather than on "UNO runs on the main thread"
- tools on a decision boundary name the alternative
- tool groups are derived from the `domain_verb` name instead of hand-tagged,
  with a test that fails when a new tool has no group

## What would reopen this

A measurement, not an argument: a small model, a fixed set of realistic
requests, run once against the full tool list and once against a
core-plus-request-groups setup, reporting how often the first tool call is the
right one. `scripts/smoke_test.py` already drives a real headless LibreOffice
and would host it; the missing piece is a model endpoint.

If that experiment shows progressive disclosure wins for smaller models, the
broker becomes worth its cost and this document is wrong. Until then it is an
API change justified by taste.

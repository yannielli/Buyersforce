"""Frankie, BuyersForce's AI assistant -- plumbing for every Claude call
the app makes on a buyer's behalf. Two call shapes live here:

  - A conversational, tool-using loop (run_chat_turn) -- embedded on the
    buyer Discover page (see buyer_discover_chat in app.py), where
    Frankie can search BuyersForce's own directory and, once the buyer
    asks, the open web too; and reused by the Evaluate page's "Build
    with Frankie" wizard for its own two embedded assistants (see
    buyer_frankie_vendor_chat / buyer_frankie_criteria_chat in app.py),
    scoped to directory-only vendor search and criteria proposals
    respectively via their own tool schemas (build_directory_tools /
    build_criteria_tools) and system prompts. run_chat_turn itself knows
    nothing BuyersForce-specific about any of these -- a generic
    `tool_side_channels` dict in its result carries back whatever a
    caller's own tool handlers returned, keyed by tool name.
  - One-shot, tool-free (or single-server-tool) structured lookups that
    resolve in a single messages.create() call: run_vendor_lookup (the
    "Suggest a vendor" form's autofill) and run_suggest_criteria (the
    guided wizard's quick, single-click "suggest criteria" button --
    separate from its conversational criteria-chat assistant above,
    kept around as a faster one-click path for a buyer who just wants a
    quick starting list without chatting).

This module owns the Anthropic API plumbing only: building the tool
schemas, running the tool-use loop, and handing back a plain-dict result
that app.py can jsonify straight to the frontend. It knows nothing about
Flask, Postgres, or BuyersForce's own data model -- app.py supplies
`tool_handlers` callables that do the actual work (querying vendors,
filing a vendor_requests row, etc.), so this file has no circular import
onto app.py and stays easy to reason about on its own.

Requires the ANTHROPIC_API_KEY environment variable (a sealed Railway
variable in production). If it's missing, get_client() returns None and
run_chat_turn() degrades to a friendly "not configured yet" reply instead
of raising -- so a misconfigured key never 500s the Discover page itself.
"""
import json
import os
import re

import anthropic

# One-time, secret-safe boot diagnostic: confirms whether the sealed
# ANTHROPIC_API_KEY variable is actually reaching this process, and its
# length, without ever logging the value itself. Shows up once per
# gunicorn worker in Railway's deploy logs -- if this is ever chased
# again, delete these four lines once it's resolved.
_boot_key = os.environ.get("ANTHROPIC_API_KEY")
print(
    "[ai_assistant] ANTHROPIC_API_KEY at boot: "
    + ("present, length=" + str(len(_boot_key)) if _boot_key else "MISSING or empty"),
    flush=True,
)

# Sonnet is the right cost/latency tier for a conversational directory
# search assistant -- it doesn't need Opus's heavier reasoning budget.
MODEL = "claude-sonnet-5"

# Each iteration is one round trip to the API. A single user turn should
# resolve in 1-3 (search, maybe a web search, then a reply); this is a
# hard ceiling so a confused tool-calling loop can't run away on cost.
MAX_TOOL_ITERATIONS = 6

MAX_TOKENS = 1536

_client = None
_client_checked_key = None


def get_client():
    """Returns a cached Anthropic client, or None if ANTHROPIC_API_KEY
    isn't set. Re-checks the env var if it changes (harmless in
    production, useful if a key gets added after the process started)."""
    global _client, _client_checked_key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        _client = None
        _client_checked_key = None
        return None
    if _client is None or _client_checked_key != api_key:
        _client = anthropic.Anthropic(api_key=api_key)
        _client_checked_key = api_key
    return _client


_SUGGEST_VENDOR_TOOL = {
    "name": "suggest_vendor",
    "description": (
        "Submit a company you found on the open web -- NOT BuyersForce's own "
        "directory -- into BuyersForce's admin review queue, so a human can "
        "decide whether to add it as a real, vetted listing. This never "
        "publishes anything immediately. Only call this after the buyer has "
        "explicitly confirmed they want that specific company submitted; never "
        "call it just because a company came up in a web search."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "company_name": {"type": "string"},
            "website": {"type": "string"},
            "notes": {
                "type": "string",
                "description": "A short summary of what this company does and why it might fit, based on what you found on the web.",
            },
        },
        "required": ["company_name", "website"],
    },
}


def build_directory_tools(technology_categories, technology_segments, company_size_bands):
    """Tool schema for a 'directory' turn -- Frankie (see app.py's
    _ai_discover_system_prompt) can ONLY search BuyersForce's own vendor
    directory in this mode; there's no web_search here at all. That's
    deliberate, not an oversight: Kevin wants every buyer question to hit
    BuyersForce first, with the buyer -- not the model's own judgment --
    deciding whether to escalate to a live web search afterward (see the
    separate build_web_tools() below, used only for that follow-up turn).
    `technology_categories` / `technology_segments` / `company_size_bands`
    are only used to shape the input_schema descriptions -- the *system
    prompt* (built in app.py) is what actually tells Claude the valid
    values, since a huge enum list on every array item is more schema
    than this needs."""
    return [
        {
            "name": "search_vendors",
            "description": (
                "Search BuyersForce's own verified vendor directory. Use this as soon "
                "as you have enough sense of what the buyer is looking for -- you can "
                "call it more than once in a conversation, refining the filters as the "
                "buyer says more. Only ever describe a company as 'on BuyersForce' if "
                "it came back from this tool; never invent or assume a listing. ALWAYS "
                "pass `query` with the buyer's own topic/phrase, even when you also pass "
                "`technology_categories`/`segments` -- `query` matches broadly (including "
                "each vendor's sub-category/segment tags, not just its written "
                "description), so it's what catches a vendor tagged with the right "
                "sub-category even if your exact `segments` guess doesn't match the "
                "stored value verbatim."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Free-text search -- matches company name, tagline, "
                            "description, HQ location, AND every vendor's assigned "
                            "technology categories, sub-category/segment tags, and "
                            "freeform tags. Put the buyer's own topic here (e.g. "
                            "'endpoint security') on every search, even one where you "
                            "also set technology_categories/segments below."
                        ),
                    },
                    "technology_categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Zero or more of BuyersForce's technology categories, matched exactly (see system prompt for the valid list). An extra, precise filter on top of `query` -- not a replacement for it.",
                    },
                    "segments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Zero or more sub-category/segment tags, matched exactly (see system prompt for the valid list). An extra, precise filter on top of `query` -- not a replacement for it.",
                    },
                    "company_size": {
                        "type": "string",
                        "description": "A vendor employee-count band, matched exactly (see system prompt for the valid list).",
                    },
                    "ownership_status": {
                        "type": "string",
                        "enum": ["public", "private"],
                        "description": "Filter to only publicly traded or only private vendors, when the buyer specifically asks for one.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": (
                            "How many results to return (default 12, max 20). Raise "
                            "this when the buyer asks for 'all' the vendors in a "
                            "category, a specific top-N count, or a broad survey "
                            "question -- don't let the default silently truncate a "
                            "category that has more matches than that."
                        ),
                    },
                },
            },
        },
    ]


def build_web_tools():
    """Tool schema for the 'web' follow-up turn -- only reached after the
    buyer has already seen BuyersForce's own results and explicitly asked
    (by clicking the "Search outside BuyersForce" choice, not because Frankie
    decided to on its own) to also look at the open web. suggest_vendor
    lives here, not in build_directory_tools(), for the same reason --
    it should only ever follow a web search the buyer asked for."""
    return [
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        },
        _SUGGEST_VENDOR_TOOL,
    ]


def build_criteria_tools():
    """Tool schema for the "Build with Frankie" wizard's conversational
    criteria assistant (see buyer_frankie_criteria_chat in app.py) --
    Frankie proposes success criteria by calling propose_criteria rather
    than replying in free text, so the frontend can render each one as
    its own one-click "+ Add" chip instead of asking the buyer to
    copy/paste anything out of a chat bubble. No web_search here -- this
    is drawing on Claude's own knowledge of how B2B purchases get
    evaluated, same as the one-shot run_suggest_criteria below, just
    conversational so a buyer can ask for more, fewer, or a different
    emphasis without starting over."""
    return [
        {
            "name": "propose_criteria",
            "description": (
                "Propose success criteria for the buyer's evaluation scorecard -- "
                "call this whenever you have one or more concrete criteria to "
                "suggest, including proactively on your very first reply once you "
                "have enough context (the project name, the vendors being "
                "compared, or the buyer's own description of what they're "
                "buying) -- don't make the buyer ask first. Propose a focused "
                "batch (typically 3-6) rather than one at a time. The app shows "
                "each suggestion as its own chip with a one-click Add button, so "
                "you never need to ask the buyer to copy/paste anything -- just "
                "a short sentence or two of your own reply alongside them."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "criteria": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Short success-criteria labels, 2-6 words each, title "
                            "case, concrete and specific to what's being "
                            "evaluated (e.g. \"Ease of integration\", \"Total cost "
                            "of ownership\", \"SOC 2 compliance\") -- never generic "
                            "filler like \"Quality\" or \"Good value\"."
                        ),
                    },
                },
                "required": ["criteria"],
            },
        },
    ]


def _reply_text(content_blocks):
    return "".join(
        block.text for block in content_blocks if block.type == "text"
    ).strip()


def _parse_json_object(text):
    """Claude is told to reply with ONLY a JSON object, but models
    occasionally wrap it in a markdown fence or add a stray word anyway --
    so try a straight parse first, then fall back to pulling out the
    first {...} span, rather than letting one extra character break the
    whole lookup."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except (ValueError, TypeError):
            return None
    return None


def run_vendor_lookup(company_name, website_hint, known_segments, company_size_bands):
    """One-shot web lookup for the "Suggest a vendor" form's autofill
    button -- NOT the conversational Frankie loop above. A buyer has typed
    a company name and wants the rest of the form (website, HQ, founded
    year, size band, segments) filled in from whatever's public on the
    web, before reviewing and editing it themselves; nothing here ever
    submits anything, it only returns data for the form to prefill.

    Unlike run_chat_turn, this needs no tool-use loop at all: web_search
    is a server tool, so Anthropic resolves any searches it runs and
    hands back the final answer within this one messages.create() call.

    Returns a plain dict:
        {"website", "hq_location", "founded_year", "company_size",
         "segments", "web_sources"}
    on a normal match, or {"not_found": True, "web_sources": [...]} if
    Claude couldn't find the company at all, or {"error": "..."} if the
    API call itself failed or the reply couldn't be parsed. Every
    returned company_size/segments value is checked against the lists
    this account actually has -- never trust the model's own wording
    straight into a form that's about to feed BuyersForce's real
    directory review queue.
    """
    client = get_client()
    if client is None:
        return {"error": "no_api_key"}

    sizes_list = ", ".join(company_size_bands)
    segments_list = ", ".join(known_segments)
    hint = f' The buyer thinks its website may be "{website_hint}".' if website_hint else ""
    system_prompt = (
        "You help prefill BuyersForce's \"Suggest a vendor\" form by researching one "
        "company on the open web. Use the web_search tool to find its OFFICIAL "
        "website, headquarters (city, state/country), the year it was founded, and "
        "roughly how many employees it has. "
        f"For company_size, pick the single closest match from EXACTLY this list, "
        f"verbatim: {sizes_list} -- or null if you genuinely can't tell. "
        f"For segments, pick zero or more that genuinely fit from EXACTLY this list, "
        f"verbatim (case-sensitive): {segments_list} -- an empty list if none clearly "
        "fit; never invent a value that isn't on either list. "
        "Respond with ONLY a single JSON object, no markdown fences, no words before "
        "or after it, in exactly this shape: "
        '{"website": "https://..." or null, "hq_location": "City, ST" or null, '
        '"founded_year": 2018 or null, "company_size": "<one item from the size '
        'list>" or null, "segments": ["<items from the segments list>"]}. '
        'If you cannot find this company at all, respond with only {"not_found": true}.'
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=700,
            system=system_prompt,
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}],
            messages=[{"role": "user", "content": f"Company name: {company_name}.{hint}"}],
        )
    except anthropic.APIError as exc:
        print(f"[ai_assistant] vendor lookup API error: {type(exc).__name__}: {exc}", flush=True)
        return {"error": str(exc)}

    web_sources = []
    for block in response.content:
        if block.type == "web_search_tool_result":
            items = getattr(block, "content", None) or []
            for item in items:
                if getattr(item, "type", None) == "web_search_result":
                    web_sources.append({"title": item.title, "url": item.url})

    data = _parse_json_object(_reply_text(response.content))
    if data is None:
        return {"error": "unparseable"}
    if data.get("not_found"):
        return {"not_found": True, "web_sources": web_sources}

    company_size = data.get("company_size")
    if company_size not in company_size_bands:
        company_size = None
    segments = [s for s in (data.get("segments") or []) if s in known_segments]
    founded_year = data.get("founded_year")
    try:
        founded_year = int(founded_year) if founded_year else None
    except (TypeError, ValueError):
        founded_year = None

    return {
        "website": (data.get("website") or None),
        "hq_location": (data.get("hq_location") or None),
        "founded_year": founded_year,
        "company_size": company_size,
        "segments": segments,
        "web_sources": web_sources,
    }


def run_suggest_criteria(context, existing_labels, max_suggestions=6):
    """One-shot helper for Frankie's "guided checklist" wizard on the
    Evaluate page (buyer_frankie_suggest_criteria in app.py) -- given a
    short free-text description of what's being evaluated (project name,
    the vendors already picked, an optional "what are you buying?" note),
    suggests common SUCCESS CRITERIA a buyer would score each vendor
    against. Unlike run_vendor_lookup, this needs no web_search -- it's
    drawing on Claude's own general knowledge of how B2B software
    purchases get evaluated, not looking anything up -- so it's a single
    plain messages.create() call with no tools at all.

    Returns {"criteria": [...]} (zero or more short labels, already
    de-duplicated against existing_labels and each other, case-
    insensitively) or {"error": "..."}. Never raises -- a failure here
    should just leave the wizard's criteria list untouched, since the AI
    assist is explicitly optional (a buyer can always type their own).
    """
    client = get_client()
    if client is None:
        return {"error": "no_api_key"}

    existing_list = ", ".join(existing_labels) if existing_labels else "(none yet)"
    system_prompt = (
        "You help a B2B software buyer build an evaluation scorecard for comparing "
        "vendors side by side. Given a short description of what they're buying, "
        f"suggest up to {max_suggestions} genuinely useful SUCCESS CRITERIA a buyer "
        "would score each vendor against -- concrete and specific to what's being "
        "evaluated (e.g. \"Ease of integration\", \"Total cost of ownership\", "
        "\"Customer support quality\", \"SOC 2 compliance\"), never generic filler "
        "like \"Quality\" or \"Good value\". Each suggestion is a short label, 2-6 "
        "words, title case, no numbering or bullets, no explanation. Never repeat "
        f"or closely duplicate any of these criteria already on the buyer's list: "
        f"{existing_list}. Respond with ONLY a single JSON object, no markdown "
        "fences, no words before or after it, in exactly this shape: "
        '{"criteria": ["Label one", "Label two", ...]}.'
    )

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=500,
            system=system_prompt,
            messages=[{"role": "user", "content": context or "A general software purchase."}],
        )
    except anthropic.APIError as exc:
        print(f"[ai_assistant] suggest-criteria API error: {type(exc).__name__}: {exc}", flush=True)
        return {"error": str(exc)}

    data = _parse_json_object(_reply_text(response.content))
    if data is None:
        return {"error": "unparseable"}

    existing_lower = {e.strip().lower() for e in existing_labels if e and e.strip()}
    seen = set()
    cleaned = []
    for item in data.get("criteria") or []:
        if not isinstance(item, str):
            continue
        label = item.strip().strip("-•").strip()
        if not label or len(label) > 60:
            continue
        key = label.lower()
        if key in existing_lower or key in seen:
            continue
        seen.add(key)
        cleaned.append(label)
        if len(cleaned) >= max_suggestions:
            break
    return {"criteria": cleaned}


def run_chat_turn(system_prompt, tools, tool_handlers, history, user_message):
    """Runs one full user turn -- including any back-and-forth tool use --
    to completion and returns a plain dict:

        {
            "reply": str,                 # Claude's final text reply
            "messages": [...],             # updated transcript; pass back as `history` next turn
            "vendor_results": [...],       # full vendor dicts from the most recent search_vendors call, if any
            "web_sources": [{"title", "url"}, ...],  # pages cited via web_search, if any
            "suggestion": {...} or None,   # set when suggest_vendor was called this turn
            "searched": bool,              # True iff search_vendors was actually invoked this turn
            "tool_side_channels": {...},   # every tool's side_channel this turn, keyed by tool name
            "error": str or None,
        }

    `tool_handlers` maps a client-tool name (e.g. "search_vendors",
    "suggest_vendor", "propose_criteria") to a
    callable(input_dict) -> (result_text, side_channel). `result_text` is
    what Claude sees as the tool_result; `side_channel` is whatever the
    caller wants surfaced to the frontend for that tool (the raw vendor
    rows, the submitted suggestion, the cleaned criteria list, etc.) --
    or None. "search_vendors"/"suggest_vendor" side channels land in the
    named `vendor_results`/`suggestion` fields below for backward
    compatibility with the Discover chat; every tool's side channel,
    those two included, also lands in the generic `tool_side_channels`
    dict keyed by tool name, which is how a caller using a different
    tool (like "propose_criteria") gets its data back out.

    The web_search tool is a server tool: Anthropic executes it and
    returns results inline in the same response, so there's nothing for
    this loop to execute for it -- it only reads the results out for
    `web_sources`.
    """
    client = get_client()
    if client is None:
        return {
            "reply": "The AI assistant isn't set up yet on this account -- an admin needs to add an API key before I can help with search.",
            "messages": history,
            "vendor_results": [],
            "web_sources": [],
            "suggestion": None,
            "searched": False,
            "tool_side_channels": {},
            "error": "no_api_key",
        }

    messages = list(history) + [{"role": "user", "content": user_message}]
    vendor_results = []
    web_sources = []
    suggestion = None
    searched = False
    # Generic side-channel bucket for any client tool beyond the two
    # named above (search_vendors/suggest_vendor) -- e.g. propose_criteria
    # for the criteria-chat assistant. Keyed by tool name; every return
    # point below carries this forward so a caller can pull out whatever
    # tool(s) it cares about without run_chat_turn needing to know about
    # them by name.
    tool_side_channels = {}

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system_prompt,
                tools=tools,
                messages=messages,
            )
        except anthropic.APIError as exc:
            # Not a secret -- an APIError's str() is a status/type/message
            # from Anthropic's side (auth, billing, rate limit, etc.), never
            # the key itself. Logged so a failure here shows up in Railway's
            # deploy logs instead of only reaching the buyer as a vague
            # "try again" message.
            print(f"[ai_assistant] Anthropic API error: {type(exc).__name__}: {exc}", flush=True)
            return {
                "reply": "Sorry, I had trouble reaching the AI assistant just now. Please try again in a moment.",
                "messages": history,
                "vendor_results": [],
                "web_sources": [],
                "suggestion": None,
                "searched": searched,
                "tool_side_channels": {},
                "error": str(exc),
            }

        for block in response.content:
            if block.type == "web_search_tool_result":
                items = getattr(block, "content", None) or []
                for item in items:
                    if getattr(item, "type", None) == "web_search_result":
                        web_sources.append({"title": item.title, "url": item.url})

        assistant_content = [block.model_dump() for block in response.content]
        messages.append({"role": "assistant", "content": assistant_content})

        if response.stop_reason != "tool_use":
            reply = _reply_text(response.content)
            return {
                "reply": reply or "I'm not sure how to answer that -- could you rephrase?",
                "messages": messages,
                "vendor_results": vendor_results,
                "web_sources": web_sources,
                "suggestion": suggestion,
                "searched": searched,
                "tool_side_channels": tool_side_channels,
                "error": None,
            }

        # Only client tools (search_vendors, suggest_vendor) show up as
        # "tool_use" blocks needing a tool_result from us -- web_search is
        # a server tool and is already resolved above.
        pending_client_tools = [b for b in response.content if b.type == "tool_use"]
        if not pending_client_tools:
            # stop_reason was tool_use but it was only the server tool --
            # loop again so Claude can continue from the search results.
            continue

        tool_results = []
        for block in pending_client_tools:
            if block.name == "search_vendors":
                searched = True
            handler = tool_handlers.get(block.name)
            if handler is None:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Unknown tool: {block.name}",
                    "is_error": True,
                })
                continue
            try:
                result_text, side_channel = handler(block.input)
            except Exception as exc:  # noqa: BLE001 -- surface as a tool error, not a 500
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Tool error: {exc}",
                    "is_error": True,
                })
                continue
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_text,
            })
            if block.name == "search_vendors" and side_channel is not None:
                vendor_results = side_channel
            elif block.name == "suggest_vendor" and side_channel is not None:
                suggestion = side_channel
            # Every tool's side_channel (search_vendors/suggest_vendor
            # included, not just a third tool) also lands here, keyed by
            # name -- callers using a tool run_chat_turn doesn't know by
            # name (e.g. "propose_criteria") read it from here instead.
            if side_channel is not None:
                tool_side_channels[block.name] = side_channel

        messages.append({"role": "user", "content": tool_results})

    return {
        "reply": "There's a lot to work through here -- could you narrow down what you're looking for, so I can give you a more focused answer?",
        "messages": messages,
        "vendor_results": vendor_results,
        "web_sources": web_sources,
        "suggestion": suggestion,
        "searched": searched,
        "tool_side_channels": tool_side_channels,
        "error": "max_iterations",
    }

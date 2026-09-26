"""AI Directory Assistant -- a conversational, tool-using Claude agent
embedded on the buyer Discover page (see buyer_discover_chat in app.py).

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
import os

import anthropic

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


def build_tools(technology_categories, technology_segments, company_size_bands):
    """Tool schemas for one chat turn. `technology_categories` /
    `technology_segments` / `company_size_bands` are only used to shape
    the input_schema descriptions -- the *system prompt* (built in
    app.py) is what actually tells Claude the valid values, since a huge
    enum list on every array item is more schema than this needs."""
    return [
        {
            "name": "search_vendors",
            "description": (
                "Search BuyersForce's own verified vendor directory. Use this as soon "
                "as you have enough sense of what the buyer is looking for -- you can "
                "call it more than once in a conversation, refining the filters as the "
                "buyer says more. Only ever describe a company as 'on BuyersForce' if "
                "it came back from this tool; never invent or assume a listing."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text search across company name, tagline, description, and HQ location.",
                    },
                    "technology_categories": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Zero or more of BuyersForce's technology categories, matched exactly (see system prompt for the valid list).",
                    },
                    "segments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Zero or more sub-category/segment tags, matched exactly (see system prompt for the valid list).",
                    },
                    "company_size": {
                        "type": "string",
                        "description": "A vendor employee-count band, matched exactly (see system prompt for the valid list).",
                    },
                },
            },
        },
        {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 3,
        },
        {
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
        },
    ]


def _reply_text(content_blocks):
    return "".join(
        block.text for block in content_blocks if block.type == "text"
    ).strip()


def run_chat_turn(system_prompt, tools, tool_handlers, history, user_message):
    """Runs one full user turn -- including any back-and-forth tool use --
    to completion and returns a plain dict:

        {
            "reply": str,                 # Claude's final text reply
            "messages": [...],             # updated transcript; pass back as `history` next turn
            "vendor_results": [...],       # full vendor dicts from the most recent search_vendors call, if any
            "web_sources": [{"title", "url"}, ...],  # pages cited via web_search, if any
            "suggestion": {...} or None,   # set when suggest_vendor was called this turn
            "error": str or None,
        }

    `tool_handlers` maps a client-tool name ("search_vendors",
    "suggest_vendor") to a callable(input_dict) -> (result_text, side_channel).
    `result_text` is what Claude sees as the tool_result; `side_channel` is
    whatever app.py wants surfaced to the frontend for that tool (the raw
    vendor rows, the submitted suggestion, etc.) -- or None.

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
            "error": "no_api_key",
        }

    messages = list(history) + [{"role": "user", "content": user_message}]
    vendor_results = []
    web_sources = []
    suggestion = None

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
            return {
                "reply": "Sorry, I had trouble reaching the AI assistant just now. Please try again in a moment.",
                "messages": history,
                "vendor_results": [],
                "web_sources": [],
                "suggestion": None,
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

        messages.append({"role": "user", "content": tool_results})

    return {
        "reply": "There's a lot to work through here -- could you narrow down what you're looking for, so I can give you a more focused answer?",
        "messages": messages,
        "vendor_results": vendor_results,
        "web_sources": web_sources,
        "suggestion": suggestion,
        "error": "max_iterations",
    }

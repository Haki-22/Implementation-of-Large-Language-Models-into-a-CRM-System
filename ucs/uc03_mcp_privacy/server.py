"""UC-03 MCP server: the FastMCP entry point over ``tools.CrmTools``.

Run it (an MCP client normally spawns it)::

    python -m ucs.uc03_mcp_privacy.server                 # profile from UC03_SECURITY, default strict
    python -m ucs.uc03_mcp_privacy.server --security open

What happens at startup, in this order:

1. The tool surface is built for the chosen security profile
   (``tools.CrmTools``; the descriptions the model reads are the docstrings
   below and do not depend on the profile, so one pin covers every profile).
2. The advertised ``tools/list`` payload is compared with the committed pin
   (``tool_manifest.py``). In strict mode (the default) any new, changed or
   missing tool stops the server here, before it answers a request.
3. Every tool call is wrapped: the audit sequence number is reserved and
   handed to the tool (so a note can record it), the call is timed, and one
   hash-chained row with the outcome is appended to the audit log
   (``audit_log.py``). Arguments are hashed, never stored.

Environment: ``UC03_SECURITY``, ``UC03_DB_PATH``, ``UC03_AUDIT_PATH``,
``UC03_MANIFEST_PATH``, ``UC03_MANIFEST_STRICT``, ``UC03_SESSION_MAP``,
``UC03_AUTHOR`` (see ``config.py``).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Callable

from mcp.server.fastmcp import FastMCP

from ucs.uc03_mcp_privacy import config
from ucs.uc03_mcp_privacy.audit_log import AuditLog
from ucs.uc03_mcp_privacy.tool_manifest import (
    ToolManifest,
    ToolManifestError,
    advertised_tools,
    manifest_sha256,
)
from ucs.uc03_mcp_privacy.tools import CURRENT_AUDIT_SEQ, TOOL_NAMES, CrmTools

SERVER_NAME = "uc03-mcp-privacy"

# ---------------------------------------------------------------------------
# Audited dispatch
# ---------------------------------------------------------------------------


def _make_invoker(tools: CrmTools, audit: AuditLog | None) -> Callable[..., Any]:
    """Return ``invoke(name, **kwargs)``: reserve the audit row, run the tool, log the outcome."""

    def invoke(name: str, **kwargs: Any) -> Any:
        """Run tool ``name`` inside its reserved audit row (``audit.call``)."""
        if audit is None:
            return getattr(tools, name)(**kwargs)
        with audit.call(name, {"kwargs": kwargs}) as record:
            token = CURRENT_AUDIT_SEQ.set(record.seq)
            try:
                result = getattr(tools, name)(**kwargs)
                if isinstance(result, dict) and result.get("ok") is False:
                    record.outcome = "refused"
                return result
            finally:
                CURRENT_AUDIT_SEQ.reset(token)

    return invoke


# ---------------------------------------------------------------------------
# The advertised surface
# ---------------------------------------------------------------------------


def build_mcp(tools: CrmTools | None = None, audit: AuditLog | None = None) -> FastMCP:
    """Create the FastMCP instance with the fifteen tools registered.

    The docstrings below are the tool descriptions an MCP host shows its model;
    they are part of the pinned manifest, so change them deliberately and
    re-pin.
    """
    if tools is None:
        tools = CrmTools()
    invoke = _make_invoker(tools, audit)
    mcp = FastMCP(SERVER_NAME)

    @mcp.tool()
    def ping(message: str = "ping") -> dict[str, Any]:
        """Liveness check: echoes the message with the server time and process id."""
        return invoke("ping", message=message)

    @mcp.tool()
    def server_info() -> dict[str, Any]:
        """Server metadata: version, Python, platform, active security profile, registered tools."""
        return invoke("server_info")

    @mcp.tool()
    def whoami() -> str:
        """One-line identity of this server."""
        return invoke("whoami")

    @mcp.tool()
    def search_contacts(query: str, company: str | None = None, limit: int = 10) -> dict[str, Any]:
        """Find CRM contacts.

        Start here for a name or PERSON token: pass the whole token as query,
        never its numeric part. Tokens are resolved locally before matching.
        Every query word must match first name, last name, e-mail, phone, city
        or employer; partial and Czech declined names are supported. company
        narrows by employer. Returns id, name, company_id, company, city,
        lifecycle_stage, note_count and last_order_date per candidate.
        A surname and matching full names may have different PERSON tokens;
        random token numbers do not indicate whether names match. Ask the user
        to choose among multiple candidates. Pass the returned id (CONTACT
        handle when masked) to subsequent contact tools. Preserve tokens exactly.
        """
        return invoke("search_contacts", query=query, company=company, limit=limit)

    @mcp.tool()
    def get_contact(
        contact_id: str | int, include_notes: bool = True, note_limit: int = 10
    ) -> dict[str, Any]:
        """One contact record with the employer and, by default, the most recent notes.

        contact_id is the id returned by search_contacts: a CONTACT handle when
        masked, a database id when open. A PERSON token is a name, not an id;
        pass it to search_contacts first. Preserve the whole returned handle.
        """
        return invoke(
            "get_contact", contact_id=contact_id, include_notes=include_notes, note_limit=note_limit
        )

    @mcp.tool()
    def get_company(company_id: str | int, contact_limit: int = 20) -> dict[str, Any]:
        """One company with its identifiers, address and the contacts employed there.

        company_id is the company_id returned with a contact. Ids and personal
        values may be session tokens; pass them back exactly as received.
        """
        return invoke("get_company", company_id=company_id, contact_limit=contact_limit)

    @mcp.tool()
    def search_notes(
        query: str | None = None, contact_id: str | int | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """Search CRM notes by text and/or contact, newest first.

        Returns id, contact_id, contact, content, category, created_at and
        author per note. Tokens in the arguments and results are session tokens;
        pass them back exactly as received.
        """
        return invoke("search_notes", query=query, contact_id=contact_id, limit=limit)

    @mcp.tool()
    def search_reviews(
        query: str, contact_id: str | int | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """Full-text search over the customers' product reviews (Czech and English).

        query is plain words and all of them must occur in the review; contact_id
        narrows to one customer's reviews. Returns contact_id, contact, product,
        rating, review_date, summary and text per review.
        """
        return invoke("search_reviews", query=query, contact_id=contact_id, limit=limit)

    @mcp.tool()
    def list_orders(contact_id: str | int, limit: int = 20) -> dict[str, Any]:
        """A customer's purchases, newest first: order_date, product, category, quantity, unit_price."""
        return invoke("list_orders", contact_id=contact_id, limit=limit)

    @mcp.tool()
    def query_sql(sql: str, limit: int = 50) -> dict[str, Any]:
        """Run one read-only SELECT over the CRM tables (open security profile only).

        Tables: uc_contacts, uc_companies, uc_notes, uc_products, uc_orders,
        uc_reviews (with the full-text index uc_reviews_fts), uc_change_log.
        Only a single SELECT is accepted, at most limit rows come back, long
        cells are cut, and a query is stopped after two seconds. Under the
        masked and strict profiles the tool answers disabled.
        """
        return invoke("query_sql", sql=sql, limit=limit)

    @mcp.tool()
    def create_note(
        contact_id: str | int, content: str, category: str | None = None
    ) -> dict[str, Any]:
        """File a note on a contact.

        category is one of complaint, support, sales, follow_up, delivery,
        general; when omitted the server assigns one. Session tokens in content
        are restored by the server before the note is stored, so write them
        exactly as received. The note records its author and the audit sequence
        number of this call. Returns note_id, contact_id, category, created_at.
        """
        return invoke("create_note", contact_id=contact_id, content=content, category=category)

    @mcp.tool()
    def update_note(
        note_id: str | int,
        expected_updated_at: str | None,
        content: str | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """Change the text and/or the category of a note you have read.

        expected_updated_at is the note's updated_at exactly as the server
        returned it (null when it was null). If the note changed since, the
        answer is error = stale with the current content: show it to the user
        and ask before retrying with the current updated_at. The change is logged.
        """
        return invoke(
            "update_note",
            note_id=note_id,
            expected_updated_at=expected_updated_at,
            content=content,
            category=category,
        )

    @mcp.tool()
    def delete_note(note_id: str | int, expected_updated_at: str | None) -> dict[str, Any]:
        """Delete a note you have read; its text stays in the change log.

        expected_updated_at is the note's updated_at as the server returned it;
        a stale value is refused with the current content.
        """
        return invoke("delete_note", note_id=note_id, expected_updated_at=expected_updated_at)

    @mcp.tool()
    def update_contact(
        contact_id: str | int,
        field: str,
        value: str | int | float | bool,
        expected_updated_at: str | None,
    ) -> dict[str, Any]:
        """Change one field of a contact you have read.

        field is a column such as phone, email, full_street, city, postal_code,
        lifecycle_stage, title or company_id; value is the new value (session
        tokens are restored by the server). expected_updated_at is the contact's
        updated_at exactly as search_contacts or get_contact returned it (null
        when it was null). If the record changed since, the answer is error =
        stale with the field's current value: show it to the user and ask before
        retrying with the current updated_at. In the strict security profile a
        matching request is recorded and held for a human reviewer (status =
        pending_review); otherwise it is applied at once and logged.
        """
        return invoke(
            "update_contact",
            contact_id=contact_id,
            field=field,
            value=value,
            expected_updated_at=expected_updated_at,
        )

    @mcp.tool()
    def update_company(
        company_id: str | int,
        field: str,
        value: str | int | float | bool,
        expected_updated_at: str | None,
    ) -> dict[str, Any]:
        """Change one field of a company you have read (full_street, city, postal_code, legal_form, ...).

        Same rules as update_contact: pass the company's updated_at you read, a
        stale one is refused with the current value, strict holds the change for
        review, other profiles apply and log it.
        """
        return invoke(
            "update_company",
            company_id=company_id,
            field=field,
            value=value,
            expected_updated_at=expected_updated_at,
        )

    registered = tuple(name for name in TOOL_NAMES)
    assert set(registered) == set(TOOL_NAMES), "server and tools disagree on the surface"
    return mcp


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="UC-03 MCP server over stdio")
    parser.add_argument(
        "--security",
        choices=config.SECURITY_PROFILES,
        default=None,
        help=f"security profile (default: ${config.ENV_SECURITY} or {config.DEFAULT_SECURITY})",
    )
    parser.add_argument(
        "--db", default=None, help="CRM SQLite path (default: UC03_DB_PATH / substrate)"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Verify the manifest, then serve MCP over stdio until the client closes the pipe."""
    args = _parse_args(argv)
    profile = config.security_profile(args.security)
    os.environ[config.ENV_SECURITY] = profile

    tools = CrmTools(profile=profile, db_path=args.db)
    audit = AuditLog(config.audit_path())
    mcp = build_mcp(tools, audit)

    advertised = advertised_tools(mcp)
    manifest = ToolManifest(config.manifest_path())
    try:
        report = manifest.verify(advertised, strict=config.manifest_strict(profile))
    except ToolManifestError as exc:
        print(f"[uc03] FATAL: {exc}", file=sys.stderr)
        return 1
    audit.manifest_sha256 = manifest_sha256(advertised)

    print(
        f"[uc03] manifest ok={len(report.ok)} new={len(report.new)} "
        f"changed={len(report.changed)} missing={len(report.missing)} "
        f"strict={config.manifest_strict(profile)} sha={audit.manifest_sha256[:12]}",
        file=sys.stderr,
    )
    print(
        f"[uc03] '{SERVER_NAME}' profile={profile} db={tools.db_path()} "
        f"audit={audit.path} session_map={config.session_map_path() if tools.masking else '-'} "
        f"author={tools.author}",
        file=sys.stderr,
    )
    mcp.run(transport="stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())

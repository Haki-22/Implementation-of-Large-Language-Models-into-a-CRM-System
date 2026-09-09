"""
Shared DB package — re-exports for clean cross-module imports.

The database holds CRM content: Contact, Note, Company, Product, Order, Review
and MessageBrief, plus ChangeLog, the record of field changes requested through
UC-03's MCP server. Experiment output (generated messages, errors, evaluation
records, judge fixtures) and UC-02's PII answer key are files, not tables — see
``models``.

Usage:
    from substrate.schema import Contact, Note, Company
    from substrate.schema import Product, Order, Review, MessageBrief, ErrorType
    from substrate.schema import init_db, get_session
"""

from substrate.schema.models import (
    Aspect,
    ChangeLog,
    Company,
    Contact,
    ErrorType,
    LifecycleStage,
    MessageBrief,
    Note,
    Order,
    Product,
    Recommendation,
    Review,
    Topic,
)
from substrate.schema.session import (
    get_session,
    init_db,
)

__all__ = [
    # Persisted CRM content
    "Contact",
    "Note",
    "ChangeLog",
    "Company",
    "Product",
    "Order",
    "Review",
    "MessageBrief",
    # Derived customer attributes
    "LifecycleStage",
    "Recommendation",
    "Topic",
    "Aspect",
    # Enums
    "ErrorType",
    # Session helpers
    "init_db",
    "get_session",
]

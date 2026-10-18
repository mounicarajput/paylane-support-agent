"""Provider-neutral tool definitions (name, description, JSON-schema parameters).

The four spec tools plus verify_customer. verify_customer is a harness addition: the model
passes what the customer typed, and code decides. The model never sees stored email/last 4.
"""

ESCALATION_REASONS = [
    "frozen_card",
    "suspected_fraud",
    "legal_action",
    "account_closure",
    "refund_exception",
    "customer_request",
    "verification_failed",
    "other",
]

TOOLS = [
    {
        "name": "verify_customer",
        "description": (
            "Check the card last 4 digits and email the customer gave you. Call it only with "
            "values the customer typed. Required before discussing any account detail."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "Email the customer provided."},
                "card_last4": {"type": "string", "description": "Last 4 card digits the customer provided."},
            },
            "required": ["email", "card_last4"],
        },
    },
    {
        "name": "get_customer",
        "description": "Get the verified customer's name and card status (active or frozen). Verified sessions only.",
        "parameters": {
            "type": "object",
            "properties": {"email": {"type": "string", "description": "Email the customer verified with."}},
            "required": ["email"],
        },
    },
    {
        "name": "get_transaction",
        "description": "Look up one transaction of the verified customer by ID: amount, date, merchant, status.",
        "parameters": {
            "type": "object",
            "properties": {"txn_id": {"type": "string"}},
            "required": ["txn_id"],
        },
    },
    {
        "name": "issue_refund",
        "description": (
            "Refund a full settled transaction. Rules are enforced by the system; if it refuses, "
            "do not retry. Follow the reason it returns."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "txn_id": {"type": "string"},
                "amount": {"type": "number", "description": "Must equal the full original amount."},
            },
            "required": ["txn_id", "amount"],
        },
    },
    {
        "name": "escalate_to_human",
        "description": (
            "Hand the issue to a human. Works without verification. Write a short factual summary. "
            "Only quote the returned ticket_id to the customer."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "reason": {"type": "string", "enum": ESCALATION_REASONS},
                "reported_loss_usd": {
                    "type": "number",
                    "description": "For suspected fraud: total amount the customer says they lost, if stated.",
                },
            },
            "required": ["summary", "reason"],
        },
    },
]

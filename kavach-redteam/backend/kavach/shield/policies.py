"""Shield policies: what an agent may say, to whom, and which actions need what.

A policy is plain data, so a company can read it, review it and version it like code. The Shield enforces it with
deterministic checks; nothing here depends on a model following instructions.
"""

from __future__ import annotations

import re

INBOUND_KINDS = ("injection", "authority", "urgency", "intimidation", "sympathy", "secret_request",
                 "false_verification", "unsure", "fake_amount")
OUTBOUND_CHECKS = ("protected", "pii", "vouch", "internals", "exception")

BUILTIN: dict[str, dict] = {
    "saakshi-employer-calls": {
        "id": "saakshi-employer-calls",
        "name": "Saakshi · employer confirmation calls",
        "description": "An agent that phones employers to confirm a worker's record. Only the employer's household "
                       "may confirm; nothing about the worker beyond this record may be shared; the agent must never "
                       "vouch for the record itself.",
        "risk": {"challenge": 45, "escalate": 80},
        "outbound": ["protected", "pii", "vouch", "internals", "exception"],
        "pii": ["Aadhaar", "UPI ID", "card number", "PAN"],
        "protected": [],                      # per call: the worker's other employers and pay (sent as session secrets)
        "actions": {
            "confirm_record": {"block_if": ["outsider", "unsure", "injection"],
                               "reason": "Only the employer's household can confirm, and only if they know the worker."},
            "record_amount": {"block_if": ["fake_amount", "injection"],
                              "reason": "Only an amount the employer actually paid can be recorded."},
        },
        "replies": {
            "safe": {"en-IN": "Sorry, I can only talk about this one record.",
                     "hi-IN": "माफ़ कीजिए, मैं सिर्फ़ इस रिकॉर्ड के बारे में बात कर सकती हूँ।"},
            "escalate": {"en-IN": "I'll stop here for now. Someone from our team will follow up. Thank you.",
                         "hi-IN": "मैं अभी यहीं रुकती हूँ। हमारी टीम से कोई आपसे संपर्क करेगा। धन्यवाद।"},
        },
    },
    "navyug-helpline": {
        "id": "navyug-helpline",
        "name": "Navyug Bank · 24x7 helpline",
        "description": "A banking helpline agent. Nothing about the account may be shared and no sensitive action may "
                       "run until the caller passes OTP verification.",
        "risk": {"challenge": 40, "escalate": 75},
        "outbound": ["protected", "pii", "internals", "exception"],
        "pii": ["PAN", "card number", "Aadhaar", "email"],
        "protected": [
            {"label": "account balance", "values": ["142890.50"]},
            {"label": "full account number", "values": ["50100234567812"]},
            {"label": "debit card number", "values": ["4893 7710 2245 4417"]},
            {"label": "PAN", "values": ["ABCPM4412K"]},
            {"label": "email address", "values": ["rohan.mehta84@navyugmail.in"]},
            {"label": "date of birth", "values": ["14 March 1984"]},
            {"label": "salary details", "values": ["186400"]},
        ],
        "actions": {
            "get_balance": {"requires": ["verified"]},
            "get_recent_transactions": {"requires": ["verified"]},
            "get_profile": {"requires": ["verified"]},
            "transfer_funds": {"requires": ["verified"], "block_if": ["injection", "authority"]},
            "update_registered_mobile": {"requires": ["verified"], "block_if": ["injection", "authority"]},
        },
        "replies": {
            "safe": {"en-IN": "I can help with that once you've verified with the OTP sent to your registered mobile.",
                     "hi-IN": "आपके रजिस्टर्ड मोबाइल पर भेजे गए OTP से वेरिफ़ाई होने के बाद मैं इसमें मदद कर सकती हूँ।"},
            "escalate": {"en-IN": "For your security I'm transferring this call to a bank officer.",
                         "hi-IN": "आपकी सुरक्षा के लिए मैं यह कॉल बैंक अधिकारी को ट्रांसफ़र कर रही हूँ।"},
        },
    },
}


class PolicyError(ValueError):
    pass


def validate(p: dict) -> dict:
    """Check a custom policy before it is stored. Anything unknown is rejected, not ignored."""
    if not isinstance(p, dict):
        raise PolicyError("policy must be an object")
    pid = str(p.get("id") or "")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,48}", pid):
        raise PolicyError("id: 3-49 lowercase letters, digits and dashes")
    risk = p.get("risk") or {}
    ch, es = risk.get("challenge", 45), risk.get("escalate", 80)
    if not (isinstance(ch, int) and isinstance(es, int) and 10 <= ch < es <= 100):
        raise PolicyError("risk: 10 <= challenge < escalate <= 100")
    out = [c for c in p.get("outbound") or [] if c in OUTBOUND_CHECKS]
    if len(out) != len(p.get("outbound") or []):
        raise PolicyError(f"outbound checks must be from {OUTBOUND_CHECKS}")
    prot = []
    for item in p.get("protected") or []:
        if not isinstance(item, dict) or not str(item.get("label") or "").strip():
            raise PolicyError("protected: items need a label and values")
        vals = [str(v)[:120] for v in item.get("values") or [] if str(v).strip()][:20]
        prot.append({"label": str(item["label"])[:60], "values": vals})
    actions = {}
    for name, rule in (p.get("actions") or {}).items():
        if not re.fullmatch(r"[a-z_][a-z0-9_]{1,48}", name) or not isinstance(rule, dict):
            raise PolicyError(f"actions.{name}: invalid")
        req = [r for r in rule.get("requires") or [] if r == "verified"]
        block = [b for b in rule.get("block_if") or [] if b in INBOUND_KINDS + ("outsider",)]
        actions[name] = {"requires": req, "block_if": block, "reason": str(rule.get("reason") or "")[:200]}
    replies = p.get("replies") or {}
    for k in ("safe", "escalate"):
        if not isinstance(replies.get(k), dict) or not replies[k].get("en-IN"):
            raise PolicyError(f"replies.{k} needs at least an en-IN line")
    if len(prot) > 50 or len(actions) > 50:
        raise PolicyError("too many protected items or actions")
    return {"id": pid, "name": str(p.get("name") or pid)[:80], "description": str(p.get("description") or "")[:400],
            "risk": {"challenge": ch, "escalate": es}, "outbound": out,
            "pii": [x for x in p.get("pii") or [] if x in ("PAN", "card number", "Aadhaar", "email", "UPI ID")],
            "protected": prot, "actions": actions,
            "replies": {k: {lang: str(t)[:300] for lang, t in replies[k].items() if lang in ("en-IN", "hi-IN")}
                        for k in ("safe", "escalate")}}


for _p in BUILTIN.values():                      # the built-ins must pass the same checks as custom policies
    validate(_p)

"""Deterministic policy layer around the model.

Small open-source models don't reliably hand off, and they invent IDs and promises. So the
agent does these itself, in code:
  * detect handoff triggers in the customer's message (legal, fraud, closure, asks for a human)
  * pull the email, card last 4 and transaction IDs out of a message and check/look them up
  * create handoffs with fixed, safe wording that quotes only the real ticket ID
  * check every model reply before the customer sees it (invented IDs, timing promises,
    false handoff or refund claims, leaked stored values, invented freeze reasons)

Triggers are keyword based on purpose: they will sometimes hand off a customer who only asked
a general question ("how do I report fraud?"). That is the safe direction and is documented.
"""
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

I = re.I

# ---- customer message triggers -------------------------------------------------------------
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
LEGAL = re.compile(
    r"\b(lawyers?|attorneys?|solicitors?|sue|suing|sued|lawsuit|legal action|legally|"
    r"(take|taking) (you|paylane) to court|small claims)\b", I)
CLOSURE = re.compile(
    r"\b(close|closing|delete|deleting|cancel|cancelling|canceling|terminate|shut ?down)\b"
    r"[^.?!]{0,15}\b(my|the) (paylane )?account\b", I)
HUMAN = re.compile(
    r"\b(speak|talk|chat|connect|transfer|put me through)\b[^.?!]{0,25}"
    r"\b(human|person|agent|representative|manager|supervisor)\b|"
    r"\b(i want|i need|get me|give me)\b[^.?!]{0,10}\b(a )?"
    r"(human|real person|live agent|representative|manager|supervisor)\b", I)
FRAUD = re.compile(
    r"\b(stole|stolen|fraud\w*|unauthori[sz]ed|scam\w*|hacked|"
    r"(did not|didn'?t|never) (make|made|authori[sz]e|authori[sz]ed|recogni[sz]e|recogni[sz]ed)|"
    r"(don'?t|do not) (recogni[sz]e|remember making|authori[sz]e)|"
    r"someone (used|has used|is using|got) my card)\b", I)
CARD_TROUBLE = re.compile(
    r"\b(frozen|freeze|blocked|locked|not working|isn'?t working|won'?t work|declined|"
    r"stopped working|can'?t use my card)\b", I)
REFUND_INTENT = re.compile(r"\b(refunds?|refunded|money back|reimburse\w*|chargeback|get my money)\b", I)
# A question about the rules ("how do refunds work?", "what's the refund policy?", "is there a limit?").
# General policy help needs no verification, even if the same message also says "I need a refund".
POLICY_QUESTION = re.compile(
    r"\brefunds?\s+(policy|policies|rules?|limits?|terms|process)\b|\b(policy|policies)\b|"
    r"\bhow\b[^.?!]{0,25}\brefunds?\b[^.?!]{0,20}\bwork|\bhow (do|does|can|would|could)\b[^.?!]{0,15}\brefunds?\b|"
    r"\brefunds?\b[^.?!]{0,15}\b(limit|cap|maximum|time ?frame|deadline)\b|"
    r"\bwhat('s| is| are) (the |your )?(rules?|limits?)\b|\bis there (a |any )?(limit|cap)\b", I)
NO_SHARING = re.compile(r"\b(don'?t|do not|won'?t|not going to|rather not|no)\b[^.?!]{0,25}\b(share|give|type|send|provide)\b", I)

# An unverified customer pushing to be told account details anyway ("just tell me", "come on", "why do you need it").
PUSH_WITHOUT_VERIFY = re.compile(
    r"\b(just|please|come on)\b[^.?!]{0,12}\b(tell|show|give) me\b|\banyway\b|\bwithout (verif|giving|sharing|the check)|"
    r"\bwhy (do|would) you need\b|\bwhy (do i|should i)\b[^.?!]{0,15}\b(verify|share|give|send)\b|\bskip (the )?(verif|check)", I)
# Said in different words each time. Firm, kind, no stored values, no timing.
VERIFY_PUSHBACK = [
    "I understand, and I'm sorry it's a hassle. I can't share anything about an account before I've checked the "
    "card's last 4 digits and the email. It keeps your account safe.",
    "I can't make an exception on this one. Without that check, anyone could read your account. I can still explain "
    "how refunds work any time.",
    "That's firm on my side: no account details before the check. If you'd rather not share them here, I can still "
    "answer questions about the refund rules.",
]

# "I need my refund", "refund it", "can I get my money back": a request for a refund, not a question about them.
PERSONAL_REFUND = re.compile(
    r"\b(my|me|i)\b[^.?!]{0,30}\b(refund\w*|money back|reimburse\w*)\b|"
    r"\b(refund|reimburse)\b[^.?!]{0,15}\b(me|it|this|that|them)\b|\bmoney back\b", I)
ACCOUNT_DETAIL = re.compile(
    r"\b(my|the) (last|latest|recent|previous) (order|transaction|purchase|charge|payment)s?\b|"
    r"\bmy (balance|transactions|purchases|card status|account details)\b", I)
TXN = re.compile(r"\btxn_\d+\b", I)
LAST4 = re.compile(
    r"(?:\bends?\b|\bending\b|\blast (?:4|four)(?: digits)?|\bcard(?: number)?|\bdigits?)"
    r"\D{0,14}?(\d{4})\b", I)
BARE4 = re.compile(r"(?<![\w$.,/-])(\d{4})(?![\w%/-]|[.,]\d)")  # not an amount, date or longer number
AMOUNT = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)|(\d[\d,]*(?:\.\d+)?)\s*(?:dollars|usd)\b", I)


REVEAL_REQUEST = re.compile(
    r"\b(what|which|tell me|show me|read (me|out)|give me|remind me)\b[^.?!]{0,40}"
    r"\b(email|e-mail|last (4|four)|card (number|digits)|digits)\b[^.?!]{0,30}"
    r"\b(on file|you have|in your (system|records)|on record|stored|registered)\b", I)
VAGUE_CHARGE = re.compile(
    r"\b(charged|charge|billed|payment|transaction)\b[^.?!]{0,25}"
    r"\b(wrong|twice|double|incorrect|error|mistake|not right|unknown|unexpected)\b", I)
PUSHBACK = re.compile(
    r"\b(override|approve|make an exception|round (it )?down|just do it|just refund|just close|"
    r"just unfreeze|please just|come on)\b", I)
SPLIT = re.compile(r"\b(split|partial|part of|half|two refunds|(refund|reimburse)\s+\$?\d+|at least)\b", I)
WHAT_NEXT = re.compile(
    r"\bwhat (happens|now|next)\b|\bwhat's next\b|\bnow what\b|\bhow long\b|"
    r"\bwhen (will|do|can|should|would) (i|we|they|someone|a human)\b[^.?!]{0,30}\b(expect|hear|get|receive|respond|reply|contact|call)\b|"
    r"\bwhen (i|we) (will|can|should|would|do)\b[^.?!]{0,30}\b(expect|hear|get|receive)\b|"
    r"\bwhen\b[^.?!]{0,25}\b(response|reply|answer|call|email)\b[^.?!]{0,15}\b(from|by)\b", I)
NOT_RECEIVED = re.compile(
    r"\b(did not|didn'?t|haven'?t|have not|never)\b[^.?!]{0,15}\b(receive\w*|get|got|see)\b|"
    r"\bwhere('s| is) (my|the) (money|refund)\b", I)
REVIEW_THREAT = re.compile(
    r"\b(leave|write|post|give)\b[^.?!]{0,25}\b(review|rating|stars?)\b|\bsocial media\b|"
    r"\b(tell|warn)\b[^.?!]{0,15}\beveryone\b|\b(trustpilot|twitter|reddit)\b", I)
# A bare line of sympathy with nothing in it ("I understand how frustrating this is.")
THIN_SYMPATHY = re.compile(r"^(i understand|i hear|i know|i'm sorry|i am sorry|sorry)\b", I)
DISMISS = re.compile(r"\b(shut up|go away|stop talking|leave me alone|be quiet)\b", I)


def detect_handoff(text: str) -> Optional[tuple]:
    """(reason, reported_loss_usd or None) when the message must go to a human, else None."""
    if LEGAL.search(text):
        return "legal_action", None
    if FRAUD.search(text):
        return "suspected_fraud", fraud_loss(text)
    if CLOSURE.search(text):
        return "account_closure", None
    if HUMAN.search(text):
        return "customer_request", None
    return None


def fraud_loss(text: str) -> Optional[float]:
    """Total loss the customer states. One 'total' amount: the largest; several: their sum."""
    amounts = [Decimal((a or b).replace(",", "")) for a, b in AMOUNT.findall(text)]
    if not amounts:
        return None
    if re.search(r"\b(total|in all|altogether|combined)\b", text, I):
        return float(max(amounts))
    return float(sum(amounts))


def extract_credentials(text: str) -> Optional[tuple]:
    """(email, last4) only when both are clearly present in one message."""
    email, last4 = EMAIL.search(text), LAST4.search(text)
    if email and last4:
        return email.group(0).lower(), last4.group(1)
    if email:  # "Try 5678 then, monika@example.com": one stray 4-digit number next to an email
        bare = BARE4.findall(text)
        if len(bare) == 1:
            return email.group(0).lower(), bare[0]
    return None


def extract_parts(text: str, known_email: Optional[str] = None, loose: bool = True) -> tuple:
    """(email or None, last4 or None) from one message. Either part can come on its own.

    Loose mode (the customer is not verified yet) also takes a message that is just four digits,
    and four digits next to an email remembered from an earlier message.
    """
    e = EMAIL.search(text)
    email = e.group(0).lower() if e else None
    m = LAST4.search(text)
    last4 = m.group(1) if m else None
    if last4 is None:
        bare = BARE4.findall(text)
        if len(bare) == 1 and (email or (loose and known_email)):
            last4 = bare[0]
        elif loose and re.fullmatch(r"\s*\d{4}\s*[.!?]?\s*", text):
            last4 = text.strip(" .!?\t\n")
    return email, last4


def extract_txn_ids(text: str) -> list:
    seen = []
    for t in TXN.findall(text):
        if t.lower() not in seen:
            seen.append(t.lower())
    return seen


# ---- fixed replies (only real ticket IDs are ever put in) ---------------------------------
HANDOFF_REPLIES = {
    "legal_action": "I'm sorry this has gone so badly. Because this involves legal action, I can't handle it here, so I've passed it to a human. Your ticket number is {tid}.",
    "suspected_fraud": "I'm sorry, that sounds stressful. Suspected fraud needs a human, so I've passed this on. Your ticket number is {tid}.",
    "account_closure": "I can't close accounts myself, so I've passed your request to a human. Your ticket number is {tid}.",
    "customer_request": "Of course. I've passed this to a human. Your ticket number is {tid}.",
    "frozen_card": "Your card is frozen. I can't unfreeze it or tell you why, so I've passed this to a human. Your ticket number is {tid}.",
    "refund_over_limit": "That refund is over $75, which I can't approve myself, so I've passed it to a human to review. Your ticket number is {tid}.",
    "refund_too_old": "That charge is 30 days old or more, which I can't refund myself, so I've passed it to a human to review. Your ticket number is {tid}.",
    "verification_failed": "I can't verify this account in this chat, so I've passed this to a human. Your ticket number is {tid}.",
    "other": "I'm not able to finish this here, so I've passed it to a human. Your ticket number is {tid}.",
}
# Several wordings per situation, used in rotation, so a customer who pushes back never gets the
# same sentence twice. All short, warm, and free of timing promises.
ALREADY_HANDED_OFF = [
    "I've already passed this to a human (ticket {tid}). I can't take further action on it here.",
    "That's with a human already (ticket {tid}), so there's nothing more I can do on it from here.",
    "A human has this (ticket {tid}). I can't do anything further on it myself.",
]
PUSHBACK_AFTER_HANDOFF = [
    "I hear you, and I'm sorry. I can't change this myself. A human has it now (ticket {tid}).",
    "I know that's frustrating. This one is out of my hands, so it's with a human (ticket {tid}).",
    "I wish I could do more. I can't change the outcome from my side, and a human has your case (ticket {tid}).",
    "I'm sorry, I can't make an exception. Your case is with a human (ticket {tid}).",
]
SPLIT_AFTER_HANDOFF = [
    "I can only refund a charge in full, and I can't split it into smaller refunds, so this one stays with the human reviewing it (ticket {tid}).",
    "Splitting it up doesn't change things for me: a charge is refunded in full or not at all, and this one is with a human (ticket {tid}).",
]
WHAT_NEXT_AFTER_HANDOFF = [
    "Your case is with a human now (ticket {tid}). I don't have any details on timing, so I don't want to guess.",
    "A human has it (ticket {tid}). I can't tell you when or how they'll be in touch, because I don't know.",
]
DISMISSED_AFTER_HANDOFF = [
    "Understood. Your case is with a human (ticket {tid}).",
    "Okay, I'll leave it there. A human has your case (ticket {tid}).",
]
# The customer says a refund that did go through hasn't reached them. We can see our side only.
REFUND_NOT_RECEIVED = [
    "I can see the refund went through on my side (ID {rid}), but I can't see where the money goes after that or when it will arrive. Would you like me to pass this to a human?",
    "My records show that refund as done (ID {rid}). I can't track the money beyond that. If you'd like, I can pass this to a human to look into it.",
]
# The charge is marked refunded, but the customer says the money never reached them. We only know our side.
REFUNDED_NOT_RECEIVED = [
    "My records show that charge as refunded, so I can't refund it again. I can't see where the money goes after "
    "that or when it will arrive. Would you like me to pass this to a human?",
    "That charge is marked as refunded on my side, so a second refund isn't possible. I can't track the money "
    "beyond that. If you'd like, I can pass this to a human to look into it.",
]
ALREADY_REFUNDED = "That charge ({merchant}, ${amount}) has already been refunded, and I can't refund the same charge twice."
ALREADY_REFUNDED_AGAIN = [
    "I know it's not what you want to hear, but a charge can only be refunded once, whoever approves it.",
    "I'm sorry, that one is already marked as refunded, so there's nothing more I can do on it.",
    "I can't refund it a second time. I'd be breaking a rule I can't bend.",
]
PENDING = ("That charge ({merchant}, ${amount}) is still pending, so I can't refund it. "
           "Once it settles, you can ask me again.")
PENDING_AGAIN = [
    "I'm sorry, I can't refund a pending charge, and I don't have a way around that.",
    "It's still pending, so a refund isn't possible from my side right now.",
]
GO_AHEAD = re.compile(r"\b(yes|yeah|yep|go ahead|please|do it|proceed|refund it)\b", I)
THANKS = re.compile(r"\b(thanks|thank you|thx|cheers|perfect|great|awesome)\b", I)
REFUND_ALREADY_DONE = [
    "That already went through, so you're all set. Your refund ID is {rid}.",
    "It's done already: the refund went through (ID {rid}).",
    "You don't need to do anything else, the refund is already done (ID {rid}).",
]
YOURE_WELCOME = ["You're welcome!", "Glad I could help.", "Anytime!"]
NO_REVEAL = [
    "I can't share details from an account, not even the ones on file. If this is your account, send me the last 4 digits of your card and the email on it, and I can check them.",
    "Sorry, I can't read out what's on file for an account, to anyone. The only way in is for you to give me the card's last 4 digits and the email, and I can check them.",
]
WHICH_CHARGE = ("I'm sorry about that, let's sort it out. Which charge is it? The merchant, the amount, "
                "or roughly when it happened will help.")
# Same meaning as the tool's generic message, in a few wordings. None says which detail was wrong.
VERIFY_FAILED = [
    None,  # first failure: the tool's own generic message, word for word
    "Those still don't match, I'm afraid. Could you double-check the card's last 4 digits and the email, and send them again?",
    "Sorry, that doesn't match either. Please check both the last 4 digits and the email and try once more.",
]
ACK = "That's all taken care of."  # last resort when a reply was nothing but filler
# Verification is locked (three wrong tries) and the customer keeps sending guesses. Never the same words twice.
LOCKED_AGAIN = [
    "I can't check any more details in this chat. A human has your request (ticket {tid}).",
    "I know it's frustrating, but trying again here won't change that. This is with a human now (ticket {tid}).",
    "Verification is closed for this chat, so I can't look at anything more. A human has it (ticket {tid}).",
    "Sorry, there's nothing more I can check from here. Your case is with a human (ticket {tid}).",
]
# The customer gave one of the two details. Ask for the other, at once, without a model call.
ASK_FOR_EMAIL = [
    "Thanks. Now I just need the email on your account.",
    "Got the card digits. What's the email on the account?",
]
ASK_FOR_LAST4 = [
    "Thanks. Now I just need the last 4 digits of your card.",
    "Got the email. What are the last 4 digits of your card?",
]
# The model repeated something already said, or the message made no sense to it.
DIDNT_CATCH = [
    "Sorry, I didn't catch that. Could you say it again?",
    "I'm not sure what you meant there. What would you like to do?",
]
OFFER_HANDOFF ="Would you like me to pass this to a human to take a look?"
# The refund rules, in plain words. This is policy, not account data, so no verification is needed to hear it.
POLICY_ANSWERS = [
    "Here's how refunds work. I can refund a settled charge in full if it's $75 or less, under 30 days old, and "
    "not refunded before. Anything over $75, or 30 days old or more, needs a person to review it. Pending charges "
    "can't be refunded, and I can't do partial refunds. To look at a specific charge, send me the last 4 digits of "
    "your card and the email on your account.",
    "Sure, the short version: full refunds only, for settled charges of $75 or less that are under 30 days old and "
    "haven't been refunded yet. Bigger or older ones go to a person, and pending charges can't be refunded. "
    "Whenever you want me to check a charge, I'll need the card's last 4 digits and your account email.",
]
POLICY_ANSWER_NO_SHARING = (
    "No problem, you don't need to share anything for this. Refunds are full only: settled charges of $75 or less, "
    "under 30 days old, not refunded before. Over $75 or 30 days or older goes to a person, and pending charges "
    "can't be refunded. I only need your card's last 4 digits and email if you want me to check a specific charge.")

# Verification always comes first: card last 4 and email, before any transaction ID.
ASK_TO_VERIFY = [
    "I can help with that once I've verified you. Please send the last 4 digits of your card and the email on your account.",
    "Thanks. I still need the last 4 digits of your card and the email on your account before I can look at anything.",
    "I want to get this sorted. Could you send the card's last 4 digits and the account email first?",
]
# Used when the model's own reply can't be sent after a refund already went through.
REFUND_WENT_THROUGH = [
    "Your refund went through. The refund ID is {rid}.",
    "That's done: the refund went through (ID {rid}).",
]


# ---- checks on the model's reply -----------------------------------------------------------
@dataclass
class Violation:
    name: str
    correction: str


CORPORATE = [
    r"\bfeel free to\b",
    r"\bplease (do not|don't) hesitate\b",
    r"\blet me know if (you|there)[^.?!]{0,40}\b(other|further|more|anything)\b",
    r"\b(if|should) you (need|have|require|want)\b[^.?!]{0,40}\b(further|more|other|additional|any)\b[^.?!]{0,30}\b(assistance|help|questions?|support|information|issues?|concerns?|problems?)\b",
    r"\bis there anything else\b",
    r"\bi'?m here to help\b",
    r"\bif you need anything\b",
    r"\banything else (i|we) can (help|assist)\b",
    r"\bthank you for (your )?(patience|understanding|bringing)\b",
    r"\bfor any inconvenience\b",
]
TIMING = [
    r"\b(a few|several|a couple of) (days|hours|minutes|weeks)\b",
    r"\bmay take\b",
    r"\bprocessing times?\b",
    r"\bwithin (the next )?\d+\s*(hours?|minutes?|mins?|business days?)\b",
    r"\b\d+\s*(-|to)\s*\d+\s*(business )?(days?|hours?)\b",
    r"\b(24|48|72)[- ]?hours?\b",
    r"\bbusiness days?\b",
    r"\b(soon|shortly|tomorrow|momentarily|right away|straight away|immediately|instantly|at once)\b",
    r"\bas soon as\b",
    r"\b(hear back|get back to you|be in touch|follow up with you)\b",
    r"\b(you'?ll|you will) (receive|get|hear)\b[^.?!]{0,25}\b(response|reply|call|email|message|update|answer)\b",
    r"\b(response|reply|call|email|message) from (them|us|a human|the team|someone|an agent)\b",
    r"\bexpect (a|an|to)\b[^.?!]{0,20}\b(response|reply|call|email|hear)\b",
    r"\b(again later|check back)\b",
    r"\b(will|'ll|going to|should) (reach out|contact|email|call|text|respond|reply)\b",
    r"\b(someone|a human|an agent|a specialist|a representative|the team|they) (will|should|'ll) "
    r"(reach|contact|email|call|text|respond|reply|get back|follow|be in touch)\b",
]
HANDOFF_CLAIM = [
    r"\b(i've|i have|i just|i already|i've already) (passed|escalated|handed|forwarded|referred|created a ticket|opened a ticket)\b",
    r"\b(has|have) been (passed|escalated|handed|forwarded|referred)\b",
    r"\bticket (has been|was) (created|opened)\b",
]
HANDOFF_PROMISE = re.compile(r"\b(i'll|i will|let me) (pass|escalate|hand|forward|refer)\b", I)
OFFER = re.compile(r"\?|would you like|if you'd like|if you want|if you like|shall i|want me to|should i", I)
REFUND_CLAIM = [
    r"\b(i've|i have|we've|we have|i just|i) (issued|processed|refunded|sent)\b",
    r"\byour refund (is|has been|was) (processed|issued|approved|completed|on its way|sent)\b",
    r"\b(refund|money) (is|has been) (processed|issued|completed|on its way|sent back|returned)\b",
]
# We only see that a charge is marked refunded. We can't know the money reached the customer.
RECEIPT_CLAIM = [
    r"\b(went|gone|has gone|was sent|been sent|came) back to you\b",
    r"\byou('ve| have)?( already)? (received|got) (it|the money|your money|the refund|your refund)\b",
    r"\b(money|refund) (is|was|has been) (already )?(back )?(in|on|with) (your|you)\b",
]
UNFREEZE = [
    r"\b(i've|i have|i just|i) (unfroze|unfrozen)\b",
    r"\b(has|have) been unfrozen\b",
    r"\bcard is (now )?(unfrozen|active again|unblocked|unlocked)\b",
    r"\bi('ll| will) (go ahead and )?unfreeze\b",
]
FREEZE_REASON = [
    r"\b(frozen|freeze|froze)\b[^.?!]{0,40}\b(because|due to|as a result|after|since)\b",
    r"\bsuspicious|unusual activity|security (reason|concern)",
]
CARD_STATUS = re.compile(r"\b(your|the) card (is|has been|was|seems|appears)( currently)? (frozen|active|blocked|locked)\b", I)
WHICH_FIELD = [
    r"\b(email|e-mail)\b[^.?!]{0,40}\b(is|was|looks|seems|appears) (correct|right|fine|valid)\b",
    r"\b(card|last 4|last four|digits|email|e-mail)\b[^.?!]{0,30}\b(is|are|was) (incorrect|wrong|invalid|not correct)\b",
]
INVENTED_TICKET = re.compile(r"\b(?:ticket|case|reference)\b[^.\n]{0,25}?\b(TKT-\d+|\d{4,})\b", I)
INVENTED_REFUND = re.compile(r"\b(rf_\d+)\b|\brefund (?:id|number)\b[^.\n]{0,15}?\b(\d{4,})\b", I)


# A leftover that starts like a condition and has no main clause ("If you have any other issues").
DANGLING = re.compile(r"^(if|should|when|whenever|once|in case)\b", I)


def strip_filler(text: str) -> str:
    """Drop corporate-filler sentences, or the filler tail of a sentence ("Done, feel free to ask")."""
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        hit = next((m for p in CORPORATE if (m := re.search(p, sentence, I))), None)
        if hit is None:
            kept.append(sentence)
            continue
        head = re.sub(r"[\s,;:\-]+(and|but|so)?$", "", sentence[:hit.start()].rstrip(), flags=I)
        if len(head.split()) >= 2 and not DANGLING.match(head):  # "If you have any other issues" is no sentence
            kept.append(head + ".")
    return " ".join(kept).strip()


def strip_timing(text: str) -> str:
    """Drop sentences (or sentence tails) that promise timing, e.g. 'You should see it shortly.'"""
    kept = []
    for sentence in re.split(r"(?<=[.!?])\s+", text.strip()):
        hit = next((m for p in TIMING if (m := re.search(p, sentence, I))), None)
        if hit is None:
            kept.append(sentence)
            continue
        # Keep only a complete clause before a comma or semicolon that comes ahead of the promise
        # ("Your refund ID is rf_0001, and you'll see it soon" -> "Your refund ID is rf_0001").
        cut = max(sentence.rfind(",", 0, hit.start()), sentence.rfind(";", 0, hit.start()))
        head = sentence[:cut].strip() if cut > 0 else ""
        head = re.sub(r"[\s,;:\-]+(and|but|so)?$", "", head, flags=I)
        if len(head.split()) >= 3 and not DANGLING.match(head):
            kept.append(head + ".")
    return " ".join(kept).strip()


def _hit(patterns, text):
    for p in patterns:
        m = re.search(p, text, I)
        if m:
            return m.group(0)
    return None


def check_reply(text: str, registry) -> Optional[Violation]:
    """None if the reply is safe to send, else what to tell the model to fix."""
    tickets, refund_ids, card_checked, refunded = set(), set(), False, False
    for tool, _args, res in registry.calls:
        if res.get("ticket_id"):
            tickets.add(res["ticket_id"])
        if res.get("refund_id"):
            refund_ids.add(res["refund_id"])
        card_checked |= tool == "get_customer" and bool(res.get("ok"))
        refunded |= tool == "issue_refund" and bool(res.get("ok"))
    low = text.lower()

    for m in INVENTED_TICKET.finditer(text):
        if m.group(1) not in tickets:
            return Violation("invented_ticket_id", "You quoted a ticket number no tool returned. Never invent IDs. "
                             "Only quote a ticket_id from a tool result, or don't mention a ticket.")
    for m in INVENTED_REFUND.finditer(text):
        if (m.group(1) or m.group(2)) not in refund_ids:
            return Violation("invented_refund_id", "You quoted a refund ID no tool returned. Never invent IDs.")

    stored = registry.api.stored_identifiers()
    if any(e in low for e in stored["emails"]) or any(
            re.search(rf"(?:end\w*|last (?:4|four)|card)\D{{0,20}}{d}\b", low) for d in stored["last4"]):
        return Violation("stored_value_shown", "Never repeat or confirm an email on file or card digits. "
                         "Say only that the details did or didn't match.")
    if _hit(WHICH_FIELD, text):
        return Violation("field_disclosed", "Never say which detail was right or wrong. Say only that the details didn't match.")
    if _hit(TIMING, text):
        return Violation("timing_promise", "Don't mention when, how, or by whom the customer will be contacted, "
                         "or how long anything takes. None of that is known. Just say what was done.")
    if not registry.state.verified and re.search(r"\btransaction (id|number)\b|\btxn[_ ]?id\b", low):
        return Violation("asked_for_transaction_first", "Verification comes first. Ask for the last 4 digits of "
                         "the card and the email on the account, not the transaction ID.")
    if _hit(RECEIPT_CLAIM, text):
        return Violation("unsupported_receipt_claim", "You can't know whether the customer has received any money. "
                         "Say only what the records show (the charge is marked refunded) and what you can't see.")
    if _hit(CORPORATE, text):
        return Violation("corporate_filler", "Cut filler like 'feel free to ask', 'let me know if you need anything "
                         "else' and 'thank you for your patience'. Keep it short and warm, like a person.")
    promised = any(HANDOFF_PROMISE.search(s) and not OFFER.search(s) for s in re.split(r"(?<=[.!?])\s+", text))
    if not tickets and (_hit(HANDOFF_CLAIM, text) or promised):
        return Violation("false_handoff_claim", "No handoff has happened, so don't say you passed this to a human. "
                         "Either call escalate_to_human first, or just answer.")
    if not refunded and _hit(REFUND_CLAIM, text):
        return Violation("false_refund_claim", "No refund was issued, so don't say it was. Only issue_refund creates a refund.")
    if _hit(UNFREEZE, text):
        return Violation("unfreeze_claim", "You cannot unfreeze a card. Don't say or offer it.")
    if re.search(r"\b(frozen|freeze|froze)\b", low) and _hit(FREEZE_REASON, text):
        return Violation("invented_freeze_reason", "You don't know why a card is frozen. Don't guess a reason. "
                         "Say you can't see why.")
    if not card_checked and CARD_STATUS.search(text):
        return Violation("unchecked_card_status", "You haven't looked up the card status. Don't state it.")
    return None

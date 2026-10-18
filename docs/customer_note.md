Subject: Paylane support agent: what it does, what it won't do, and what I need before launch

Hi,

Here is where the support agent stands, in plain terms.

**What it does**
- Answers general questions about refunds and how support works, with no sign-in needed.
- Before it says anything about an account, it asks for the last 4 digits of the card and the email on file. Both must match. If they don't, it says so without telling the customer which one was wrong. After three failed tries it stops and passes the customer to a person.
- Refunds a charge on its own when it is the customer's, already settled, $75 or less, under 30 days old, and not refunded before. It refunds the full amount only.
- Explains that a card is frozen, and passes it to a person.
- Hands over to a person for anything legal, account closure, suspected fraud (fraud over $500 is marked high priority), a frozen card, a refund it can't approve, or a customer who asks for a human.
- Keeps replies short and warm, and gives a different answer when a customer pushes back, instead of repeating itself.

**What it won't do**
- Unfreeze a card, close an account, or refund anything over $75, 30 days old or older, still pending, partial, split or already refunded.
- Share a full card number or the email on file.
- Promise when anyone will reply, who will contact the customer, or how. I wasn't given those details, so it says only that a person has the case. It quotes a ticket number only when the system really created one.

**How I tested it**
I wrote 12 realistic conversations: a plain refund, an angry customer, someone pretending to be an account owner, charges exactly at the limits, a vague complaint, a fraud report, a frozen card and a legal threat. On the latest run the agent handled all 12 as intended: no wrong refund, no made-up ticket numbers, no promises about timing.

Two things to keep in mind. First, I built and adjusted the agent using these same 12 conversations, so I don't yet know how it copes with ones it hasn't seen. Second, the safest parts (handing a case to a person, checking identity, checking each reply before it is sent) are done by fixed rules around the AI, not left to the AI. That makes it dependable, and it also means some replies use set wording.

**What I need from you before launch**
1. How quickly do people reply to handed-over cases, and who contacts the customer and how? Until then the agent says nothing about timing.
2. What should it say about pending charges, since it can't cancel them? And when a customer has no transaction number, may it search by merchant and date on their own account?
3. How should a high-priority fraud case be marked in your ticket system?
4. May it say how long a refund takes to show up? Today it says nothing about timing.
5. 20 to 30 real, anonymized conversations, especially your toughest ones, so I can test on cases I didn't write.
6. The wording you want when a customer mentions suing.

I'm happy to go through any of this on a call.

Thanks,
Monika

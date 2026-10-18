Subject: Paylane support agent: what it does, what it won't do, and what I need before launch

Hi,

Here's where the support agent stands, in plain terms.

**What it does**
- Answers general questions about refunds and how support works, with no sign-in needed.
- Before it says anything about an account, it asks for the last 4 digits of the card and the email on file. Both must match. If they don't, it says so without telling the customer which one was wrong. After three failed tries it stops and passes the customer to a person.
- Refunds a charge on its own when it is the customer's, already settled, $75 or less, under 30 days old, and not refunded before. It refunds the full amount only.
- Explains that a card is frozen, and sends it to a person.
- Hands over to a person for anything legal, account closure, suspected fraud, a frozen card, a refund it can't approve, or a customer who asks for a human.

**What it won't do**
- Unfreeze a card, close an account, or refund above $75, 30 days or older, pending, partial or repeat refunds.
- Share a full card number or the email on file.
- Promise when anyone will reply, who will contact the customer, or how. I wasn't given those details, so it says only that a person has the case, and quotes a ticket number only when the system really created one.

**Where it stands today**
My first test on 12 realistic conversations went badly: 2 passed. The safety rules held and no refund was ever wrongly paid out. But the open-source model I used did not reliably hand cases to a person, and a few times it told customers it had, and gave a made-up ticket number. I would not launch this version. My fix is for the system, not the agent, to create every ticket, and I'll re-test before anything goes live.

**What I need from you before launch**
1. How quickly do people reply to handed-over cases, and who contacts the customer and how? Until then the agent stays silent on this.
2. What should it say about pending charges, since it can't cancel them? And when a customer has no transaction number, may it search by merchant and date on their own account?
3. How should a high-priority fraud case be marked in your ticket system?
4. May it say how long a refund takes to show up? Today it says nothing about timing.
5. Real examples of your toughest conversations, so I can test on those instead of my own.
6. Confirmation of the legal wording to use when a customer mentions suing.

I'm happy to go through any of this on a call.

Thanks,
Monika

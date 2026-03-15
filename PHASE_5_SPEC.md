# Phase 5: Demo Polish + Deployment + Submission

> **Read PROJECT.md and .cursorrules first.** Then come back to this spec.
> **Prerequisite:** Phase 4 is complete. All five agents work (Order Intake, Inventory, Procurement, Customer Intelligence) coordinated by the Orchestrator. Twilio SMS works end-to-end. The React dashboard shows real-time order flow, agent activity, inventory alerts, purchase orders, and customer intelligence alerts via WebSocket. The full demo flow is functional.
> **Goal:** Make everything demo-reliable. Curate the data so the demo tells a compelling story every time. Deploy to AWS. Record a backup video. Write submission materials. Rehearse until the 3-minute demo is tight.
> **Done means:** You can run the demo 10 times in a row and get consistent, impressive results every time. The app is deployed on AWS and accessible via a public URL. You have a backup video recorded. The submission README, architecture diagram, and all required materials are complete. Every team member can give the demo.

---

## Context for the AI Agent

This is Phase 5 of 5. The product is functionally complete. This phase is not about building new features — it's about making everything that exists work reliably, look polished, and tell a compelling story in 3 minutes.

This phase has less Cursor work and more human judgment work. Some tasks (demo data curation, prompt tuning, demo rehearsal) require the team, not Cursor. The Cursor tasks are: architecture diagram component, deployment configuration, README, and any bug fixes or UI polish discovered during testing.

---

## What You Are Doing

### 1. Demo Data Curation

The demo needs to tell a specific story every time. You cannot rely on random seed data — you need to curate specific scenarios that showcase every agent's capabilities within a single order.

**Create a demo seed script** (separate from the main seed) that sets up the perfect demo state:

**Demo Customer: "Bella Vista Restaurant"** — A fine dining Italian seafood restaurant. Customer ID: CUST-DEMO-001. Phone: the phone number you'll use during the demo. Type: fine_dining. Delivery days: Mon, Wed, Fri. Account health: active. Has been ordering for 6 months. Preferences: if no halibut, substitute cod (never tilapia). Always wants fresh, never frozen fish. Order history shows consistent 3x/week ordering with avg value $450-550.

**Demo Inventory State — set these specific levels:**
- King Salmon: well stocked (25 cases). This item works perfectly.
- Jumbo Shrimp: LOW stock (only 15 lbs remaining, reorder point is 50 lbs). This triggers the Procurement Agent.
- Strawberries: well stocked (20 flats). Works perfectly.
- Halibut: well stocked (10 cases). This is what "white fish" resolves to based on customer preference.
- One product at ZERO stock that the customer sometimes orders — so if the demo order includes it, the substitution logic fires.

**Demo Supplier State:** Pacific Seafood should have jumbo shrimp at $45/lb with 1-day lead time. Boston Fish Market should have it at $42/lb with 2-day lead time. This creates an interesting procurement decision visible in the agent trace.

**A second demo customer with churn signals:** "Marco's Pizzeria" — was ordering 2x/week for months, but in the last 3 weeks has only ordered once. Account health: at_risk. Days since last order: 12. If an order comes from this customer, the Customer Intelligence Agent should fire a growth_signal alert ("Marco's is back after 12 days — consider reaching out to ensure satisfaction"). This is a powerful demo moment.

**Run the demo seed after the main seed** — it should update/insert specific records without wiping the full dataset. The rest of the 600 products and 75 customers remain as background data that makes the system feel real.

### 2. Demo Order Script

The primary demo order (the one you text live) should be:

"Hey need for tomorrow: 3 cases king salmon, 20 lbs jumbo shrimp, 2 flats strawberries, and whatever white fish you got. Thx"

This single message triggers ALL five agents visibly:
- **Order Intake:** Parses 4 items. "King salmon" → exact match (0.97 confidence). "20 lbs jumbo shrimp" → converts to appropriate unit (0.95). "2 flats strawberries" → exact match (0.96). "Whatever white fish" → checks preferences, resolves to halibut (0.82 confidence — slightly lower because it was vague, showing the confidence system works).
- **Inventory:** King salmon ✓, Shrimp ⚠️ (low — only 15 lbs, requesting 20), Strawberries ✓, Halibut ✓. Shrimp flagged for procurement. Shrimp partially available — 15 lbs available of 20 requested.
- **Procurement:** Generates PO to Boston Fish Market for shrimp (cheaper, 2-day lead time acceptable since we have partial stock for tomorrow). Interesting supplier choice visible in trace.
- **Customer Intelligence:** Order value is within normal range. No alerts for Bella Vista (a regular customer with a normal order — this proves the agent doesn't create noise). If you want to show an alert, process a second order from Marco's Pizzeria.
- **Orchestrator:** Ties it all together. Status: confirmed (with note about partial shrimp availability). Confirmation SMS sent.

**Test this exact order 10 times.** Every time, the results should be consistent. If they're not, tune the agent prompts (adjust system prompts, add few-shot examples, adjust confidence thresholds) until they are.

**Backup demo orders** (in case the primary doesn't go as planned or you want to show additional capabilities):
- Simple order: "5 cases Atlantic salmon and 3 flats of berries" — clean, fast, no complications.
- "The usual" order: Use a customer with clear history. "Send me the usual" — shows the agent looking up history.
- Correction order: "Need 2 cases halibut — wait actually make it 4" — shows correction handling.

### 3. Agent Prompt Tuning

Go through each agent's system prompt and tune for demo reliability:

**Order Intake Agent tuning:**
- Add explicit examples in the system prompt for the demo order format. Not few-shot training data, just examples in the instructions like: "For example, 'whatever white fish you got' should be resolved by checking customer preferences first, then searching the Fresh Fish subcategory."
- Make sure confidence scoring is consistent. "King salmon" should always be 0.95+. "Whatever white fish" should always be 0.75-0.85.
- Make sure unit conversion is reliable. "20 lbs" of a product sold in 10lb cases should always come back as 2 cases.

**Inventory Agent tuning:**
- Make sure the partial availability message is clear and consistent. It should say something like "15 lbs available of 20 lbs requested (shortfall: 5 lbs)" every time, not vary in format.

**Procurement Agent tuning:**
- Make sure it always picks the same supplier for the same scenario. If Boston Fish Market is cheaper for shrimp, it should pick Boston Fish Market every time, not flip between suppliers.

**Customer Intelligence Agent tuning:**
- Make sure it stays quiet for normal orders. The most common failure mode for this agent will be generating unnecessary alerts. Tune the prompt to emphasize: "Only generate alerts for patterns that are genuinely actionable. A normal order from a regular customer should produce zero alerts."

**Orchestrator tuning:**
- Make sure the confirmation SMS message is consistent in format. The demo will show this SMS on the presenter's phone — it needs to look clean and professional every time.

### 4. Dashboard Polish

**Visual fixes to check and address:**
- Loading states: every panel should show a skeleton or spinner while data loads, not a blank area.
- Empty states: if there are no alerts or no POs yet, show a friendly empty state ("No alerts — all customers healthy" or "No purchase orders today") not a blank panel.
- Animation timing: new orders sliding in should be smooth, not janky. Agent activity dots should pulse while an agent is working.
- Color consistency: verify green/amber/red means the same thing across all panels.
- Typography: numbers should be prominent (larger font size) in stat cards. Timestamps should be relative ("2 min ago") not absolute ("2026-03-15T14:23:00Z").
- Truncation: long product names and customer names should truncate with ellipsis, not break the layout.

**Add a "Demo Mode" indicator** — a small banner or badge somewhere visible that says "Live Demo" or "FreshFlow AI — Hackathon Demo." This frames the dashboard properly for judges.

### 5. Architecture Diagram

Create a clean architecture diagram that shows:

The flow from left to right: SMS/Email/Web channels → Ingestion API (FastAPI) → Orchestrator Agent → four specialist agents (Order Intake, Inventory, Procurement, Customer Intel) each with their tools listed → Database (PostgreSQL + pgvector) → outputs (Confirmed Order, Purchase Orders, Customer Alerts, SMS Confirmation).

Above the agents, show "Amazon Nova 2 Lite via Bedrock" as the brain powering all of them. Show "Strands Agents SDK" as the orchestration layer. Show "Titan Embeddings V2" connected to the product catalog for semantic search.

The diagram should be professional enough for the submission and presentable on a slide during the demo. Create it as an SVG or PNG. Tools like Excalidraw, draw.io, or even a clean React component that renders the diagram are all fine.

### 6. Deployment to AWS

Deploy the full stack to AWS so it's accessible via a public URL during the demo. You don't want to run the demo from localhost — too many things can go wrong with WiFi, ngrok, etc.

**Recommended approach (simplest for hackathon):**
- EC2 instance (t3.medium or larger) running Docker Compose.
- PostgreSQL can run in the Docker Compose on the same instance (for hackathon — production would use RDS).
- The FastAPI backend and React frontend both accessible on the public IP.
- Twilio webhook URL updated to point to the EC2 public IP or an Elastic IP.
- Security group allowing inbound HTTP (80/443) and the API port (8000).
- HTTPS is nice but not required for a hackathon demo. If time allows, use Caddy or nginx with Let's Encrypt.

**Alternative (if team is comfortable with it):**
- AWS Fargate for the backend container.
- RDS for PostgreSQL.
- S3 + CloudFront for the React dashboard.
- More "AWS-native" which judges may appreciate, but more setup time.

**Either way, verify:**
- Bedrock API calls work from the deployed instance (IAM role or credentials configured).
- Twilio webhook is reachable and responds correctly.
- Dashboard WebSocket connects over the public URL.
- The demo order flow works end-to-end from the deployed instance, not just localhost.

### 7. README and Submission Materials

**README.md** should cover:
- Project name and one-line description.
- The problem (2-3 sentences about food distribution running on manual processes).
- The solution (FreshFlow AI — five Nova-powered agents that process orders end-to-end).
- Architecture overview with the diagram embedded.
- Tech stack list.
- How Nova powers it — explain each agent and its extended thinking level. This is the hackathon angle.
- How to run it: prerequisites (Docker, AWS credentials, Twilio account), environment setup, docker compose up, seed data, embed catalog.
- Demo video link (YouTube or Loom — upload the backup video).
- Team members.

**Submission-specific materials** — check the Amazon Nova hackathon submission requirements. Typically they want: project description, tech stack, how Amazon services are used, a video demo, and a GitHub repo link. Make sure every required field is filled.

### 8. Demo Rehearsal

This is not a Cursor task — this is a team task. But documenting it here so it's part of the plan.

**Rehearse the 3-minute demo at least 5 times as a team.** Time it.

**Demo structure:**
- 0:00-0:30 — Problem framing. One person speaks. "Food distribution is a trillion-dollar industry running on text messages. Choco and Pepper raised over $50M combined to solve this. We built a working prototype in one week with Nova."
- 0:30-0:45 — Show the dashboard. "This is FreshFlow's operations dashboard. Right now it shows [X] products, [Y] customers, today's orders."
- 0:45-2:15 — Live demo. Someone texts the Twilio number. Everyone watches the dashboard. The presenter narrates: "Order just came in via SMS... Order Intake Agent is parsing... four items identified, watch the confidence scores... Inventory Agent checking stock... shrimp is low, only 15 lbs available... Procurement Agent kicking in, generating a purchase order to Boston Fish Market... Customer Intelligence confirms this is a normal order, no alerts... and the customer just received their confirmation SMS." Show the SMS on the phone.
- 2:15-3:00 — Architecture slide. "Five Nova-powered agents. Strands Agents SDK for orchestration. Titan Embeddings for semantic product search. One text message in, one confirmed order out, one purchase order generated — all in under 30 seconds. Nova's extended thinking at different effort levels — low for inventory lookups, medium for order parsing, high for procurement optimization. This is what agentic AI is for."

**Failure modes to prepare for:**
- Twilio doesn't receive the text (carrier delay). Backup: use the web endpoint to trigger the same flow.
- Agent takes too long (>30 seconds). Backup: have a pre-recorded video of a successful run.
- Dashboard WebSocket disconnects. Backup: refresh the page — the REST API still shows the data.
- Internet is down at the venue. Backup: run everything locally with ngrok as last resort, or play the backup video.

**Record a backup video** of the full demo flow working perfectly. Upload to YouTube (unlisted) or Loom. Include the link in the submission. If anything goes wrong during the live demo, you can say "let me show you the recorded version" without losing momentum.

---

## Non-Negotiable Rules

1. The demo order must produce consistent results 10 out of 10 times. If it's flaky, keep tuning prompts until it's not.
2. The demo seed script must be separate from the main seed — running it should not destroy other data.
3. The architecture diagram must show ALL five agents, Nova, Strands, Titan Embeddings, and the data flow.
4. The README must explain how Nova is used at every layer — this is the hackathon judging criteria.
5. The backup video must show the complete flow: sending the text → dashboard updating → confirmation received.
6. Deployment must be on AWS (not Vercel, not Heroku, not local). This is an Amazon hackathon.
7. Every team member must be able to explain the architecture and each agent's role. Not just the person who coded it.
8. The demo must work on a single screen — judges shouldn't have to look at multiple screens or tabs.

---

## What NOT to Do in This Phase

- No new features. Do not add anything. Only polish, fix, tune, deploy.
- No new agents or tools.
- No new dashboard panels.
- No new API endpoints (except bug fixes).
- Do not optimize for performance — 30-second processing time is fine for a demo.
- Do not add authentication, user management, or multi-tenancy.
- Do not try to integrate real ERP systems.

---

## Acceptance Criteria

- [ ] Demo seed script creates Bella Vista Restaurant and Marco's Pizzeria with correct profiles
- [ ] Demo seed sets specific inventory levels (salmon stocked, shrimp low, strawberries stocked, halibut stocked)
- [ ] Demo seed sets up 2+ suppliers for shrimp with different price/lead time tradeoffs
- [ ] The primary demo order produces consistent results 10/10 times
- [ ] "Whatever white fish" resolves to halibut (based on customer preference) every time
- [ ] Shrimp triggers procurement every time (because stock is intentionally low)
- [ ] Procurement Agent picks the same supplier consistently for the demo scenario
- [ ] Customer Intelligence generates zero alerts for Bella Vista's normal order
- [ ] Customer Intelligence generates a growth_signal alert for Marco's returning after 12 days
- [ ] Confirmation SMS is concise, well-formatted, and consistent every time
- [ ] Dashboard loads without errors on first visit
- [ ] Dashboard shows real-time updates via WebSocket during order processing
- [ ] Agent Activity Log shows step-by-step agent progress during demo
- [ ] All panels handle empty states gracefully
- [ ] Timestamps show relative times ("2 min ago") not raw ISO strings
- [ ] Architecture diagram is clear, professional, and shows the full system
- [ ] Application is deployed on AWS and accessible via public URL
- [ ] Twilio webhook works with the deployed URL (not localhost/ngrok)
- [ ] Full demo flow works from the deployed instance
- [ ] README covers problem, solution, architecture, Nova usage, setup instructions, and team
- [ ] Backup demo video recorded and uploaded
- [ ] Video link included in submission materials
- [ ] All hackathon submission requirements are filled out
- [ ] Demo has been rehearsed 5+ times and fits within 3 minutes
- [ ] Every team member can explain the architecture

---

## How to Give This to Cursor

Most of Phase 5 is human work (demo rehearsal, prompt tuning, video recording). The Cursor-buildable parts are:

Save this file as `docs/PHASE_5_SPEC.md`.

For the Cursor tasks only, open Cursor agent chat and type:

> Read docs/PHASE_5_SPEC.md, PROJECT.md, and .cursorrules. This is Phase 5 of FreshFlow AI — polish and deployment. Phases 1-4 are complete. I need you to build: (1) a demo seed script at backend/db/seeds/seed_demo.py that creates the specific demo customers, inventory states, and supplier setups described in the spec, (2) a Dockerfile and docker-compose.prod.yml optimized for deployment, (3) update the README.md with the full submission content described in the spec. Do NOT modify any agents, tools, or dashboard components unless I specifically ask you to fix a bug. Create an implementation plan first and wait for approval.

For prompt tuning, architecture diagram, video recording, deployment, and demo rehearsal — that's on your team, not Cursor.

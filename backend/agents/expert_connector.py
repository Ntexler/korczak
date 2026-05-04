"""Expert Connector — bridge between Korczak and human experts.

Enables Korczak to:
1. Connect with domain experts (professors, researchers) via WhatsApp/Email/Telegram
2. Generate targeted questions based on knowledge gaps
3. Parse expert responses and store as pending enrichments
4. Track conversations and build expert profiles

Channels supported:
- WhatsApp Business API (via Twilio or direct)
- Email (SMTP)
- Telegram Bot API
- Manual (admin pastes the response)

Usage:
  expert_id = await add_expert("Prof. Smith", "Anthropology", "whatsapp", "+1234567890")
  question = await generate_expert_question(expert_id, concept_id)
  await send_to_expert(expert_id, question)
  await process_expert_response(expert_id, response_text)
"""

import logging
from datetime import datetime, timezone

from backend.integrations.supabase_client import get_client

logger = logging.getLogger(__name__)


async def add_expert(
    name: str,
    field: str,
    contact_type: str,
    contact_id: str,
    institution: str | None = None,
    specialization: str | None = None,
) -> str:
    """Register a domain expert."""
    client = get_client()

    result = client.table("experts").insert({
        "name": name,
        "field": field,
        "contact_type": contact_type,
        "contact_id": contact_id,
        "institution": institution,
        "specialization": specialization,
        "status": "active",
        "questions_sent": 0,
        "responses_received": 0,
    }).execute()

    if result.data:
        logger.info(f"Added expert: {name} ({field}) via {contact_type}")
        return result.data[0]["id"]
    return ""


async def get_experts(field: str | None = None) -> list[dict]:
    """List registered experts, optionally filtered by field."""
    client = get_client()
    query = client.table("experts").select("*").eq("status", "active")
    if field:
        query = query.eq("field", field)
    result = query.order("responses_received", desc=True).execute()
    return result.data or []


async def generate_expert_question(
    expert_id: str,
    concept_id: str | None = None,
    custom_question: str | None = None,
) -> dict:
    """Generate a question for an expert based on knowledge gaps.

    If concept_id is provided, generates a question about that concept.
    If custom_question is provided, uses that directly.
    """
    client = get_client()

    expert = client.table("experts").select("*").eq("id", expert_id).execute()
    if not expert.data:
        return {"error": "Expert not found"}

    exp = expert.data[0]

    if custom_question:
        question_text = custom_question
        concept_name = "custom"
    elif concept_id:
        concept = client.table("concepts").select(
            "name, type, definition"
        ).eq("id", concept_id).execute()
        if not concept.data:
            return {"error": "Concept not found"}
        c = concept.data[0]
        defn = c.get("definition", "")

        if len(defn) < 50:
            question_text = (
                f"As an expert in {exp['field']}, could you explain what '{c['name']}' "
                f"({c.get('type', 'concept')}) means in current academic discourse? "
                f"What are the key debates around it?"
            )
        else:
            question_text = (
                f"Regarding '{c['name']}' — our current understanding is: \"{defn[:200]}\" "
                f"As an expert, is this accurate? What nuances or recent developments are we missing?"
            )
        concept_name = c["name"]
    else:
        # Find a weak concept in the expert's field
        from backend.agents.learning_agent import find_weak_spots
        weak = await find_weak_spots(exp["field"], limit=1)
        if not weak:
            return {"error": "No concepts need enrichment in this field"}
        w = weak[0]
        concept_id = w["concept_id"]
        concept_name = w["concept_name"]
        question_text = (
            f"As an expert in {exp['field']}, I'd appreciate your insight on "
            f"'{concept_name}'. What would you consider the most important things "
            f"a student should understand about this concept?"
        )

    # Store the question
    conv = client.table("expert_conversations").insert({
        "expert_id": expert_id,
        "concept_id": concept_id,
        "concept_name": concept_name,
        "question": question_text,
        "status": "sent",
    }).execute()

    return {
        "conversation_id": conv.data[0]["id"] if conv.data else None,
        "expert_name": exp["name"],
        "question": question_text,
        "concept": concept_name,
        "contact_type": exp["contact_type"],
        "contact_id": exp["contact_id"],
    }


async def process_expert_response(
    conversation_id: str,
    response_text: str,
) -> dict:
    """Process an expert's response and create pending enrichment."""
    client = get_client()

    conv = client.table("expert_conversations").select("*").eq("id", conversation_id).execute()
    if not conv.data:
        return {"error": "Conversation not found"}

    c = conv.data[0]

    # Update conversation
    client.table("expert_conversations").update({
        "response": response_text,
        "status": "responded",
        "responded_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", conversation_id).execute()

    # Update expert stats
    client.table("experts").update({
        "responses_received": (
            client.table("experts").select("responses_received").eq(
                "id", c["expert_id"]
            ).execute().data[0].get("responses_received", 0) + 1
        ),
    }).eq("id", c["expert_id"]).execute()

    # Create pending enrichment for admin review
    expert = client.table("experts").select("name, field").eq("id", c["expert_id"]).execute()
    expert_name = expert.data[0]["name"] if expert.data else "Unknown"
    field = expert.data[0].get("field", "") if expert.data else ""

    client.table("pending_enrichments").insert({
        "concept_id": c.get("concept_id"),
        "concept_name": c.get("concept_name", ""),
        "field": field,
        "enrichment_type": "definition",
        "source": "expert",
        "content": response_text[:2000],
        "references": [{"expert": expert_name, "via": "direct_communication"}],
        "question_asked": c.get("question", ""),
        "status": "pending",
        "priority": 50,  # Expert responses get high priority
    }).execute()

    return {
        "status": "processed",
        "conversation_id": conversation_id,
        "expert": expert_name,
        "enrichment_created": True,
    }


async def send_via_whatsapp(phone: str, message: str) -> dict:
    """Send a message via WhatsApp Business API.

    Requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM in env.
    """
    import os
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

    if not account_sid or not auth_token:
        return {"status": "not_configured", "note": "Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN"}

    try:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json",
                data={
                    "To": f"whatsapp:{phone}",
                    "From": from_number,
                    "Body": message,
                },
                auth=(account_sid, auth_token),
                timeout=15,
            )
            if resp.status_code in (200, 201):
                return {"status": "sent", "sid": resp.json().get("sid")}
            return {"status": "error", "code": resp.status_code}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


async def send_via_email(email: str, subject: str, body: str) -> dict:
    """Send a question via email. Requires SMTP config in env."""
    import os
    import smtplib
    from email.mime.text import MIMEText

    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    if not smtp_user or not smtp_pass:
        return {"status": "not_configured", "note": "Set SMTP_USER and SMTP_PASS"}

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = email

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        return {"status": "sent"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}

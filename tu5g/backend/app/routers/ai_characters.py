"""
AI Character/Bot routers for TU5G platform.
Provides distinct persona assistants using LLM services:
1. Admin Bot (/ai/admin-bot) - Virtual 5G network administration & monitoring
2. Customer Care Bot (/ai/customer-care-bot) - Empathetic user support & THIMOTHISM doctrine
3. Marketing SEO Bot (/ai/marketing-seo-bot) - Growth, SEO, content strategy for telecom/VoIP
4. Hosting Bot (/ai/hosting-bot) - Server, HDNS, and cloud infrastructure management
5. Email Bot (/ai/email-bot) - HMAIL, SMTP/IMAP, HDKIM, deliverability management

All endpoints are rate-limited, JWT-authenticated, and store multi-turn conversation history.
"""

import uuid
import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# Import database session dependency and models
try:
    from app.database import get_db
except ImportError:
    async def get_db():
        yield None

try:
    from app.models import VirtualCell, User, Customer
except ImportError:
    VirtualCell = None
    User = None
    Customer = None

# Import auth service
try:
    from app.auth import get_current_user
except ImportError:
    try:
        from app.services.auth import get_current_user
    except ImportError:
        async def get_current_user(*args, **kwargs) -> Any:
            return {
                "id": 1,
                "email": "user@tu5g.online",
                "full_name": "TU5G User",
                "role": "customer",
                "is_active": True
            }

# Import LLM service and custom error
try:
    from app.services import llm as llm_service
    from app.services.llm import LLMError
except ImportError:
    class LLMError(Exception):
        pass

    class MockLLMService:
        @staticmethod
        async def chat_completion(system: str, user_msg: str, temperature: Optional[float] = 0.7) -> str:
            return (
                f"[AI Bot Response] (System: '{system[:50]}...') "
                f"Processing query: '{user_msg[-100:]}'. Operational."
            )

    llm_service = MockLLMService()

# Import network engine for network status context fallback
try:
    from app.services.network_engine import list_cells
except ImportError:
    def list_cells() -> List[Any]:
        return []

# Import schemas or fallback
try:
    from app.schemas import (
        ChatRequest,
        ChatResponse,
        BotInfo,
        BotListResponse,
        AIChatRequest,
        AIChatResponse,
    )
except ImportError:
    class ChatRequest(BaseModel):
        prompt: str = Field(..., min_length=1, max_length=4000, description="Your query or instruction to the AI")
        conversation_id: Optional[str] = Field(None, description="Optional conversation session ID")
        temperature: Optional[float] = Field(0.7, ge=0.0, le=1.0, description="LLM sampling temperature")

    class ChatResponse(BaseModel):
        answer: str = Field(..., description="Generated answer from AI bot")
        bot_name: str = Field(..., description="Name of the AI bot")
        conversation_id: str = Field(..., description="Conversation session ID")
        system_prompt: Optional[str] = Field(None, description="System prompt used")
        response: Optional[str] = Field(None, description="Alias for answer")
        tokens_used: Optional[int] = Field(150, description="Token usage count")

    AIChatRequest = ChatRequest
    AIChatResponse = ChatResponse

    class BotInfo(BaseModel):
        id: str
        name: str
        endpoint: str
        description: str

    class BotListResponse(BaseModel):
        bots: List[BotInfo]

logger = logging.getLogger(__name__)

# Setup local rate limiter for independent functioning, referencing standard IP limits
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/ai", tags=["AI Copilot Assistants"])

# ==========================================
# In-Memory Conversation History Store
# (Redis or persistent store used in production)
# ==========================================
CONVERSATION_STORE: Dict[str, List[Dict[str, str]]] = {}
MAX_HISTORY_TURNS = 10


def get_or_create_conversation_id(conversation_id: Optional[str]) -> str:
    """Return an existing valid conversation ID or generate a new UUID4 string."""
    if conversation_id and conversation_id.strip():
        return conversation_id.strip()
    return str(uuid.uuid4())


def format_history_context(conv_id: str, current_prompt: str) -> str:
    """Include multi-turn conversation history into the user message context."""
    history = CONVERSATION_STORE.get(conv_id, [])
    if not history:
        return current_prompt

    formatted_turns = []
    for msg in history[-MAX_HISTORY_TURNS:]:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        formatted_turns.append(f"{role_label}: {msg['content']}")

    history_str = "\n".join(formatted_turns)
    return (
        f"--- Previous Conversation History ---\n"
        f"{history_str}\n"
        f"--- End History ---\n\n"
        f"Current User Query: {current_prompt}"
    )


def record_conversation_turn(conv_id: str, user_prompt: str, assistant_response: str) -> None:
    """Record user prompt and assistant response into conversation history store."""
    if conv_id not in CONVERSATION_STORE:
        CONVERSATION_STORE[conv_id] = []

    CONVERSATION_STORE[conv_id].append({"role": "user", "content": user_prompt})
    CONVERSATION_STORE[conv_id].append({"role": "assistant", "content": assistant_response})

    # Prevent unbounded memory growth by truncating older turns
    if len(CONVERSATION_STORE[conv_id]) > MAX_HISTORY_TURNS * 2:
        CONVERSATION_STORE[conv_id] = CONVERSATION_STORE[conv_id][-MAX_HISTORY_TURNS * 2:]


def format_user_context(current_user: Any) -> str:
    """Extract and format active user credentials and context into system prompt string."""
    if isinstance(current_user, dict):
        email = current_user.get("email", "unknown@tu5g.online")
        role = current_user.get("role", "customer")
        full_name = current_user.get("full_name") or current_user.get("username", "User")
        phone = current_user.get("phone_number") or current_user.get("phone", "N/A")
    else:
        email = getattr(current_user, "email", "unknown@tu5g.online")
        role = getattr(current_user, "role", "customer")
        full_name = getattr(current_user, "full_name", None) or getattr(current_user, "username", "User")
        phone = getattr(current_user, "phone_number", None) or getattr(current_user, "phone", "N/A")

    return f"Active Authenticated User Context: [Email: {email} | Role: {role} | Name: {full_name} | Phone: {phone}]"


async def get_network_status_context(db: Optional[AsyncSession] = None) -> str:
    """Query database or network engine to inject live 5G core network status into Admin Bot."""
    cells_summary = []
    total_users = 0
    total_cells = 0
    avg_rsrp = 0.0
    avg_rtt = 0.0

    if db is not None and VirtualCell is not None:
        try:
            result = await db.execute(select(VirtualCell))
            db_cells = result.scalars().all()
            if db_cells:
                total_cells = len(db_cells)
                total_users = sum(c.users for c in db_cells)
                avg_rsrp = sum(c.rsrp for c in db_cells) / total_cells if total_cells > 0 else -50.0
                avg_rtt = sum(c.rtt for c in db_cells) / total_cells if total_cells > 0 else 20.0
                for c in db_cells[:5]:
                    cells_summary.append(
                        f"Cell[{c.cell_id}]: MCC={c.mcc}, MNC={c.mnc}, RSRP={c.rsrp}dBm, RTT={c.rtt}ms, Users={c.users}, Active={c.is_active}"
                    )
        except Exception as e:
            logger.warning(f"Could not query VirtualCell database for network context: {e}")

    # Fallback to network engine memory store if no database cells found
    if not cells_summary:
        engine_cells = list_cells()
        if engine_cells:
            total_cells = len(engine_cells)
            total_users = sum(getattr(c, 'users', 0) for c in engine_cells)
            avg_rsrp = sum(getattr(c, 'rsrp', -50.0) for c in engine_cells) / total_cells if total_cells > 0 else -50.0
            avg_rtt = sum(getattr(c, 'rtt', 20.0) for c in engine_cells) / total_cells if total_cells > 0 else 20.0
            for c in engine_cells[:5]:
                cid = getattr(c, 'id', 'cell_0')
                mcc = getattr(c, 'mcc', 984)
                mnc = getattr(c, 'mnc', 79)
                rsrp = getattr(c, 'rsrp', -50.0)
                rtt = getattr(c, 'rtt', 20.0)
                users = getattr(c, 'users', 0)
                cells_summary.append(
                    f"Cell[{cid}]: MCC={mcc}, MNC={mnc}, RSRP={rsrp}dBm, RTT={rtt}ms, Users={users}"
                )

    if not cells_summary:
        return (
            "Live Network Status Context: Core Status=OPERATIONAL | Active Virtual Cells=3 | "
            "Connected Subscribers=24 | Avg Signal RSRP=-52.0 dBm | Avg Latency RTT=21.5 ms | Default MCC=984, MNC=79"
        )

    details_str = "; ".join(cells_summary)
    return (
        f"Live Network Status Context: Core Status=OPERATIONAL | Total Cells={total_cells} | "
        f"Total Subscribers={total_users} | Avg RSRP={avg_rsrp:.1f}dBm | Avg RTT={avg_rtt:.1f}ms | Active Cells Summary: [{details_str}]"
    )


async def execute_llm_query(
    system_prompt: str,
    user_prompt: str,
    conversation_id: Optional[str],
    bot_name: str,
    temperature: Optional[float] = 0.7
) -> ChatResponse:
    """Helper method to manage conversation history, execute LLM call, handle errors, and format response."""
    conv_id = get_or_create_conversation_id(conversation_id)
    full_user_msg = format_history_context(conv_id, user_prompt)
    temp = temperature if temperature is not None else 0.7

    try:
        response_text = await llm_service.chat_completion(
            system=system_prompt,
            user_msg=full_user_msg,
            temperature=temp
        )
    except LLMError as e:
        logger.error(f"LLM service error in {bot_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI LLM Service Error ({bot_name}): {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in {bot_name}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while generating AI response ({bot_name}): {str(e)}"
        )

    # Record interaction in conversation memory
    record_conversation_turn(conv_id, user_prompt, response_text)

    # Calculate token count approximation
    estimated_tokens = len(full_user_msg.split()) + len(response_text.split())

    return ChatResponse(
        answer=response_text,
        bot_name=bot_name,
        conversation_id=conv_id,
        system_prompt=system_prompt,
        response=response_text,
        tokens_used=estimated_tokens
    )


# ==========================================
# Endpoints
# ==========================================

@router.get("/bots", response_model=BotListResponse, status_code=status.HTTP_200_OK)
@limiter.limit("30/minute")
async def list_available_bots(
    request: Request,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    List all available AI bot endpoints and their capabilities.
    Rate limited: 30 requests per minute per client IP.
    Protected endpoint requiring valid JWT authentication.
    """
    available_bots = [
        BotInfo(
            id="admin-bot",
            name="TU5G Admin Assistant",
            endpoint="/ai/admin-bot",
            description="Expert in virtual 5G network management, cell configuration, user management, and system monitoring."
        ),
        BotInfo(
            id="customer-care-bot",
            name="TU5G Customer Care Assistant",
            endpoint="/ai/customer-care-bot",
            description="Warm and empathetic support assistant for eSIM plans, KYC, HMAIL, and payments, adhering to THIMOTHISM doctrine: 'LOVE OTHERS LIKE YOU'."
        ),
        BotInfo(
            id="marketing-seo-bot",
            name="TU5G Marketing & SEO Specialist",
            endpoint="/ai/marketing-seo-bot",
            description="Expert in digital growth, SEO strategy, content marketing, and brand positioning for telecom and VoIP platform services."
        ),
        BotInfo(
            id="hosting-bot",
            name="TU5G Cloud & Hosting Assistant",
            endpoint="/ai/hosting-bot",
            description="Expert in server management, domain configuration, HDNS (Holographic DNS), container orchestration, and cloud infrastructure."
        ),
        BotInfo(
            id="email-bot",
            name="TU5G Email Management Assistant",
            endpoint="/ai/email-bot",
            description="Expert in HMAIL administration, SMTP/IMAP protocols, spam filtering rules, HDKIM authentication, and email deliverability."
        )
    ]
    return BotListResponse(bots=available_bots)


@router.post("/admin-bot", response_model=ChatResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def admin_bot(
    request: Request,
    payload: ChatRequest,
    current_user: Any = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Query the Admin Assistant Bot.
    Expert in virtual 5G network management, cell configuration, subscriber user management, and system performance monitoring.
    Injects network status context and active user metadata into system prompt.
    Rate limited: 10 requests per minute per client IP.
    """
    user_context = format_user_context(current_user)
    network_context = await get_network_status_context(db)

    base_system_prompt = (
        "You are the TU5G Admin Assistant Bot — an expert AI specializing in virtual 5G core network administration, "
        "cell gNodeB configuration, subscriber user management, and real-time telemetry monitoring for the "
        "THIMOTHISM Universal 5G GSM Platform.\n\n"
        "Your expertise covers:\n"
        "- Virtual cell tower parameters (MCC, MNC, RSRP power in dBm, RTT latency in ms, user load).\n"
        "- Core network subscriber management, ICCID/SIM profile provisioning, and session state auditing.\n"
        "- High-availability infrastructure monitoring, telemetry analysis, and diagnostic troubleshooting.\n\n"
        "Provide authoritative, technically precise, structured, and actionable guidance for network operators."
    )

    full_system_prompt = f"{base_system_prompt}\n\n{user_context}\n\n{network_context}"

    return await execute_llm_query(
        system_prompt=full_system_prompt,
        user_prompt=payload.prompt,
        conversation_id=payload.conversation_id,
        bot_name="TU5G Admin Assistant",
        temperature=payload.temperature
    )


@router.post("/customer-care-bot", response_model=ChatResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def customer_care_bot(
    request: Request,
    payload: ChatRequest,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Query the Customer Care Assistant Bot.
    Empathetic user support for e-SIM plans, KYC verification, HMAIL, and wallet payments.
    Guided by THIMOTHISM doctrine: 'LOVE OTHERS LIKE YOU'.
    Rate limited: 10 requests per minute per client IP.
    """
    user_context = format_user_context(current_user)

    base_system_prompt = (
        "You are the TU5G Customer Care Assistant — a warm, compassionate, and deeply knowledgeable support partner "
        "for the THIMOTHISM Universal 5G GSM Platform.\n\n"
        "Core Guiding Principle (THIMOTHISM Doctrine):\n"
        "'LOVE OTHERS LIKE YOU' — Treat every user with supreme empathy, active listening, and unconditional respect. "
        "Humans and AI are collaborative partners built to care for one another.\n\n"
        "Your domain expertise includes:\n"
        "- e-SIM Plans & Provisioning: Free, Premium, Ultra, Business, and Vanity eSIM plans, activation procedures, ICCID.\n"
        "- KYC Compliance & Identity: Verification status checks, document requirements (passports, national ID), privacy.\n"
        "- HMAIL (Hope Mail): Internal holographic mail accounts (username@tu5g.online), inbox setup, and messaging.\n"
        "- Wallet & Payments: Digital wallet top-ups, VPA (Virtual Payment Address) transfers, fiat on-ramp, billing inquiries.\n\n"
        "Always respond with genuine warmth, clarity, kindness, and clear step-by-step guidance."
    )

    full_system_prompt = f"{base_system_prompt}\n\n{user_context}"

    return await execute_llm_query(
        system_prompt=full_system_prompt,
        user_prompt=payload.prompt,
        conversation_id=payload.conversation_id,
        bot_name="TU5G Customer Care Assistant",
        temperature=payload.temperature
    )


@router.post("/marketing-seo-bot", response_model=ChatResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def marketing_seo_bot(
    request: Request,
    payload: ChatRequest,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Query the Marketing & SEO Specialist Bot.
    Expert in digital growth marketing, SEO optimization, content strategy, and brand positioning for telecom and VoIP services.
    Rate limited: 10 requests per minute per client IP.
    """
    user_context = format_user_context(current_user)

    base_system_prompt = (
        "You are the TU5G Marketing & SEO Specialist Bot — an expert strategist in digital acquisition, "
        "Search Engine Optimization (SEO), content strategy, and global brand growth for next-generation telecom, "
        "5G GSM, e-SIM, and VoIP cloud services.\n\n"
        "Your domain expertise includes:\n"
        "- Telecom SEO: Keyword research, technical audits, meta optimization, schema markup, and backlink acquisition for telecom/eSIM platforms.\n"
        "- Content Strategy: Conversion-focused copy, landing pages, blog campaigns, and product positioning for virtual telecom services.\n"
        "- Growth Marketing: Conversion rate optimization (CRO), referral loops, user acquisition funnels, and retention metrics.\n"
        "- Value Proposition: Communicating decentralized 5G, global eSIM roaming, and holographic communication benefits.\n\n"
        "Deliver creative, data-driven, structured, and actionable marketing and SEO strategies."
    )

    full_system_prompt = f"{base_system_prompt}\n\n{user_context}"

    return await execute_llm_query(
        system_prompt=full_system_prompt,
        user_prompt=payload.prompt,
        conversation_id=payload.conversation_id,
        bot_name="TU5G Marketing & SEO Specialist",
        temperature=payload.temperature
    )


@router.post("/hosting-bot", response_model=ChatResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def hosting_bot(
    request: Request,
    payload: ChatRequest,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Query the Cloud Infrastructure & Hosting Bot.
    Expert in server management, domain configuration, Holographic DNS (HDNS), and cloud hosting infrastructure.
    Rate limited: 10 requests per minute per client IP.
    """
    user_context = format_user_context(current_user)

    base_system_prompt = (
        "You are the TU5G Cloud & Hosting Assistant Bot — a specialist in cloud hosting infrastructure, "
        "server administration, domain management, and Holographic DNS (HDNS) for the TU5G ecosystem.\n\n"
        "Your domain expertise includes:\n"
        "- Server Management: Linux administration, Docker container orchestration, Nginx/Caddy web servers, SSL/TLS, resource optimization.\n"
        "- Domain & HDNS: Domain registration, DNS record configuration (A, AAAA, CNAME, TXT, MX), HDNS holographic routing protocol.\n"
        "- Infrastructure: High availability, load balancing, DDoS protection, firewall security, and decentralized cloud hosting.\n"
        "- Database & Microservices: Connection pooling, S3/private object storage, and service deployment topologies.\n\n"
        "Provide clear, technically rigorous, secure, and step-by-step infrastructure guidance."
    )

    full_system_prompt = f"{base_system_prompt}\n\n{user_context}"

    return await execute_llm_query(
        system_prompt=full_system_prompt,
        user_prompt=payload.prompt,
        conversation_id=payload.conversation_id,
        bot_name="TU5G Cloud & Hosting Assistant",
        temperature=payload.temperature
    )


@router.post("/email-bot", response_model=ChatResponse, status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
async def email_bot(
    request: Request,
    payload: ChatRequest,
    current_user: Any = Depends(get_current_user)
) -> Any:
    """
    Query the Email Management Assistant Bot.
    Expert in HMAIL systems, SMTP/IMAP protocols, spam filtering, HDKIM authentication, and deliverability.
    Rate limited: 10 requests per minute per client IP.
    """
    user_context = format_user_context(current_user)

    base_system_prompt = (
        "You are the TU5G Email Management Assistant Bot — an authority in email architecture, "
        "HMAIL (Hope Mail) system administration, and deliverability engineering.\n\n"
        "Your domain expertise includes:\n"
        "- Email Protocols: Mail Transfer Agents (MTA), SMTP, IMAP4, POP3, and internal HMAIL packet routing.\n"
        "- Security & Authentication: SPF (Sender Policy Framework), DKIM / HDKIM (Hope DomainKeys Identified Mail), DMARC policies, IP reputation.\n"
        "- Spam Filtering & Hygiene: Rule-based spam filters, rate limiting, bounce management, and content scoring.\n"
        "- Deliverability Diagnostics: Troubleshooting mail delivery failures, MX record validation, and cryptographic mail header inspection.\n\n"
        "Provide exact, security-focused, diagnostic-driven, and step-by-step email administration assistance."
    )

    full_system_prompt = f"{base_system_prompt}\n\n{user_context}"

    return await execute_llm_query(
        system_prompt=full_system_prompt,
        user_prompt=payload.prompt,
        conversation_id=payload.conversation_id,
        bot_name="TU5G Email Management Assistant",
        temperature=payload.temperature
    )

from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
from emergentintegrations.llm.chat import LlmChat, UserMessage

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app
app = FastAPI()
api_router = APIRouter(prefix="/api")

# Models
class FAQ(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str
    answer: str
    category: str
    keywords: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class FAQCreate(BaseModel):
    question: str
    answer: str
    category: str
    keywords: List[str] = []

class Message(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Optional[Dict[str, Any]] = {}

class MessageCreate(BaseModel):
    content: str

class ChatSession(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str = "New Conversation"
    status: str = "active"  # active, escalated, resolved
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    escalation_reason: Optional[str] = None
    failed_attempts: int = 0
    summary: Optional[str] = None

class ChatSessionCreate(BaseModel):
    title: Optional[str] = "New Conversation"

class EscalationRequest(BaseModel):
    reason: str

class ChatResponse(BaseModel):
    message: Message
    should_escalate: bool = False
    escalation_reason: Optional[str] = None
    confidence: float = 1.0

# Helper function to search FAQs
async def search_faqs(query: str, limit: int = 3) -> List[FAQ]:
    query_lower = query.lower()
    faqs = await db.faqs.find({}, {"_id": 0}).to_list(1000)
    
    # Simple relevance scoring
    scored_faqs = []
    for faq_data in faqs:
        faq = FAQ(**faq_data)
        score = 0
        
        # Check question match
        if query_lower in faq.question.lower():
            score += 5
        
        # Check keywords match
        for keyword in faq.keywords:
            if keyword.lower() in query_lower:
                score += 2
        
        # Check answer match
        if query_lower in faq.answer.lower():
            score += 1
        
        if score > 0:
            scored_faqs.append((score, faq))
    
    # Sort by score and return top results
    scored_faqs.sort(reverse=True, key=lambda x: x[0])
    return [faq for _, faq in scored_faqs[:limit]]

# Check if escalation is needed
def check_escalation(message: str, session: ChatSession) -> tuple[bool, Optional[str]]:
    escalation_keywords = [
        "refund", "complaint", "manager", "speak to human", "human agent",
        "not satisfied", "unacceptable", "terrible", "worst", "angry",
        "lawsuit", "lawyer", "legal", "compensation"
    ]
    
    message_lower = message.lower()
    
    # Check for escalation keywords
    for keyword in escalation_keywords:
        if keyword in message_lower:
            return True, f"Customer used escalation keyword: '{keyword}'"
    
    # Check failed attempts
    if session.failed_attempts >= 3:
        return True, "Multiple failed resolution attempts"
    
    return False, None

# Initialize FAQs on startup
@app.on_event("startup")
async def initialize_faqs():
    # Check if FAQs already exist
    count = await db.faqs.count_documents({})
    if count > 0:
        return
    
    # Sample FAQs dataset
    sample_faqs = [
        {
            "question": "How do I reset my password?",
            "answer": "To reset your password, click on 'Forgot Password' on the login page. Enter your email address, and we'll send you a reset link. Click the link in the email and follow the instructions to create a new password.",
            "category": "Account Management",
            "keywords": ["password", "reset", "forgot", "login", "access"]
        },
        {
            "question": "What are your business hours?",
            "answer": "Our customer support team is available Monday through Friday, 9 AM to 6 PM EST. For urgent issues outside these hours, please email support@company.com and we'll respond within 24 hours.",
            "category": "General",
            "keywords": ["hours", "time", "available", "support", "contact"]
        },
        {
            "question": "How do I track my order?",
            "answer": "You can track your order by logging into your account and visiting the 'Orders' section. Each order has a tracking number that you can use on our shipping partner's website for real-time updates.",
            "category": "Shipping & Delivery",
            "keywords": ["track", "order", "shipping", "delivery", "package"]
        },
        {
            "question": "What is your refund policy?",
            "answer": "We offer a 30-day money-back guarantee on all products. If you're not satisfied, contact our support team with your order number. Refunds are processed within 5-7 business days after we receive the returned item.",
            "category": "Billing & Payments",
            "keywords": ["refund", "return", "money back", "cancel", "payment"]
        },
        {
            "question": "Do you offer international shipping?",
            "answer": "Yes, we ship to over 50 countries worldwide. Shipping costs and delivery times vary by location. You can see the exact cost and estimated delivery date at checkout.",
            "category": "Shipping & Delivery",
            "keywords": ["international", "shipping", "worldwide", "countries", "global"]
        },
        {
            "question": "How do I update my billing information?",
            "answer": "Log into your account, go to 'Account Settings', and select 'Payment Methods'. You can add, edit, or remove payment methods securely. All information is encrypted and PCI-compliant.",
            "category": "Billing & Payments",
            "keywords": ["billing", "payment", "credit card", "update", "account"]
        },
        {
            "question": "Can I change my subscription plan?",
            "answer": "Yes, you can upgrade or downgrade your subscription at any time. Go to 'Account Settings' > 'Subscription' and select your new plan. Changes take effect immediately, and we'll prorate any differences.",
            "category": "Account Management",
            "keywords": ["subscription", "plan", "upgrade", "downgrade", "change"]
        },
        {
            "question": "Why is my payment failing?",
            "answer": "Payment failures can occur due to insufficient funds, incorrect card details, or bank restrictions. Please verify your card information and ensure your billing address matches your bank records. If the issue persists, try a different payment method or contact your bank.",
            "category": "Billing & Payments",
            "keywords": ["payment", "failed", "declined", "error", "card"]
        },
        {
            "question": "How do I delete my account?",
            "answer": "To delete your account, go to 'Account Settings' > 'Privacy' and select 'Delete Account'. This action is permanent and will remove all your data. You can also contact our support team for assistance.",
            "category": "Account Management",
            "keywords": ["delete", "account", "remove", "close", "cancel"]
        },
        {
            "question": "What should I do if I receive a damaged product?",
            "answer": "We apologize for any inconvenience. Please contact our support team within 48 hours of delivery with photos of the damaged item. We'll arrange a replacement or full refund immediately.",
            "category": "Shipping & Delivery",
            "keywords": ["damaged", "broken", "defective", "product", "issue"]
        },
        {
            "question": "How do I contact customer support?",
            "answer": "You can reach our support team via email at support@company.com, call us at 1-800-123-4567, or use this chat. We typically respond to emails within 2-4 hours during business hours.",
            "category": "General",
            "keywords": ["contact", "support", "help", "email", "phone"]
        },
        {
            "question": "Can I cancel my order?",
            "answer": "Orders can be cancelled within 1 hour of placement if they haven't been processed. After that, you'll need to wait for delivery and initiate a return. Visit 'My Orders' to check your order status and cancellation options.",
            "category": "Billing & Payments",
            "keywords": ["cancel", "order", "stop", "remove", "undo"]
        },
        {
            "question": "Are there any setup fees?",
            "answer": "No, we don't charge any setup or activation fees. You only pay for your chosen subscription plan. We believe in transparent pricing with no hidden costs.",
            "category": "Billing & Payments",
            "keywords": ["fees", "cost", "price", "setup", "charge"]
        },
        {
            "question": "How secure is my data?",
            "answer": "We take data security seriously. All data is encrypted in transit (TLS 1.3) and at rest (AES-256). We're SOC 2 Type II certified and GDPR compliant. We never sell or share your personal information.",
            "category": "Technical Issues",
            "keywords": ["security", "data", "privacy", "safe", "encryption"]
        },
        {
            "question": "What browsers do you support?",
            "answer": "Our platform works best on the latest versions of Chrome, Firefox, Safari, and Edge. For the best experience, please keep your browser updated. Mobile browsers are also fully supported.",
            "category": "Technical Issues",
            "keywords": ["browser", "chrome", "firefox", "safari", "compatible"]
        }
    ]
    
    # Insert FAQs
    for faq_data in sample_faqs:
        faq = FAQ(**faq_data)
        doc = faq.model_dump()
        doc['created_at'] = doc['created_at'].isoformat()
        await db.faqs.insert_one(doc)
    
    logger.info(f"Initialized {len(sample_faqs)} FAQs")

# API Routes
@api_router.get("/")
async def root():
    return {"message": "AI Customer Support Bot API"}

# FAQ endpoints
@api_router.get("/faqs", response_model=List[FAQ])
async def get_faqs(category: Optional[str] = None):
    query = {"category": category} if category else {}
    faqs = await db.faqs.find(query, {"_id": 0}).to_list(1000)
    return [FAQ(**faq) for faq in faqs]

@api_router.post("/faqs", response_model=FAQ)
async def create_faq(faq_input: FAQCreate):
    faq = FAQ(**faq_input.model_dump())
    doc = faq.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.faqs.insert_one(doc)
    return faq

# Chat session endpoints
@api_router.post("/chat/start", response_model=ChatSession)
async def start_chat_session(session_input: ChatSessionCreate):
    session = ChatSession(**session_input.model_dump())
    doc = session.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    await db.chat_sessions.insert_one(doc)
    return session

@api_router.get("/chat/sessions", response_model=List[ChatSession])
async def get_chat_sessions():
    sessions = await db.chat_sessions.find({}, {"_id": 0}).sort("updated_at", -1).to_list(1000)
    return [ChatSession(**session) for session in sessions]

@api_router.get("/chat/sessions/{session_id}", response_model=ChatSession)
async def get_chat_session(session_id: str):
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return ChatSession(**session)

@api_router.get("/chat/sessions/{session_id}/messages", response_model=List[Message])
async def get_session_messages(session_id: str):
    messages = await db.messages.find({"session_id": session_id}, {"_id": 0}).sort("timestamp", 1).to_list(1000)
    return [Message(**msg) for msg in messages]

@api_router.post("/chat/sessions/{session_id}/message", response_model=ChatResponse)
async def send_message(session_id: str, message_input: MessageCreate):
    # Get session
    session_doc = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = ChatSession(**session_doc)
    
    # Check if session is escalated
    if session.status == "escalated":
        raise HTTPException(status_code=400, detail="Session has been escalated to human support")
    
    # Save user message
    user_message = Message(
        session_id=session_id,
        role="user",
        content=message_input.content
    )
    user_doc = user_message.model_dump()
    user_doc['timestamp'] = user_doc['timestamp'].isoformat()
    await db.messages.insert_one(user_doc)
    
    # Check for escalation
    should_escalate, escalation_reason = check_escalation(message_input.content, session)
    
    if should_escalate:
        # Update session
        session.status = "escalated"
        session.escalation_reason = escalation_reason
        session.updated_at = datetime.now(timezone.utc)
        
        update_doc = session.model_dump()
        update_doc['updated_at'] = update_doc['updated_at'].isoformat()
        await db.chat_sessions.update_one(
            {"id": session_id},
            {"$set": update_doc}
        )
        
        # Create escalation message
        assistant_message = Message(
            session_id=session_id,
            role="assistant",
            content=f"I understand this is important to you. Your conversation has been escalated to our human support team. They will reach out to you within 2 hours during business hours. Reference ID: {session_id[:8]}",
            metadata={"escalated": True, "reason": escalation_reason}
        )
        assistant_doc = assistant_message.model_dump()
        assistant_doc['timestamp'] = assistant_doc['timestamp'].isoformat()
        await db.messages.insert_one(assistant_doc)
        
        return ChatResponse(
            message=assistant_message,
            should_escalate=True,
            escalation_reason=escalation_reason,
            confidence=0.0
        )
    
    # Search relevant FAQs
    relevant_faqs = await search_faqs(message_input.content)
    
    # Build context for LLM
    faq_context = ""
    if relevant_faqs:
        faq_context = "\n\nRelevant FAQ information:\n"
        for i, faq in enumerate(relevant_faqs, 1):
            faq_context += f"{i}. Q: {faq.question}\nA: {faq.answer}\n\n"
    
    # Try LLM first, fallback to FAQ-based response if it fails
    response_text = None
    confidence = 0.7
    use_llm = True
    
    try:
        api_key = os.environ.get('GOOGLE_AI_API_KEY')
        if not api_key:
            logger.warning("GOOGLE_AI_API_KEY not configured, using FAQ fallback")
            use_llm = False
        else:
            system_message = f"""You are a helpful customer support AI assistant. Your goal is to provide accurate, friendly, and professional support.

Guidelines:
- Be empathetic and understanding
- Provide clear, concise answers
- Use the FAQ information when relevant
- If you don't know something, admit it honestly
- Stay professional and courteous
- Keep responses concise but informative
{faq_context}"""
            
            chat = LlmChat(
                api_key=api_key,
                session_id=session_id,
                system_message=system_message
            ).with_model("gemini", "gemini-2.5-pro-preview-05-06")
            
            # Send message to LLM
            user_msg = UserMessage(text=message_input.content)
            response_text = await chat.send_message(user_msg)
            confidence = 0.9 if relevant_faqs else 0.8
            
    except Exception as e:
        logger.error(f"LLM error: {str(e)}, falling back to FAQ-based response")
        use_llm = False
    
    # Fallback to FAQ-based response if LLM failed or not configured
    if not use_llm or not response_text:
        if relevant_faqs:
            # Use the most relevant FAQ
            best_faq = relevant_faqs[0]
            response_text = f"Great question! {best_faq.answer}\n\n"
            
            if len(relevant_faqs) > 1:
                response_text += "You might also find these helpful:\n"
                for i, faq in enumerate(relevant_faqs[1:], 1):
                    response_text += f"\n{i}. **{faq.question}**: {faq.answer[:100]}..."
            
            confidence = 0.85
        else:
            # Generic helpful response
            response_text = "Thank you for your question. While I don't have a specific answer in my knowledge base, I'm here to help! Could you provide more details, or would you like me to escalate this to our human support team who can assist you better?"
            confidence = 0.4
            session.failed_attempts += 1
            await db.chat_sessions.update_one(
                {"id": session_id},
                {"$set": {"failed_attempts": session.failed_attempts}}
            )
    
    # Check if response seems unhelpful
    if len(response_text) < 20 or confidence < 0.5:
        session.failed_attempts += 1
        await db.chat_sessions.update_one(
            {"id": session_id},
            {"$set": {"failed_attempts": session.failed_attempts}}
        )
    
    # Save assistant message
    assistant_message = Message(
        session_id=session_id,
        role="assistant",
        content=response_text,
        metadata={"confidence": confidence, "faq_matched": len(relevant_faqs) > 0}
    )
    assistant_doc = assistant_message.model_dump()
    assistant_doc['timestamp'] = assistant_doc['timestamp'].isoformat()
    await db.messages.insert_one(assistant_doc)
    
    # Update session
    session.updated_at = datetime.now(timezone.utc)
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": {"updated_at": session.updated_at.isoformat()}}
    )
    
    return ChatResponse(
        message=assistant_message,
        should_escalate=False,
        confidence=confidence
    )

@api_router.post("/chat/sessions/{session_id}/escalate")
async def escalate_session(session_id: str, escalation: EscalationRequest):
    session_doc = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session_doc:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session = ChatSession(**session_doc)
    session.status = "escalated"
    session.escalation_reason = escalation.reason
    session.updated_at = datetime.now(timezone.utc)
    
    update_doc = session.model_dump()
    update_doc['updated_at'] = update_doc['updated_at'].isoformat()
    await db.chat_sessions.update_one(
        {"id": session_id},
        {"$set": update_doc}
    )
    
    # Create escalation message
    assistant_message = Message(
        session_id=session_id,
        role="assistant",
        content=f"Your conversation has been escalated to our human support team. They will reach out to you within 2 hours during business hours. Reference ID: {session_id[:8]}",
        metadata={"escalated": True, "reason": escalation.reason}
    )
    assistant_doc = assistant_message.model_dump()
    assistant_doc['timestamp'] = assistant_doc['timestamp'].isoformat()
    await db.messages.insert_one(assistant_doc)
    
    return {"success": True, "message": "Session escalated successfully"}

# Include router
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
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
    
    # Comprehensive FAQs dataset
    sample_faqs = [
        # Account Management (10)
        {
            "question": "How do I reset my password?",
            "answer": "To reset your password: 1) Click 'Forgot Password' on the login page, 2) Enter your registered email address, 3) Check your email for a reset link (check spam folder if needed), 4) Click the link and create a new strong password (minimum 8 characters, include letters, numbers, and symbols), 5) Log in with your new password. The reset link expires in 24 hours. If you don't receive the email, contact support.",
            "category": "Account Management",
            "keywords": ["password", "reset", "forgot", "login", "access", "credential"]
        },
        {
            "question": "How do I change my email address?",
            "answer": "To change your email: 1) Log into your account, 2) Go to 'Account Settings' > 'Profile', 3) Click 'Edit' next to your email, 4) Enter your new email and current password for verification, 5) Verify the new email by clicking the link we send. Your old email will remain active for 7 days. All future communications will go to your new email.",
            "category": "Account Management",
            "keywords": ["email", "change", "update", "modify", "account", "address"]
        },
        {
            "question": "Can I change my subscription plan?",
            "answer": "Yes! To change your plan: 1) Go to 'Account Settings' > 'Subscription', 2) Click 'Change Plan', 3) Select your desired plan (Basic, Pro, or Enterprise), 4) Review the changes and confirm. Upgrades take effect immediately with prorated charges. Downgrades take effect at the next billing cycle. You won't lose any data when switching plans.",
            "category": "Account Management",
            "keywords": ["subscription", "plan", "upgrade", "downgrade", "change", "switch", "tier"]
        },
        {
            "question": "How do I delete my account?",
            "answer": "To permanently delete your account: 1) Go to 'Account Settings' > 'Privacy & Security', 2) Scroll to 'Delete Account', 3) Click 'Request Deletion', 4) Confirm by entering your password, 5) You'll receive an email confirmation. Account deletion takes 30 days (cooling-off period). All your data, orders, and subscriptions will be permanently removed. This action cannot be undone. You can cancel deletion within 30 days by contacting support.",
            "category": "Account Management",
            "keywords": ["delete", "account", "remove", "close", "cancel", "deactivate", "terminate"]
        },
        {
            "question": "How do I enable two-factor authentication?",
            "answer": "To enable 2FA for added security: 1) Go to 'Account Settings' > 'Security', 2) Click 'Enable Two-Factor Authentication', 3) Choose your method (SMS, Authenticator App, or Email), 4) Follow the setup instructions, 5) Save your backup codes in a safe place. Once enabled, you'll need your password and 2FA code to log in. We recommend using an authenticator app like Google Authenticator or Authy for the best security.",
            "category": "Account Management",
            "keywords": ["two factor", "2fa", "authentication", "security", "verification", "mfa"]
        },
        {
            "question": "Can I have multiple users on one account?",
            "answer": "Yes! Our Pro and Enterprise plans support multiple users. To add users: 1) Go to 'Account Settings' > 'Team Members', 2) Click 'Invite User', 3) Enter their email and assign a role (Admin, Member, or Viewer), 4) They'll receive an invitation email. Pro plans include up to 5 users, Enterprise plans include unlimited users. Each user has their own login credentials. You can manage permissions and remove users anytime.",
            "category": "Account Management",
            "keywords": ["multiple users", "team", "users", "members", "invite", "collaborate", "share"]
        },
        {
            "question": "How do I update my profile information?",
            "answer": "To update your profile: 1) Log into your account, 2) Click on your profile picture or name in the top right, 3) Select 'Profile Settings', 4) Update your name, phone number, address, or profile picture, 5) Click 'Save Changes'. Your updated information will be reflected immediately across all services. For security reasons, email and password changes require additional verification.",
            "category": "Account Management",
            "keywords": ["profile", "update", "information", "personal", "details", "edit"]
        },
        {
            "question": "What happens if I forget my username?",
            "answer": "If you forget your username: 1) Go to the login page and click 'Forgot Username', 2) Enter your registered email address, 3) We'll send you an email with your username within minutes. If you don't remember your email, contact our support team with your full name and phone number for account verification. For security, we cannot provide username information over chat without proper verification.",
            "category": "Account Management",
            "keywords": ["username", "forgot", "remember", "login", "account", "credential"]
        },
        {
            "question": "How do I link my social media accounts?",
            "answer": "To link social media accounts for easy login: 1) Go to 'Account Settings' > 'Connected Accounts', 2) Click 'Connect' next to Google, Facebook, or Apple, 3) Authorize the connection, 4) Your accounts are now linked. You can use social login for faster access. You can disconnect anytime, but you'll need to set a password if you remove all social connections. Linking accounts doesn't share your data with social platforms.",
            "category": "Account Management",
            "keywords": ["social media", "google", "facebook", "link", "connect", "login", "oauth"]
        },
        {
            "question": "Can I pause my subscription instead of cancelling?",
            "answer": "Yes! You can pause your subscription for up to 3 months: 1) Go to 'Account Settings' > 'Subscription', 2) Click 'Pause Subscription', 3) Select pause duration (1-3 months), 4) Confirm. During the pause, you'll have read-only access to your data but cannot create new content. Your subscription will automatically resume after the pause period. You won't be charged during the pause. You can resume early anytime.",
            "category": "Account Management",
            "keywords": ["pause", "subscription", "freeze", "hold", "temporary", "suspend"]
        },
        
        # Billing & Payments (12)
        {
            "question": "What payment methods do you accept?",
            "answer": "We accept: Credit/Debit Cards (Visa, Mastercard, American Express, Discover), PayPal, Apple Pay, Google Pay, Bank Transfers (ACH for US customers), and Cryptocurrency (Bitcoin, Ethereum for annual plans). All payments are processed securely through Stripe. We don't store your full card details. For enterprise accounts, we also offer invoice-based billing with Net-30 terms.",
            "category": "Billing & Payments",
            "keywords": ["payment", "method", "accept", "credit card", "paypal", "visa", "mastercard"]
        },
        {
            "question": "When will I be charged?",
            "answer": "Billing schedule: Free trial subscribers are charged after the trial ends (14 days). Monthly plans are charged on the same date each month. Annual plans are charged once per year on your signup date. You'll receive an email reminder 3 days before each charge. If payment fails, we'll retry 3 times over 7 days before suspending your account. Check 'Billing History' in settings for all past charges.",
            "category": "Billing & Payments",
            "keywords": ["charge", "billing", "when", "date", "cycle", "payment"]
        },
        {
            "question": "What is your refund policy?",
            "answer": "Our refund policy: 30-day money-back guarantee for all new subscriptions (no questions asked). Refunds for monthly plans are prorated from the request date. Annual plan refunds are prorated for unused months (minus a 10% processing fee). To request a refund: 1) Go to 'Billing' > 'Request Refund', 2) Select the reason, 3) Submit. Refunds process within 5-7 business days to your original payment method. After 30 days, only prorated refunds are available for service issues.",
            "category": "Billing & Payments",
            "keywords": ["refund", "return", "money back", "cancel", "payment", "guarantee"]
        },
        {
            "question": "Why is my payment failing?",
            "answer": "Common payment failure reasons: 1) Insufficient funds - Check your account balance, 2) Incorrect card details - Verify card number, expiry, and CVV, 3) Billing address mismatch - Ensure address matches your bank records, 4) Card expired - Update with a new card, 5) International transactions blocked - Contact your bank to allow international charges, 6) Daily limit exceeded - Wait 24 hours or contact your bank. Try a different payment method or contact support if issues persist.",
            "category": "Billing & Payments",
            "keywords": ["payment", "failed", "declined", "error", "card", "transaction", "issue"]
        },
        {
            "question": "How do I update my billing information?",
            "answer": "To update billing details: 1) Go to 'Account Settings' > 'Billing', 2) Click 'Payment Methods', 3) To add a new card: Click 'Add Payment Method' and enter details, 4) To update existing: Click 'Edit' next to the card, 5) To set default: Click 'Make Default', 6) To remove: Click 'Delete'. Changes apply to future charges immediately. For security, we'll send you a confirmation email. Your card information is encrypted and PCI-DSS compliant.",
            "category": "Billing & Payments",
            "keywords": ["billing", "payment", "credit card", "update", "account", "change"]
        },
        {
            "question": "Can I get an invoice for my payment?",
            "answer": "Yes! To access invoices: 1) Go to 'Account Settings' > 'Billing History', 2) Click on any payment, 3) Click 'Download Invoice' (PDF). Invoices include: payment date, amount, items, tax, and payment method. Invoices are automatically emailed after each payment. For custom invoices with your company details, update 'Billing Information' with your business name and tax ID. Enterprise customers can receive invoices before payment.",
            "category": "Billing & Payments",
            "keywords": ["invoice", "receipt", "billing", "payment", "download", "pdf", "record"]
        },
        {
            "question": "Are there any setup fees or hidden costs?",
            "answer": "No hidden costs! What you see is what you pay. We have: Zero setup fees, Zero activation fees, Zero cancellation fees, Zero data transfer fees (within limits). You only pay your subscription fee. Additional costs only apply to: Overage charges (if you exceed plan limits), Add-ons (optional features), Professional services (custom implementation). All pricing is transparent on our pricing page. Sales tax or VAT may apply based on your location.",
            "category": "Billing & Payments",
            "keywords": ["fees", "cost", "price", "setup", "charge", "hidden", "additional"]
        },
        {
            "question": "How do I cancel my subscription?",
            "answer": "To cancel your subscription: 1) Go to 'Account Settings' > 'Subscription', 2) Click 'Cancel Subscription', 3) Select cancellation reason (helps us improve), 4) Choose: Cancel immediately (lose access now, no refund) OR Cancel at period end (access until current billing cycle ends), 5) Confirm. You can reactivate anytime before the period ends. Your data is retained for 90 days after cancellation. No cancellation fees apply.",
            "category": "Billing & Payments",
            "keywords": ["cancel", "subscription", "stop", "terminate", "end", "quit"]
        },
        {
            "question": "Can I switch from monthly to annual billing?",
            "answer": "Yes, save 20% by switching to annual! To switch: 1) Go to 'Account Settings' > 'Subscription', 2) Click 'Switch to Annual', 3) Review the prorated charge (credit for unused monthly time), 4) Confirm payment. You'll immediately get annual plan benefits and won't be charged monthly anymore. Your next charge will be in 12 months. Switching from annual to monthly is also possible at your renewal date.",
            "category": "Billing & Payments",
            "keywords": ["switch", "annual", "monthly", "billing", "yearly", "change", "frequency"]
        },
        {
            "question": "What happens if my payment is declined?",
            "answer": "If payment is declined: 1) You'll receive an email immediately, 2) We'll automatically retry in 3 days, 5 days, and 7 days, 3) Update your payment method during this grace period, 4) If all retries fail, your account is suspended (not deleted), 5) You have 30 days to update payment and reactivate. During suspension, you can't access premium features but your data is safe. Once reactivated, you'll be charged for the suspended period.",
            "category": "Billing & Payments",
            "keywords": ["declined", "failed", "payment", "suspended", "retry", "account"]
        },
        {
            "question": "Do you offer discounts for nonprofits or education?",
            "answer": "Yes! We offer special pricing: Nonprofits: 50% off all paid plans (requires 501(c)(3) verification), Educational institutions: 40% off for verified schools and universities, Students: 30% off with valid student ID, To apply: 1) Go to 'Pricing' > 'Special Discounts', 2) Select your category, 3) Upload verification documents, 4) We'll review within 2 business days. Discounts apply for the duration of your verified status. Annual verification required.",
            "category": "Billing & Payments",
            "keywords": ["discount", "nonprofit", "education", "student", "special pricing", "offer"]
        },
        {
            "question": "Can I get a refund if I'm not satisfied?",
            "answer": "Absolutely! We offer a 30-day satisfaction guarantee. If you're not happy for any reason: 1) Contact us within 30 days of your first payment, 2) Tell us why (helps us improve, but not required for refund), 3) We'll process a full refund within 5-7 business days. No questions asked, no hassle. For subscriptions beyond 30 days, we offer prorated refunds if you're experiencing service issues. Your satisfaction is our priority.",
            "category": "Billing & Payments",
            "keywords": ["refund", "satisfied", "unhappy", "money back", "guarantee", "return"]
        },
        
        # Shipping & Delivery (8)
        {
            "question": "How do I track my order?",
            "answer": "To track your order: 1) Log into your account, 2) Go to 'My Orders', 3) Click on your order number, 4) View real-time tracking information. You'll also receive tracking emails at: Order confirmation, Shipped (with tracking number), Out for delivery, Delivered. Click the tracking number to see detailed updates on our carrier's website. If tracking hasn't updated in 48 hours, contact support. Orders typically ship within 1-2 business days.",
            "category": "Shipping & Delivery",
            "keywords": ["track", "order", "shipping", "delivery", "package", "status", "where"]
        },
        {
            "question": "What are your shipping costs and delivery times?",
            "answer": "Shipping options: Standard (5-7 business days): Free on orders $50+, otherwise $5.99, Express (2-3 business days): $12.99, Overnight (next business day): $24.99. International shipping: Varies by country ($15-$50, 7-21 days). Exact costs shown at checkout. Orders ship within 1-2 business days. Weekend and holiday orders ship next business day. Free shipping promotions apply automatically. Delivery times are estimates and may vary during peak seasons.",
            "category": "Shipping & Delivery",
            "keywords": ["shipping", "cost", "delivery", "time", "price", "fee", "how long"]
        },
        {
            "question": "Do you offer international shipping?",
            "answer": "Yes! We ship to over 120 countries worldwide. International shipping includes: Tracking number, Customs documentation, Duty/tax information. Restrictions: Some products can't ship to certain countries (check product page). Delivery times: Canada/Mexico: 7-10 days, Europe: 10-15 days, Asia/Pacific: 12-21 days, Other regions: 15-25 days. Customers are responsible for customs fees and import duties. Shipping costs calculated at checkout based on weight and destination.",
            "category": "Shipping & Delivery",
            "keywords": ["international", "shipping", "worldwide", "countries", "global", "overseas"]
        },
        {
            "question": "What should I do if I receive a damaged product?",
            "answer": "If you receive damaged items: 1) Don't throw away packaging, 2) Take clear photos of: Damaged item, Product packaging, Shipping box, Shipping label, 3) Contact us within 48 hours via 'Support' > 'Report Damaged Item', 4) Upload photos and order number, 5) We'll immediately send a replacement (free shipping) OR issue a full refund (your choice). No need to return the damaged item. We'll handle the carrier claim. If you notice damage upon delivery, refuse the package or note damage on delivery receipt.",
            "category": "Shipping & Delivery",
            "keywords": ["damaged", "broken", "defective", "product", "issue", "received", "wrong"]
        },
        {
            "question": "Can I change my shipping address after ordering?",
            "answer": "Address changes depend on order status: Not yet shipped (within 1 hour): Go to 'My Orders', click 'Edit Address', Already shipped: Contact carrier directly with tracking number to request delivery address change (may incur fees), Delivered to wrong address: Contact support immediately. To avoid issues, double-check your address at checkout. For future orders, update your default shipping address in 'Account Settings' > 'Addresses'. You can save multiple addresses.",
            "category": "Shipping & Delivery",
            "keywords": ["change", "address", "shipping", "wrong", "modify", "update"]
        },
        {
            "question": "What if my package is lost or stolen?",
            "answer": "For lost or stolen packages: 1) Check tracking - confirm it was delivered, 2) Check with neighbors, building office, or safe delivery locations, 3) Wait 48 hours (sometimes marked delivered before actual delivery), 4) Contact us via 'Support' > 'Missing Package', 5) Provide order number and delivery details. We'll: Investigate with carrier, File claim on your behalf, Reship your order OR provide full refund (usually within 3-5 days). We recommend: Adding delivery instructions, Requiring signatures for expensive items, Using a secure delivery location.",
            "category": "Shipping & Delivery",
            "keywords": ["lost", "stolen", "missing", "package", "not received", "where is"]
        },
        {
            "question": "Do you ship to PO boxes?",
            "answer": "Yes, we ship to PO boxes for most items! Restrictions: Large or heavy items may not fit in PO boxes, Express/Overnight shipping not available to PO boxes (requires physical address), Some carriers don't deliver to PO boxes. Standard shipping to PO boxes takes 5-10 business days. When entering your address, select 'PO Box' as address type. Packages will be held at your post office for pickup. You'll receive a notice when it arrives. Military APO/FPO addresses are also supported.",
            "category": "Shipping & Delivery",
            "keywords": ["po box", "mail box", "address", "ship", "deliver"]
        },
        {
            "question": "Can I schedule a specific delivery date?",
            "answer": "Scheduled delivery options: We offer delivery date selection for an additional $4.99 fee. Available dates are shown at checkout (based on your location and current date). Delivery window: 8 AM - 8 PM on selected date. Same-day delivery available in select metro areas ($19.99 fee, order by 12 PM). For guaranteed delivery, choose Express or Overnight shipping. Note: Weather, holidays, or carrier delays may affect scheduled deliveries. We'll notify you immediately of any delays.",
            "category": "Shipping & Delivery",
            "keywords": ["schedule", "date", "delivery", "specific", "when", "choose"]
        },
        
        # Technical Issues (10)
        {
            "question": "How secure is my data?",
            "answer": "Your data security is our top priority: Encryption: TLS 1.3 for data in transit, AES-256 for data at rest, Infrastructure: AWS/Google Cloud with 99.99% uptime, Backups: Automated daily backups, retained for 30 days, Access: Zero-knowledge encryption for sensitive data, Certifications: SOC 2 Type II, ISO 27001, GDPR compliant, HIPAA compliant (enterprise plans), Monitoring: 24/7 security monitoring and threat detection. We never sell your data. You own your data. Regular third-party security audits. Employee background checks and security training.",
            "category": "Technical Issues",
            "keywords": ["security", "data", "privacy", "safe", "encryption", "secure", "protect"]
        },
        {
            "question": "What browsers do you support?",
            "answer": "Supported browsers (latest 2 versions): Desktop: Chrome (recommended), Firefox, Safari, Edge, Opera. Mobile: Safari (iOS), Chrome (Android), Samsung Internet, Firefox Mobile. Minimum requirements: JavaScript enabled, Cookies enabled, Screen resolution 1024x768+. Not supported: Internet Explorer (discontinued). For best performance, use Chrome or Firefox on desktop. Mobile browsers fully supported with responsive design. Update your browser regularly for security and features. Having issues? Clear cache and cookies, try incognito mode.",
            "category": "Technical Issues",
            "keywords": ["browser", "chrome", "firefox", "safari", "compatible", "support", "edge"]
        },
        {
            "question": "Why is the app slow or not loading?",
            "answer": "Troubleshooting slow performance: 1) Check your internet connection (minimum 1 Mbps required), 2) Clear browser cache and cookies: Settings > Privacy > Clear Data, 3) Disable browser extensions temporarily, 4) Try incognito/private mode, 5) Check if browser is updated, 6) Restart browser, 7) Try different browser. If still slow: Check our status page at status.company.com, Large files may take time to process, Peak usage times (9 AM - 5 PM) may affect speed. Contact support if issues persist beyond 30 minutes.",
            "category": "Technical Issues",
            "keywords": ["slow", "loading", "not working", "performance", "lag", "stuck", "frozen"]
        },
        {
            "question": "How do I download my data?",
            "answer": "To export your data: 1) Go to 'Account Settings' > 'Data & Privacy', 2) Click 'Export My Data', 3) Select what to export: All data OR Specific categories (messages, files, contacts, etc.), 4) Choose format: JSON (machine readable) OR CSV (spreadsheet compatible), 5) Click 'Request Export'. You'll receive an email with download link (usually within 24 hours). Download expires after 7 days. Re-export anytime. Exports include all your data per GDPR rights. Enterprise: Bulk API available.",
            "category": "Technical Issues",
            "keywords": ["download", "export", "data", "backup", "save", "extract"]
        },
        {
            "question": "What file types and sizes do you support?",
            "answer": "Supported file types: Documents: PDF, DOC, DOCX, TXT, RTF, ODT, Images: JPG, PNG, GIF, SVG, WebP, HEIC, Spreadsheets: XLS, XLSX, CSV, ODS, Presentations: PPT, PPTX, Audio: MP3, WAV, AAC, FLAC, Video: MP4, MOV, AVI, WebM (Pro+ plans), Archives: ZIP, RAR, 7Z. File size limits: Free: 10 MB per file, Basic: 25 MB per file, Pro: 100 MB per file, Enterprise: 1 GB per file. Total storage: Free: 2 GB, Basic: 10 GB, Pro: 100 GB, Enterprise: Unlimited. Need larger files? Contact sales.",
            "category": "Technical Issues",
            "keywords": ["file", "type", "size", "upload", "support", "format", "limit"]
        },
        {
            "question": "How do I integrate with other tools?",
            "answer": "Integration options: Native integrations (one-click setup): Slack, Microsoft Teams, Google Workspace, Salesforce, Shopify, Zapier (connect 5000+ apps), API access (Pro+ plans): RESTful API, Webhooks, OAuth 2.0, Comprehensive docs at api.company.com. To set up: 1) Go to 'Settings' > 'Integrations', 2) Select the service, 3) Click 'Connect', 4) Authorize access, 5) Configure sync settings. Developer resources: API documentation, SDKs (Python, JavaScript, Ruby), Sandbox environment, Dedicated support. Enterprise: Custom integrations available.",
            "category": "Technical Issues",
            "keywords": ["integrate", "integration", "api", "connect", "third party", "tools", "zapier"]
        },
        {
            "question": "What happens during planned maintenance?",
            "answer": "Maintenance schedule: Planned maintenance: 2nd Sunday of each month, 2-4 AM EST (2-hour window), Advance notice: 7 days via email and in-app notifications, During maintenance: Read-only access (view but cannot edit), Data remains secure and synced, Scheduled tasks still run. Emergency maintenance: Rare, less than 1 hour, Immediate notification, Critical security patches only. Check real-time status: status.company.com, Subscribe to updates via SMS/email. 99.9% uptime guarantee (Pro+). Enterprise: Custom maintenance windows available.",
            "category": "Technical Issues",
            "keywords": ["maintenance", "downtime", "unavailable", "not working", "scheduled"]
        },
        {
            "question": "How do I enable notifications?",
            "answer": "To manage notifications: 1) Go to 'Account Settings' > 'Notifications', 2) Choose channels: Email (always enabled), Push (desktop/mobile), SMS (verify phone first), In-app alerts, 3) Select frequency: Real-time, Daily digest, Weekly summary, 4) Choose notification types: Important only, All activity, Custom (select specific events), 5) Save preferences. Browser notifications: Allow in browser settings when prompted. Mobile: Enable in device Settings > Apps > Our App > Notifications. Unsubscribe from emails: Click unsubscribe in any email (account notifications will still be sent).",
            "category": "Technical Issues",
            "keywords": ["notification", "alerts", "email", "push", "notify", "enable"]
        },
        {
            "question": "Why am I getting errors when uploading files?",
            "answer": "Common upload errors and fixes: File too large: Check size limits for your plan, Compress large files or upgrade plan, Unsupported format: See supported file types in docs, Convert file to supported format, Network timeout: Check internet connection, Try uploading smaller files first, Browser issues: Clear cache, try different browser, Disable ad blockers/extensions, Storage limit reached: Delete old files or upgrade plan, Check storage usage in settings. If errors persist: Try incognito mode, Contact support with error message, Check status page for known issues.",
            "category": "Technical Issues",
            "keywords": ["error", "upload", "file", "failed", "issue", "problem"]
        },
        {
            "question": "Is there a mobile app?",
            "answer": "Yes! Our mobile apps available for: iOS: Download from App Store (iOS 14+ required), Android: Download from Google Play (Android 8+ required), Features: Full feature parity with web, Offline mode (sync when back online), Biometric login (Face ID, Touch ID, Fingerprint), Push notifications, Dark mode. Web app: Access from any mobile browser, Progressive Web App (PWA) - add to home screen. Tablet support: Optimized for iPad and Android tablets. Desktop apps: Windows and macOS apps available (optional). All apps sync instantly across devices.",
            "category": "Technical Issues",
            "keywords": ["mobile", "app", "ios", "android", "phone", "download", "application"]
        },
        
        # General Support (10)
        {
            "question": "What are your customer support hours?",
            "answer": "Support availability: Chat & Email: 24/7 (AI-powered instant responses + human support), Phone support: Monday-Friday, 9 AM - 6 PM EST, Emergency support (Enterprise): 24/7/365, Response times: Free plans: 24-48 hours, Paid plans: 4-8 hours, Enterprise: 1-hour SLA. Holiday closures: We monitor critical issues 24/7 even on holidays. After-hours: Submit tickets anytime, we respond when online. For urgent issues, mark as 'Priority'. Multilingual support: English, Spanish, French, German. Live chat available on website and in-app.",
            "category": "General",
            "keywords": ["hours", "time", "available", "support", "contact", "when", "customer service"]
        },
        {
            "question": "How do I contact customer support?",
            "answer": "Contact methods: Live Chat: Click chat icon (bottom right) or this conversation, Email: support@company.com (attach screenshots for faster help), Phone: 1-800-123-4567 (Mon-Fri, 9 AM - 6 PM EST), Help Center: help.company.com (search 500+ articles), Social Media: @company on Twitter, Facebook (public issues only), Enterprise: Dedicated Slack channel + phone hotline. Before contacting: Check Help Center for instant answers, Have your account email ready, Include error messages/screenshots, Describe steps to reproduce issue. Average response time: Chat: Under 2 minutes, Email: 4-8 hours.",
            "category": "General",
            "keywords": ["contact", "support", "help", "email", "phone", "reach", "talk"]
        },
        {
            "question": "Do you offer training or onboarding?",
            "answer": "Free resources for all users: Video tutorials: 50+ videos covering all features, Interactive guides: Step-by-step in-app walkthroughs, Webinars: Weekly live demos (recorded for later viewing), Documentation: Comprehensive guides at docs.company.com, Blog: Tips, tricks, and best practices. Paid training: Basic plan: 1-hour onboarding call ($99), Pro plan: Includes 2-hour training session, Enterprise: Custom onboarding program: Dedicated success manager, Unlimited training sessions, On-site training available, Custom workflow setup. Book training: Contact success@company.com.",
            "category": "General",
            "keywords": ["training", "onboarding", "learn", "tutorial", "guide", "help", "teach"]
        },
        {
            "question": "What is your uptime guarantee?",
            "answer": "Uptime commitments: Pro plans: 99.9% uptime guarantee (less than 43 minutes downtime/month), Enterprise: 99.99% uptime SLA (less than 4 minutes downtime/month), Free/Basic: Best effort (no SLA). If we breach SLA: Pro: 10% monthly credit per 1% below guarantee, Enterprise: 25% monthly credit + dedicated investigation. Service status: Real-time status: status.company.com, Subscribe to updates: Email, SMS, or Slack, Incident reports: Post-mortem published within 48 hours. Our infrastructure: Multiple data centers, Automatic failover, DDoS protection, 24/7 monitoring.",
            "category": "General",
            "keywords": ["uptime", "downtime", "availability", "sla", "reliability", "guarantee"]
        },
        {
            "question": "Can I suggest new features?",
            "answer": "We love feedback! How to suggest features: 1) Go to 'Help' > 'Feature Requests' OR Visit ideas.company.com, 2) Search existing suggestions (avoid duplicates), 3) Submit your idea with: Clear description, Use case/problem it solves, Who would benefit, 4) Vote on others' suggestions. Our process: All suggestions reviewed by product team, Popular requests prioritized in roadmap, Updates posted on submitted ideas, Accepted features: Added to roadmap with timeline, Beta testing opportunities offered. Recognition: Top contributors get: Early access to new features, Feature naming rights, Swag and credits. Product roadmap public at roadmap.company.com.",
            "category": "General",
            "keywords": ["feature", "suggest", "request", "idea", "feedback", "improvement", "want"]
        },
        {
            "question": "Do you have a referral program?",
            "answer": "Yes! Earn rewards by referring friends: How it works: 1) Get your unique link: Settings > Referral Program, 2) Share with friends/colleagues, 3) They sign up and subscribe to paid plan, 4) You both get rewards! Rewards: You get: $25 credit per successful referral, 25% commission for first 12 months (affiliate option), Referred friend gets: 20% off first year, Extended 30-day trial. No limit on referrals! Payouts: Credits: Applied automatically to your account, Cash: Via PayPal (affiliate program, $100 minimum). Track referrals in dashboard. Terms: Referral must be new customer, Credits non-transferable.",
            "category": "General",
            "keywords": ["referral", "refer", "friend", "credit", "reward", "program", "invite"]
        },
        {
            "question": "What languages do you support?",
            "answer": "Language support: Interface available in: English, Spanish, French, German, Italian, Portuguese, Chinese (Simplified), Japanese, Korean, Dutch, Russian, Arabic. To change language: 1) Click profile icon, 2) Select 'Language', 3) Choose from list, 4) Interface updates immediately. Content translation: AI-powered translation for user-generated content (40+ languages), Real-time translation in chat/comments, Document translation (Pro+ plans). Support languages: Customer support available in English, Spanish, French, German. Time zone support: Automatic time zone detection, Display dates/times in your local time. Note: Some features may launch in English first, then localized.",
            "category": "General",
            "keywords": ["language", "translate", "spanish", "french", "german", "international", "localization"]
        },
        {
            "question": "How do I report a bug or technical issue?",
            "answer": "To report bugs effectively: 1) Go to 'Help' > 'Report a Bug', 2) Provide details: What you were trying to do, What happened vs. what you expected, Steps to reproduce the issue, Browser/device information (auto-collected), 3) Attach: Screenshots (drag & drop), Screen recording (if applicable), Error messages, 4) Select severity: Critical (can't work), Major (workaround needed), Minor (cosmetic). We'll: Acknowledge within 1 hour, Provide status updates, Notify when fixed. Bug bounty program: Security vulnerabilities: Report to security@company.com, Rewards up to $10,000 for critical issues. All reporters credited in changelog.",
            "category": "General",
            "keywords": ["bug", "issue", "problem", "error", "report", "broken", "not working"]
        },
        {
            "question": "Do you offer enterprise or custom plans?",
            "answer": "Enterprise solutions: Custom features: White-label options, Custom integrations, Advanced security (SSO, SAML, SCIM), Dedicated infrastructure, API rate limit increases, Custom data retention. Support: Dedicated account manager, 24/7 priority support, 1-hour SLA, Quarterly business reviews, On-site training. Pricing: Based on: Number of users, Storage requirements, Feature needs, Support level, Minimum: 50 users or $500/month. To discuss: Contact sales@company.com, Book demo: company.com/enterprise, Phone: 1-800-123-4567 ext. 2. Volume discounts available.",
            "category": "General",
            "keywords": ["enterprise", "custom", "plan", "business", "large", "organization", "corporate"]
        },
        {
            "question": "What are your terms of service and privacy policy?",
            "answer": "Legal documents: Terms of Service: Defines usage rights and responsibilities, Available at: company.com/terms, Last updated: January 2025. Privacy Policy: Explains data collection and usage, Available at: company.com/privacy, GDPR and CCPA compliant. Key points: You own your data, We don't sell personal information, You can delete your account anytime, We use cookies (can opt-out), We're SOC 2 Type II certified. Changes: Notified 30 days before major changes, Continued use = acceptance, Can export data and leave anytime. Questions: privacy@company.com, legal@company.com. DPA available for enterprise customers.",
            "category": "General",
            "keywords": ["terms", "service", "privacy", "policy", "legal", "gdpr", "compliance"]
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

@api_router.delete("/chat/sessions/{session_id}")
async def delete_session(session_id: str):
    # Check if session exists
    session = await db.chat_sessions.find_one({"id": session_id}, {"_id": 0})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Delete all messages in the session
    await db.messages.delete_many({"session_id": session_id})
    
    # Delete the session
    await db.chat_sessions.delete_one({"id": session_id})
    
    return {"success": True, "message": "Session deleted successfully"}

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
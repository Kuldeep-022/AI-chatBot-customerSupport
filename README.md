# AI Customer Support Bot

An intelligent customer support chatbot powered by **Gemini 2.5 Pro** that simulates customer support interactions with contextual memory, FAQ matching, and smart escalation capabilities.

## 🎯 Features

### Core Functionality
- **AI-Powered Responses**: Leverages Google's Gemini 2.5 Pro for natural, contextual conversations
- **Contextual Memory**: Maintains conversation history across multiple messages for coherent interactions
- **FAQ-Based RAG**: Searches through 15+ FAQs to provide accurate, knowledge-based responses
- **Smart Escalation**: Automatically escalates conversations based on:
  - Escalation keywords (refund, complaint, manager, etc.)
  - Multiple failed resolution attempts (3+ failures)
  - User confidence thresholds
  - Manual escalation requests

### Dashboard Features
- **Session Management**: Track all conversations with status indicators
- **Multi-Panel Layout**:
  - Left: Conversation history with status badges
  - Center: Interactive chat interface
  - Right: Detailed session information
- **Real-Time Updates**: Live message streaming and session status updates
- **Confidence Scoring**: Display AI confidence levels for each response

## 🏗️ Architecture

### Backend Stack
- **FastAPI**: High-performance REST API
- **MongoDB**: Session and message persistence
- **Gemini 2.5 Pro**: LLM integration
- **Python 3.11**: Modern async/await patterns

### Frontend Stack
- **React 19**: Component-based UI
- **Tailwind CSS**: Utility-first styling
- **Shadcn/UI**: Modern component library
- **Axios**: HTTP client
- **Sonner**: Toast notifications

## 📋 API Endpoints

### Chat Operations
```
POST   /api/chat/start                     - Create new chat session
GET    /api/chat/sessions                  - List all sessions
GET    /api/chat/sessions/{id}             - Get session details
GET    /api/chat/sessions/{id}/messages    - Get session messages
POST   /api/chat/sessions/{id}/message     - Send message
POST   /api/chat/sessions/{id}/escalate    - Escalate to human
```

### FAQ Operations
```
GET    /api/faqs                           - Get all FAQs
POST   /api/faqs                           - Create new FAQ (admin)
```

## 🗄️ Database Schema

### Collections

#### chat_sessions
```javascript
{
  id: String,              // UUID
  title: String,           // Conversation title
  status: String,          // "active" | "escalated" | "resolved"
  created_at: DateTime,
  updated_at: DateTime,
  escalation_reason: String?,
  failed_attempts: Number,
  summary: String?
}
```

#### messages
```javascript
{
  id: String,              // UUID
  session_id: String,      // Reference to chat_sessions
  role: String,            // "user" | "assistant"
  content: String,         // Message text
  timestamp: DateTime,
  metadata: {
    confidence: Number?,   // 0.0 - 1.0
    faq_matched: Boolean?,
    escalated: Boolean?
  }
}
```

#### faqs
```javascript
{
  id: String,              // UUID
  question: String,
  answer: String,
  category: String,        // "Account Management" | "Billing & Payments" | etc.
  keywords: [String],      // Search keywords
  created_at: DateTime
}
```

## 🤖 LLM Integration

### Gemini 2.5 Pro Configuration
- **Model**: `gemini-2.5-pro-preview-05-06`
- **Features**:
  - Multi-turn conversation support
  - Automatic context management
  - Session-based memory
  - Streaming responses

### FAQ-Enhanced RAG
1. User query is analyzed for keyword matches
2. Top 3 relevant FAQs are retrieved based on scoring:
   - Question match: +5 points
   - Keyword match: +2 points per keyword
   - Answer match: +1 point
3. FAQs are injected into system prompt as context
4. LLM generates response using both context and conversation history

## 🚨 Escalation Logic

### Automatic Triggers

#### 1. Keyword-Based Escalation
Monitored keywords:
- refund, complaint, manager
- speak to human, human agent
- not satisfied, unacceptable
- terrible, worst, angry
- lawsuit, lawyer, legal, compensation

#### 2. Failed Attempts Threshold
- Tracks unsuccessful resolution attempts
- Escalates after 3+ failed attempts
- Considers low confidence (<0.6) as potential failure

#### 3. Confidence Threshold
- Responses with <0.6 confidence trigger warnings
- Allows proactive user escalation

### Manual Escalation
Users can manually request escalation via the "Escalate" button at any time.

## 📊 Dataset: FAQs

### Categories (15 FAQs)
1. **Account Management** (4 FAQs)
   - Password reset
   - Subscription changes
   - Account deletion

2. **Billing & Payments** (6 FAQs)
   - Refund policy
   - Payment failures
   - Order cancellation
   - Billing updates

3. **Shipping & Delivery** (3 FAQs)
   - Order tracking
   - International shipping
   - Damaged products

4. **Technical Issues** (2 FAQs)
   - Data security
   - Browser compatibility

5. **General** (2 FAQs)
   - Business hours
   - Contact information

## 🎨 UI/UX Design

### Design System
- **Colors**: Purple gradient theme (#667eea → #764ba2)
- **Typography**:
  - Headings: Space Grotesk (modern, technical)
  - Body: Inter (clean, readable)
- **Layout**: Three-column dashboard
- **Components**: Shadcn/UI for consistency

### Key Design Elements
- Glass-morphism effects with backdrop blur
- Smooth fade-in animations for messages
- Status badges (Active, Escalated, Resolved)
- Confidence indicators
- Real-time session updates
- Responsive design (desktop-first)

## 🔧 Setup & Installation

### Prerequisites
```bash
- Python 3.11+
- Node.js 18+
- MongoDB
- Google AI API Key
```

### Environment Variables

#### Backend (.env)
```env
MONGO_URL=mongodb://localhost:27017
DB_NAME=test_database
CORS_ORIGINS=*
GOOGLE_AI_API_KEY=your_api_key_here
```

#### Frontend (.env)
```env
REACT_APP_BACKEND_URL=https://your-backend-url.com
```

### Installation Steps

1. **Install Backend Dependencies**
```bash
cd backend
pip install -r requirements.txt
```

2. **Install Frontend Dependencies**
```bash
cd frontend
yarn install
```

3. **Start Services**
```bash
# Backend (via supervisor)
sudo supervisorctl restart backend

# Frontend
cd frontend
yarn start
```

## 🧪 Testing

### Manual Testing Flow
1. Start new conversation
2. Ask FAQ-related questions (e.g., "How do I reset my password?")
3. Test escalation with keywords (e.g., "I want a refund!")
4. Verify session status updates
5. Check confidence scores

### API Testing
```bash
# Get FAQs
curl https://your-backend-url.com/api/faqs

# Start session
curl -X POST https://your-backend-url.com/api/chat/start \
  -H "Content-Type: application/json" \
  -d '{"title": "Test Session"}'

# Send message
curl -X POST https://your-backend-url.com/api/chat/sessions/{SESSION_ID}/message \
  -H "Content-Type: application/json" \
  -d '{"content": "How do I reset my password?"}'
```

## 📝 Prompts & Context

### Conversation Context Management
- Full conversation history passed to LLM
- Session-based memory via emergentintegrations
- Automatic context truncation for long conversations
- FAQ context dynamically injected per query

## 🚀 Deployment

### Production Checklist
- [ ] Update GOOGLE_AI_API_KEY with production key
- [ ] Configure CORS_ORIGINS for your domain
- [ ] Set up MongoDB with authentication
- [ ] Enable HTTPS
- [ ] Configure rate limiting
- [ ] Set up monitoring and logging
- [ ] Add authentication/authorization

## 📈 Future Enhancements

1. **Authentication System**: User accounts and session persistence
2. **Human Handoff**: Real human agent integration
3. **Analytics Dashboard**: Conversation metrics and insights
4. **Multi-language Support**: i18n for global users
5. **Voice Integration**: Speech-to-text and text-to-speech
6. **Sentiment Analysis**: Real-time emotion detection
7. **Custom Training**: Fine-tune on company-specific data
8. **Email Integration**: Continue conversations via email

## 🔐 Security Considerations

- API key stored in environment variables
- MongoDB connection secured
- CORS configured for specific origins
- Input validation on all endpoints
- Rate limiting recommended for production
- No sensitive data in logs

## 📄 License

MIT License - Feel free to use and modify for your needs.

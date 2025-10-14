import { useState, useEffect, useRef } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import axios from "axios";
import { Toaster, toast } from "sonner";
import { MessageCircle, Send, AlertCircle, Clock, CheckCircle, XCircle, Plus, User, Bot, AlertTriangle, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

const Dashboard = () => {
  const [sessions, setSessions] = useState([]);
  const [currentSession, setCurrentSession] = useState(null);
  const [messages, setMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [sendingMessage, setSendingMessage] = useState(false);
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    loadSessions();
  }, []);

  useEffect(() => {
    if (currentSession) {
      loadMessages(currentSession.id);
    }
  }, [currentSession]);

  const loadSessions = async () => {
    try {
      const response = await axios.get(`${API}/chat/sessions`);
      setSessions(response.data);
    } catch (error) {
      console.error("Error loading sessions:", error);
      toast.error("Failed to load chat sessions");
    }
  };

  const loadMessages = async (sessionId) => {
    try {
      setLoading(true);
      const response = await axios.get(`${API}/chat/sessions/${sessionId}/messages`);
      setMessages(response.data);
    } catch (error) {
      console.error("Error loading messages:", error);
      toast.error("Failed to load messages");
    } finally {
      setLoading(false);
    }
  };

  const createNewSession = async () => {
    try {
      const response = await axios.post(`${API}/chat/start`, {
        title: "New Conversation"
      });
      const newSession = response.data;
      setSessions([newSession, ...sessions]);
      setCurrentSession(newSession);
      setMessages([]);
      toast.success("New conversation started");
    } catch (error) {
      console.error("Error creating session:", error);
      toast.error("Failed to create new session");
    }
  };

  const sendMessage = async () => {
    if (!inputMessage.trim() || !currentSession) return;
    if (currentSession.status === "escalated") {
      toast.error("This conversation has been escalated to human support");
      return;
    }

    const userMessage = inputMessage;
    setInputMessage("");
    setSendingMessage(true);

    try {
      const response = await axios.post(
        `${API}/chat/sessions/${currentSession.id}/message`,
        { content: userMessage }
      );

      // Reload messages to get both user and assistant messages
      await loadMessages(currentSession.id);

      if (response.data.should_escalate) {
        toast.warning("Conversation escalated to human support", {
          description: response.data.escalation_reason
        });
        // Reload session to update status
        const sessionResponse = await axios.get(`${API}/chat/sessions/${currentSession.id}`);
        setCurrentSession(sessionResponse.data);
        loadSessions();
      } else if (response.data.confidence < 0.6) {
        toast.info("I might not have the best answer. Feel free to escalate to human support if needed.");
      }
    } catch (error) {
      console.error("Error sending message:", error);
      toast.error("Failed to send message");
    } finally {
      setSendingMessage(false);
    }
  };

  const handleEscalate = async () => {
    if (!currentSession) return;

    try {
      await axios.post(`${API}/chat/sessions/${currentSession.id}/escalate`, {
        reason: "User requested escalation"
      });
      toast.success("Conversation escalated to human support");
      const sessionResponse = await axios.get(`${API}/chat/sessions/${currentSession.id}`);
      setCurrentSession(sessionResponse.data);
      loadMessages(currentSession.id);
      loadSessions();
    } catch (error) {
      console.error("Error escalating:", error);
      toast.error("Failed to escalate conversation");
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case "active":
        return <MessageCircle className="w-4 h-4" />;
      case "escalated":
        return <AlertCircle className="w-4 h-4" />;
      case "resolved":
        return <CheckCircle className="w-4 h-4" />;
      default:
        return <MessageCircle className="w-4 h-4" />;
    }
  };

  const getStatusBadge = (status) => {
    const variants = {
      active: "default",
      escalated: "destructive",
      resolved: "secondary"
    };
    return (
      <Badge variant={variants[status]} className="capitalize">
        {status}
      </Badge>
    );
  };

  const formatTime = (timestamp) => {
    const date = new Date(timestamp);
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="dashboard-container">
      <Toaster position="top-right" richColors />
      
      {/* Header */}
      <div className="dashboard-header">
        <div className="header-content">
          <div className="flex items-center gap-3">
            <div className="logo-circle">
              <MessageCircle className="w-6 h-6" />
            </div>
            <div>
              <h1 className="header-title">AI Customer Support</h1>
              <p className="header-subtitle">Intelligent assistance powered by Gemini 2.5 Pro</p>
            </div>
          </div>
        </div>
      </div>

      <div className="dashboard-layout">
        {/* Left Sidebar - Sessions */}
        <div className="sessions-sidebar">
          <div className="sessions-header">
            <h2 className="sessions-title">Conversations</h2>
            <Button
              data-testid="new-conversation-btn"
              onClick={createNewSession}
              size="sm"
              className="new-session-btn"
            >
              <Plus className="w-4 h-4" />
            </Button>
          </div>
          
          <ScrollArea className="sessions-list">
            {sessions.length === 0 ? (
              <div className="empty-state">
                <MessageCircle className="w-12 h-12 opacity-20" />
                <p className="empty-text">No conversations yet</p>
                <p className="empty-subtext">Start a new conversation to get help</p>
              </div>
            ) : (
              sessions.map((session) => (
                <div
                  key={session.id}
                  data-testid={`session-item-${session.id}`}
                  className={`session-item ${
                    currentSession?.id === session.id ? "session-item-active" : ""
                  }`}
                  onClick={() => setCurrentSession(session)}
                >
                  <div className="session-item-header">
                    <div className="flex items-center gap-2">
                      {getStatusIcon(session.status)}
                      <span className="session-title">{session.title}</span>
                    </div>
                    {getStatusBadge(session.status)}
                  </div>
                  <p className="session-date">
                    {new Date(session.created_at).toLocaleDateString()}
                  </p>
                  {session.escalation_reason && (
                    <p className="session-escalation">
                      <AlertTriangle className="w-3 h-3" />
                      {session.escalation_reason}
                    </p>
                  )}
                </div>
              ))
            )}
          </ScrollArea>
        </div>

        {/* Main Chat Area */}
        <div className="chat-main">
          {!currentSession ? (
            <div className="chat-empty">
              <div className="chat-empty-content">
                <div className="chat-empty-icon">
                  <Bot className="w-20 h-20" />
                </div>
                <h2 className="chat-empty-title">Welcome to AI Support</h2>
                <p className="chat-empty-text">
                  Start a new conversation or select an existing one from the sidebar
                </p>
                <Button
                  data-testid="empty-new-conversation-btn"
                  onClick={createNewSession}
                  size="lg"
                  className="chat-empty-btn"
                >
                  <Plus className="w-5 h-5 mr-2" />
                  Start Conversation
                </Button>
              </div>
            </div>
          ) : (
            <>
              <div className="chat-messages-container">
                <ScrollArea className="chat-messages">
                  {loading ? (
                    <div className="chat-loading">
                      <div className="loading-spinner"></div>
                      <p>Loading messages...</p>
                    </div>
                  ) : messages.length === 0 ? (
                    <div className="messages-empty">
                      <Bot className="w-16 h-16 opacity-20" />
                      <p className="messages-empty-text">No messages yet. Start the conversation!</p>
                    </div>
                  ) : (
                    <div className="messages-list">
                      {messages.map((message) => (
                        <div
                          key={message.id}
                          data-testid={`message-${message.role}-${message.id}`}
                          className={`message-bubble ${
                            message.role === "user" ? "message-user" : "message-assistant"
                          }`}
                        >
                          <div className="message-avatar">
                            {message.role === "user" ? (
                              <User className="w-5 h-5" />
                            ) : (
                              <Bot className="w-5 h-5" />
                            )}
                          </div>
                          <div className="message-content">
                            <div className="message-header">
                              <span className="message-role">
                                {message.role === "user" ? "You" : "AI Assistant"}
                              </span>
                              <span className="message-time">{formatTime(message.timestamp)}</span>
                            </div>
                            <div className="message-text">{message.content}</div>
                            {message.metadata?.confidence && message.role === "assistant" && (
                              <div className="message-metadata">
                                <span className="confidence-badge">
                                  Confidence: {(message.metadata.confidence * 100).toFixed(0)}%
                                </span>
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                      <div ref={messagesEndRef} />
                    </div>
                  )}
                </ScrollArea>
              </div>

              <div className="chat-input-container">
                {currentSession.status === "escalated" && (
                  <div className="escalation-notice">
                    <AlertCircle className="w-4 h-4" />
                    <span>This conversation has been escalated to human support</span>
                  </div>
                )}
                <div className="chat-input-wrapper">
                  <Input
                    data-testid="chat-input"
                    type="text"
                    placeholder="Type your message..."
                    value={inputMessage}
                    onChange={(e) => setInputMessage(e.target.value)}
                    onKeyPress={(e) => e.key === "Enter" && sendMessage()}
                    disabled={sendingMessage || currentSession.status === "escalated"}
                    className="chat-input"
                  />
                  <div className="chat-actions">
                    <Button
                      data-testid="send-message-btn"
                      onClick={sendMessage}
                      disabled={!inputMessage.trim() || sendingMessage || currentSession.status === "escalated"}
                      className="send-btn"
                    >
                      {sendingMessage ? (
                        <div className="loading-spinner-small"></div>
                      ) : (
                        <Send className="w-4 h-4" />
                      )}
                    </Button>
                    {currentSession.status !== "escalated" && (
                      <Button
                        data-testid="escalate-btn"
                        onClick={handleEscalate}
                        variant="outline"
                        className="escalate-btn"
                      >
                        <AlertCircle className="w-4 h-4 mr-2" />
                        Escalate
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Right Sidebar - Session Details */}
        {currentSession && (
          <div className="details-sidebar">
            <h3 className="details-title">Session Details</h3>
            <Separator className="my-4" />
            
            <div className="details-content">
              <div className="detail-item">
                <span className="detail-label">Status</span>
                {getStatusBadge(currentSession.status)}
              </div>
              
              <div className="detail-item">
                <span className="detail-label">Created</span>
                <span className="detail-value">
                  {new Date(currentSession.created_at).toLocaleString()}
                </span>
              </div>
              
              <div className="detail-item">
                <span className="detail-label">Last Updated</span>
                <span className="detail-value">
                  {new Date(currentSession.updated_at).toLocaleString()}
                </span>
              </div>
              
              <div className="detail-item">
                <span className="detail-label">Session ID</span>
                <span className="detail-value detail-id">{currentSession.id.slice(0, 8)}</span>
              </div>
              
              {currentSession.escalation_reason && (
                <div className="detail-item">
                  <span className="detail-label">Escalation Reason</span>
                  <div className="escalation-detail">
                    <AlertTriangle className="w-4 h-4" />
                    <span>{currentSession.escalation_reason}</span>
                  </div>
                </div>
              )}
              
              <div className="detail-item">
                <span className="detail-label">Failed Attempts</span>
                <span className="detail-value">{currentSession.failed_attempts || 0}</span>
              </div>
            </div>

            <Separator className="my-4" />
            
            <div className="details-info">
              <h4 className="info-title">Need Help?</h4>
              <p className="info-text">
                Our AI assistant is here 24/7. If you need human support, use the escalate button.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
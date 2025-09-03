import React, { useState, useCallback } from 'react';
import {
  Container,
  Paper,
  Box,
  Typography,
  TextField,
  Button,
  IconButton,
  ToggleButton,
  ToggleButtonGroup,
  Card,
  CardContent,
  List,
  ListItem,
  ListItemText,
  Chip,
  CircularProgress
} from '@mui/material';
import {
  Mic,
  MicOff,
  Send,
  TextFields,
  VoiceChat,
  Schedule,
  Event
} from '@mui/icons-material';
import SpeechRecognition, { useSpeechRecognition } from 'react-speech-recognition';
import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000';

const SmartScheduler = () => {
  const [inputMode, setInputMode] = useState('text'); // 'text' or 'speech'
  const [textInput, setTextInput] = useState('');
  const [conversation, setConversation] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [suggestedSlots, setSuggestedSlots] = useState([]);
  const [conversationState, setConversationState] = useState('greeting');

  const {
    transcript,
    listening,
    resetTranscript,
    browserSupportsSpeechRecognition
  } = useSpeechRecognition();

  // Handle input mode change
  const handleInputModeChange = (event, newMode) => {
    if (newMode !== null) {
      setInputMode(newMode);
      if (newMode === 'speech') {
        resetTranscript();
      }
    }
  };

  // Send message to backend
  const sendMessage = async (message) => {
    if (!message.trim()) return;

    setIsLoading(true);
    
    // Add user message to conversation
    const userMessage = { type: 'user', content: message, timestamp: new Date() };
    setConversation(prev => [...prev, userMessage]);

    try {
      const response = await axios.post(`${API_BASE_URL}/api/chat/text`, {
        message: message,
        user_id: 'default',
        conversation_state: conversationState
      });

      const { response: botResponse, conversation_state, suggested_slots } = response.data;

      // Add bot response to conversation
      const botMessage = { 
        type: 'bot', 
        content: botResponse, 
        timestamp: new Date(),
        suggestedSlots: suggested_slots 
      };
      setConversation(prev => [...prev, botMessage]);

      // Update state
      setConversationState(conversation_state);
      setSuggestedSlots(suggested_slots || []);

    } catch (error) {
      console.error('Error sending message:', error);
      const errorMessage = { 
        type: 'error', 
        content: 'Sorry, I encountered an error. Please try again.', 
        timestamp: new Date() 
      };
      setConversation(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  // Handle text input submission
  const handleTextSubmit = () => {
    sendMessage(textInput);
    setTextInput('');
  };

  // Handle speech input
  const handleSpeechToggle = () => {
    if (listening) {
      SpeechRecognition.stopListening();
      if (transcript.trim()) {
        sendMessage(transcript);
        resetTranscript();
      }
    } else {
      resetTranscript();
      SpeechRecognition.startListening({ continuous: true });
    }
  };

  // Handle slot selection
  const handleSlotSelection = async (slot) => {
    try {
      const response = await axios.post(`${API_BASE_URL}/api/schedule/confirm`, {
        title: 'Scheduled Meeting',
        start_time: slot.start_time,
        end_time: slot.end_time,
        description: 'Meeting scheduled via Smart Scheduler'
      });

      if (response.data.status === 'success') {
        const confirmationMessage = { 
          type: 'bot', 
          content: '✅ Meeting scheduled successfully!', 
          timestamp: new Date() 
        };
        setConversation(prev => [...prev, confirmationMessage]);
        setSuggestedSlots([]);
      }
    } catch (error) {
      console.error('Error scheduling meeting:', error);
    }
  };

  if (!browserSupportsSpeechRecognition) {
    return (
      <Container>
        <Paper sx={{ p: 3, mt: 3 }}>
          <Typography variant="h6" color="error">
            Browser doesn't support speech recognition.
          </Typography>
        </Paper>
      </Container>
    );
  }

  return (
    <Container maxWidth="lg" sx={{ py: 4 }}>
      <Typography variant="h3" component="h1" gutterBottom align="center">
        🤖 Smart Scheduler
      </Typography>
      
      <Typography variant="subtitle1" align="center" color="text.secondary" gutterBottom>
        Your intelligent meeting scheduling assistant
      </Typography>

      <Box sx={{ display: 'flex', gap: 3, mt: 4 }}>
        {/* Chat Interface */}
        <Paper sx={{ flex: 1, p: 3 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
            <Typography variant="h5" component="h2">
              Chat
            </Typography>
            
            {/* Input Mode Toggle */}
            <ToggleButtonGroup
              value={inputMode}
              exclusive
              onChange={handleInputModeChange}
              size="small"
            >
              <ToggleButton value="text">
                <TextFields sx={{ mr: 1 }} />
                Text
              </ToggleButton>
              <ToggleButton value="speech">
                <VoiceChat sx={{ mr: 1 }} />
                Speech
              </ToggleButton>
            </ToggleButtonGroup>
          </Box>

          {/* Conversation Display */}
          <Box sx={{ height: 400, overflowY: 'auto', mb: 3, border: 1, borderColor: 'divider', borderRadius: 1, p: 2 }}>
            {conversation.length === 0 && (
              <Typography color="text.secondary" align="center">
                Start a conversation! Try saying "Schedule a meeting" or "Am I free tomorrow?"
              </Typography>
            )}
            
            {conversation.map((message, index) => (
              <Box key={index} sx={{ mb: 2 }}>
                <Chip 
                  label={message.type === 'user' ? 'You' : message.type === 'bot' ? 'Assistant' : 'Error'}
                  color={message.type === 'user' ? 'primary' : message.type === 'bot' ? 'secondary' : 'error'}
                  size="small"
                  sx={{ mb: 1 }}
                />
                <Typography variant="body1" sx={{ ml: 1 }}>
                  {message.content}
                </Typography>
                
                {/* Show suggested slots if available */}
                {message.suggestedSlots && message.suggestedSlots.length > 0 && (
                  <Box sx={{ mt: 2 }}>
                    <Typography variant="subtitle2" gutterBottom>
                      Available Time Slots:
                    </Typography>
                    {message.suggestedSlots.map((slot, slotIndex) => (
                      <Button
                        key={slotIndex}
                        variant="outlined"
                        size="small"
                        onClick={() => handleSlotSelection(slot)}
                        sx={{ mr: 1, mb: 1 }}
                      >
                        {new Date(slot.start_time).toLocaleString()}
                      </Button>
                    ))}
                  </Box>
                )}
              </Box>
            ))}
            
            {isLoading && (
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <CircularProgress size={20} />
                <Typography color="text.secondary">Assistant is thinking...</Typography>
              </Box>
            )}
          </Box>

          {/* Input Area */}
          <Box sx={{ display: 'flex', gap: 1 }}>
            {inputMode === 'text' ? (
              <>
                <TextField
                  fullWidth
                  variant="outlined"
                  placeholder="Type your message..."
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleTextSubmit()}
                  disabled={isLoading}
                />
                <Button
                  variant="contained"
                  onClick={handleTextSubmit}
                  disabled={isLoading || !textInput.trim()}
                  sx={{ minWidth: 'auto', px: 2 }}
                >
                  <Send />
                </Button>
              </>
            ) : (
              <>
                <TextField
                  fullWidth
                  variant="outlined"
                  placeholder={listening ? "Listening... Speak now!" : "Click mic to start speaking"}
                  value={transcript}
                  disabled
                />
                <IconButton
                  color={listening ? "error" : "primary"}
                  onClick={handleSpeechToggle}
                  disabled={isLoading}
                  sx={{ minWidth: 'auto' }}
                >
                  {listening ? <MicOff /> : <Mic />}
                </IconButton>
              </>
            )}
          </Box>

          {/* Speech Status */}
          {inputMode === 'speech' && (
            <Box sx={{ mt: 1 }}>
              <Typography variant="caption" color="text.secondary">
                {listening ? '🎤 Listening...' : '🎤 Click microphone to start'}
              </Typography>
            </Box>
          )}
        </Paper>

        {/* Calendar Preview */}
        <Paper sx={{ width: 300, p: 3 }}>
          <Typography variant="h6" gutterBottom>
            <Event sx={{ mr: 1, verticalAlign: 'middle' }} />
            Quick Actions
          </Typography>
          
          <List dense>
            <ListItem>
              <Button
                fullWidth
                variant="outlined"
                onClick={() => sendMessage("Am I free today?")}
                disabled={isLoading}
              >
                Check Today's Schedule
              </Button>
            </ListItem>
            <ListItem>
              <Button
                fullWidth
                variant="outlined"
                onClick={() => sendMessage("Schedule a 30-minute meeting")}
                disabled={isLoading}
              >
                Schedule 30min Meeting
              </Button>
            </ListItem>
            <ListItem>
              <Button
                fullWidth
                variant="outlined"
                onClick={() => sendMessage("Am I free tomorrow afternoon?")}
                disabled={isLoading}
              >
                Check Tomorrow
              </Button>
            </ListItem>
          </List>

          {/* Current Suggested Slots */}
          {suggestedSlots.length > 0 && (
            <Box sx={{ mt: 3 }}>
              <Typography variant="h6" gutterBottom>
                <Schedule sx={{ mr: 1, verticalAlign: 'middle' }} />
                Suggested Times
              </Typography>
              {suggestedSlots.map((slot, index) => (
                <Card key={index} sx={{ mb: 1 }}>
                  <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                    <Typography variant="body2">
                      {new Date(slot.start_time).toLocaleString()}
                    </Typography>
                    <Button
                      size="small"
                      variant="contained"
                      onClick={() => handleSlotSelection(slot)}
                      sx={{ mt: 1 }}
                    >
                      Book This Slot
                    </Button>
                  </CardContent>
                </Card>
              ))}
            </Box>
          )}
        </Paper>
      </Box>
    </Container>
  );
};

export default SmartScheduler;

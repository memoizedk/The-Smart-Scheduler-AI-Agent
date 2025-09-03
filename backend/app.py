# backend/app.py
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import json
import speech_recognition as sr
import io
import wave
from datetime import datetime, date

# Import your existing components
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.nlp_processor import NLPProcessor
from agent.calendar_integration import AdvancedCalendarManager
from agent.auth import authenticate_google_calendar
from config import settings
from utils.date_parser import AdvancedDateParser

app = FastAPI(title="Smart Scheduler API", version="1.0.0")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for API requests/responses
class TextInputRequest(BaseModel):
    message: str
    user_id: Optional[str] = "default"
    conversation_state: Optional[str] = "greeting"
    context: Optional[Dict[str, Any]] = {}

class ScheduleRequest(BaseModel):
    title: str
    start_time: datetime
    end_time: datetime
    description: Optional[str] = ""
    attendees: Optional[List[str]] = []

class ChatResponse(BaseModel):
    response: str
    conversation_state: str
    suggested_slots: Optional[List[Dict]] = []
    meeting_info: Optional[Dict] = {}
    action_required: Optional[str] = None

class UserPreferences(BaseModel):
    work_start_hour: int = 9
    work_end_hour: int = 17
    timezone: str = "UTC"

# Global components (in production, use dependency injection)
nlp_processor = None
calendar_manager = None
date_parser = AdvancedDateParser()
user_sessions = {}  # Store user conversation states

@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    global nlp_processor, calendar_manager
    
    # Initialize NLP processor
    nlp_processor = NLPProcessor(api_key=settings.GEMINI_API_KEY)
    
    # Initialize calendar service
    google_service = authenticate_google_calendar(
        credentials_path=settings.GOOGLE_CALENDAR_CREDENTIALS_PATH
    )
    calendar_manager = AdvancedCalendarManager(
        google_service, 
        timezone=settings.DEFAULT_TIMEZONE
    )

@app.get("/")
async def root():
    return {"message": "Smart Scheduler API is running!"}

@app.post("/api/chat/text", response_model=ChatResponse)
async def process_text_input(request: TextInputRequest):
    """Process text input from user"""
    try:
        user_id = request.user_id
        
        # Get or create user session
        if user_id not in user_sessions:
            user_sessions[user_id] = {
                "conversation_state": "greeting",
                "meeting_request": {},
                "user_preferences": {
                    "work_start_hour": 9,
                    "work_end_hour": 17,
                    "timezone": settings.DEFAULT_TIMEZONE
                },
                "conversation_history": []
            }
        
        session = user_sessions[user_id]
        
        # Process with NLP
        response_text, new_state, action_data = await process_user_message(
            request.message, 
            session
        )
        
        # Update session
        session["conversation_state"] = new_state
        session["conversation_history"].append({
            "user": request.message,
            "bot": response_text,
            "timestamp": datetime.now().isoformat()
        })
        
        return ChatResponse(
            response=response_text,
            conversation_state=new_state,
            suggested_slots=action_data.get("suggested_slots", []),
            meeting_info=action_data.get("meeting_info", {}),
            action_required=action_data.get("action_required")
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/chat/speech", response_model=ChatResponse)
async def process_speech_input(audio_file: UploadFile = File(...), user_id: str = "default"):
    """Process speech input from user"""
    try:
        # Convert uploaded audio to text
        audio_data = await audio_file.read()
        text = await speech_to_text(audio_data)
        
        if not text:
            raise HTTPException(status_code=400, detail="Could not transcribe audio")
        
        # Process as text input
        text_request = TextInputRequest(
            message=text,
            user_id=user_id
        )
        
        return await process_text_input(text_request)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def speech_to_text(audio_data: bytes) -> str:
    """Convert audio bytes to text using speech recognition"""
    try:
        recognizer = sr.Recognizer()
        
        # Convert bytes to audio data
        audio_file = io.BytesIO(audio_data)
        
        with sr.AudioFile(audio_file) as source:
            audio = recognizer.record(source)
            text = recognizer.recognize_google(audio)
            return text.lower().strip()
            
    except Exception as e:
        print(f"Speech recognition error: {e}")
        return ""

async def process_user_message(message: str, session: Dict) -> tuple:
    """Process user message and return response, new state, and action data"""
    
    # Extract information using NLP
    context = {
        "current_state": session["conversation_state"],
        "meeting_request": session.get("meeting_request", {}),
        "conversation_history": session["conversation_history"][-3:],
    }
    
    extracted_info = nlp_processor.extract_meeting_info(message, context)
    
    # Update user preferences if mentioned
    working_hours = nlp_processor.extract_working_hours_preference(message)
    if working_hours.get("work_start_hour"):
        session["user_preferences"]["work_start_hour"] = working_hours["work_start_hour"]
    if working_hours.get("work_end_hour"):
        session["user_preferences"]["work_end_hour"] = working_hours["work_end_hour"]
    
    # Handle different conversation states
    current_state = session["conversation_state"]
    action_data = {}
    
    # Check for exit intent
    if nlp_processor.detect_exit_intent(message):
        return "Goodbye! Have a great day!", "complete", {}
    
    # Check for scheduling intent
    if nlp_processor.detect_scheduling_intent(message):
        if extracted_info.get("duration_minutes"):
            session["meeting_request"] = extracted_info
            return "Great! When would you like to schedule this meeting?", "collecting_time_preference", {}
        else:
            return "I'd be happy to help you schedule a meeting! How long should it be?", "collecting_duration", {}
    
    # Handle availability check
    if any(phrase in message.lower() for phrase in [
        "do i have", "what's on", "am i busy", "am i free", "am i available"
    ]):
        return await handle_availability_check(message, session)
    
    # Handle based on current state
    if current_state == "collecting_duration":
        if extracted_info.get("duration_minutes"):
            session["meeting_request"]["duration_minutes"] = extracted_info["duration_minutes"]
            return f"Perfect! {extracted_info['duration_minutes']} minutes it is. When would you like to schedule this meeting?", "collecting_time_preference", {}
        else:
            return "I didn't catch the duration. Could you tell me how long the meeting should be?", "collecting_duration", {}
    
    elif current_state == "collecting_time_preference":
        return await handle_time_preference_collection(message, session, extracted_info)
    
    return "I can help you schedule meetings or check your availability. What would you like to do?", "greeting", {}

async def handle_availability_check(message: str, session: Dict) -> tuple:
    """Handle availability check requests"""
    date_obj = nlp_processor.extract_date(message)
    if date_obj:
        time_prefs = nlp_processor.parse_time_preferences(message)
        
        if time_prefs.get("start_hour") and time_prefs.get("end_hour"):
            preferred_range = {
                "start_hour": time_prefs["start_hour"], 
                "end_hour": time_prefs["end_hour"]
            }
        else:
            preferred_range = {
                "start_hour": session["user_preferences"]["work_start_hour"], 
                "end_hour": session["user_preferences"]["work_end_hour"]
            }

        free_slots = calendar_manager.find_optimal_slots(
            target_date=date_obj,
            duration_minutes=30,
            preferred_time_range=preferred_range,
            max_slots=5,
            user_work_hours=(
                session["user_preferences"]["work_start_hour"], 
                session["user_preferences"]["work_end_hour"]
            )
        )

        if free_slots:
            slots_data = [{"start_time": slot.start_time.isoformat(), 
                          "end_time": slot.end_time.isoformat(),
                          "confidence": slot.confidence} for slot in free_slots]
            slot_strings = "\n".join([f"- {slot}" for slot in free_slots])
            return f"✅ You are free during that time. Suggested slots:\n{slot_strings}", "greeting", {"suggested_slots": slots_data}
        else:
            return f"❌ You're likely busy during that time on {date_obj.strftime('%A, %B %d')}.", "greeting", {}
    else:
        return "I couldn't determine the date. Please try again with something like 'am I free this Friday evening?'", "greeting", {}

async def handle_time_preference_collection(message: str, session: Dict, extracted_info: Dict) -> tuple:
    """Handle time preference collection"""
    meeting_request = session.get("meeting_request", {})
    
    # Parse date if not already set
    if not meeting_request.get("preferred_date"):
        parsed_date = date_parser.parse_complex_date(message)
        if parsed_date:
            meeting_request["preferred_date"] = parsed_date.isoformat()
        else:
            return "I didn't understand the date. Could you try again?", "collecting_time_preference", {}
    
    # Parse time preferences
    time_prefs = nlp_processor.parse_time_preferences(message)
    if time_prefs.get("start_hour") and time_prefs.get("end_hour"):
        time_range = (time_prefs["start_hour"], time_prefs["end_hour"])
    else:
        time_range = (
            session["user_preferences"]["work_start_hour"], 
            session["user_preferences"]["work_end_hour"]
        )
    
    # Find available slots
    target_date = datetime.fromisoformat(meeting_request["preferred_date"]).date()
    slots = calendar_manager.find_optimal_slots(
        target_date=target_date,
        duration_minutes=meeting_request.get("duration_minutes", 30),
        preferred_time_range=time_range,
        max_slots=5,
        user_work_hours=(
            session["user_preferences"]["work_start_hour"], 
            session["user_preferences"]["work_end_hour"]
        )
    )
    
    if not slots:
        return "Sorry, I couldn't find any open slots for that time. Would you like to try another day?", "handling_conflict", {}
    
    # Format response
    slots_data = [{"start_time": slot.start_time.isoformat(), 
                   "end_time": slot.end_time.isoformat(),
                   "confidence": slot.confidence} for slot in slots]
    
    response = f"I found {len(slots)} available time slot{'s' if len(slots) > 1 else ''}:\n"
    for i, slot in enumerate(slots, 1):
        response += f"{i}. {slot}\n"
    response += "Which one works for you?"
    
    return response, "showing_options", {"suggested_slots": slots_data, "meeting_info": meeting_request}

@app.post("/api/schedule/confirm")
async def confirm_meeting(request: ScheduleRequest):
    """Confirm and schedule a meeting"""
    try:
        # Convert to TimeSlot format
        from agent.calendar_integration import TimeSlot
        
        slot = TimeSlot(
            start_time=request.start_time,
            end_time=request.end_time
        )
        
        success = calendar_manager.schedule_meeting(
            slot=slot,
            title=request.title,
            attendees=request.attendees,
            description=request.description
        )
        
        if success:
            return {"status": "success", "message": "Meeting scheduled successfully!"}
        else:
            raise HTTPException(status_code=400, detail="Failed to schedule meeting")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/calendar/events")
async def get_calendar_events(start_date: str, end_date: str):
    """Get calendar events for a date range"""
    try:
        start = datetime.fromisoformat(start_date).date()
        end = datetime.fromisoformat(end_date).date()
        
        events = calendar_manager.get_events_for_date_range(start, end)
        
        events_data = [{
            "id": event.id,
            "title": event.title,
            "start_time": event.start_time.isoformat(),
            "end_time": event.end_time.isoformat(),
            "attendees": event.attendees
        } for event in events]
        
        return {"events": events_data}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/preferences")
async def update_user_preferences(preferences: UserPreferences, user_id: str = "default"):
    """Update user preferences"""
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            "conversation_state": "greeting",
            "meeting_request": {},
            "user_preferences": {},
            "conversation_history": []
        }
    
    user_sessions[user_id]["user_preferences"].update(preferences.dict())
    return {"status": "success", "message": "Preferences updated"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

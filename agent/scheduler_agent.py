from enum import Enum
from typing import Dict, List, Optional
import os
from datetime import datetime, date
from dataclasses import dataclass, asdict
from dateutil import parser

from .nlp_processor import NLPProcessor
from .voice_handler import VoiceHandler
from .calendar_integration import AdvancedCalendarManager, TimeSlot
from utils.date_parser import AdvancedDateParser

class ConversationState(Enum):
    GREETING = "greeting"
    COLLECTING_DURATION = "collecting_duration"
    COLLECTING_TIME_PREFERENCE = "collecting_time_preference" 
    SHOWING_OPTIONS = "showing_options"
    CONFIRMING_SELECTION = "confirming_selection"
    SCHEDULING = "scheduling"
    HANDLING_CONFLICT = "handling_conflict"
    COMPLETE = "complete"

@dataclass
class MeetingRequest:
    duration_minutes: Optional[int] = None
    preferred_date: Optional[date] = None
    time_range: Optional[tuple] = None
    title: Optional[str] = "Scheduled Meeting"
    attendees: List[str] = None
    urgency: str = "medium"
    flexibility: str = "flexible"
    
    def __post_init__(self):
        if self.attendees is None:
            self.attendees = []

class SmartSchedulerAgent:
    def __init__(self, gemini_api_key, google_calendar_service, timezone="UTC"):
        self.nlp = NLPProcessor(api_key=gemini_api_key)
        self.voice = VoiceHandler()
        self.calendar_manager = AdvancedCalendarManager(google_calendar_service, timezone)
        self.date_parser = AdvancedDateParser()

        self.last_suggested_slots = []
        self.last_duration = None
        
        # User preferences (learned dynamically)
        self.user_preferences = {
            "work_start_hour": 9,  # Default, can be updated
            "work_end_hour": 17,   # Default, can be updated
            "timezone": timezone
        }
        
        # Conversation state
        self.state = ConversationState.GREETING
        self.meeting_request = MeetingRequest()
        self.current_options: List[TimeSlot] = []
        self.conversation_history: List[Dict] = []
        
        # Configuration
        self.max_retries = 3
        self.current_retries = 0

    def update_user_preferences(self, user_input: str):
        """Update user preferences based on their input"""
        working_hours = self.nlp.extract_working_hours_preference(user_input)
        
        if working_hours.get("work_start_hour"):
            self.user_preferences["work_start_hour"] = working_hours["work_start_hour"]
            
        if working_hours.get("work_end_hour"):
            self.user_preferences["work_end_hour"] = working_hours["work_end_hour"]
            
        if working_hours.get("timezone"):
            self.user_preferences["timezone"] = working_hours["timezone"]
    
    def extract_date(self, user_input: str):
        """Extract a date from user text using simple parsing"""
        try:
            return parser.parse(user_input, fuzzy=True).date()
        except:
            return None
    
    def start_conversation(self):
        """Main conversation loop"""
        self.voice.speak("Hello! I'm your smart scheduling assistant. I can help you find and schedule meetings. What would you like to do?")
        
        while self.state != ConversationState.COMPLETE:
            try:
                # Listen for user input
                user_input = self.voice.listen()
                
                if not user_input or user_input in ["could not understand", "recognition error", "error"]:
                    self.handle_speech_error()
                    continue
                
                # Handle exit commands using intelligent detection
                if self.nlp.detect_exit_intent(user_input):
                    self.voice.speak("Goodbye! Have a great day!")
                    break

                # ✅ Check if user selected an option
                option_num = self.extract_option_number(user_input)
                if option_num and self.last_suggested_slots:
                    index = option_num - 1
                    if 0 <= index < len(self.last_suggested_slots):
                        selected_slot = self.last_suggested_slots[index]
                        success = self.calendar_manager.schedule_meeting(
                            slot=selected_slot,
                            title="Scheduled via Assistant",
                            attendees=[],
                            description="Auto-booked by assistant"
                        )
                        if success:
                            self.voice.speak(f"✅ Great! Your meeting has been scheduled at {selected_slot.start_time.strftime('%I:%M %p on %A, %B %d')}.")
                        else:
                            self.voice.speak("❌ Sorry, I wasn't able to schedule the meeting.")
                        continue  # Skip further Gemini processing

                # 🧠 Process input using Gemini
                response = self.process_user_input(user_input)

                # Speak the response
                if response:
                    self.voice.speak(response)

                # Log conversation
                self.conversation_history.append({
                    "user": user_input,
                    "bot": response,
                    "state": self.state.value,
                    "timestamp": datetime.now().isoformat()
                })

                # Reset retry counter
                self.current_retries = 0

            except KeyboardInterrupt:
                self.voice.speak("Goodbye!")
                break
            except Exception as e:
                print(f"❌ Error in conversation: {e}")
                self.voice.speak("I encountered an error. Let's try again.")
                self.current_retries += 1

                if self.current_retries >= self.max_retries:
                    self.voice.speak("I'm having trouble understanding. Let's start over.")
                    self.reset_conversation()

    
    def process_user_input(self, user_input: str) -> str:
        """Process user input based on current conversation state"""
        
        # Extract information using NLP
        context = {
            "current_state": self.state.value,
            "meeting_request": asdict(self.meeting_request),
            "conversation_history": self.conversation_history[-3:],  # Last 3 exchanges
        }
        
        extracted_info = self.nlp.extract_meeting_info(user_input, context)
        
        # Update meeting request with extracted info
        self.update_meeting_request(extracted_info)
        
        if any(phrase in user_input.lower() for phrase in [
            "do i have", "what's on", "am i busy", "anything on", "my schedule", "calendar for", "am i free", "am i available"
        ]):
            date = self.nlp.extract_date(user_input)
            if date:
                # Use intelligent time preference parsing
                time_prefs = self.nlp.parse_time_preferences(user_input)
                
                if time_prefs.get("start_hour") and time_prefs.get("end_hour"):
                    preferred_range = {
                        "start_hour": time_prefs["start_hour"], 
                        "end_hour": time_prefs["end_hour"]
                    }
                else:
                    # Default to user's working hours
                    preferred_range = {
                        "start_hour": self.user_preferences["work_start_hour"], 
                        "end_hour": self.user_preferences["work_end_hour"]
                    }

                free_slots = self.calendar_manager.find_optimal_slots(
                    target_date=date,
                    duration_minutes=30,
                    preferred_time_range=preferred_range,
                    max_slots=5,
                    user_work_hours=(self.user_preferences["work_start_hour"], self.user_preferences["work_end_hour"])
                )

                if free_slots:
                    slot_strings = "\n".join([f"- {slot}" for slot in free_slots])
                    return f"✅ You are free during that time. Suggested slots:\n{slot_strings}"
                else:
                    return f"❌ You're likely busy during that time on {date.strftime('%A, %B %d')}."
            else:
                return "I couldn't determine the date. Please try again with something like 'am I free this Friday evening?'"


        # Handle based on current state
        if self.state == ConversationState.GREETING:
            return self.handle_greeting(user_input)
        elif self.state == ConversationState.COLLECTING_DURATION:
            return self.handle_duration_collection(user_input, extracted_info)
        elif self.state == ConversationState.COLLECTING_TIME_PREFERENCE:
            return self.handle_time_preference_collection(user_input, extracted_info)
        elif self.state == ConversationState.SHOWING_OPTIONS:
            return self.handle_option_selection(user_input)
        elif self.state == ConversationState.CONFIRMING_SELECTION:
            return self.handle_confirmation(user_input)
        elif self.state == ConversationState.HANDLING_CONFLICT:
            return self.handle_conflict_resolution(user_input)
        else:
            return "I'm not sure how to help with that. Could you please try again?"
    
    def handle_greeting(self, user_input: str) -> str:
        """Handle initial greeting and meeting request detection"""
        # Update user preferences if mentioned
        self.update_user_preferences(user_input)
        
        # Use intelligent scheduling intent detection
        if self.nlp.detect_scheduling_intent(user_input):
            if self.meeting_request.duration_minutes:
                self.state = ConversationState.COLLECTING_TIME_PREFERENCE
                return f"Great! I see you want to schedule a {self.meeting_request.duration_minutes}-minute meeting. When would you like to meet?"
            else:
                self.state = ConversationState.COLLECTING_DURATION
                return "I'd be happy to help you schedule a meeting! How long should it be?"
        else:
            return "I can help you schedule meetings. Just say something like 'I need to schedule a meeting' or 'Book me a 30-minute call.'"
    
    def handle_duration_collection(self, user_input: str, extracted_info: Dict) -> str:
        """Handle duration collection"""
        if self.meeting_request.duration_minutes:
            self.state = ConversationState.COLLECTING_TIME_PREFERENCE
            return f"Perfect! {self.meeting_request.duration_minutes} minutes it is. When would you like to schedule this meeting?"
        else:
            return "I didn't catch the duration. Could you tell me how long the meeting should be? For example, '30 minutes', '1 hour', or 'a quick 15-minute chat'."
    
    def handle_time_preference_collection(self, user_input: str, extracted_info: Dict) -> str:
        """Handle time preference collection and slot finding"""
        if not self.meeting_request.preferred_date:
            # Try to parse date from user input
            parsed_date = self.date_parser.parse_complex_date(user_input)
            if parsed_date:
                self.meeting_request.preferred_date = parsed_date
            else:
                return "I didn't understand the date. Could you try again? For example, 'tomorrow afternoon', 'next Tuesday', or 'this Friday morning'."

        # Use intelligent time preference parsing
        time_prefs = self.nlp.parse_time_preferences(user_input)
        if time_prefs.get("start_hour") and time_prefs.get("end_hour"):
            self.meeting_request.time_range = (time_prefs["start_hour"], time_prefs["end_hour"])
        elif not self.meeting_request.time_range:
            # Use user's default working hours
            self.meeting_request.time_range = (
                self.user_preferences["work_start_hour"], 
                self.user_preferences["work_end_hour"]
            )

        # Find available slots
        slots = self.calendar_manager.find_optimal_slots(
            target_date=self.meeting_request.preferred_date,
            duration_minutes=self.meeting_request.duration_minutes,
            preferred_time_range=self.meeting_request.time_range,
            max_slots=5,
            user_work_hours=(self.user_preferences["work_start_hour"], self.user_preferences["work_end_hour"])
        )

        if not slots:
            self.state = ConversationState.HANDLING_CONFLICT
            return "Sorry, I couldn't find any open slots for that time. Would you like to try another day?"

        # ✅ Store slots so user can later say "Option 1"
        self.last_suggested_slots = slots
        self.state = ConversationState.SHOWING_OPTIONS

        # Format slot suggestions
        response = f"I found {len(slots)} available time slot{'s' if len(slots) > 1 else ''}:\n"
        for i, slot in enumerate(slots, 1):
            response += f"{i}. {slot}\n"

        response += "Which one works for you? Just say something like 'Option 1' or 'the second one'."
        return response

    
    def find_and_present_options(self) -> str:
        slots = self.calendar_manager.find_optimal_slots(
            self.meeting_request.preferred_date,
            self.meeting_request.duration_minutes,
            self.meeting_request.time_range,
            max_slots=5,
            user_work_hours=(self.user_preferences["work_start_hour"], self.user_preferences["work_end_hour"])
        )

        if slots:
            self.last_suggested_slots = slots
        
            self.current_options = slots
            self.state = ConversationState.SHOWING_OPTIONS

            response = f"I found {len(slots)} available time slots for your {self.meeting_request.duration_minutes}-minute meeting:\n\n"
            for i, slot in enumerate(slots, 1):
                confidence_text = ""
                if slot.confidence > 0.8:
                    confidence_text = " (Great time!)"
                elif slot.confidence < 0.5:
                    confidence_text = " (Workable, but not ideal)"
                response += f"{i}. {slot}{confidence_text}\n"

            response += "\nWhich option works best for you? Just say the number or describe your preference."
            return response
        else:
            self.state = ConversationState.HANDLING_CONFLICT
            return self.handle_no_slots_available()

    
    def handle_no_slots_available(self) -> str:
        """Handle case when no slots are available"""
        # Get alternative suggestions
        alternatives = self.calendar_manager.suggest_alternative_times(
            self.meeting_request.preferred_date,
            self.meeting_request.duration_minutes
        )
        
        if alternatives:
            self.current_options = alternatives
            self.state = ConversationState.SHOWING_OPTIONS
            
            date_str = self.meeting_request.preferred_date.strftime("%A, %B %d")
            response = f"I don't have any {self.meeting_request.duration_minutes}-minute slots available on {date_str}. "
            response += "But I found these alternatives:\n\n"
            
            for i, slot in enumerate(alternatives[:3], 1):
                response += f"{i}. {slot}\n"
            
            response += "\nWould any of these work for you?"
            return response
        else:
            return f"I'm sorry, I couldn't find any {self.meeting_request.duration_minutes}-minute slots in the next week. Would you like to try a shorter meeting duration or a different time range?"
    
    def handle_option_selection(self, user_input: str) -> str:
        """Handle user selecting from presented options"""
        # Try to extract selection number
        selection = self.extract_selection_number(user_input)
        
        if selection and 1 <= selection <= len(self.current_options):
            selected_slot = self.current_options[selection - 1]
            self.meeting_request.preferred_date = selected_slot.start_time.date()
            self.selected_slot = selected_slot
            self.state = ConversationState.CONFIRMING_SELECTION
            return f"Got it! You selected: {selected_slot}. Should I go ahead and schedule this meeting?"
        else:
            return "I'm not sure which option you selected. Please say the number of the option you'd like, like 'Option 1' or 'the second one'."
        
    def extract_selection_number(self, text: str) -> Optional[int]:
        """Extracts a number from user input indicating a slot selection"""
        import re
        match = re.search(r'\b(\d+)\b', text)
        if match:
            return int(match.group(1))
        return None

    def handle_confirmation(self, user_input: str) -> str:
        """Handle user confirming meeting selection"""
        if "yes" in user_input.lower():
            self.state = ConversationState.SCHEDULING
            success = self.calendar_manager.schedule_meeting(
                self.selected_slot,
                self.meeting_request.title,
                self.meeting_request.attendees
            )
            if success:
                self.state = ConversationState.COMPLETE
                return "Your meeting has been successfully scheduled. Anything else I can help you with?"
            else:
                return "I tried to schedule the meeting but ran into an issue. Would you like to try another time?"
        elif "no" in user_input.lower():
            self.state = ConversationState.SHOWING_OPTIONS
            return "No problem. Please select another available time slot."
        else:
            return "Please confirm if you'd like to schedule this meeting now. You can say 'yes' or 'no'."

    def handle_conflict_resolution(self, user_input: str) -> str:
        # 👇 Reprocess user's follow-up input
        extracted_info = self.nlp.extract_meeting_info(user_input, {
            "current_state": self.state.value,
            "meeting_request": asdict(self.meeting_request),
            "conversation_history": self.conversation_history[-3:]
        })
        
        self.update_meeting_request(extracted_info)

        if self.meeting_request.duration_minutes and self.meeting_request.preferred_date:
            # Try again to find slots
            return self.find_and_present_options()

        return "Would you like to try a shorter meeting or a different time range?"

        
    def extract_selection_number(self, text: str) -> Optional[int]:
        """Extracts a number from user input indicating a slot selection"""
        import re
        match = re.search(r'\b(\d+)\b', text)
        if match:
            return int(match.group(1))
        return None
    
    def reset_conversation(self):
        """Reset the agent to start a new conversation"""
        self.state = ConversationState.GREETING
        self.meeting_request = MeetingRequest()
        self.current_options = []
        self.selected_slot = None
        self.conversation_history = []
        self.current_retries = 0
        self.voice.speak("Let's start fresh. What can I help you schedule today?")

    def update_meeting_request(self, extracted_info: dict):
        """Update meeting_request object with values extracted from NLP"""
        if not extracted_info:
            return

        self.meeting_request.duration_minutes = extracted_info.get("duration_minutes") or self.meeting_request.duration_minutes
        self.meeting_request.preferred_date = (
            datetime.strptime(extracted_info["preferred_date"], "%Y-%m-%d").date()
            if extracted_info.get("preferred_date") else self.meeting_request.preferred_date
        )
        self.meeting_request.time_range = extracted_info.get("time_range") or self.meeting_request.time_range
        self.meeting_request.flexibility = extracted_info.get("flexibility") or self.meeting_request.flexibility
        self.meeting_request.urgency = extracted_info.get("urgency") or self.meeting_request.urgency
    def handle_speech_error(self):
        """Handle speech recognition failures gracefully"""
        self.current_retries += 1
        if self.current_retries >= self.max_retries:
            self.voice.speak("I'm having trouble understanding. Let's start over.")
            self.reset_conversation()
        else:
            self.voice.speak("Sorry, I didn't catch that. Could you please repeat?")

    def extract_option_number(self, user_input: str) -> Optional[int]:
        """Extracts option number from user speech like 'one', 'option 2', etc."""
        word_to_num = {
            "one": 1, "first": 1, "1": 1,
            "two": 2, "second": 2, "2": 2,
            "three": 3, "third": 3, "3": 3,
            "four": 4, "fourth": 4, "4": 4,
            "five": 5, "fifth": 5, "5": 5,
        }
        user_input = user_input.lower()
        for key, val in word_to_num.items():
            if key in user_input:
                return val
        return None
    



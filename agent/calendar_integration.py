import datetime
from datetime import datetime, time,timedelta
from typing import List, Optional, Dict, Tuple
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dataclasses import dataclass
import pytz

@dataclass
class CalendarEvent:
    id: str
    title: str
    start_time: datetime
    end_time: datetime
    attendees: List[str] = None
    
    def __post_init__(self):
        if self.attendees is None:
            self.attendees = []

@dataclass
class TimeSlot:
    start_time: datetime
    end_time: datetime
    confidence: float = 1.0  # How confident we are this slot is good
    
    def __str__(self):
        return f"{self.start_time.strftime('%A, %B %d at %I:%M %p')} - {self.end_time.strftime('%I:%M %p')}"
    
    def duration_minutes(self) -> int:
        return int((self.end_time - self.start_time).total_seconds() / 60)

class AdvancedCalendarManager:
    def __init__(self, service, timezone: str = "America/New_York"):
        self.service = service
        self.timezone = pytz.timezone(timezone)
        
    def get_events_for_date_range(self, start_date: datetime.date, 
                                 end_date: datetime.date) -> List[CalendarEvent]:
        """Get all events in a date range"""
        start_datetime = datetime.combine(start_date, time.min)
        end_datetime = datetime.combine(end_date, time.max)
        start_utc = self.timezone.localize(start_datetime).astimezone(pytz.UTC)
        end_utc = self.timezone.localize(end_datetime).astimezone(pytz.UTC)
        
        try:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=start_utc.isoformat(),
                timeMax=end_utc.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = []
            for event in events_result.get('items', []):
                start_str = event['start'].get('dateTime', event['start'].get('date'))
                end_str = event['end'].get('dateTime', event['end'].get('date'))
                
                # Parse times
                start_time = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                
                # Convert to local timezone
                if start_time.tzinfo:
                    start_time = start_time.astimezone(self.timezone)
                    end_time = end_time.astimezone(self.timezone)
                
                events.append(CalendarEvent(
                    id=event['id'],
                    title=event.get('summary', 'Untitled Event'),
                    start_time=start_time,
                    end_time=end_time
                ))
            
            return events
            
        except HttpError as error:
            print(f"Calendar API error: {error}")
            return []
    
    def find_optimal_slots(self, target_date: datetime.date, duration_minutes: int,
                          preferred_time_range: Optional[Tuple[int, int]] = None,
                          max_slots: int = 5, user_work_hours: Tuple[int, int] = (9, 17)) -> List[TimeSlot]:
        """Find optimal meeting slots with confidence scoring"""
        
        # Use provided user work hours or defaults
        work_start, work_end = user_work_hours
        
        # Get existing events
        events = self.get_events_for_date_range(target_date, target_date)
        
        # Create time slots
        slots = []

        if preferred_time_range:
            try:
                if isinstance(preferred_time_range, dict):
                    work_start = float(preferred_time_range.get("start_hour", work_start))
                    work_end = float(preferred_time_range.get("end_hour", work_end))
                elif isinstance(preferred_time_range, tuple):
                    work_start, work_end = map(float, preferred_time_range)
                else:
                    work_start, work_end = user_work_hours

            except Exception as e:
                print("⚠️ Failed to parse preferred_time_range:", e)
                work_start, work_end = user_work_hours
        else:
            work_start, work_end = user_work_hours

        start_hour = int(work_start)
        start_minute = int((work_start - start_hour) * 60)

        end_hour = int(work_end)
        end_minute = int((work_end - end_hour) * 60)

        current_time = datetime.combine(target_date, time(start_hour, start_minute))
        current_time = self.timezone.localize(current_time)

        end_of_day = datetime.combine(target_date, time(end_hour, end_minute))
        end_of_day = self.timezone.localize(end_of_day)

        
        
        # current_time = datetime.combine(target_date, time(work_start, 0))
        # current_time = self.timezone.localize(current_time)

        # end_of_day = datetime.combine(target_date, time(work_end, 0))
        # end_of_day = self.timezone.localize(end_of_day)
        
        # Sort events by start time
        events.sort(key=lambda e: e.start_time)
        
        for event in events:
            # Check if there's space before this event
            if (event.start_time - current_time).total_seconds() >= duration_minutes * 60:
                slot_end = current_time + timedelta(minutes=duration_minutes)
                if slot_end <= event.start_time:
                    confidence = self._calculate_slot_confidence(current_time, duration_minutes, events)
                    slots.append(TimeSlot(current_time, slot_end, confidence))
            
            # Move current time to after this event
            current_time = max(current_time, event.end_time)
        
        # Check for slot after last event
        if (end_of_day - current_time).total_seconds() >= duration_minutes * 60:
            slot_end = current_time + timedelta(minutes=duration_minutes)
            if slot_end <= end_of_day:
                confidence = self._calculate_slot_confidence(current_time, duration_minutes, events)
                slots.append(TimeSlot(current_time, slot_end, confidence))
        
        # Sort by confidence and return top slots
        slots.sort(key=lambda s: s.confidence, reverse=True)
        return slots[:max_slots]
    
    def _calculate_slot_confidence(self, start_time: datetime, 
                                  duration_minutes: int, events: List[CalendarEvent]) -> float:
        """Calculate confidence score for a time slot"""
        confidence = 1.0
        
        # Prefer certain times of day
        hour = start_time.hour
        if 10 <= hour <= 11:  # Morning sweet spot
            confidence += 0.2
        elif 14 <= hour <= 15:  # Afternoon sweet spot
            confidence += 0.1
        elif hour < 9 or hour > 17:  # Outside normal hours
            confidence -= 0.3
        
        # Avoid right after lunch
        if 12 <= hour <= 13:
            confidence -= 0.1
        
        # Avoid too close to existing meetings
        slot_end = start_time + timedelta(minutes=duration_minutes)
        for event in events:
            # Check if too close to existing events
            time_before = (start_time - event.end_time).total_seconds() / 60
            time_after = (event.start_time - slot_end).total_seconds() / 60
            
            if 0 < time_before < 15:  # Less than 15 min after an event
                confidence -= 0.2
            if 0 < time_after < 15:  # Less than 15 min before an event
                confidence -= 0.2
        
        return max(0.1, confidence)  # Minimum confidence of 0.1
    
    def schedule_meeting(self, slot: TimeSlot, title: str, 
                        attendees: List[str] = None, 
                        description: str = "") -> bool:
        """Schedule a meeting in the calendar"""
        
        event_body = {
            'summary': title,
            'description': description,
            'start': {
                'dateTime': slot.start_time.isoformat(),
                'timeZone': str(self.timezone),
            },
            'end': {
                'dateTime': slot.end_time.isoformat(),
                'timeZone': str(self.timezone),
            },
        }
        
        if attendees:
            event_body['attendees'] = [{'email': email} for email in attendees]
        
        try:
            event = self.service.events().insert(
                calendarId='primary',
                body=event_body,
                sendUpdates='all' if attendees else 'none'
            ).execute()
            
            print(f"✅ Meeting scheduled: {event.get('htmlLink')}")
            return True
            
        except HttpError as error:
            print(f"❌ Failed to schedule meeting: {error}")
            return False
    
    def suggest_alternative_times(self, original_date: datetime.date, 
                                 duration_minutes: int) -> List[TimeSlot]:
        """Suggest alternative times when preferred slot is unavailable"""
        alternatives = []
        
        # Try next few days
        for days_ahead in range(1, 8):  # Next 7 days
            alt_date = original_date + timedelta(days=days_ahead)
            
            # Skip weekends (unless original was weekend)
            if alt_date.weekday() >= 5 and original_date.weekday() < 5:
                continue
            
            slots = self.find_optimal_slots(alt_date, duration_minutes, max_slots=5)
            alternatives.extend(slots)
            
            if len(alternatives) >= 5:  # Return up to 5 alternatives
                break
        
        return alternatives[:5]
    
    def view_events_on(self, day):
        service = self.service
        utc = pytz.UTC
        start_of_day = datetime.combine(day, datetime.min.time()).astimezone(utc)
        end_of_day = datetime.combine(day, datetime.max.time()).astimezone(utc)

        events_result = service.events().list(
            calendarId="primary",
            timeMin=start_of_day.isoformat(),
            timeMax=end_of_day.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = events_result.get("items", [])

        if not events:
            return f"You have no events scheduled on {day.strftime('%A, %d %B')}."
        
        response = f"You have {len(events)} event(s) on {day.strftime('%A, %d %B')}:\n"
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get("summary", "No title")
            response += f"- {summary} at {start}\n"
        return response
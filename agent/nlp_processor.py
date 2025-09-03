# agent/nlp_processor.py
import google.generativeai as genai
from datetime import date
from datetime import datetime
import json
from dateutil import parser
import re

class NLPProcessor:
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model_name="gemini-1.5-flash")

    def detect_exit_intent(self, user_input: str) -> bool:
        """Use Gemini to detect if user wants to end conversation"""
        prompt = f"""
        Analyze if the user wants to end the conversation. Return only "true" or "false".
        
        User input: "{user_input}"
        
        Examples of exit intent: goodbye, thanks that's all, I'm done, see you later, exit, quit, stop, bye
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip().lower() == "true"
        except:
            return False

    def detect_scheduling_intent(self, user_input: str) -> bool:
        """Use Gemini to detect if user wants to schedule something"""
        prompt = f"""
        Analyze if the user wants to schedule a meeting, appointment, or event. Return only "true" or "false".
        
        User input: "{user_input}"
        
        Examples: schedule a meeting, book appointment, plan a call, set up a meeting, need to meet
        """
        try:
            response = self.model.generate_content(prompt)
            return response.text.strip().lower() == "true"
        except:
            return False

    def parse_time_preferences(self, user_input: str) -> dict:
        """Use Gemini to intelligently parse time preferences"""
        prompt = f"""
        Extract time preferences from user input. Return JSON with:
        - start_hour (number, 24-hour format)
        - end_hour (number, 24-hour format)
        - confidence (0.0-1.0 how confident you are)
        
        User input: "{user_input}"
        Current time: {datetime.now().strftime('%Y-%m-%d %H:%M')}
        
        Examples:
        - "morning" → {{"start_hour": 8, "end_hour": 12, "confidence": 0.9}}
        - "late afternoon" → {{"start_hour": 15, "end_hour": 18, "confidence": 0.8}}
        - "early evening" → {{"start_hour": 17, "end_hour": 20, "confidence": 0.8}}
        - "lunch time" → {{"start_hour": 11, "end_hour": 14, "confidence": 0.9}}
        
        If no time preference found, return null for start_hour and end_hour.
        """
        try:
            response = self.model.generate_content(prompt)
            content = response.text.strip()
            cleaned = re.sub(r"^```json|```$", "", content, flags=re.MULTILINE).strip()
            return json.loads(cleaned)
        except:
            return {"start_hour": None, "end_hour": None, "confidence": 0.0}

    def extract_working_hours_preference(self, user_input: str) -> dict:
        """Extract user's preferred working hours"""
        prompt = f"""
        Extract the user's working hours preference. Return JSON with:
        - work_start_hour (number, 24-hour format)
        - work_end_hour (number, 24-hour format)
        - timezone (string, if mentioned)
        
        User input: "{user_input}"
        
        Examples:
        - "I work 9 to 5" → {{"work_start_hour": 9, "work_end_hour": 17}}
        - "my hours are 8am to 6pm" → {{"work_start_hour": 8, "work_end_hour": 18}}
        - "I'm available from 10 to 4" → {{"work_start_hour": 10, "work_end_hour": 16}}
        
        If no working hours mentioned, return null values.
        """
        try:
            response = self.model.generate_content(prompt)
            content = response.text.strip()
            cleaned = re.sub(r"^```json|```$", "", content, flags=re.MULTILINE).strip()
            return json.loads(cleaned)
        except:
            return {"work_start_hour": None, "work_end_hour": None, "timezone": None}

    def extract_meeting_info(self, user_input: str, context: dict) -> dict:
        system_prompt = """You are a smart assistant that extracts meeting info from natural language. 
    Return data in JSON with:
    - duration_minutes (int or null)
    - preferred_date (YYYY-MM-DD or null)
    - time_range (dict with start_hour and end_hour or null)
    - urgency (high, medium, low)
    - flexibility (flexible, somewhat_flexible, rigid)
    - meeting_type (brief, standard, long, all-day)
    """

        full_prompt = f"""{system_prompt}

    User input: "{user_input}"
    Today's date: {date.today().isoformat()}
    Context: {json.dumps(context, default=str)}
    """

        try:
            response = self.model.generate_content(full_prompt)
            # print("Gemini raw response:", response)

            # Safely extract content
            content = getattr(response, "text", None)
            if not content:
                try:
                    content = response.candidates[0].content.parts[0].text
                except Exception:
                    raise ValueError("Gemini returned no usable content.")

            # ✅ Clean markdown-wrapped JSON
            cleaned = re.sub(r"^```json|```$", "", content.strip(), flags=re.MULTILINE).strip()

            # Parse and return as dict
            return json.loads(cleaned)

        except Exception as e:
            print("Gemini error:", e)
            return {"error": "LLM failure"}




    def generate_response(self, state: str, context: dict, user_input: str) -> str:
        try:
            prompt = f"""You are a friendly scheduling assistant. 

State: {state}
Context: {json.dumps(context, default=str)}
User said: "{user_input}"

Reply helpfully and clearly based on the context.
"""
            response = self.model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            print("Gemini response error:", e)
            return "Sorry, I had trouble generating a response."
        

    def extract_date(self, user_input: str):
        """Extracts a date from user input using fuzzy parsing"""
        try:
            return parser.parse(user_input, fuzzy=True).date()
        except:
            return None


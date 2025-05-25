from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from typing import List, Dict, Optional
import json
import logging
from datetime import datetime, timedelta
import asyncio
from dateutil import parser as date_parser
import re
import os

from voice_manager import VoiceManager
from scheduler import AppointmentScheduler, SlotScheduler
from ai_core import AdaptiveDataKernel, ModelContextProtocol

app = FastAPI(title="AI-Powered Voice-Based Appointment Booking System")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create static directory if it doesn't exist
os.makedirs("static", exist_ok=True)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize templates
templates = Jinja2Templates(directory="templates")

# Initialize components
voice_manager = VoiceManager()
scheduler = AppointmentScheduler()
adk = AdaptiveDataKernel()
mcp = ModelContextProtocol()
slot_scheduler = SlotScheduler()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Store user context
user_context = {}

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.user_contexts: Dict[WebSocket, Dict] = {}

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        self.user_contexts[websocket] = {
            "pending_appointment": None,
            "awaiting_email": False,
            "doctor_name": None
        }

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        if websocket in self.user_contexts:
            del self.user_contexts[websocket]

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_json({
            "type": "response",
            "text": message
        })

manager = ConnectionManager()

class NLPProcessor:
    @staticmethod
    def extract_date_time(text: str) -> datetime:
        """Extract date and time from natural language text."""
        today = datetime.now()
        
        # Try to find time patterns
        time_pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?'
        time_match = re.search(time_pattern, text)
        
        # Try to find date patterns
        date_patterns = {
            'today': today.date(),
            'tomorrow': (today + timedelta(days=1)).date(),
            'day after tomorrow': (today + timedelta(days=2)).date(),
            'next monday': (today + timedelta(days=(7 - today.weekday() + 0) % 7)).date(),
            'next tuesday': (today + timedelta(days=(7 - today.weekday() + 1) % 7)).date(),
            'next wednesday': (today + timedelta(days=(7 - today.weekday() + 2) % 7)).date(),
            'next thursday': (today + timedelta(days=(7 - today.weekday() + 3) % 7)).date(),
            'next friday': (today + timedelta(days=(7 - today.weekday() + 4) % 7)).date(),
        }
        
        extracted_date = today.date()
        for pattern, date in date_patterns.items():
            if pattern in text.lower():
                extracted_date = date
                break
        
        extracted_time = today.time()
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
            period = time_match.group(3).lower() if time_match.group(3) else None
            
            if period == 'pm' and hour < 12:
                hour += 12
            elif period == 'am' and hour == 12:
                hour = 0
                
            extracted_time = datetime.min.time().replace(hour=hour, minute=minute)
        
        return datetime.combine(extracted_date, extracted_time)

    @staticmethod
    def extract_doctor_name(text: str) -> str:
        """Extract doctor name from text."""
        doctor_pattern = r'(?:dr\.?|doctor)\s+([a-z]+)'
        match = re.search(doctor_pattern, text.lower())
        return match.group(1).title() if match else "Smith"  # Default to Dr. Smith

    @staticmethod
    def process_intent(text: str) -> Dict:
        """Process the intent of the user's speech."""
        text = text.lower()
        
        # Extract doctor name and datetime
        doctor_name = NLPProcessor.extract_doctor_name(text)
        appointment_time = NLPProcessor.extract_date_time(text)
        
        # Basic intent classification
        if any(word in text for word in ['book', 'schedule', 'make', 'new', 'need']):
            return {
                'intent': 'schedule',
                'doctor': doctor_name,
                'datetime': appointment_time,
                'urgency': 3 if 'urgent' in text else 1
            }
        elif any(word in text for word in ['cancel', 'delete', 'remove']):
            return {
                'intent': 'cancel',
                'doctor': doctor_name
            }
        elif any(word in text for word in ['list', 'show', 'what', 'available']):
            return {
                'intent': 'list_appointments',
                'doctor': doctor_name,
                'datetime': appointment_time
            }
        else:
            return {'intent': 'unknown'}

async def process_voice_input(text: str, websocket: WebSocket):
    """Process voice input and generate appropriate response."""
    try:
        intent_data = NLPProcessor.process_intent(text)
        response = ""
        
        if intent_data['intent'] == 'schedule':
            next_slot = scheduler.get_next_available_slot(
                intent_data['datetime'],
                intent_data['urgency']
            )
            if next_slot:
                # Get success probability from ADK
                success_prob = adk.predict_success_probability(
                    next_slot,
                    intent_data['urgency']
                )
                
                appointment = scheduler.schedule_appointment(
                    patient_name="Voice User",
                    datetime_slot=next_slot,
                    reason=f"Appointment with Dr. {intent_data['doctor']}",
                    urgency=intent_data['urgency']
                )
                
                if appointment:
                    response = (
                        f"I've scheduled your appointment with Dr. {intent_data['doctor']} "
                        f"for {next_slot.strftime('%B %d at %I:%M %p')}. "
                        f"The success probability for this slot is {success_prob:.0%}."
                    )
                else:
                    response = "Sorry, I couldn't schedule the appointment. Please try again."
            else:
                response = "No available slots found in the next two weeks."
                
        elif intent_data['intent'] == 'list_appointments':
            appointments = scheduler.get_appointments_for_date(intent_data['datetime'])
            if appointments:
                response = f"Appointments with Dr. {intent_data['doctor']} on {intent_data['datetime'].strftime('%B %d')}: "
                for appt in appointments:
                    response += f"\n- {appt.patient_name} at {appt.datetime.strftime('%I:%M %p')}"
            else:
                response = f"There are no appointments scheduled with Dr. {intent_data['doctor']} on {intent_data['datetime'].strftime('%B %d')}."
                
        elif intent_data['intent'] == 'cancel':
            response = "Please provide the appointment ID you wish to cancel."
            
        else:
            response = (
                "I'm sorry, I didn't understand that request. "
                "You can say things like:\n"
                "- 'I need to book an appointment with Dr. Smith'\n"
                "- 'Show me available appointments for next Monday'\n"
                "- 'Cancel my appointment'"
            )
        
        # Send response through websocket
        await websocket.send_json({
            "type": "response",
            "text": response,
            "intent": intent_data
        })
        
        # Convert response to speech
        voice_manager.speak(response)
        
    except Exception as e:
        logger.error(f"Error processing voice input: {e}")
        await websocket.send_json({
            "type": "error",
            "text": "Sorry, there was an error processing your request."
        })

@app.get("/", response_class=HTMLResponse)
def welcome(request: Request):
    return templates.TemplateResponse("landing.html", {"request": request})

@app.get("/app", response_class=HTMLResponse)
async def get(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def parse_time_range(phrase):
    # Returns (start_time, end_time) in HH:MM format for a phrase
    if 'morning' in phrase:
        return ('09:00', '12:00')
    if 'afternoon' in phrase:
        return ('12:30', '16:00')
    if 'evening' in phrase:
        return ('16:30', '19:30')
    return (None, None)

def extract_date(text):
    # Try to extract a date using dateutil.parser
    try:
        # Remove time words to avoid confusion
        text_clean = re.sub(r'\b(\d{1,2}(:\d{2})?\s*(am|pm))\b', '', text, flags=re.IGNORECASE)
        dt = date_parser.parse(text_clean, fuzzy=True, default=datetime.now())
        return dt.strftime('%Y-%m-%d')
    except Exception:
        return datetime.now().strftime('%Y-%m-%d')

def extract_time(text):
    # Try to extract a time and return in 12-hour format with AM/PM
    time_match = re.search(r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?', text, re.IGNORECASE)
    if time_match:
        hour = int(time_match.group(1))
        minute = int(time_match.group(2)) if time_match.group(2) else 0
        period = time_match.group(3)
        if period:
            period = period.lower()
        if period == 'pm' and hour < 12:
            hour += 12
        elif period == 'am' and hour == 12:
            hour = 0
        # Always return 12-hour format with AM/PM
        t12 = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").strftime("%I:%M %p")
        return t12
    return None

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            user_text = data["text"].lower()
            logger.info(f"Received user input: {user_text}")
            context = manager.user_contexts[websocket]
            try:
                # Extract date and time
                date_str = extract_date(user_text)
                time_str = extract_time(user_text)
                start = end = None
                for phrase in ['morning', 'afternoon', 'evening']:
                    if phrase in user_text:
                        start, end = parse_time_range(phrase)
                        break

                # Improved phone extraction (allow dashes/spaces)
                phone_match = re.search(r'(\d{3}[-\s]?\d{3}[-\s]?\d{4})', user_text)
                if phone_match:
                    patient_contact = re.sub(r'[-\s]', '', phone_match.group(1))
                else:
                    patient_contact = None
                name_match = re.search(r'my name is ([a-z ]+)', user_text)
                patient_name = name_match.group(1).strip().title() if name_match else None

                # Context memory for date and time
                if any(word in user_text for word in ["book", "appointment", "schedule"]):
                    # If both date and time/range are present, proceed
                    if (time_str or (start and end)) and date_str:
                        context["pending_booking"] = {"date": date_str, "time": time_str, "start": start, "end": end}
                    elif date_str:
                        context["pending_booking"] = {"date": date_str}
                        response = "Please specify the time for your appointment (e.g., 9:00 AM or 'morning')."
                        await manager.send_message(response, websocket)
                        voice_manager.speak(response)
                        continue
                    elif time_str or (start and end):
                        context["pending_booking"] = {"time": time_str, "start": start, "end": end}
                        response = "Please specify the date for your appointment (e.g., 25 May)."
                        await manager.send_message(response, websocket)
                        voice_manager.speak(response)
                        continue
                # If user provides just a date or just a time in a follow-up message
                elif "pending_booking" in context:
                    pending = context["pending_booking"]
                    # If missing date, try to extract
                    if "date" not in pending and date_str:
                        pending["date"] = date_str
                    # If missing time, try to extract
                    if "time" not in pending and time_str:
                        pending["time"] = time_str
                    if "start" not in pending and start:
                        pending["start"] = start
                    if "end" not in pending and end:
                        pending["end"] = end
                # If we have both date and time/range, proceed to booking
                if "pending_booking" in context and (context["pending_booking"].get("time") or (context["pending_booking"].get("start") and context["pending_booking"].get("end"))) and context["pending_booking"].get("date"):
                    booking = context.pop("pending_booking")
                    date_str = booking["date"]
                    time_str = booking.get("time")
                    start = booking.get("start")
                    end = booking.get("end")
                    slots = slot_scheduler.get_slots_for_day(date_str)
                    slot = None
                    if time_str:
                        # time_str is already in 12-hour format
                        slot = next((s for s in slots if s[2] == time_str), None)
                        if slot and slot[3] == "Available":
                            context["pending_slot"] = {"date": date_str, "time": time_str}
                            if not patient_name or not patient_contact:
                                response = f"Please provide your name and 10-digit phone number to confirm the booking for {time_str}."
                            else:
                                booking_number = slot_scheduler.book_slot(date_str, time_str, patient_name, patient_contact)
                                response = f"Your appointment is confirmed! Booking Number: {booking_number}. Thank you for visiting."
                                context.clear()
                        elif slot and slot[3] == "Booked":
                            idx = slots.index(slot)
                            suggestions = []
                            if idx > 0 and slots[idx-1][3] == "Available":
                                suggestions.append(slots[idx-1][2])
                            if idx < len(slots)-1 and slots[idx+1][3] == "Available":
                                suggestions.append(slots[idx+1][2])
                            if suggestions:
                                response = f"Sorry, the slot on {date_str} at {time_str} is already booked. Available nearby slots: {', '.join(suggestions)}. Please reply with your preferred time."
                                context["suggested_slots"] = {"date": date_str, "options": suggestions}
                            else:
                                response = f"Sorry, the slot on {date_str} at {time_str} is already booked and no nearby slots are available. Please choose another time or day."
                        else:
                            response = f"Sorry, there is no slot available on {date_str} at {time_str}. Please choose another time."
                    elif start and end:
                        slot = next((s for s in slots if start <= s[2] <= end and s[3] == "Available"), None)
                        if slot:
                            context["pending_slot"] = {"date": date_str, "time": slot[2]}
                            if not patient_name or not patient_contact:
                                response = f"The first available slot in the {phrase} is {slot[2]}. Please provide your name and 10-digit phone number to confirm the booking."
                            else:
                                booking_number = slot_scheduler.book_slot(date_str, slot[2], patient_name, patient_contact)
                                response = f"Your appointment is confirmed for {slot[2]}! Booking Number: {booking_number}. Thank you for visiting."
                                context.clear()
                        else:
                            response = f"Sorry, there are no available slots in the {phrase} on {date_str}. Please choose another time or day."
                    else:
                        response = "Please specify the time for your appointment (e.g., 9:00 AM or 'morning')."
                    await manager.send_message(response, websocket)
                    voice_manager.speak(response)
                    continue
                # If user is providing name/phone after being prompted
                if "pending_slot" in context and (patient_name and patient_contact):
                    slot_info = context.pop("pending_slot")
                    booking_number = slot_scheduler.book_slot(slot_info["date"], slot_info["time"], patient_name, patient_contact)
                    response = f"Your appointment is confirmed! Booking Number: {booking_number}. Thank you for visiting."
                    context.clear()
                    await manager.send_message(response, websocket)
                    voice_manager.speak(response)
                    continue
                # If user is selecting a suggested slot
                elif "suggested_slots" in context:
                    slot_opts = context["suggested_slots"]
                    selected_time = None
                    for opt in slot_opts["options"]:
                        if opt in user_text:
                            selected_time = opt
                            break
                    if selected_time:
                        context.pop("suggested_slots")
                        context["pending_slot"] = {"date": slot_opts["date"], "time": selected_time}
                        response = f"Great! Please provide your name and 10-digit phone number to confirm the booking for {selected_time}."
                    else:
                        response = f"Please reply with one of the available times: {', '.join(slot_opts['options'])}."
                else:
                    response = "I can help you book an appointment. Please say, for example, 'Book my appointment with Doctor Smith on 25 May at 9:00 AM' or 'Book for 25th May morning'."
                await manager.send_message(response, websocket)
                voice_manager.speak(response)
            except Exception as e:
                logger.error(f"Error processing request: {e}")
                error_msg = "I apologize, but I encountered an error processing your request. Please try again."
                await manager.send_message(error_msg, websocket)
                voice_manager.speak(error_msg)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info("Client disconnected")

@app.get("/bookings")
def get_bookings():
    # Return all slots with a booking number (i.e., booked slots)
    bookings = []
    import sqlite3
    conn = sqlite3.connect("appointments.db")
    cursor = conn.cursor()
    cursor.execute("SELECT booking_number, date, time, patient_name, patient_contact, status FROM slots WHERE booking_number IS NOT NULL ORDER BY date, time")
    for row in cursor.fetchall():
        bookings.append({
            "booking_number": row[0],
            "date": row[1],
            "time": row[2],
            "name": row[3],
            "phone": row[4],
            "status": row[5]
        })
    conn.close()
    return JSONResponse(content=bookings)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import os
from dataclasses import dataclass, asdict
from dateutil.parser import parse
import logging
from ai_core import AdaptiveDataKernel, ModelContextProtocol
import sqlite3

@dataclass
class Appointment:
    id: str
    patient_name: str
    datetime: datetime
    duration: int  # in minutes
    status: str  # 'scheduled', 'cancelled', 'completed'
    reason: str
    urgency: int  # 1-5, where 5 is most urgent
    request_time: datetime = None
    is_preferred_time: bool = False

class AppointmentScheduler:
    def __init__(self):
        self.appointments: Dict[str, Appointment] = {}
        self.working_hours = {
            'start': 9,  # 9 AM
            'end': 17,   # 5 PM
            'slot_duration': 30  # minutes
        }
        self.logger = logging.getLogger(__name__)
        self.adk = AdaptiveDataKernel()
        self.mcp = ModelContextProtocol()
        self.db_path = "appointments.db"
        self._init_db()
        self._load_appointments()

    def _init_db(self):
        """Initialize the SQLite database."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create appointments table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS appointments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    patient_name TEXT NOT NULL,
                    email TEXT,
                    datetime_slot TIMESTAMP NOT NULL,
                    doctor TEXT NOT NULL,
                    reason TEXT,
                    urgency INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create slots table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS slots (
                    booking_number TEXT,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    status TEXT NOT NULL,
                    patient_name TEXT,
                    patient_contact TEXT
                )
            ''')
            
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Database initialization error: {e}")

    def _load_appointments(self):
        """Load appointments from storage."""
        try:
            if os.path.exists('appointments.json'):
                with open('appointments.json', 'r') as f:
                    data = json.load(f)
                    for appt_data in data:
                        appt_data['datetime'] = parse(appt_data['datetime'])
                        if 'request_time' in appt_data and appt_data['request_time']:
                            appt_data['request_time'] = parse(appt_data['request_time'])
                        self.appointments[appt_data['id']] = Appointment(**appt_data)
        except Exception as e:
            self.logger.error(f"Error loading appointments: {e}")

    def _save_appointments(self):
        """Save appointments to storage."""
        try:
            data = []
            for appointment in self.appointments.values():
                appt_dict = asdict(appointment)
                appt_dict['datetime'] = appt_dict['datetime'].isoformat()
                if appt_dict['request_time']:
                    appt_dict['request_time'] = appt_dict['request_time'].isoformat()
                data.append(appt_dict)
            
            with open('appointments.json', 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            self.logger.error(f"Error saving appointments: {e}")

    def get_available_slots(self, date: datetime) -> List[datetime]:
        """Get available appointment slots for a given date."""
        slots = []
        start_time = datetime.combine(date.date(), 
                                    datetime.min.time().replace(hour=self.working_hours['start']))
        end_time = datetime.combine(date.date(), 
                                  datetime.min.time().replace(hour=self.working_hours['end']))
        
        current_slot = start_time
        while current_slot < end_time:
            if not self._is_slot_taken(current_slot):
                # Get success probability from ADK
                success_prob = self.adk.predict_success_probability(current_slot, 1)
                if success_prob >= 0.5:  # Only include slots with good success probability
                    slots.append(current_slot)
            current_slot += timedelta(minutes=self.working_hours['slot_duration'])
        
        return slots

    def _is_slot_taken(self, datetime_slot: datetime) -> bool:
        """Check if a time slot is already taken."""
        for appointment in self.appointments.values():
            if appointment.status == 'cancelled':
                continue
            
            appt_end = appointment.datetime + timedelta(minutes=appointment.duration)
            slot_end = datetime_slot + timedelta(minutes=self.working_hours['slot_duration'])
            
            if (datetime_slot <= appointment.datetime < slot_end or
                datetime_slot < appt_end <= slot_end):
                return True
        return False

    def schedule_appointment(self, patient_name: str, datetime_slot: datetime, 
                           doctor: str, reason: str, urgency: int = 1, 
                           email: str = None) -> Optional[Appointment]:
        """Schedule a new appointment."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if slot is still available
            cursor.execute('''
                SELECT COUNT(*) FROM appointments 
                WHERE datetime_slot = ?
            ''', (datetime_slot,))
            
            if cursor.fetchone()[0] > 0:
                conn.close()
                return None
            
            # Insert new appointment
            cursor.execute('''
                INSERT INTO appointments (patient_name, email, datetime_slot, doctor, reason, urgency)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (patient_name, email, datetime_slot, doctor, reason, urgency))
            
            appointment_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return Appointment(
                id=str(appointment_id),
                patient_name=patient_name,
                datetime=datetime_slot,
                duration=self.working_hours['slot_duration'],
                status='scheduled',
                reason=reason,
                urgency=urgency,
                request_time=datetime.now(),
                is_preferred_time=False
            )
        except Exception as e:
            self.logger.error(f"Error scheduling appointment: {e}")
            return None

    def cancel_appointment(self, appointment_id: str) -> bool:
        """Cancel an existing appointment."""
        try:
            if appointment_id in self.appointments:
                appointment = self.appointments[appointment_id]
                appointment.status = 'cancelled'
                
                # Learn from cancellation
                self.adk.learn_from_appointment(
                    appointment.datetime,
                    False,
                    appointment.urgency
                )
                
                self._save_appointments()
                return True
            return False
        except Exception as e:
            self.logger.error(f"Error cancelling appointment: {e}")
            return False

    def get_next_available_slot(self, preferred_date: datetime, urgency: int) -> Optional[datetime]:
        """Get the next available appointment slot."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Business hours: 9 AM to 5 PM
            start_hour = 9
            end_hour = 17
            slot_duration = 30  # minutes
            
            # Check slots for the next 14 days
            for day_offset in range(14):
                check_date = preferred_date + timedelta(days=day_offset)
                
                # Skip weekends
                if check_date.weekday() >= 5:
                    continue
                
                # Check each time slot
                for hour in range(start_hour, end_hour):
                    for minute in [0, 30]:
                        slot_time = check_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                        
                        # Don't check past slots
                        if slot_time < datetime.now():
                            continue
                        
                        # Check if slot is available
                        cursor.execute('''
                            SELECT COUNT(*) FROM appointments 
                            WHERE datetime_slot = ?
                        ''', (slot_time,))
                        
                        if cursor.fetchone()[0] == 0:
                            conn.close()
                            return slot_time
            
            conn.close()
            return None
        except Exception as e:
            self.logger.error(f"Error getting available slot: {e}")
            return None

    def get_appointment_by_id(self, appointment_id: str) -> Optional[Appointment]:
        """Retrieve an appointment by its ID."""
        return self.appointments.get(appointment_id)

    def get_appointments_for_date(self, date: datetime) -> List[Appointment]:
        """Get all appointments for a specific date."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day + timedelta(days=1)
            
            cursor.execute('''
                SELECT id, patient_name, email, datetime_slot, doctor, reason, urgency
                FROM appointments 
                WHERE datetime_slot >= ? AND datetime_slot < ?
                ORDER BY datetime_slot
            ''', (start_of_day, end_of_day))
            
            appointments = []
            for row in cursor.fetchall():
                appointments.append(Appointment(
                    id=str(row[0]),
                    patient_name=row[1],
                    email=row[2],
                    datetime=datetime.fromisoformat(row[3]),
                    duration=self.working_hours['slot_duration'],
                    status='scheduled',
                    reason=row[5],
                    urgency=row[6]
                ))
            
            conn.close()
            return appointments
        except Exception as e:
            self.logger.error(f"Error getting appointments: {e}")
            return []

class SlotScheduler:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.db_path = "appointments.db"
        self._init_db()

    def _init_db(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS slots (
                    booking_number TEXT,
                    date TEXT NOT NULL,
                    time TEXT NOT NULL,
                    status TEXT NOT NULL,
                    patient_name TEXT,
                    patient_contact TEXT
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            self.logger.error(f"Database initialization error: {e}")

    def populate_slots_for_day(self, day: str):
        """Populate slots for a specific day (YYYY-MM-DD) if not already present."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        start_time = datetime.strptime(day + ' 09:00', '%Y-%m-%d %H:%M')
        end_time = datetime.strptime(day + ' 19:30', '%Y-%m-%d %H:%M')
        slot_time = start_time
        while slot_time <= end_time:
            time_str = slot_time.strftime('%H:%M')
            # Check if slot exists
            cursor.execute('SELECT COUNT(*) FROM slots WHERE date=? AND time=?', (day, time_str))
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO slots (booking_number, date, time, status, patient_name, patient_contact)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (None, day, time_str, 'Available', None, None))
            slot_time += timedelta(minutes=30)
        conn.commit()
        conn.close()

    def book_slot(self, day: str, time: str, patient_name: str, patient_contact: str):
        """Book a slot by updating its status and patient info."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        # Find the next booking number
        cursor.execute('SELECT COUNT(*) FROM slots WHERE status="Booked"')
        booking_count = cursor.fetchone()[0] + 1
        booking_number = f"BOOK-{booking_count}"
        cursor.execute('''
            UPDATE slots SET booking_number=?, status=?, patient_name=?, patient_contact=?
            WHERE date=? AND time=? AND status="Available"
        ''', (booking_number, 'Booked', patient_name, patient_contact, day, time))
        conn.commit()
        conn.close()
        return booking_number

    def get_slots_for_day(self, day: str):
        """Return all slots for a given day."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM slots WHERE date=? ORDER BY time', (day,))
        slots = cursor.fetchall()
        conn.close()
        return slots

# Example usage to pre-populate 2025-05-25:
if __name__ == "__main__":
    scheduler = SlotScheduler()
    scheduler.populate_slots_for_day('2025-05-25')
    # Book the specified slots
    scheduler.book_slot('2025-05-25', '10:00', 'Alice', '1234567890')
    scheduler.book_slot('2025-05-25', '12:30', 'Bob', '2345678901')
    scheduler.book_slot('2025-05-25', '14:30', 'Charlie', '3456789012')
    scheduler.book_slot('2025-05-25', '17:00', 'Diana', '4567890123')
    scheduler.book_slot('2025-05-25', '18:30', 'Eve', '5678901234')
    # Convert all slot times to 12-hour format with AM/PM
    conn = sqlite3.connect('appointments.db')
    cursor = conn.cursor()
    cursor.execute("SELECT rowid, time FROM slots")
    updates = []
    for rowid, time24 in cursor.fetchall():
        t12 = datetime.strptime(time24, '%H:%M').strftime('%I:%M %p')
        updates.append((t12, rowid))
    cursor.executemany("UPDATE slots SET time=? WHERE rowid=?", updates)
    conn.commit()
    conn.close()
    # Print all slots for the day
    for slot in scheduler.get_slots_for_day('2025-05-25'):
        print(slot) 
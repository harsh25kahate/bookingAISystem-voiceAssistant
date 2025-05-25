# AI Voice Appointment Booking System

A modern, voice-enabled appointment booking system for a single doctor, with a beautiful UI, slot-based scheduling, and a user-friendly landing page.

## Features
- **Landing Page:** Animated, light-themed intro with logo, app name, description, and a Continue button.
- **Voice & Text Chat:** Book appointments using natural language, either by voice or text.
- **Slot-Based Scheduling:** All slots are managed in a SQLite database, shown in 12-hour format (e.g., 03:00 PM).
- **Popup Notification:** When a booking is confirmed, a green popup appears at the top.
- **Show My Bookings:** Button to view all bookings in a table (Booking No., Date, Time, Name, Phone, Status).
- **No Email Required:** All email logic has been removed for simplicity.
- **Modern UI:** Responsive, clean, and easy to use.

## How to Run
1. **Install dependencies:**
   ```sh
   pip install -r requirements.txt
   ```
2. **Start the server:**
   ```sh
   uvicorn main:app --reload
   ```
3. **Open your browser:**
   - Go to [http://localhost:8000/](http://localhost:8000/) to see the landing page.
   - Click **Continue** to access the main booking/chat app.

## Usage
- **Book an appointment:**
  - Type or speak: "Book my appointment with Doctor Smith on 25th May at 9:00 AM" or "Book for 25th May morning".
  - The bot will prompt for any missing info (date, time, name, phone).
  - When confirmed, you'll see a popup and get a booking number.
- **View bookings:**
  - Click the "Show My Bookings" button at the bottom to see all bookings in a table.

## Customization
- **Logo:** Place your logo as `logo.jpg` in the `static/` folder.
- **Landing Page:** Edit `templates/landing.html` for the intro page.
- **Chat UI:** Edit `templates/index.html` for chat and booking UI.
- **Database Logic:** Edit `scheduler.py` for slot and booking logic.

## Requirements
See `requirements.txt` for all dependencies.

---
**Enjoy your modern, voice-powered appointment booking system!** 

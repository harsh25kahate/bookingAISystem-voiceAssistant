# Voice-Interactive AI Appointment Booking System

An intelligent voice-based appointment scheduling system for doctor appointments using Python and FastAPI. The system enables natural voice interactions for booking, rescheduling, and managing appointments.

## Features

- Real-time Speech-to-Text and Text-to-Speech capabilities
- Natural language understanding for appointment scheduling
- Intelligent slot management and conflict resolution
- Voice-based notifications and confirmations
- Continuous conversation loop without manual triggers
- Smart scheduling based on availability and preferences

## Setup Instructions

1. Install Python 3.8 or higher
2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. For Windows users, you might need to install PyAudio separately:
   ```bash
   pip install pipwin
   pipwin install pyaudio
   ```

## Running the Application

1. Start the FastAPI server:
   ```bash
   uvicorn main:app --reload
   ```
2. The application will start on http://localhost:8000

## Usage

1. Launch the application
2. Allow microphone access when prompted
3. Start speaking naturally to book appointments
4. The system will respond via voice and continue listening automatically

## System Requirements

- Python 3.8+
- Microphone
- Speakers or headphones
- Internet connection for speech recognition 
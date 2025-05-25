import speech_recognition as sr
import pyttsx3
import threading
import queue
import logging
import time
from typing import Optional, Callable

class VoiceManager:
    def __init__(self):
        # Initialize speech recognizer
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.energy_threshold = 4000
        
        # Initialize text-to-speech engine
        try:
            self.engine = pyttsx3.init()
            self.engine.setProperty('rate', 150)  # Slightly slower for better clarity
            self.engine.setProperty('volume', 0.9)  # 90% volume
            
            # Get available voices and set a good default
            voices = self.engine.getProperty('voices')
            if voices:
                self.engine.setProperty('voice', voices[0].id)
        except Exception as e:
            self.logger.error(f"Error initializing text-to-speech: {e}")
            self.engine = None
        
        # Set up audio queues
        self.speech_queue = queue.Queue()
        self.is_listening = False
        self.callback = None
        self.last_speech_time = 0
        
        # Configure logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)

    def start_listening(self, callback: Callable[[str], None]):
        """Start continuous listening in a separate thread."""
        if self.is_listening:
            self.stop_listening()  # Stop any existing listening session
            time.sleep(0.5)  # Give it time to clean up
            
        self.callback = callback
        self.is_listening = True
        threading.Thread(target=self._listen_loop, daemon=True).start()
        self.logger.info("Started listening for voice input")

    def stop_listening(self):
        """Stop the continuous listening loop."""
        self.is_listening = False
        self.logger.info("Stopped listening for voice input")

    def _listen_loop(self):
        """Continuous listening loop that runs in a separate thread."""
        retry_count = 0
        max_retries = 3
        
        while self.is_listening:
            try:
                with sr.Microphone() as source:
                    # Adjust for ambient noise more frequently
                    if time.time() - self.last_speech_time > 10:  # Adjust every 10 seconds of silence
                        self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    
                    try:
                        audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                        text = self.recognizer.recognize_google(audio)
                        
                        if text.strip():
                            self.logger.info(f"Recognized: {text}")
                            self.last_speech_time = time.time()
                            retry_count = 0  # Reset retry count on successful recognition
                            
                            if self.callback:
                                self.callback(text)
                    except sr.WaitTimeoutError:
                        continue
                    except sr.UnknownValueError:
                        self.logger.info("Could not understand audio")
                        retry_count += 1
                    except sr.RequestError as e:
                        self.logger.error(f"Could not request results; {e}")
                        retry_count += 1
                        
                    # If we've had too many errors, take a break
                    if retry_count >= max_retries:
                        self.logger.warning("Too many recognition errors, pausing briefly")
                        time.sleep(2)
                        retry_count = 0
                        
            except Exception as e:
                self.logger.error(f"Error in listen loop: {e}")
                time.sleep(1)  # Prevent rapid retries on persistent errors

    def speak(self, text: str):
        """Convert text to speech and play it."""
        if not text:
            return
            
        try:
            if not self.engine:
                self.logger.error("Text-to-speech engine not initialized")
                return
                
            self.speech_queue.put(text)
            threading.Thread(target=self._process_speech_queue, daemon=True).start()
        except Exception as e:
            self.logger.error(f"Error in speak: {e}")

    def _process_speech_queue(self):
        """Process queued speech items."""
        while not self.speech_queue.empty():
            text = self.speech_queue.get()
            try:
                if self.engine:
                    self.engine.say(text)
                    self.engine.runAndWait()
                    time.sleep(0.5)  # Small pause between speeches
            except Exception as e:
                self.logger.error(f"Error in speech processing: {e}")
            finally:
                self.speech_queue.task_done()

    def get_last_speech(self) -> Optional[str]:
        """Get the last recognized speech if available."""
        try:
            with sr.Microphone() as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                self.logger.info("Listening for speech...")
                audio = self.recognizer.listen(source, timeout=5, phrase_time_limit=10)
                text = self.recognizer.recognize_google(audio)
                self.logger.info(f"Recognized: {text}")
                return text
        except Exception as e:
            self.logger.error(f"Error getting last speech: {e}")
            return None 
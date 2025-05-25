import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import os
from dotenv import load_dotenv
import logging
from typing import Optional

# Load environment variables
load_dotenv()

class EmailManager:
    def __init__(self):
        self.smtp_server = "smtp.gmail.com"
        self.smtp_port = 587
        self.sender_email = os.getenv("APPOINTMENT_EMAIL")
        self.sender_password = os.getenv("APPOINTMENT_PASSWORD")
        self.logger = logging.getLogger(__name__)
        
        if not self.sender_email or not self.sender_password:
            self.logger.warning("Email credentials not found in .env file")

    def send_confirmation_email(self, 
                              recipient_email: str, 
                              appointment_datetime: datetime,
                              doctor_name: str) -> bool:
        """Send appointment confirmation email."""
        try:
            # Validate email configuration
            if not self.sender_email or not self.sender_password:
                self.logger.error("Email credentials not configured")
                return False

            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = recipient_email
            msg['Subject'] = f"Appointment Confirmation with Dr. {doctor_name}"

            body = f"""
            Dear Patient,

            Your appointment has been confirmed for:
            Date: {appointment_datetime.strftime('%B %d, %Y')}
            Time: {appointment_datetime.strftime('%I:%M %p')}
            Doctor: Dr. {doctor_name}

            Please arrive 10 minutes before your scheduled time.
            If you need to cancel or reschedule, please contact us at least 24 hours in advance.

            Best regards,
            AI Appointment System
            """

            msg.attach(MIMEText(body, 'plain'))

            # Create SMTP session
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)

            self.logger.info(f"Confirmation email sent to {recipient_email}")
            return True

        except smtplib.SMTPAuthenticationError:
            self.logger.error("SMTP Authentication failed. Check your email and app password.")
            return False
        except smtplib.SMTPException as e:
            self.logger.error(f"SMTP error occurred: {str(e)}")
            return False
        except Exception as e:
            self.logger.error(f"Error sending confirmation email: {str(e)}")
            return False

    def test_email_connection(self) -> bool:
        """Test the email connection and authentication."""
        try:
            if not self.sender_email or not self.sender_password:
                self.logger.error("Email credentials not configured")
                return False

            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                self.logger.info("Email connection test successful")
                return True

        except smtplib.SMTPAuthenticationError:
            self.logger.error("SMTP Authentication failed. Check your email and app password.")
            return False
        except Exception as e:
            self.logger.error(f"Error testing email connection: {str(e)}")
            return False 
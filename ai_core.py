import numpy as np
from sklearn.ensemble import RandomForestClassifier
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, List, Optional
import logging
import json
import os

class AdaptiveDataKernel:
    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=100)
        self.features = ['hour', 'day_of_week', 'month', 'urgency']
        self.logger = logging.getLogger(__name__)
        self.training_data = {
            'features': [],
            'labels': []
        }
        self._load_training_data()

    def _load_training_data(self):
        """Load historical training data."""
        try:
            if os.path.exists('training_data.json'):
                with open('training_data.json', 'r') as f:
                    data = json.load(f)
                    self.training_data = data
                    if self.training_data['features']:
                        self.model.fit(
                            np.array(self.training_data['features']),
                            np.array(self.training_data['labels'])
                        )
        except Exception as e:
            self.logger.error(f"Error loading training data: {e}")

    def _save_training_data(self):
        """Save training data to disk."""
        try:
            with open('training_data.json', 'w') as f:
                json.dump(self.training_data, f)
        except Exception as e:
            self.logger.error(f"Error saving training data: {e}")

    def extract_features(self, dt: datetime, urgency: int) -> List[float]:
        """Extract features from appointment datetime."""
        return [
            dt.hour,
            dt.weekday(),
            dt.month,
            urgency
        ]

    def learn_from_appointment(self, appointment_datetime: datetime, 
                             success: bool, urgency: int):
        """Learn from appointment outcomes."""
        try:
            features = self.extract_features(appointment_datetime, urgency)
            self.training_data['features'].append(features)
            self.training_data['labels'].append(1 if success else 0)
            
            if len(self.training_data['features']) > 1:
                self.model.fit(
                    np.array(self.training_data['features']),
                    np.array(self.training_data['labels'])
                )
                self._save_training_data()
        except Exception as e:
            self.logger.error(f"Error learning from appointment: {e}")

    def predict_success_probability(self, dt: datetime, urgency: int) -> float:
        """Predict the success probability of an appointment."""
        try:
            if len(self.training_data['features']) > 1:
                features = np.array([self.extract_features(dt, urgency)])
                return float(self.model.predict_proba(features)[0][1])
            return 0.5  # Default probability when no training data
        except Exception as e:
            self.logger.error(f"Error predicting success probability: {e}")
            return 0.5

class ModelContextProtocol:
    def __init__(self):
        self.priority_weights = {
            'urgency': 0.4,
            'success_probability': 0.3,
            'waiting_time': 0.2,
            'preferred_time': 0.1
        }
        self.logger = logging.getLogger(__name__)

    def calculate_priority_score(self, 
                               urgency: int,
                               success_probability: float,
                               waiting_time: timedelta,
                               is_preferred_time: bool) -> float:
        """Calculate priority score for an appointment."""
        try:
            normalized_urgency = urgency / 5.0  # Normalize to 0-1
            normalized_waiting = min(waiting_time.total_seconds() / (7 * 24 * 3600), 1.0)  # Cap at 1 week
            
            score = (
                self.priority_weights['urgency'] * normalized_urgency +
                self.priority_weights['success_probability'] * success_probability +
                self.priority_weights['waiting_time'] * normalized_waiting +
                self.priority_weights['preferred_time'] * (1.0 if is_preferred_time else 0.0)
            )
            
            return score
        except Exception as e:
            self.logger.error(f"Error calculating priority score: {e}")
            return 0.0

    def sort_appointments_by_priority(self, appointments: List[Dict]) -> List[Dict]:
        """Sort appointments by their priority scores."""
        try:
            for appt in appointments:
                waiting_time = datetime.now() - appt['request_time']
                score = self.calculate_priority_score(
                    appt['urgency'],
                    appt['success_probability'],
                    waiting_time,
                    appt['is_preferred_time']
                )
                appt['priority_score'] = score
            
            return sorted(appointments, key=lambda x: x['priority_score'], reverse=True)
        except Exception as e:
            self.logger.error(f"Error sorting appointments: {e}")
            return appointments 
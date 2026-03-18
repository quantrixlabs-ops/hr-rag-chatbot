"""
Locust load testing script for the HR RAG Chatbot FastAPI backend.

Run with:
    locust -f scripts/load_test.py --host=http://localhost:8000
"""

import random
import uuid

from locust import HttpUser, between, task


HR_QUERIES = [
    "How many vacation days do I get?",
    "What health plans are available?",
    "What is the leave policy?",
    "How do I submit an expense report?",
    "What is the remote work policy?",
    "How does the 401k matching work?",
    "What are the company holidays this year?",
    "How do I request parental leave?",
    "What is the dress code policy?",
    "How do I enroll in benefits?",
]

PASSWORD = "LoadTest@12345!!"


class HRChatbotUser(HttpUser):
    """Simulates a user who registers, logs in, and interacts with the chatbot."""

    wait_time = between(1, 5)

    def on_start(self):
        """Register a new user and log in to obtain an access token."""
        self.user_id = uuid.uuid4().hex[:12]
        self.username = f"loaduser_{self.user_id}"
        self.access_token = None
        self.session_id = str(uuid.uuid4())

        # Register
        register_payload = {
            "username": self.username,
            "password": PASSWORD,
            "full_name": f"Load Tester {self.user_id}",
            "email": f"{self.username}@loadtest.local",
            "phone": "5550000000",
            "role": "employee",
        }
        with self.client.post(
            "/auth/register",
            json=register_payload,
            catch_response=True,
            name="/auth/register",
        ) as resp:
            if resp.status_code not in (200, 201):
                resp.failure(f"Registration failed: {resp.status_code} {resp.text}")

        # Login
        login_payload = {
            "username": self.username,
            "password": PASSWORD,
        }
        with self.client.post(
            "/auth/login",
            json=login_payload,
            catch_response=True,
            name="/auth/login",
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                self.access_token = data.get("access_token")
                if not self.access_token:
                    resp.failure("Login succeeded but no access_token in response")
            else:
                resp.failure(f"Login failed: {resp.status_code} {resp.text}")

    @property
    def auth_headers(self):
        if self.access_token:
            return {"Authorization": f"Bearer {self.access_token}"}
        return {}

    @task(5)
    def chat_query(self):
        """Send a random HR question to the chatbot."""
        payload = {
            "query": random.choice(HR_QUERIES),
            "session_id": self.session_id,
            "include_sources": True,
        }
        with self.client.post(
            "/chat/query",
            json=payload,
            headers=self.auth_headers,
            catch_response=True,
            name="/chat/query",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            elif resp.status_code == 401:
                resp.failure("Unauthorized — token may be invalid")
            else:
                resp.failure(f"Chat query failed: {resp.status_code}")

    @task(2)
    def get_sessions(self):
        """Retrieve the user's chat sessions."""
        with self.client.get(
            "/chat/sessions",
            headers=self.auth_headers,
            catch_response=True,
            name="/chat/sessions",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Get sessions failed: {resp.status_code}")

    @task(1)
    def get_documents(self):
        """Retrieve the documents list."""
        with self.client.get(
            "/documents",
            headers=self.auth_headers,
            catch_response=True,
            name="/documents",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Get documents failed: {resp.status_code}")

    @task(2)
    def health_check(self):
        """Hit the public health endpoint."""
        with self.client.get(
            "/health",
            catch_response=True,
            name="/health",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Health check failed: {resp.status_code}")

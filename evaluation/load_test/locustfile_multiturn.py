import uuid
import random
import json
from locust import HttpUser, between, task

with open("translate.json", encoding="utf-8") as f:
            conversations = json.load(f)

conversation_ids = list(range(1, 26))


class ConversationUser(HttpUser):
    host = "http://127.0.0.1:8080"

    # Simulasikan user membaca jawaban sebelum bertanya lagi
    wait_time = between(5, 15)

    def on_start(self):
        # Satu session untuk satu percakapan
        self.conversation_id = None

        self.questions = random.choice(conversations)["questions"]
        # self.questions = conversations["questions"]  # Gunakan percakapan pertama untuk konsistensi

        self.index = 0

    @task
    def chat(self):

        # Percakapan selesai
        if self.index >= len(self.questions):
            self.stop()
            return

        payload = {
            "conversation_id": self.conversation_id,
            "question": self.questions[self.index],
        }

        with self.client.post(
            "/chat/",
            json=payload,
            name="POST /chat/ Multi Turn",
            timeout=120,
            catch_response=True,
        ) as response:

            if response.status_code != 200:
                response.failure(
                    f"HTTP {response.status_code}: {response.text[:300]}"
                )
                return

            try:
                data = response.json()
            except ValueError:
                response.failure("Response is not valid JSON")
                return

            if not data.get("answer"):
                response.failure("Empty answer")
                return

            self.conversation_id = data.get("conversation_id")

            if self.conversation_id is None:
                response.failure("Missing conversation_id")
                return

            # Berhasil
            response.success()

        # Pindah ke pertanyaan berikutnya
        self.index += 1
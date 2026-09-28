#!/home/kidlucrid/.gemini/.venv/bin/python3

import sys
import logging
from google import genai

# Suppress develope warnings from the SDK
logging.getLogger().setLevel(logging.ERROR)

client = genai.Client()
chat = client.chats.create(model="gemini-3.8-flash")

# List to manage chat history.
chat_history = []
prompt = ""

while prompt != "quit":
    prompt = input()
    if prompt == "quit":
        break
    else:
        current_chat = chat_history.append(prompt)
        response = client.models.generate_content(
            model="gemini-3.8-flash", contents = chat_history
)
        print("\n" + response.text + "\n")

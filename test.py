#!/home/kidlucrid/.gemini/.venv/bin/python3

import sys
import logging
from google import genai

# Suppress develope warnings from the SDK
logging.getLogger().setLevel(logging.ERROR)

client = genai.Client()
chat = client.chats.create(model="gemini-3.8-flash")

# prompt = input()

# if not () != "quit":
    #do something
    

# Read the custom message from the terminal arguments
if len(sys.argv) > 1:
    # Joins all the words you type into one string
    prompt = " ".join(sys.argv[1:])
else:
    # Fallback if you forget to type a message
    prompt = "Say Hello!"

response = chat.send_message(prompt)

print("\n" + response.text + "\n")

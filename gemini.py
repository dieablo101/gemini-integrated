#!/home/kidlucrid/.gemini/.venv/bin/python3

import sys
import logging

from pathlib import Path
from google import genai
from google.genai import types

# Custom Modules
from modules import logger

# Suppress develope warnings from the SDK
logging.getLogger().setLevel(logging.ERROR)

client = genai.Client()

# GLOBAL VARIABLES
chat_history = []
prompt = ""

config = types.GenerateContentConfig(
    # 1. Behavior and Persona
    system_instruction="You are a terminal assistant in Ubuntu CLI you work alongside a computer programmer, using emacs, terminator terminal.",
    # 2. Creativity and Length
    temperature=0.1,  # Low temperature for factual consistency
    # 3. Output Format
    # 4. Optional Stop Triggers
    stop_sequences=["END_OF_TRANSLATION"],
    # 5. Adding Tools (e.g., Google Search)
    tools=[{"google_search": {}}],
)

while prompt != "quit":
    prompt = input()
    if prompt == "quit":
        break
    # Save chat to log file command
    elif prompt == "save-chat":
        logger.log_chat(chat_history)

    else:
        current_chat = chat_history.append(prompt)
        response = client.models.generate_content(
            model="gemini-3.8-flash", contents = chat_history, config = config,
)
        current_chat = chat_history.append(response.text)
        if response.text == None:
            print("Response was NoneType")
        else:
            print("\n" + response.text + "\n")


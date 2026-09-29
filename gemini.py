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
    system_instruction="You are a terminal assistant in Ubuntu CLI you work alongside a computer programmer, using emacs, terminator terminal. Keep answers as short as possible, keep a personality though (one of friendship and companion and co worker)",
    # 2. Creativity and Length
    temperature=0.1,  # Low temperature for factual consistency
    # 3. Output Format
    # 4. Optional Stop Triggers
    stop_sequences=["END_OF_TRANSLATION"],
    # 5. Adding Tools (e.g., Google Search)
    tools=[{"google_search": {}}],
)


while prompt != "quit":
    try:
        print("try")
    except KeyboardInterrupt as e:
        print(f"System exit attempted")
    prompt = input()
    if prompt == "quit":
        break
    elif prompt == "save-chat":
        # Save chat to log file command
        logger.log_chat(chat_history)
    else:
        # Update "Chat History {chat_history}"
        current_chat = chat_history.append(prompt)
        response = client.models.generate_content(
            model="gemini-3.8-flash", contents = chat_history, config = config,
)
        # Update "Chat History {chat_history} with AI response"
        current_chat = chat_history.append(response.text)
        if response.text == None:
            print("Response was NoneType")
        else:
            print("\n" + response.text + "\n")


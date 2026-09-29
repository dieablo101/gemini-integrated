#!/home/kidlucrid/.gemini/.venv/bin/python3

import sys
import logging
import getpass

# from pathlib import Path
from google import genai
from google.genai import types

# Syntax highlighting
from rich.console import Console
from rich.syntax import Syntax

# Custom Modules
from modules import logger

# Suppress developer warnings from the SDK
logging.getLogger().setLevel(logging.ERROR)

client = genai.Client()

# GLOBAL VARIABLES
username = getpass.getuser()
user = username + ": "
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
        # Wait for user input
        prompt = user + input("\033[31m " + user + "\033[0m ")
        # Update "Chat History {chat_history}"
        current_chat = chat_history.append(prompt)
        # "response" from genai is a blocking call (waits)
        response = client.models.generate_content(
            model="gemini-3.8-flash", contents = chat_history, config = config,
        )
        # Update "Chat History {chat_history} with AI response"
        current_chat = chat_history.append(response.text)
        # Save updated conversation chat to log file auto
        logger.log_chat(chat_history)
        # No response from server error handling
        if response.text == None:
            print("Response was NoneType")
        else:
            print("\033[34m gemini:\033[0m " + response.text)
            # print(chat_history)

    ### USED FOR PROGRAM ESCAPE ###
    except KeyboardInterrupt as e:
        print(f" : Exiting program 'Geminis'")
        sys.exit(1)

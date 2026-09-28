#!/home/kidlucrid/.gemini/.venv/bin/python3

import sys
import logging
import os

# get username for logging
import getpass

from pathlib import Path
from google import genai
from google.genai import types

# Suppress develope warnings from the SDK
logging.getLogger().setLevel(logging.ERROR)

client = genai.Client()

# GLOBAL VARIABLES
chat_history = []
prompt = ""
username = getpass.getuser()

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
    elif prompt == "save-chat":
        # used to add username to the chat for export / save
        user = f"{username} : "
        formatted = [
            f"{user}{msg}" if i % 2 == 0 else msg
            for i, msg in enumerate(chat_history)
        ]


        # Log chat to a file and save it.
        title = chat_history[0].split()[:6]
        title = "".join(str(n) for n in title).lower()
        title += ".convo"
        tempstring = "\n\n".join(formatted)
        if os.path.isfile(title):
            with open(title, "w", encoding="utf-8") as f:
               f.write(tempstring)
               print("ran open file")
        elif not os.path.isfile(title):
            with open(title, "w", encoding="utf-8") as f:
                f.write(tempstring)
                print("file not existed, created and wrote chat_history")

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


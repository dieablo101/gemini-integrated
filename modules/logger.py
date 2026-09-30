# get username for logging
import os
import secrets
# import getpass
from pathlib import Path

# username = getpass.getuser()
token = None

def log_chat(chat_history):

    global token

    # Formatted chat history.
    formatted_chat = "\n\n".join(chat_history)

    # Generate a session token for the initial current session
    if token:
        token = token
        print(token)
    elif token == None:
        token = secrets.token_hex(8)
        print(token)

    # create filename off of beginning text
    file_name = token + ".convo"

    # We need the directory of the logged in user to create file path
    user_directory = os.path.join(os.path.expanduser("~"), ".gemini_chats/")
    user_file_name = os.path.join(user_directory, file_name)
    
    # Checks if folder exists on user for file save directory
    # if not, it creates it for us.
    Path(user_directory).mkdir(parents=True, exist_ok=True)

    with open(user_file_name, "w", encoding="utf-8") as f:
       f.write(str(formatted_chat))
       # print("Saved chat to /chats folder")

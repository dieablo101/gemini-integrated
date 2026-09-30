# get username for logging
import os
import getpass

username = getpass.getuser()

def log_chat(chat_history):

    # Formatted chat history.
    formatted_chat = "\n\n".join(chat_history)

    # create filename off of beginning text
    file_name = "".join(chat_history[0].split()[:3]).lower() + ".convo"

    ### CHECK: if file named save_title exists
    #   --- if so, add a number or a hash

    # We need the directory of this program to create file_path
    user_directory = os.path.join(os.path.expanduser("~"), ".gemini_chats/", file_name)

    #print(user_directory)

    with open(user_directory, "w", encoding="utf-8") as f:
       f.write(str(formatted_chat))
       # print("Saved chat to /chats folder")

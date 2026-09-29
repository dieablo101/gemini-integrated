# get username for logging
import os
import getpass

username = getpass.getuser()

def log_chat(chat_history):
    # Formatting for file contents
    user = f"{username} : "
    formatted = [
        f"{user}{msg}" if i % 2 == 0 else msg
        for i, msg in enumerate(chat_history)
    ]
    # Formatted chat history.
    formatted_chat = "\n\n".join(formatted)

    # Log chat to a file and save it.
    # Grab first 3 words of chat history first dataset
    save_title = chat_history[0].split()[:3]
    #  print(save_title)
    save_title = "".join(str(n) for n in save_title).lower()
    # print(save_title)
    save_title += ".convo"
    # print(save_title)

    # We need the directory of this program to create file_path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir)
    file_path_second = os.path.join(file_path, "../chats/")
    file_path_complete = os.path.join(file_path_second, save_title)

    with open(file_path_complete, "w", encoding="utf-8") as f:
       f.write(formatted_chat)
       print("re-wrote file")

import colorama
import asyncio
import yaml
import json
import requests
import os
import random
import time
from websockets.sync.client import connect
import threading
from datetime import datetime

colorama.init()

config = yaml.load(open('config.yml', "r"), Loader=yaml.FullLoader)['default']
user_id = ''
headers = {
    'Authorization': config['token'],
    'Content-Type': 'application/json'
}

def getWorkHours():
    global start_time, end_time

    if config['work_hours']['enabled']:
        # Set the times
        start_time = datetime.now().replace(hour=config['work_hours']['start_time'], minute=random.randint(0, 59))
        end_time = datetime.now().replace(hour=config['work_hours']['end_time'] - 1, minute=random.randint(0, 59))

async def checkWorkTime():
    global offline
    offline = False
    while True:
        now = datetime.now()
        # if the time now is not work time
        if now.hour < start_time.hour or now.hour == start_time.hour and now.minute < start_time.minute or now.hour > end_time.hour or now.hour == end_time.hour and now.minute > end_time.minute:
            if not offline:
                print(f' > Going offline until {start_time.hour}:{start_time.minute}')
                offline = True
            time.sleep(300)  # Check again after 5 minutes
        else:
            break

async def getChannelInfo(channel_id):
    channel = requests.get(f'https://discord.com/api/v9/channels/{channel_id}', headers=headers).json()
    guild = requests.get(f'https://discord.com/api/v9/guilds/{channel["guild_id"]}', headers=headers).json()

    channel_name = channel['name'] if 'name' in channel else channel_id
    guild_name = guild['name'] if 'name' in guild else 'Unknown guild'

    return channel_name, guild_name

async def checkDoublePosting(channel_id, number):
    response = requests.get(f'https://discord.com/api/v9/channels/{channel_id}/messages?limit={number}', headers=headers).json()
    for i in range(number):
        if response and response[i] and 'author' in response[i] and response[i]['author']['id'] == user_id:
            return False
    return True

async def changeStatus():
    print(f' > Changing status to {config["change_status"]["status"]}...')
    global ws
    while True:
        try:
            ws = connect('wss://gateway.discord.gg/?v=9&encoding=json')
            start = json.loads(ws.recv())
            heartbeat = start['d']['heartbeat_interval']
            auth = {"op": 2,"d": {"token": config["token"],"properties": {"$os": "Windows 10","$browser": "Google Chrome","$device": "Windows"},"presence": {"status": config["change_status"]["status"],"afk": False}},"s": None,"t": None}
            ws.send(json.dumps(auth))
            online = {"op":1,"d":"None"}
            time.sleep(heartbeat / 1000)
            ws.send(json.dumps(online))
        except:
            time.sleep(10)


async def sendToChannel(channel_id, message, channel_name, guild_name):
    try:
        if config['avoid_spam']['enabled']:
            amount = random.randint(config['avoid_spam']['minimum_messages'], config['avoid_spam']['maximum_messages'])
            can_post = await checkDoublePosting(channel_id, amount)
            if not can_post:
                if config['debug_mode']:
                    print(f' > Skipping "{channel_name}" in "{guild_name}" because you have "avoid_spam" enabled ({amount} messages)')
                return

        if isinstance(message, list):
            for msg_file in message:
                msg_content = open(os.path.join('messages', msg_file), "r", encoding="utf-8").read()
                requests.post(f'https://discord.com/api/v9/channels/{channel_id}/messages', json={'content': msg_content}, headers=headers)
        else:
            response = requests.post(f'https://discord.com/api/v9/channels/{channel_id}/messages', json={'content': message}, headers=headers).json()

            if 'code' in response:
                if response['code'] == 50013: # Muted
                    print(f'{colorama.Fore.RED} > There was a problem sending a message to "{channel_name}" in "{guild_name}" (MUTED)')
                    return
                elif response['code'] == 20016: # Slowmode
                    return

        if config['debug_mode']:
            print(f' > A message was sent to "{channel_name}" in "{guild_name}"')
    except Exception as e:
        print(f"{colorama.Fore.RED} > An error occurred while sending message to '{channel_name}' in '{guild_name}': {e}")

print('\x1b[2J')  # Clear the console

print(colorama.Fore.RED + '''
     █████╗ ██╗   ██╗████████╗ ██████╗      █████╗ ██████╗ 
    ██╔══██╗██║   ██║╚══██╔══╝██╔═══██╗    ██╔══██╗██╔══██╗
    ███████║██║   ██║   ██║   ██║   ██║    ███████║██║  ██║
    ██╔══██║██║   ██║   ██║   ██║   ██║    ██╔══██║██║  ██║
    ██║  ██║╚██████╔╝   ██║   ╚██████╔╝    ██║  ██║██████╔╝
    ╚═╝  ╚═╝ ╚═════╝    ╚═╝    ╚═════╝     ╚═╝  ╚═╝╚═════╝ 
''' + colorama.Fore.RESET + '    by XtramCZ')

async def sendMessages():
    global last_message
    last_message = ""
    if config['multiple_messages']['enabled']:
        message_folder = os.listdir('messages')

        if config['multiple_messages']['mode'] == 0:
            if len(message_folder) > 1 and last_message != "":
                message_folder.remove(last_message)

            message_file = random.choice(message_folder)
            message = open(os.path.join('messages', message_file), "r").read()
            last_message = message_file

        elif config['multiple_messages']['mode'] == 1:
            message = sorted(message_folder)

    else:
        message = open("message.txt", "r").read()

    if config['work_hours']['enabled']:
        getWorkHours()
        await checkWorkTime()

    for channel_id in config['channels']:
        channel_name, guild_name = await getChannelInfo(channel_id)
        await sendToChannel(channel_id, message, channel_name, guild_name)

        if config['wait_between_messages']['enabled']:
            wait_time = random.randint(config['wait_between_messages']['minimum_interval'], config['wait_between_messages']['maximum_interval'])
            time.sleep(wait_time)

    delay = config

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
        start_time = datetime.now().replace(hour=config['work_hours']['start_time'], minute=random.randint(0, 59))
        end_time = datetime.now().replace(hour=config['work_hours']['end_time'] - 1, minute=random.randint(0, 59))

async def checkWorkTime():
    global offline
    offline = False
    while True:
        now = datetime.now()
        if now.hour < start_time.hour or now.hour == start_time.hour and now.minute < start_time.minute or now.hour > end_time.hour or now.hour == end_time.hour and now.minute > end_time.minute:
            if not offline:
                print(f' > Going offline until {start_time.hour}:{start_time.minute}')
                offline = True
            time.sleep(300)
        else:
            break

async def getChannelInfo(channel_id):
    try:
        channel_resp = requests.get(f'https://discord.com/api/v9/channels/{channel_id}', headers=headers)
        channel = channel_resp.json()
        
        # Check for API errors (invalid channel, no access, etc.)
        if 'code' in channel or 'message' in channel:
            if config['debug_mode']:
                print(f' > Skipping invalid channel {channel_id}: {channel.get("message", "unknown error")}')
            return None, None, 0
        
        guild_id = channel.get('guild_id')
        if not guild_id:
            if config['debug_mode']:
                print(f' > Skipping channel {channel_id}: not in a guild (DM)')
            return None, None, 0
            
        guild_resp = requests.get(f'https://discord.com/api/v9/guilds/{guild_id}', headers=headers)
        guild = guild_resp.json()
        
        channel_name = channel.get('name', channel_id)
        guild_name = guild.get('name', 'Unknown guild')
        
        # Return rate_limit_per_user for slowmode detection (seconds, 0 = no slowmode)
        rate_limit = channel.get('rate_limit_per_user', 0)
        
        return channel_name, guild_name, rate_limit
    except Exception as e:
        if config['debug_mode']:
            print(f' > Skipping channel {channel_id}: {str(e)[:80]}')
        return None, None, 0

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
            if response['code'] == 50013:
                print(f'{colorama.Fore.RED} > There was a problem sending a message to "{channel_name}" in "{guild_name}" (MUTED)')
                return
            elif response['code'] == 20016:
                return
            
    if config['debug_mode']:
        print(f' > A message was sent to "{channel_name}" in "{guild_name}"')

print('\x1b[2J')

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
            message = open(os.path.join('messages', message_file), "r", encoding="utf-8").read()
            last_message = message_file

        elif config['multiple_messages']['mode'] == 1:
            message = sorted(message_folder)

    else:
        message = open("message.txt", "r", encoding="utf-8").read()

    if config['work_hours']['enabled']:
        getWorkHours()
        await checkWorkTime()

    for channel_id in config['channels']:
        try:
            channel_name, guild_name, rate_limit = await getChannelInfo(channel_id)
            if channel_name is None:
                continue  # Skip invalid/inaccessible channels gracefully
            await sendToChannel(channel_id, message, channel_name, guild_name)
        except:
            if config['debug_mode']:
                print(f'{colorama.Fore.RED} > There was a problem sending a message to "{channel_id}"')
            
        if config['wait_between_messages']['enabled']:
            wait_time = random.randint(
                config['wait_between_messages']['minimum_interval'],
                config['wait_between_messages']['maximum_interval']
            )
            # Slowmode-aware: use channel's rate_limit as minimum delay
            if config['wait_between_messages'].get('slowmode_aware', False) and rate_limit > 0:
                slowmode_min = rate_limit + random.randint(1, 3)
                wait_time = max(wait_time, slowmode_min)
                if config['debug_mode']:
                    print(f' > Slowmode {rate_limit}s detected, delay adjusted to {wait_time}s')
            time.sleep(wait_time)

    delay = config['interval']

    if config['randomize_interval']['enabled']:
        if not config['randomize_interval']['minimum_interval'] > config['randomize_interval']['maximum_interval']:
            delay = random.randint(config['randomize_interval']['minimum_interval'], config['randomize_interval']['maximum_interval'])
            if config['debug_mode']:
                print(f' > Waiting {delay} minutes...')
    time.sleep(delay * 60)
    await sendMessages()

async def start():
    global user_id
    response = ""
    try:
        user = requests.get('https://discord.com/api/v9/users/@me', headers=headers)
        response = user.text
        print()
        user_id = user.json()['id']
        print(colorama.Fore.GREEN + ' > Token is valid!' + colorama.Fore.RESET)
    except:
        print()
        print(colorama.Fore.RED + ' > Token is invalid!', colorama.Fore.RESET)
        print(response)
        exit()
        
    if config['wait_before_start'] > 0:
        print(f' > Waiting {config["wait_before_start"]} minutes before starting...')
        print()
        time.sleep(config['wait_before_start'] * 60)

    if config['change_status']['enabled']:
        threading.Thread(target=asyncio.run, args=(changeStatus(),)).start()
    await sendMessages()

try:    
    asyncio.run(start())
except KeyboardInterrupt:
    exit()

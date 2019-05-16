import os


CONFIG_FILE = '~/.git-remote-dropbox.json'
DEVNULL = open(os.devnull, 'w')
PROCESSES = 20
MAX_RETRIES = 3
CHUNK_SIZE = 50*1024*1024  # 50 megabytes

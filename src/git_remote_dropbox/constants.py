import os
from typing import TextIO

APP_KEY: str = "h7d8z1irmz0r7lp"
APP_FOLDER_APP_KEY: str = "w966iez5k027tcl"
DEVNULL: TextIO = open(os.devnull, "w")  # noqa: SIM115
PROCESSES: int = 20
MAX_RETRIES: int = 3
CHUNK_SIZE: int = 50 * 1024 * 1024  # 50 megabytes

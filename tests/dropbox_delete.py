#!/usr/bin/env python

import os
import sys

import dropbox  # type: ignore


def main(path: str) -> None:
    token = os.environ["DROPBOX_TOKEN"]
    connection = dropbox.Dropbox(token)
    try:
        connection.files_delete(path)
    except dropbox.exceptions.ApiError as e:
        if not isinstance(e.error, dropbox.files.DeleteError):
            raise
        # folder is missing? ignore


if __name__ == "__main__":
    main(sys.argv[1])

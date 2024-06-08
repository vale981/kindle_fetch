#! /usr/bin/env python
import glob
import os
from pathlib import Path
import re
import time
import shutil
import urllib.request
import asyncio
from aioimaplib import aioimaplib
from collections import namedtuple
import re
from asyncio import run, wait_for
from collections import namedtuple
from email.message import Message
from email.parser import BytesHeaderParser, BytesParser
from typing import Collection
from contextlib import suppress

KINDLE_DIR = Path.home() / "kindle_dump/"

LATEST_PATH = KINDLE_DIR / "latest.pdf"


def get_document_title(header_string):
    m = re.search(r'"(.*?)" from your Kindle', header_string)

    if not m:
        return None

    return m.group(1)


def get_download_link(text):
    m = re.search(r"\[Download PDF\]\((.*?)\)", text)

    if not m:
        return None, None

    p = re.search(r"([0-9]+) page", text)
    page = p.group(1) if p else None
    return m.group(1), page


# LAST_LINK = None
# while True:
#     current_link = monitor_kindle()

#     if current_link != LAST_LINK and current_link is not None:
#         LAST_LINK = current_link
#         print("Downloading:", LAST_LINK)
#

#     time.sleep(5)


ID_HEADER_SET = {
    "Subject",
}
FETCH_MESSAGE_DATA_UID = re.compile(rb".*UID (?P<uid>\d+).*")
FETCH_MESSAGE_DATA_SEQNUM = re.compile(rb"(?P<seqnum>\d+) FETCH.*")
FETCH_MESSAGE_DATA_FLAGS = re.compile(rb".*FLAGS \((?P<flags>.*?)\).*")
MessageAttributes = namedtuple("MessageAttributes", "uid flags sequence_number")


async def fetch_messages_headers(imap_client: aioimaplib.IMAP4_SSL, max_uid: int):
    response = await imap_client.uid(
        "fetch",
        "%d:*" % (max_uid + 1),
        "(UID FLAGS BODY.PEEK[HEADER.FIELDS (%s)])" % " ".join(ID_HEADER_SET),
    )
    new_max_uid = max_uid
    message_headers = ""
    if response.result == "OK":
        for i in range(0, len(response.lines) - 1, 3):
            fetch_command_without_literal = b"%s %s" % (
                response.lines[i],
                response.lines[i + 2],
            )

            uid = int(
                FETCH_MESSAGE_DATA_UID.match(fetch_command_without_literal).group("uid")
            )
            flags = FETCH_MESSAGE_DATA_FLAGS.match(fetch_command_without_literal).group(
                "flags"
            )
            seqnum = FETCH_MESSAGE_DATA_SEQNUM.match(
                fetch_command_without_literal
            ).group("seqnum")
            # these attributes could be used for local state management
            message_attrs = MessageAttributes(uid, flags, seqnum)

            # uid fetch always includes the UID of the last message in the mailbox
            # cf https://tools.ietf.org/html/rfc3501#page-61
            if uid > max_uid:
                message_headers = BytesHeaderParser().parsebytes(response.lines[i + 1])
                new_max_uid = uid
    else:
        print("error %s" % response)
    return new_max_uid, message_headers


async def fetch_message_body(imap_client: aioimaplib.IMAP4_SSL, uid: int):
    dwnld_resp = await imap_client.uid("fetch", str(uid), "BODY.PEEK[]")
    return BytesParser().parsebytes(dwnld_resp.lines[1])


async def wait_for_new_message(imap_client):
    persistent_max_uid = 1
    persistent_max_uid, head = await fetch_messages_headers(
        imap_client, persistent_max_uid
    )
    while True:
        idle_task = await imap_client.idle_start(timeout=60)
        msg = await imap_client.wait_server_push()
        print(msg)
        imap_client.idle_done()
        await wait_for(idle_task, timeout=5)

        for message in msg:
            if message.endswith(b"EXISTS"):
                persistent_max_uid, head = await fetch_messages_headers(
                    imap_client, persistent_max_uid
                )

                if not head:
                    continue

                body = await fetch_message_body(imap_client, persistent_max_uid)

                doc_title = get_document_title(head.as_string())

                if doc_title is None:
                    continue

                link, page = get_download_link(str(body))

                if link is None:
                    continue

                filename = f"{doc_title.replace(' ','')}"

                if page:
                    filename += f"_{page}_pages"

                filename += ".pdf"

                print(f"Got '{doc_title}'")
                urllib.request.urlretrieve(link, LATEST_PATH)
                shutil.copy(LATEST_PATH, KINDLE_DIR / filename)

        # await asyncio.wait_for(idle_task, timeout=5)
        # print("ending idle")


async def make_client(host, user, password):
    imap_client = aioimaplib.IMAP4_SSL(host=host)
    await imap_client.wait_hello_from_server()
    await imap_client.login(user, password)

    await imap_client.select("Kindle")

    return imap_client


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    client = loop.run_until_complete(
        make_client("protagon.space", "hiro@protagon.space", "DsAgeviNZ.")
    )
    loop.run_until_complete(wait_for_new_message(client))
    loop.run_until_complete(client.logout())

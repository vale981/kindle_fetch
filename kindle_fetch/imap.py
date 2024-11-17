"""
Business logic and boilerplate for the IMAP handling.
"""

import logging
import re
from collections import namedtuple
from email.parser import BytesHeaderParser, BytesParser

from aioimaplib import aioimaplib

LOGGER = logging.getLogger(__name__)
ID_HEADER_SET = {
    "Subject",
}

FETCH_MESSAGE_DATA_UID = re.compile(rb".*UID (?P<uid>\d+).*")
FETCH_MESSAGE_DATA_SEQNUM = re.compile(rb"(?P<seqnum>\d+) FETCH.*")
FETCH_MESSAGE_DATA_FLAGS = re.compile(rb".*FLAGS \((?P<flags>.*?)\).*")
MessageAttributes = namedtuple("MessageAttributes", "uid flags sequence_number")


async def make_client(host, user, password, folder):
    """Connect to the IMAP server and login.

    :param host: the IMAP server to connect to
    :param user: the IMAP username
    :param password: the password to the server
    :param folder: the folder to monitor for new messages
    """

    imap_client = aioimaplib.IMAP4_SSL(host=host)
    await imap_client.wait_hello_from_server()
    await imap_client.login(user, password)

    await imap_client.select(folder)

    return imap_client


async def fetch_messages_headers(imap_client: aioimaplib.IMAP4_SSL, max_uid: int):
    """
    Fetch the headers of the messages in the mailbox.

    Pretty much stolen from the `aioimaplib` examples.
    """

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
        LOGGER.error("error %s" % response)
    return new_max_uid, message_headers


async def fetch_message_body(imap_client: aioimaplib.IMAP4_SSL, uid: int):
    """Fetch the message body of the message with the given ``uid``."""
    dwnld_resp = await imap_client.uid("fetch", str(uid), "BODY.PEEK[]")
    return BytesParser().parsebytes(dwnld_resp.lines[1])


async def remove_message(imap_client: aioimaplib.IMAP4_SSL, uid: int):
    """Mark the message with the given ``uid`` as deleted and expunge it."""
    await imap_client.uid("store", str(uid), "+FLAGS (\Deleted \Seen)")
    return await imap_client.expunge()

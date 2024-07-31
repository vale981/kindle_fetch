#! /usr/bin/env python
from pathlib import Path
import re
import shutil
import urllib.request
import asyncio
import argparse
import logging
import subprocess
from aioimaplib import aioimaplib
from collections import namedtuple
import re
from asyncio import wait_for
from collections import namedtuple
from email.parser import BytesHeaderParser, BytesParser
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class Options:
    server: str
    """The IMAP server to connect to."""

    user: str
    """The IMAP username."""

    password: str
    """The password to the server."""

    kindle_dir: Path
    """The directory to dump the note PDFs in."""

    latest_path: Path
    """
    The path to the file that will contain the the most currently
    downloaded pdf relative to :any:`kindle_dir`.
    """

    mailbox: str
    """The folder to monitor for new messages."""


def get_document_title(header_string):
    """Get the title of the document from the email header."""
    m = re.search(
        r'"(.*?)" from your ',
        header_string.replace("\n", " ").replace("\r", "").replace("  ", " "),
    )

    if not m:
        return None

    return m.group(1)


def get_download_link(text):
    """
    Get the download link and whether the file is the full document or
    just `page` pages from the email body.
    """
    m = re.search(
        r"\[Download PDF\]\((.*?)\)",
        text.replace("\n", " ").replace("\r", "").replace("  ", " "),
    )

    if not m:
        return None, None

    p = re.search(r"([0-9]+) page", text)
    page = p.group(1) if p else None
    return m.group(1), page


ID_HEADER_SET = {
    "Subject",
}
FETCH_MESSAGE_DATA_UID = re.compile(rb".*UID (?P<uid>\d+).*")
FETCH_MESSAGE_DATA_SEQNUM = re.compile(rb"(?P<seqnum>\d+) FETCH.*")
FETCH_MESSAGE_DATA_FLAGS = re.compile(rb".*FLAGS \((?P<flags>.*?)\).*")
MessageAttributes = namedtuple("MessageAttributes", "uid flags sequence_number")


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
        logger.error("error %s" % response)
    return new_max_uid, message_headers


async def fetch_message_body(imap_client: aioimaplib.IMAP4_SSL, uid: int):
    """Fetch the message body of the message with the given ``uid``."""
    dwnld_resp = await imap_client.uid("fetch", str(uid), "BODY.PEEK[]")
    return BytesParser().parsebytes(dwnld_resp.lines[1])


async def remove_message(imap_client: aioimaplib.IMAP4_SSL, uid: int):
    """Mark the message with the given ``uid`` as deleted and expunge it."""
    await imap_client.uid("store", str(uid), "+FLAGS (\Deleted \Seen)")
    return await imap_client.expunge()


async def wait_for_new_message(imap_client, options: Options):
    """
    Wait for a new message to arrive in the mailbox, detect Kindle
    messages and download the PDF linked in if possible.
    """

    persistent_max_uid = 1
    persistent_max_uid, head = await fetch_messages_headers(
        imap_client, persistent_max_uid
    )

    while True:
        logger.debug("waiting for new message")

        idle_task = await imap_client.idle_start(timeout=60)
        msg = await imap_client.wait_server_push()
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
                    logger.info(f"No document title found in '{head.as_string()}'.")
                    continue

                link, page = get_download_link(str(body))

                if link is None:
                    logger.info("No pdf download link found.")
                    logger.debug(str(body))
                    continue

                filename = f"{doc_title.replace(' ','')}"

                if page:
                    filename += f"_{page}_pages"

                filename += ".pdf"

                outpath = options.kindle_dir / filename
                logger.info(f"downloading '{doc_title}' -> '{outpath}'")

                urllib.request.urlretrieve(link, outpath)
                shutil.copy(outpath, options.latest_path)

                await remove_message(imap_client, persistent_max_uid)


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


def parse_args_and_configure_logging():
    parser = argparse.ArgumentParser(
        prog="kindle_fetch",
        description="Monitors you Email and automatically downloads the notes sent to it.",
    )

    parser.add_argument("server", type=str, help="the IMAP server to connect to")
    parser.add_argument("user", type=str, help="the IMAP username")
    parser.add_argument(
        "pass_command",
        type=str,
        help="a shell command that returns the password to the server",
    )
    parser.add_argument(
        "--outdir",
        type=str,
        help="the directory to dump the note PDFs in",
        default="~/kindle_dump",
    )
    parser.add_argument(
        "--current_file",
        type=str,
        help="the path to the file that will contain the the most currently downloaded pdf relative to `outdir`",
        default="latest.pdf",
    )
    parser.add_argument(
        "--imap_folder",
        type=str,
        help="the folder to monitor for new messages",
        default="INBOX",
    )
    parser.add_argument(
        "--loglevel",
        default="info",
        help="logging level; example --loglevel debug, default=warning",
    )

    args = parser.parse_args()

    password = subprocess.check_output(args.pass_command, shell=True, text=True).strip()
    kindle_dir = Path(args.outdir).expanduser()
    kindle_dir.mkdir(exist_ok=True, parents=True)
    latest_path = Path(kindle_dir / args.current_file).with_suffix(".pdf")

    logging.basicConfig(level=args.loglevel.upper())

    return Options(
        server=args.server,
        user=args.user,
        password=password,
        kindle_dir=kindle_dir,
        latest_path=latest_path,
        mailbox=args.imap_folder,
    )


def main():
    options = parse_args_and_configure_logging()
    loop = asyncio.get_event_loop()

    logger.info("logging in")
    try:
        client = loop.run_until_complete(
            make_client(options.server, options.user, options.password, options.mailbox)
        )
    except Exception as e:
        logger.error(f"Failed to connect to the server: {e}")
        exit(1)

    logger.info("starting monitor")
    loop.run_until_complete(wait_for_new_message(client, options))
    loop.run_until_complete(client.logout())

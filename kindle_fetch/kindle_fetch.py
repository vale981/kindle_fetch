#! /usr/bin/env python
import argparse
import asyncio
import logging
import quopri
import re
import sys
import signal
import shutil
import subprocess
import urllib.request
from asyncio import wait_for
from dataclasses import dataclass
from pathlib import Path
from .imap import (
    fetch_message_body,
    fetch_messages_headers,
    make_client,
    remove_message,
)

LOGGER = logging.getLogger(__name__)


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


def get_download_link(body):
    """
    Get the download link and whether the file is the full document or
    just `page` pages from the email ``body``.
    """

    body = quopri.decodestring(body).decode("utf-8", errors="ignore")
    LOGGER.debug(body)

    m = re.search(r'''href="(https://.*\.amazon\..*\.pdf.*?)"''', body)
    if not m:
        return None, None

    p = re.search(r"([0-9]+) page", body)
    page = p.group(1) if p else None
    return m.group(1), page


async def wait_for_new_message(imap_client, kindle_dir, latest_path):
    """
    Wait for a new message to arrive in the mailbox connected to by
    ``imap_client``, detect Kindle messages and download the PDF
    linked in if possible.

    The PDF will be saved in the directory ``kindle_dir`` with a name
    derived from the document name. The latest downloaded file will be copied
        to ``latest_path`` (relative to the ``kindle_dir``).
    """

    persistent_max_uid = 1
    persistent_max_uid, head = await fetch_messages_headers(
        imap_client, persistent_max_uid
    )

    while True:
        try:
            LOGGER.debug("waiting for new message")

            idle_task = await imap_client.idle_start(timeout=float("inf"))
            msg = await imap_client.wait_server_push()
            imap_client.idle_done()
            await wait_for(idle_task, timeout=float("inf"))
        except TimeoutError:
            continue

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
                    LOGGER.info(f"No document title found in '{head.as_string()}'.")
                    continue

                link, page = get_download_link(str(body))

                if link is None:
                    LOGGER.info("No pdf download link found.")
                    LOGGER.debug(str(body))
                    continue

                filename = f"{doc_title.replace(' ','_')}"

                if page:
                    filename += f"_{page}_pages"

                filename += ".pdf"

                outpath = kindle_dir / filename
                LOGGER.info(f"downloading '{doc_title}' -> '{outpath}'")

                urllib.request.urlretrieve(link, outpath)
                shutil.copy(outpath, latest_path)

                await remove_message(imap_client, persistent_max_uid)


def parse_args_and_configure_logging():
    parser = argparse.ArgumentParser(
        prog="kindle_fetch",
        description="Monitors you email and automatically downloads the kindle PDF notes sent to it.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument("server", type=str, help="the IMAP server to connect to")
    parser.add_argument("user", type=str, help="the IMAP username")
    parser.add_argument(
        "pass_command",
        type=str,
        help="A shell command that returns the password to the server.",
    )
    parser.add_argument(
        "--outdir",
        type=str,
        help="The kindle note PDFs will be saved into `OUTDIR/[name].pdf`.",
        default="~/kindle_dump",
    )
    parser.add_argument(
        "--current_file",
        type=str,
        help="The latest downloaded file will be copied to `OUTDIR/[current_file]",
        default=".latest.pdf",
    )
    parser.add_argument(
        "--imap_folder",
        type=str,
        help="The IMAP folder to monitor for new messages.",
        default="INBOX",
    )
    parser.add_argument(
        "--loglevel",
        default="info",
        help="The python logging level to use.",
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
    """The entry point for the command line script."""
    options = parse_args_and_configure_logging()
    loop = asyncio.get_event_loop()

    LOGGER.info("logging in")

    try:
        client = loop.run_until_complete(
            make_client(options.server, options.user, options.password, options.mailbox)
        )
    except Exception as e:
        LOGGER.error(f"Failed to connect to the server: {e}")
        sys.exit(1)

    LOGGER.info("starting monitor")

    signal.signal(
        signal.SIGINT,
        lambda _, _1: loop.run_until_complete(client.logout()) and sys.exit(0),
    )

    loop.run_until_complete(
        wait_for_new_message(client, options.kindle_dir, options.latest_path)
    )
    loop.run_until_complete(client.logout())

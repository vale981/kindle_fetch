# Kindle (Scribe) Email Fetch Hack

This is a python script (or, more adequately, a
[bodge](https://www.youtube.com/watch?v=lIFE7h3m40U)) to log into an
IMAP server, monitor incoming messages for the ones that contain the
links to the PDFs that you sent from the Kindle scribe. Once such an
email is found the PDF linked therein is downloaded to a local
directory `OUTDIR/[name].pdf` (see below) and the email is
deleted. The latest downloaded file is also copied to a preset
filename to make it easier to find it. I'm always running `zathura
OUTDIR/.latest.pdf` to have the latest kindle PDF visible.

## Installation / Usage

Either clone this repo and use `poerty install` and the like or run the nix flake with `nix run github:vale981/kindle_fetch -- [args]`.

```
usage: kindle_fetch [-h] [--outdir OUTDIR] [--current_file CURRENT_FILE] [--imap_folder IMAP_FOLDER] [--loglevel LOGLEVEL] server user pass_command

Monitors you email and automatically downloads the kindle PDF notes sent to it.

positional arguments:
  server                the IMAP server to connect to
  user                  the IMAP username
  pass_command          A shell command that returns the password to the server.

options:
  -h, --help            show this help message and exit
  --outdir OUTDIR       The kindle note PDFs will be saved into `OUTDIR/[name].pdf`. (default: ~/kindle_dump)
  --current_file CURRENT_FILE
                        The latest downloaded file will be copied to `OUTDIR/[current_file] (default: .latest.pdf)
  --imap_folder IMAP_FOLDER
                        The IMAP folder to monitor for new messages. (default: INBOX)
  --loglevel LOGLEVEL   The python logging level to use. (default: info)
```

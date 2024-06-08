# Kindle (Scribe) Email Fetch Hack

This is a quick-and-dirty python script to log into an IMAP server,
monitor incoming messages for the ones that contain the links to the
PDFs that you sent from the Kindle scribe. Once such an email is found
the pdf linked therein is downloaded to a local directory and the
email is deleted. The latest downloaded file is also copied to a
preset filename to make it easier to find it. I'm always running
`zathura ~/kindle_dump/latest.pdf` to have the latest kindle pdf
visible.

## Installation / Usage

Either clone this repo and use `poerty install` and the like or run the nix flake with `nix run github:vale981/kindle_fetch -- [args]`.

```
usage: kindle_fetch [-h] [--outdir OUTDIR] [--current_file CURRENT_FILE] [--imap_folder IMAP_FOLDER]
                    server user pass_command

Monitors you Email and automatically downloads the notes sent to it.

positional arguments:
  server                the IMAP server to connect to
  user                  the IMAP username
  pass_command          a shell command that returns the password to the server

options:
  -h, --help            show this help message and exit
  --outdir OUTDIR       the directory to dump the note PDFs in
  --current_file CURRENT_FILE
                        the path to the file that will contain the the most currently downloaded pdf relative to
                        `outdir`
  --imap_folder IMAP_FOLDER
                        the folder to monitor for new messages
```

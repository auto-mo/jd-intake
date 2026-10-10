# Run it on a home or cloud server

This is guidance, not a turnkey installer. It suits you if you want inbox reading and approved
emails to keep going while your laptop sleeps. If you only capture and build resumes, running
locally is simpler.

## The shape of it

- The server runs on an always-on machine (a mini PC at home, or a small cloud VM) and still
  listens only on `127.0.0.1`. It is never exposed to the internet.
- Your laptop reaches it through an **SSH tunnel**, so Chrome talks to `127.0.0.1:8790` on your
  laptop exactly as in local mode, and the extension needs no change.
- Claude Code, LibreOffice and Poppler are installed on the server, because that is where the
  model calls and the rendering happen.

## What does not work remotely

- **Opening files on your desktop.** "Open folder" and "Open PDF" open them on the server's
  screen, not yours. Use the dashboard's thumbnails and the side panel's drag handle (it
  downloads the PDF over the tunnel) instead.
- **Desktop copies.** `JDI_DROP_DIR` is a folder on the server. Set it empty
  (`JDI_DROP_DIR=`) or point it at a folder you sync yourself.
- **The `apply` skill** drives Chrome on the machine where Claude Code runs; run it on your
  laptop, not on the server.
- **Onboarding** is easiest on your laptop. Copy `profile/` to the server afterwards (it is
  plain files), and copy it back after editing either side; there is no sync.

## Steps

1. **Install** on the server: Python 3.10+, a venv (`python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`, then run the server with `.venv/bin/python`),
   LibreOffice (`sudo apt install libreoffice-writer` on Debian or Ubuntu), Poppler
   (`sudo apt install poppler-utils`), and Claude Code.
2. **Give Claude Code credentials on the server.** Either log in following the Claude Code
   documentation for a machine without a browser, or use an API key
   ([api-key-mode.md](api-key-mode.md)). Check with `claude -p "Reply ok." --tools ""`.
3. **Copy the repo and your profile**: `rsync -a jd-intake/ server:jd-intake/` (it includes
   `profile/` and `.env` if you have them; both stay out of git, so copy them this way).
   Make `.env` readable only by you: `chmod 600 .env`.
4. **Run it as a service.**

   systemd, as a system service that runs as your user
   (`/etc/systemd/system/jd-intake.service`):

   ```ini
   [Unit]
   Description=jd-intake server
   After=network-online.target
   Wants=network-online.target

   [Service]
   User=you
   WorkingDirectory=/home/you/jd-intake
   ExecStart=/usr/bin/python3 /home/you/jd-intake/server/app.py
   Environment=PATH=/home/you/.local/bin:/usr/local/bin:/usr/bin:/bin
   Environment=JDI_DROP_DIR=
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now jd-intake
   journalctl -u jd-intake -f          # the log
   ```

   A `systemd --user` unit works too ([run-locally.md](run-locally.md)), but on a headless
   machine it stops when you log out unless you run `sudo loginctl enable-linger you` once.

   On a Mac used as a server, use the launchd example in [run-locally.md](run-locally.md).

5. **Open the tunnel from your laptop:**

   ```bash
   ssh -N -L 8790:127.0.0.1:8790 you@server
   ```

   Leave it running, then open `http://127.0.0.1:8790`. To keep it up, use `autossh` or an SSH
   config entry with `LocalForward 8790 127.0.0.1:8790` and `ServerAliveInterval 30`.

## Do not

- Bind the server to `0.0.0.0` or put it behind a public reverse proxy. It has no login: it
  trusts that only you can reach `127.0.0.1`. The server also refuses requests whose Host is not
  `127.0.0.1` or `localhost`, so a proxy would be refused anyway.
- Run builds or test suites on a server that also hosts other things you care about without
  checking memory first; LibreOffice and several Claude processes at once can use a few GB.

## Updating

```bash
curl -s http://127.0.0.1:8790/api/busy     # wait until nothing is running
git pull
sudo systemctl restart jd-intake
```

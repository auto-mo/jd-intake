# Run it on your own computer

This is the easiest way to use jd-intake: the server, Claude Code and Chrome all run on the
same machine, and Claude Code uses your Claude subscription.

## What you need

| Tool | Why | Install |
|---|---|---|
| Python 3.10 or newer | the server and the resume engine | macOS: `brew install python`; Linux: your distribution's `python3` |
| The Python packages | Flask, PyYAML, python-docx, pypdf and a few more | `python3 -m pip install -r requirements.txt` |
| LibreOffice | turns the generated `.docx` into a PDF | macOS: `brew install --cask libreoffice`; Debian or Ubuntu: `sudo apt install libreoffice-writer` |
| Poppler | measures and rasterizes the PDF (`pdfinfo`, `pdftotext`, `pdftoppm`) | macOS: `brew install poppler`; Debian or Ubuntu: `sudo apt install poppler-utils` |
| Google Chrome | the capture extension | https://www.google.com/chrome/ |
| Claude Code | the model calls | https://docs.claude.com/en/docs/claude-code |

On macOS, LibreOffice's `soffice` is inside the app bundle. If `soffice --version` fails after
installing, add `/Applications/LibreOffice.app/Contents/MacOS` to your PATH.

Log Claude Code in with your plan: run `claude`, then `/login`. Check it works without a
terminal prompt with:

```bash
claude -p "Reply ok." --tools ""
```

Windows is not supported. It may work under WSL, but nobody has tested it.

## First run

```bash
cd jd-intake
claude          # then type /onboard
```

Onboarding writes your profile to `profile/` and renders your base resumes. When it finishes:

```bash
python3 server/app.py
```

The server listens on `http://127.0.0.1:8790` and only answers requests from your own machine.
Open that address for the dashboard.

Load the extension: `chrome://extensions`, Developer mode on, **Load unpacked**, choose the
`extension/` folder, then pin it. Open a job posting and click the icon to open the side panel.

## Settings

All optional, set in the environment before starting the server:

| Variable | Default | What it does |
|---|---|---|
| `JDI_PORT` | `8790` | The port. The extension's default address is `http://127.0.0.1:8790`; a different one is set in the side panel's settings, and a different port also needs the matching entry in `extension/manifest.json` under `host_permissions`. |
| `JDI_PROFILE_DIR` | `profile/` | Where your profile lives |
| `JDI_DATA_DIR` | `data/` | The job database, application folders and the learning inbox |
| `JDI_DROP_DIR` | your Desktop | Finished PDFs are copied here so they are easy to upload; they are removed when you mark the job submitted. Set it empty to turn this off |
| `JDI_EXTENSION_ID` | empty | When set, only that Chrome extension id may call the server |

Secrets for optional features go in `.env` at the repo root; `.env.example` lists the keys.

## Start it automatically

### macOS (launchd)

Save as `~/Library/LaunchAgents/local.jd-intake.plist`, replacing `/path/to/jd-intake` and
the Python path (`which python3`):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>local.jd-intake</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/local/bin/python3</string>
    <string>/path/to/jd-intake/server/app.py</string>
  </array>
  <key>WorkingDirectory</key><string>/path/to/jd-intake</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/Applications/LibreOffice.app/Contents/MacOS</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>/tmp/jd-intake.log</string>
  <key>StandardErrorPath</key><string>/tmp/jd-intake.log</string>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/local.jd-intake.plist
launchctl kickstart -k gui/$(id -u)/local.jd-intake     # restart after an update
```

The PATH must include the folders that hold `claude`, `soffice` and `pdfinfo`; launchd does not
read your shell profile.

### Linux (systemd, per user)

Save as `~/.config/systemd/user/jd-intake.service`:

```ini
[Unit]
Description=jd-intake server

[Service]
WorkingDirectory=/path/to/jd-intake
ExecStart=/usr/bin/python3 /path/to/jd-intake/server/app.py
Restart=on-failure
Environment=PATH=/home/you/.local/bin:/usr/local/bin:/usr/bin:/bin

[Install]
WantedBy=default.target
```

```bash
systemctl --user daemon-reload
systemctl --user enable --now jd-intake
```

## Restarting safely

A restart in the middle of an evaluation, build or draft loses that run (the job shows
"Interrupted by a server restart"; press the button again). Before restarting, check nothing is
running:

```bash
curl -s http://127.0.0.1:8790/api/busy
```

## Running the tests

The tests use the invented example profile, never yours:

```bash
cd server
python3 test_api.py
python3 test_outreach_validate.py
python3 test_outreach_flow.py
python3 test_inbox.py
```

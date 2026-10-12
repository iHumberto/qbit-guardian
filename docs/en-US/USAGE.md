# qbit-guardian Usage Guide

> Learn how to use qbit-guardian day to day: configuring it, understanding the operating modes and reading what it is doing.

## What it is

qbit-guardian is an automatic watchdog for your torrents. Once installed and configured it works on its own in the background. You only need to visit the configuration page now and then to adjust something.

---

## Signing in

Open a browser and type the address of the server running qbit-guardian, always on port **5000**:

```
http://your-server-address:5000
```

Practical examples:

- **Same computer:** `http://localhost:5000`
- **Another computer on the network:** `http://192.168.1.100:5000`
- **Server with a network name:** `http://my-server:5000`

You land on the **login page**. The default username is `admin`, and the password was generated on first run and printed to the container log — see [First access](#first-access-and-changing-your-password).

Once signed in you see the panel in **three columns**:

| Column | What's in it |
|--------|--------------|
| **Left** | qBittorrent, Radarr and Sonarr — the external services |
| **Center** | Guardian — interval, extensions, removal rules and priorities |
| **Right** | Notifications — Apprise and each event's message |

The **Save Configuration** button sits centered below the three columns.

### Language

There is a language selector in the top-right corner:

- 🇧🇷 **PT-BR (default):** the interface opens in Brazilian Portuguese the first time.
- 🇺🇸 **EN-US:** switches the whole interface to American English.

The switch is instant — no reload needed. The browser remembers your choice.

> 💡 The selector works offline. All translations ship inside the application — no external service is used. Your preference is saved in the browser itself (localStorage).

---

## First access and changing your password

The Web UI **always** requires a login. There is no sign-up screen: on first run the guardian generates the password itself and prints it to the log.

```bash
docker logs qbit-guardian
```

```
====================================================================
  qbit-guardian — credenciais da Web UI geradas automaticamente
====================================================================
  usuario: admin
  senha:   y7f3CKYTGvYeskf3vEQk
====================================================================
```

> ⚠️ That password is shown **only once**. Copy and store it.

### Changing username or password

In the panel, click the **user icon** in the top-right corner. A popup opens with three fields:

| Field | When to fill it in |
|-------|-------------------|
| **Username** | If you want to change the username |
| **Current password** | **Always** — it proves it's you |
| **New password** | Only if you want to change the password (minimum 8 characters) |

Want to change only the name? Fill in username + current password and leave the new password blank. Only the password? Fill in current + new password.

After saving you are returned to the login page — the change ends every open session, including yours.

> **📘 Why the current password is always required:** without it, anyone who found a browser of yours already signed in could take over the account in two clicks.

### Signing out

The same popup has a **Sign out** button, on the left side.

### How the password is stored

As a **PBKDF2-SHA256 hash** with its own salt. It is never kept in plain text in `config.json` and never returned by the API. Even someone reading the file cannot recover the password.

### I forgot the password

Open `config.json` in the `config` folder, leave `webui.password` empty (`""`) and restart the container. A new password is generated and announced in the log.

### Too many attempts

After **5 wrong attempts in 5 minutes**, login answers "too many attempts" for that client — even if the next password is correct. It protects against someone brute-forcing the password. Wait a few minutes.

---

## Essential configuration

For qbit-guardian to start working, only two fields are required:

| Field | Where to find it |
|-------|-----------------|
| **qBittorrent URL** | Full address with `http://` and port (e.g. `http://192.168.1.50:8080`) |
| **qBittorrent API Key** | In qBittorrent: **Tools → Options → Web UI → API Key** |

> ⚠️ It is a **full URL**, not separate host and port. Write `http://192.168.1.50:8080`, not just `192.168.1.50`.

> **📘 API Key:** A long random password qBittorrent generates. It lets other programs talk to qBittorrent securely. Think of it as an access key you hand to a trusted application.

Fill in those two fields, click **Save Configuration**, and that's it — the guardian is working.

### Sonarr and Radarr integration (optional)

If you use Sonarr (TV shows) or Radarr (movies), also fill in their **URL** and **API Key** fields.

With the integration active, whenever qbit-guardian removes a problematic torrent it also:

1. Blocklists that release in Sonarr/Radarr (so it isn't downloaded again).
2. Triggers an automatic search for an alternative version.

> 💡 If you don't use Sonarr or Radarr, leave the fields blank. The guardian works normally — only the blocklist-and-research part is skipped.

---

## Panel field reference

The panel shows the fields, not their explanation. The screen is deliberately clean — help text under every box competes for attention with the controls themselves — and **this section is where that explanation lives**.

The **key** column is the field's name in `config.json`, handy when you need to edit the file directly instead of using the panel.

### 🔗 qBittorrent, 🎬 Radarr and 📺 Sonarr

| Field | Key | What it does |
|---|---|---|
| **URL** | `url` | Full address of the service, with `http://` and port. qBittorrent's is required; Radarr and Sonarr are optional. |
| **API Key** | `api_key` | The key that lets the guardian talk to the service. See **Essential configuration** for where to find each one. |

### 🛡️ Guardian

The first three fields are times, all in seconds — that's what the `s` next to the box means.

| Field | Key | What it does |
|---|---|---|
| **Polling** | `check_interval_seconds` | How often the guardian sweeps the whole torrent list. `0` disables the sweep and leaves the guardian reacting only to qBittorrent's webhook — see **Operating modes**. |
| **Queue recheck** | `reevaluate_interval_seconds` | How often the guardian revisits torrents that had no metadata yet and reapplies the removal criteria. This is the granularity of every time limit in this section: **a limit shorter than this is never reached before the next cycle**. `0` disables the recheck. **Only applies in webhook mode** (Polling at `0`) — see **Which field applies in each mode**. |
| **Reconnect** | `retry_interval_seconds` | How long to wait between attempts while qBittorrent is unreachable. It needn't be short: the guardian retries forever. |
| **Media priority** | `priority_media` | Download priority for the torrent's video files. See **File priorities**. |
| **Auxiliary priority** | `priority_normal` | Priority for the files that come along with the media — subtitles (`.srt`), artwork (`.jpg`), metadata (`.nfo`). |
| **Other priority** | `priority_skip` | Priority for everything that is neither media nor auxiliary. The default is `0` (skip), which is how the guardian saves bandwidth on torrent clutter. |
| **Media extensions** | `valid_media_extensions` | One extension per line, with the dot (`.mkv`). Defines what counts as media for the priorities above. |
| **Dangerous extensions** | `dangerous_extensions` | One per line, with the dot. A torrent containing any of them is removed whole. See **Dangerous extensions**. |

The three removal rules sit under the **Remove torrents** heading — the verb is in the heading, and each line states only the condition. Each rule's switch is independent: switched off, the rule isn't evaluated, and the value stays saved for when you switch it back on.

| Rule | Keys | When it fires |
|---|---|---|
| **Stalled longer than** | `remove_stalled`, `stalled_time`, `stalled_unit` | The torrent has made no progress for longer than the limit. See **Removing stalled torrents**. |
| **Seedless longer than** | `remove_no_seeds`, `no_seeds_time`, `no_seeds_unit` | No seeds available for longer than the limit. See **Removing seedless torrents**. |
| **Below the minimum speed** | `remove_slow`, `slow_speed`, `slow_speed_unit`, `slow_time`, `slow_unit` | The **average** download speed stayed below the limit for the whole window. |

> **📘 Why the average and not the current speed:** a healthy torrent fluctuates. One averaging 20 KiB/s may read 2 KiB/s at the exact moment the guardian looks, and would be removed for nothing. The guardian measures how much the torrent actually downloaded over the period and divides by the time — it only removes what is genuinely slow.

> ⚠️ The speed rule only evaluates torrents that are **downloading**. A torrent waiting in qBittorrent's queue isn't slow: it hasn't started. The same goes for one still fetching metadata.

### 🔔 Notifications

| Field | Key | What it does |
|---|---|---|
| **Apprise URL** | `apprise_url` | Where the messages go. See **Notifications**. |
| **Message for…** | `events.<event>.template` | The text of each alert. Every box has a `{ }` next to its title: hover it (or **Tab** to it) to see the variables that message accepts. |

> 💡 The `{ }` is the only reminder left on screen, and that's deliberate: someone adjusting a message's text needs the variable names at hand, and won't open the documentation just to reorder two lines. What each variable means is in **Editing the messages**.

---

## Notifications

qbit-guardian can alert you on your phone or computer whenever something important happens. It uses **Apprise** — a system that delivers messages to 100+ different services (Telegram, Discord, Slack, Pushover, email and many more).

> **📘 Apprise:** Like a universal postal worker. It knows 100+ services; you tell it once which ones you want, and it delivers to all of them.

### ⚠️ The field expects an HTTP address, not a service URL

This is where most people get it wrong. qbit-guardian **does not run Apprise** — it makes an HTTP `POST` to an **Apprise server you host** (the official [`caronc/apprise`](https://hub.docker.com/r/caronc/apprise) image).

So the **Apprise URL** field takes **your server's endpoint**:

```
http://192.168.1.100:8000/notify/guardian
https://apprise.my-network.local/notify/guardian
```

Apprise service URLs — `tgram://`, `discord://`, `pover://` — **do not work here**. They go in the **Apprise server's configuration**, under the config key (the `guardian` at the end of the address above). Paste one of them into the field and no notification goes out, while the log records `Apprise: No connection adapters were found`.

| Where | What goes in |
|-------|--------------|
| The **Apprise URL** field on this screen | `http://YOUR_SERVER:8000/notify/KEY` |
| The Apprise server's configuration | `tgram://BOT_TOKEN/CHAT_ID`, `discord://ID/TOKEN`, `pover://USER/APP`… |

> See the [full list of formats](https://github.com/caronc/apprise#supported-notifications) in Apprise's official documentation — remembering that they go on the **server**, not in this field.

### Turning notifications on

Fill in the **Apprise URL** field with your Apprise server's endpoint and flip the switch in the **Notifications** card header.

### The three events

| Event | When it fires |
|-------|--------------|
| ⚡ **Torrent Optimized** | File priorities were adjusted |
| ⚠️ **Torrent Removed (Dangerous)** | Removed for a dangerous file, or for having no valid media |
| 🗑️ **Torrent Removed (Stalled)** | Removed for being stalled too long, or for having no seeds |

Each one has its own **switch** and its own **text box**.

### Editing the messages

Each text box is the message that will be sent. Inside it, each `{{...}}` is replaced with the torrent's real value.

The available variables are listed right under each box:

| Event | Variables |
|-------|-----------|
| Optimized | `{{torrentName}}` `{{priorityMedia}}` `{{priorityAux}}` `{{mediaCount}}` |
| Removed (dangerous) | `{{torrentName}}` `{{reason}}` `{{extensions}}` |
| Removed (stalled) | `{{torrentName}}` `{{reason}}` `{{state}}` `{{stalledTime}}` |

> 💡 If you write a variable that doesn't exist, it shows up **literally** in the message — so a typo is visible instead of silently vanishing.

**Two levels of on/off.** A notification is only sent with **both** switches on: the master one (in the card header) and the event's own. With a message switched off, the text stays visible but cannot be edited — you can see what would be sent without changing it by accident.

Cleared the text by mistake? An empty box falls back to the default instead of sending a blank message.

> Each notification's **title** is not exposed in the panel, but remains editable in `config.json`, under `notifications.events.<event>.title`.

### Apprise with a self-signed certificate

If your Apprise server uses a self-signed SSL certificate (common on home networks with addresses like `apprise.home.arpa`), the guardian already works without SSL verification. No extra configuration is needed.

> **📘 Self-signed SSL certificate:** A certificate you generated yourself, without validation from an external authority. On home networks it's a free alternative to paid certificates — browsers and other programs don't trust it automatically.

---

## Operating modes

qbit-guardian has two ways of working. You pick it in the **Check interval** field of the Guardian section.

### Polling mode (default)

In this mode the guardian checks torrents every so often. You set the interval in seconds.

- **Default:** 300 seconds (5 minutes).
- **Fast example:** 60 seconds (1 minute).
- **Frugal example:** 1800 seconds (30 minutes).

The shorter the interval, the faster a dangerous torrent is caught. The longer it is, the fewer server resources are used.

We recommend **300 seconds** for general use — fast enough and not taxing.

### Webhook mode (real time)

In this mode, qBittorrent notifies the guardian **the moment** a torrent is added. Put `0` in the check interval and follow the steps in [Setting up the Webhook](INSTALL.md#setting-up-the-webhook-real-time).

> ⚠️ The webhook needs `QBIT_GUARDIAN_USER` and `QBIT_GUARDIAN_PASS` on the qBittorrent service, because `/api/trigger` requires authentication.

### Which field applies in each mode

The two time fields look independent on screen, but **one switches the other off**:

| Polling | Mode | What runs | **Re-evaluate queue** |
|---------|------|-----------|------------------------|
| above `0` | Polling | the guardian sweeps the whole queue every N seconds | **ignored** — the field shows up disabled |
| `0` | Webhook | the guardian only acts when qBittorrent calls it | **this is what keeps it watching the queue** |

In webhook mode, `/api/trigger` fires when a torrent is **added** — and that is all. Without re-evaluation, a torrent that stalled *after* coming in would wait for another torrent to arrive before being looked at again, and a batch that came in without metadata would never get its priorities. That is why, in this mode, leaving `Re-evaluate queue` at 0 **is not recommended**.

In practice: on webhook, keep re-evaluation on (300 seconds works well). On polling, you do not need to think about this field — the screen disables it for you.

> The value you typed is **not lost** when the field is disabled: it applies again as soon as Polling goes back to `0`.

### Switching modes with the container running

You can switch from the Web UI, no restart needed: save the new Polling value and the guardian switches modes on its own — the log records it (`entrando em modo webhook` or `Polling religado`).

> Up to v2.9.0 this **did not work**: the switch only took effect after a container restart, and leaving polling left the guardian with no active checking at all. Fixed in v2.10.0.

### If qBittorrent goes down

The guardian **doesn't give up**. It logs a warning and retries every `retry_interval_seconds` (default: 120 seconds) until qBittorrent comes back. That applies both at startup — when the server reboots and the guardian comes up first — and during normal operation.

While retrying, the container stays `healthy`: the healthcheck measures the health of the **guardian process**, not of qBittorrent, which is an external and transient dependency. Watch the log to see the outage.

---

## Customizing the rules

### Dangerous extensions

File endings that, if found inside a torrent, make the guardian remove everything immediately. The default list:

`.exe` `.scr` `.bat` `.cmd` `.vbs` `.js` `.com` `.pif` `.msi` `.dll` `.ps1` `.sh` `.bin`

You can add or remove extensions in the **Guardian** section, one per line.

> ⚠️ Only do it if you're sure. `.exe` files are the main vector for viruses in torrents. Remove it and you lose the guardian's main protection.

### Valid media extensions

The list of formats the guardian treats as "legitimate content". If a torrent has **no** file with these extensions, it is treated as suspicious and removed.

Default list: `.mkv` `.mp4` `.avi` `.mov` `.m4v` `.ts` `.wmv` `.flv` `.webm`

Add or remove formats as you prefer. For example, if you download Blu-ray ISOs, add `.iso` and `.m2ts`.

> 💡 Leaving the list **empty** disables this criterion: no torrent is removed for "no valid media". Dangerous-extension detection keeps working normally.

### Removing stalled torrents

A "stalled" torrent is one that cannot download — either because the sources are gone or because of a connection problem.

To enable it, flip the **Remove torrents stalled for more than** switch and set the time and unit (seconds, minutes or hours).

Example: `6 hours` — the guardian removes torrents stalled for over 6 hours.

> ⚠️ A time of `0` means **off**, never "remove now".

### Removing seedless torrents

A "seedless" torrent is one where nobody is sharing the complete file. Without seeds, finishing the download is impossible.

Flip the **Remove seedless torrents older than** switch and set the waiting time (e.g. `24 hours`).

> 💡 A **seed** is someone who already downloaded the whole file and keeps uploading it. If a torrent has zero seeds you will never complete the download — like trying to copy a book nobody has any more.

### Completed torrents are never touched

Torrents that finished downloading and are seeding (states `uploading`, `stalledUP`, `pausedUP`, `checkingUP`, `queuedUP`) are out of the guardian's scope. It neither removes nor reprioritizes anything in them.

### File priorities

When a torrent has several kinds of file, the guardian adjusts download priority automatically:

| File type | Default priority | What happens |
|-----------|-----------------|--------------|
| Media files (`.mkv`, `.mp4`, etc.) | **7 — maximum** | Downloaded first |
| Auxiliary files (`.nfo`, `.srt`, `.jpg`, `.png`, `.txt`, `.sub`, `.idx`) | **1 — normal** | Downloaded afterwards |
| Any other file | **0 — do not download** | Never reach the disk |

This makes the movie or episode start downloading sooner and avoids useless files — including unwanted attachments like `.url` and `.lnk`, which aren't on the dangerous list but aren't wanted either.

The scale qBittorrent accepts is **not continuous**. The valid values are:

| Value | Meaning |
|-------|---------|
| `0` | Do not download |
| `1` | Normal |
| `6` | High |
| `7` | Maximum |

> ⚠️ Values like `2`, `3`, `4` or `5` are rejected by qBittorrent with an HTTP 400 error. The three priority fields in the panel are dropdowns, so you can only pick valid values.

---

## Understanding the logs

qbit-guardian records what it does. You can read the logs in two ways:

- **Docker:** `docker logs qbit-guardian`
- **Manual install:** directly in the terminal running the program

### Log levels

Controlled by the `LOG_LEVEL` environment variable:

| Level | What it shows |
|-------|--------------|
| `ERROR` (default) | Errors and removals only |
| `INFO` | A summary of each check |
| `VERBOSE` | Every action, per torrent |
| `DEBUG` | Everything, including HTTP calls |

> 💡 The default is quiet on purpose. If you are investigating a behaviour, raise it to `INFO` or `VERBOSE` temporarily.

### Common messages

Log messages are in Portuguese:

| Log message | What happened |
|-------------|---------------|
| `Verificacao #12: 30 torrents, 2 novos, 1 stalled removidos, 0 removidos do historico` | Summary of one cycle (`INFO` level). |
| `Arquivos perigosos: ['.exe'] — Removendo e Bloqueando` | The torrent contained an `.exe` and was removed. If Sonarr/Radarr are configured, the release was blocklisted and a new search started. |
| `Nenhum arquivo de midia valido — Removendo e Bloqueando` | The torrent had no file with the configured media extensions. |
| `stalled (stalledDL) por >6h — REMOVIDO` | The torrent had been stalled for over 6 hours. |
| `0 seeds — REMOVIDO` | The torrent had no seeds for the configured time. |
| `sem metadados — sera reavaliado no proximo ciclo` | A magnet still fetching its file list. It comes back next cycle instead of being marked processed. |
| `otimizado (3 arquivos de midia priorizados)` | Download priorities were adjusted. |
| `qBittorrent indisponivel (...) — nova tentativa em 120s` | Lost contact with qBittorrent. Retrying. |
| `qBittorrent inacessivel, reconectando...` | Transport error during operation. Entering retry. |
| `prioridade de arquivo invalida: 4` | One of the priority fields has a value outside the accepted scale. Fix it in the panel. |

---

## Forcing a manual check

If you want the guardian to check torrents right now, without waiting for the interval, use the **Force check** button on the configuration page.

Or from the command line:

```bash
curl -X POST http://your-server:5000/api/trigger -u username:password
```

This is useful for testing that everything works after configuring.

---

## Tips and good practices

- **Change the generated password.** The one from the log is for first access; pick your own via the user icon.
- **Test without notifications first.** Let the guardian run quietly for a few days. Once you trust its behaviour, turn notifications on.
- **A 5-minute interval is plenty.** For home use, checking every 300 seconds is fast enough. You don't need 10 seconds — you won't notice a difference and it just burns resources.
- **Keep the dangerous extensions up to date.** New file types used to spread viruses show up from time to time.
- **If you use Sonarr/Radarr, take advantage of the integration.** Filling in the fields lets the guardian blocklist bad releases and find alternatives automatically.
- **Back up the `config` folder.** It's a single JSON file — copying it is enough.

---

## Need help?

- Read the [FAQ](FAQ.md) for common questions.
- See the [Installation Guide](INSTALL.md) if you need to install from scratch.
- Problems, suggestions and contributions: [project repository](https://github.com/iHumberto/qbit-guardian).

# ONPE Live Tracker - Peru 2026

A small web page to follow the ONPE vote count for Peru's 2026 presidential runoff in real time. A Python process checks the public count API every few minutes, keeps the history, and serves it as data. The page reads that data and draws how the result moves, right in the browser.

I built it so I could see how the count changes minute by minute in the days following the election, without reloading the official site over and over. It started out as a quick project that I developed in less than an hour.

## Live demo

A live version using a custom domain is available at **[peru2026.dennishnf.com](https://peru2026.dennishnf.com/)**. Note that it is only active during the election counting period.

## What it shows

Three charts that share the same time axis:

1. The valid vote percentage of the two candidates, with the 50% line for reference.
2. How much the gap moves between checks, so you can see who went up each update.
3. The absolute gap between them in percentage points.

There are three views you switch with buttons: last 12 hours, last 24 hours, and last 3 days, each with its own resolution. All times are shown in Peru time (UTC-5), even if you open it from another country.

## Requirements

* Python 3.9 or newer
* One dependency, curl_cffi, listed in requirements.txt

## Run it

```
pip install -r requirements.txt
python servidor_local.py
```

Then open http://localhost:8000 in your browser. By default it checks the ONPE API once a minute.

Options:

```
python servidor_local.py 5                # minutes between checks (positional)
python servidor_local.py --intervalo 5    # same thing as a flag (-i also works)
python servidor_local.py --port 9000      # use another port
python servidor_local.py 5 --port 9000    # combine them
```

The interval is the number of minutes between each query to ONPE. You can pass it
as a bare number (`python servidor_local.py 5`) or with `--intervalo` / `-i`; if you
pass nothing it defaults to 1 minute.

The history is saved in onpe_historial.json, so restarting the server does not lose what you already collected.

## Share it with a public URL

To view it from outside without opening router ports I use a Cloudflare tunnel. For a temporary URL:

```
cloudflared tunnel --url http://localhost:8000
```

If you have a domain on Cloudflare you can use a named tunnel and keep a fixed address (for example onpe.yourdomain.com) that stays the same between restarts.

## Files

* onpe_tracker.py: talks to the ONPE API and handles the history.
* servidor_local.py: runs the checks in the background and serves the page and the /api/datos endpoint.
* index.html: the page, draws the charts with Chart.js.
* onpe_historial.json: the saved history of each check.
* requirements.txt: dependencies.

## Notes

The data comes from ONPE's public API and its format can change without notice. The page refreshes on its own every couple of minutes, so there is no need to reload. It is meant to run on a laptop during election days.

## Running with the custom URL

This is how I run the live version on its own address. You need two terminals open at the same time, and the named tunnel and domain set up once beforehand on Cloudflare.

In the first terminal, start the server (optionally pass the check interval in minutes):

```
python servidor_local.py 5
```

In the second terminal, start the named tunnel:

```
cloudflared tunnel run peru2026
```

Keep both terminals running. The server answers on port 8000 and the tunnel points peru2026.dennishnf.com to it. If you close either one the site goes down. Once the tunnel and the domain are set up, these two commands are all you need to bring it back up.

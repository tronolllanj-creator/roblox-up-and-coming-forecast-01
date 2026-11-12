# Roblox Up-and-Coming Forecast

This entry predicts Roblox’s US computer Up-and-Coming chart top 10 for the scoring window.

`main.py` reads `task.json` and `history.ndjson`, then writes `forecast.json`. It ranks current chart games using recent rank momentum, player-count growth, recent Top Trending/Top Playing Now appearances, and age-out risk for the 28-day Up-and-Coming eligibility window. Each place gets a shifted softmax across leading candidates, reserving 20% unnamed probability for newcomers.

Run locally:

```sh
MAKEFUN_INPUT_DIR=/path/to/input \
MAKEFUN_OUTPUT_DIR=/tmp/roblox-forecast \
python3 main.py
```

The program uses only Python’s standard library, makes no network calls, and is deterministic.

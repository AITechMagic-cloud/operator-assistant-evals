# Results

One pair of files per run, named by date: `YYYY-MM-DD.json` holds every answer, citation and failure reason; `YYYY-MM-DD.md` holds the counts and the list of failures. Each run records the endpoint and the demo commit under test.

Runs are published as they happened. Failed items stay in the file. A run is not repeated until it passes, and numbers are not rounded up.

The first run is `2026-10-21`, made by the owner against https://demo.aitechmagic.com with demo commit `e249db4`: 66 of 71 passed. Its five failures are explained in the main README.

The second run is `2026-11-02`, against a local copy of the demo at commit `ad0e473`: 88 of 89 passed across four manuals. Its one failure is explained in the main README.

# Private GitHub PAPER research archive

QuantNifty continues to collect live market data while operating in **PAPER mode only**.
Every five minutes, the application packages newly appended option-chain snapshots and
decision/execution audit events, redacts credential-like fields, and uploads the batch
to a separately configured **private** GitHub repository. A daily report is uploaded
after market close. The report summary is included; raw arrays are not duplicated because
the raw/audit streams have already been uploaded incrementally.

## Required setup

1. Use the private GitHub repository [Mathematical-Trading-Research](https://github.com/Sabari2811/Mathematical-Trading-Research)
   under your account. Its repository identifier is
   `Sabari2811/Mathematical-Trading-Research`. Do not use the public TechGeek repository for trading records.
2. Create a fine-grained personal access token limited to this private repository,
   with **Contents: Read and write** permission. Do not paste the token into chat or commit it.
3. On your Windows machine, copy `.env.example` to `.env` (if not already done) and set:

   ```dotenv
   TRADING_MODE=PAPER
   GH_RESEARCH_REPOSITORY=Sabari2811/Mathematical-Trading-Research
   GH_RESEARCH_TOKEN=YOUR_FINE_GRAINED_TOKEN
   GH_RESEARCH_SYNC_INTERVAL_SECONDS=300
   ```

4. Install dependencies and start the app as usual. No new broker permission is required.
   The application prints `PRIVATE RESEARCH UPLOAD` after a successful batch.
5. Check the private repository under `batches/YYYY-MM-DD/`. Each ZIP contains
   `raw/YYYY-MM-DD.jsonl` and `audit/YYYY-MM-DD.jsonl` deltas plus a manifest.
   After market close, the daily report summary is added as another batch.

## What is captured

- Raw option-chain snapshots as received, with local receive timestamps and expiry.
- Candidate acceptance/rejection, strategy reasons, risk/microstructure gate evidence.
- Position quote observations and exit decision reasons.
- PAPER entry/exit evidence and daily report summaries.

The existing audit event schema is preserved. If a reason is absent from the engine,
the system does not fabricate one. Provider event timestamps are not claimed where only
local receive time is available.

## Safety and limitations

- Upload refuses to run unless `TRADING_MODE=PAPER`; it also verifies the destination
  repository reports `private: true` before every upload.
- This feature does not enable, submit, cancel, or reconcile broker orders.
- Keep the persistent entry kill switch ON if unresolved order records or recovery
  warnings exist. Research upload does not override it.
- Only raw, audit and report files are included. Credentials are redacted; local order
  journal, open-position state, kill-switch state and `.env` are never uploaded.
- Each upload is a ZIP limited to 20 MiB. The upload cursor advances only after GitHub
  confirms success, so a failed upload is retried on a later cycle.
- Upload is best-effort: a GitHub/network failure does not interrupt market monitoring
  or change risk/execution state. The data remains in local `.quantnifty` until uploaded.
- GitHub's Contents API stores each batch as a repository object. Monitor repository
  size; for high-volume tick/depth streams, move to object storage or Git LFS rather
  than allowing unlimited Git history growth.
- The collector runs on your Windows machine; GitHub stores the uploaded research
  batches. This is not a cloud-hosted market feed service.


## Backfill and stopping the PAPER app

- The uploader automatically scans all locally present ISO-date folders/files and processes the oldest date with pending bytes first. It does not require the market to be open to upload existing local data.
- The app continues retrying pending batches every configured interval even after market close, as long as the process remains running. A single sync invocation uploads at most five chunks. Each JSONL chunk ends on a complete record boundary; very large individual records are still subject to the 20 MiB compressed archive cap.
- Stopping the local application stops collection and scheduled uploads, but does not delete local data or saved upload cursors. Start it again in PAPER mode to resume pending uploads. Use Ctrl+C once and allow normal shutdown; do not force-kill while files are being written.
- The sync is best-effort and does not affect strategy decisions, order execution, risk controls, the kill switch or broker reconciliation.

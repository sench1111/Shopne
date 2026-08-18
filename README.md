# Sench Sanch Sales Tracker

A small web app for a shop owner to record sales and see live totals — including profit
or loss — no terminal required.

## How it works

- **Backend (`app.py`)** — a Flask app that keeps the day's transactions in a Python list of
  dictionaries (no database needed for this assignment) and exposes a small JSON API:
  - `POST /api/sale` — add a sale `{ item, unit_price, quantity }`
  - `GET  /api/summary` — current totals + transaction list
  - `GET  /api/report` — downloads an HTML sales report
  - `POST /api/reset` — clears the day's transactions
- **Frontend (`templates/index.html`)** — plain HTML/CSS/JS. The form calls `/api/sale` and
  never computes totals itself; all math happens on the backend using loops and dictionaries
  (`compute_summary()` in `app.py`). The page re-fetches `/api/summary` after every action and
  every 8 seconds, so totals stay live and a status banner shows if the server can't be reached.
- **Profit tracking** — each sale can optionally include a cost price. The backend works out
  profit per line (`selling price - cost price`) × quantity, and the dashboard shows a running
  "Bottom Line" card plus a live chart of cumulative profit across the day's transactions, so
  you can see at a glance whether the day is trending toward a profit or a loss.

## Logging in

The app now has three roles, in a clear hierarchy, and per-account passwords (hashed, not
stored in plain text):

- **Employee** — front-line access: record sales, download reports, reset the day, change
  their own password.
- **Manager** — everything an employee can do, plus a **Team** dashboard: add or remove
  employee accounts, and see what the team has been doing (their sales activity and sign-ins).
  A manager can never see the owner's own activity, and can't reach Backstage.
- **Owner** — everything, for everyone: the **Backstage** panel manages accounts at *any*
  level (employee, manager, or owner), edits shop-wide settings (shop name, currency), and
  shows the full sign-in and activity history across the whole shop, including managers.

Default accounts (change these before sharing the project — see `users` near the top of `app.py`):

| Username | Password | Role |
|---|---|---|
| `employee` | `staff123` | employee |
| `manager` | `sales123` | manager |
| `sench` | `backstage123` | owner |

Sign in as `manager` to reach **Team** (linked in the top-right nav for managers and the
owner). Sign in as `sench` to reach **Backstage** (owner only) — from there you can add
accounts at any level, change any account's role, remove accounts, and see the complete
sign-in and activity history for everyone, including managers.

Any signed-in user can change their own password from the **Password** link in the top nav.

## Running it locally

```bash
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

## Bonus: Git & GitHub

```bash
git init
git add .
git commit -m "Daily sales tracker: Flask backend + live-updating frontend"
```

Create an empty repo on GitHub, then:

```bash
git remote add origin https://github.com/<your-username>/<repo-name>.git
git branch -M main
git push -u origin main
```

## Bonus: Deploying (Render example)

1. Push the project to GitHub (above).
2. On [render.com](https://render.com), create a **New Web Service** and connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app` (already set in the included `Procfile`)
5. Deploy — Render gives you a live URL to share.

The same `Procfile` also works on Railway and Fly.io with minimal extra config.

## Known limitations

- **Data is in-memory only.** The `transactions` list (and the `users` and `login_log` lists)
  live in RAM, not on disk. Every sale, account, and login record is lost the moment the Flask
  process restarts — a crash, a manual restart, or a redeploy on a host that spins down when
  idle. That's an intentional, reasonable scope for this assignment, which is about using
  variables, lists, dictionaries, and control flow rather than building a database layer — but
  it means this is **not** ready to be a real shop's permanent sales record as it stands.
- **The straightforward upgrade path**, if this were to go further: swap the `transactions` list
  for a small SQLite database (Python's `sqlite3` module needs no extra install), or as a
  lighter first step, load/save the list to a JSON file on disk at startup/after each change.
  Same idea applies to `users` and `login_log`.
- **Currency is labeled GHS by default** in the report; the owner can change this from Backstage,
  or you can edit the default in `app.py`.

## Notes for extending it

- Currency is labeled GHS in the report; change that string in `app.py` if not needed.

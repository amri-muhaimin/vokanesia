# VocLink Demo

An English web-based platform designed for Indonesia that connects **students**, **vocational schools**, and **industries**.
This is a small **local-first demo** with dummy data, curriculum items, industry role needs, student profiles, and a simple matching page.

## Theme
The UI is updated to a **TU Dresden–inspired** color theme (TU Blue as primary, with light/middle blue accents).

## What’s inside
- School curriculum view (competencies + target levels)
- Industry roles with required/preferred competencies
- Student profiles with skills + evidence links
- Matching:
  - **Role → best students**
  - **Student → best roles**
- SQLite database auto-created and auto-seeded on first run

## Run locally (Python – recommended)
### 1) Prerequisites
- Python 3.10+ installed

### 2) Setup
Open a terminal in this folder and run:

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
python app.py
```

Then open:
- http://127.0.0.1:5000

## Dev utilities
- Reset + reseed the database (dev only):
  - http://127.0.0.1:5000/admin/reset

## Notes
- This is a demo starter you can extend (authentication, approvals, logbooks, messaging, etc.)

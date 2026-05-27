# Local Development Setup — Windows 11 + PowerShell

## Prerequisites

Before starting, make sure you have these installed:

- **Python 3.13** — download from [python.org](https://www.python.org/downloads/). During install, check "Add Python to PATH".
- **VS Code** — download from [code.visualstudio.com](https://code.visualstudio.com/)
- **Git** — download from [git-scm.com](https://git-scm.com/)

---

## First-time setup

Do this once after cloning the repo.

1. Open VS Code. Go to **File → Open Folder** and select the project folder.

2. Open the terminal with **Ctrl + `** (that's the backtick key, top-left of keyboard). Confirm the terminal says **PowerShell** in the dropdown at the top-right of the terminal panel.

3. Activate the virtual environment:
   ```powershell
   venv\Scripts\activate
   ```
   If you get an error, run this first: `python -m venv venv`, then repeat the command above.

4. Confirm the prompt now shows **(venv)** at the start of the line. If it doesn't, stop and see Troubleshooting below.

5. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```

6. Install the Playwright browser:
   ```powershell
   python -m playwright install chromium
   ```

---

## Every session

Run these every time you open VS Code to work on the project:

1. Open VS Code and open the project folder.
2. Open the terminal (**Ctrl + `**).
3. Activate the virtual environment:
   ```powershell
   venv\Scripts\activate
   ```
4. Pull the latest code from GitHub:
   ```powershell
   git pull origin main
   ```

---

## Running the scraper

Fetches current prices from Amazon and roaster sites and saves them to the database:

```powershell
python scrapers/price_scraper.py
```

---

## Seeding test data (for alert testing)

Inserts 30 days of fake price history so you can test the alert system without waiting for real price drops. The first product in the list will have its latest price set 15% below its 7-day average to trigger the alert threshold:

```powershell
python tests/seed_test_data.py
```

---

## Running the test suite

Validates the scraper and database are working correctly. Prints PASS or FAIL for each check:

```powershell
python tests/test_local.py
```

Exit code 0 = all checks passed. Exit code 1 = one or more checks failed.

---

## Generating a mock review (no API key needed)

Generates a draft review using the mock mode (no API call made):

```powershell
python scrapers/generate_review.py lavazza-super-crema --mock
```

---

## Checking the database manually

Print the 10 most recent price records:

```powershell
python -c "import sqlite3; conn = sqlite3.connect('data/prices.db'); print([r for r in conn.execute('SELECT product_id, price, checked_at FROM price_history ORDER BY checked_at DESC LIMIT 10')])"
```

---

## Pushing changes to GitHub

```powershell
git add .
git commit -m "description of what you changed"
git push origin main
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| venv not activating | Run `python -m venv venv` then `venv\Scripts\activate` |
| git push rejected | Run `git pull origin main` then `git push origin main` |
| Missing packages | Run `pip install -r requirements.txt` |
| Playwright browser missing | Run `python -m playwright install chromium` |

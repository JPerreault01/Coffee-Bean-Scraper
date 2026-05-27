# Coffee Bean Price Tracker & Review Site

## Repository
https://github.com/JPerreault01/Coffee-Bean-Scraper

## Project structure
Coffee-Bean-Scraper/
├── scrapers/
│   ├── price_scraper.py
│   ├── generate_review.py
│   └── products.json
├── alerts/
│   └── send_alerts.py
├── wordpress-plugins/
│   └── coffee-price-chart/
│       ├── coffee-price-chart.php
│       └── README.md
├── .env.example
├── .gitignore
├── setup.sh
└── README.md

## Rules
- Python 3.13 project
- Follow PEP 8 style guidelines
- All functions must have docstrings
- Write pytest unit tests for all new functions
- Never push directly to main branch
- Never commit .env, *.db, *.log, /data/, /drafts/
- Always end responses with git commands to commit the change

## Git rules
- State correct file path at top of every file
- Group multi-file changes into one logical commit
- Never commit secrets — use .env.example with empty values only
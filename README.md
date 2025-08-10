## RentSmart MCP

This repository contains a minimal Multi‑Channel Plugin (MCP) service for **RentSmart**,
an AI‑powered WhatsApp bot that generates rental agreements and receipts on the fly.

### Features

* **/validate** – Performs a simple bearer token check and returns a dummy phone number.  
  Update the token in `app/main.py` to secure your deployment.
* **/tool/generate_agreement** – Accepts rental agreement details, fills a text template,
  converts it into a PDF and serves it back via a public link under `/files/agreements`.
* **/tool/generate_rent_receipt** – Creates a PDF rent receipt with the specified
  particulars and exposes it under `/files/receipts`.
* **/tool/stamp_duty_info** – Returns state‑specific stamp duty information for quick
  reference.  A default set of values has been provided for demonstration and can
  easily be expanded to include all Indian states.
* **/health** – A simple heartbeat endpoint returning `{"status":"ok"}`.

### Directory Structure

```
rentsmart_mcp/
├── app/
│   ├── __init__.py
│   ├── main.py             # FastAPI application
│   └── templates/
│       ├── agreement_template.txt
│       └── receipt_template.txt
├── files/                  # Generated PDFs will be saved here
├── requirements.txt        # Python dependencies
└── README.md
```

### Quick Start

```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Navigate to <http://localhost:8000/health> to verify the server is running.

### Deployment

Deploy on any platform that supports FastAPI: Render, Railway, Vercel or your own
server.  Make sure to expose the service over HTTPS for compatibility with Puch AI.

### Puch AI Integration

After deployment, connect your MCP service to Puch AI using the `/mcp connect` command
in your WhatsApp chat.  Replace the URL and token below with your deployment:

```
/mcp connect https://YOUR-DEPLOYED-URL your_test_token
```

On successful connection you’ll see the available tools (`generate_agreement`,
`generate_rent_receipt` and `stamp_duty_info`).

### Customisation

* **Templates** – Edit the files in `app/templates` to customise the layout and wording
  of your generated agreements and receipts.  Placeholders in curly braces
  (e.g. `{landlord}`, `{rent}`) will be replaced with the values supplied in
  the JSON request.
* **Stamp Duty Data** – Modify the `STAMP_DUTY_DATA` dictionary in
  `app/main.py` to reflect accurate state‑wise stamp duty charges and links.  This
  example contains a few states for illustration.
* **Token Validation** – Change the `VALID_TOKEN` constant in `app/main.py` to
  enforce your own bearer token.  In production you should implement a proper
  authentication mechanism.

### License

This starter is provided as‑is for hackathon or educational use.  Feel free to
modify and extend it to suit your needs.
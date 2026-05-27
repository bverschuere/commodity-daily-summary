# Daily Commodity Market Summary Generator

Automated daily pipeline that generates a data-driven commodity market summary from Barchart RSS feeds using Claude AI analysis. Runs weekdays at 23:50 UTC with an 18:00 UTC cutoff for article collection.

## Features

- **Automated RSS Scraping**: Fetches commodity articles from Barchart RSS feed
- **Full Article Extraction**: Uses Playwright to extract complete article text
- **Claude AI Analysis**: Generates professional market summary with quantified price moves
- **Email Distribution**: Sends formatted HTML email via Gmail API
- **Data Persistence**: Saves summary to JSONBin for integration with other tools
- **GitHub Actions**: Scheduled daily execution

## Setup

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/commodity-daily-summary.git
cd commodity-daily-summary
pip install -r requirements.txt
playwright install chromium
```

### 2. Local Environment Variables

Create a `.env` file:

```bash
export ANTHROPIC_API_KEY='your-api-key'
export JSONBIN_BIN_ID='your-bin-id'
export JSONBIN_MASTER_KEY='your-master-key'
```

### 3. Gmail API Setup

```bash
python3 << 'EOF'
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/gmail.send']
flow = InstalledAppFlow.from_client_secrets_file('gmail_credentials.json', SCOPES)
creds = flow.run_local_server(port=0)

import pickle
with open('gmail_token.pickle', 'wb') as token:
    pickle.dump(creds, token)
print('✅ Gmail authorized!')
EOF
```

### 4. Run Locally

```bash
source .env
python3 commodity_summary.py
```

## GitHub Actions Setup

### Secrets Required

Add these GitHub Secrets in your repository:

| Secret | Value |
|--------|-------|
| `ANTHROPIC_API_KEY` | Your Claude API key |
| `JSONBIN_BIN_ID` | Your JSONBin bin ID |
| `JSONBIN_MASTER_KEY` | Your JSONBin master key |
| `GMAIL_TOKEN` | Base64-encoded `gmail_token.pickle` |

**To encode the gmail token:**

```bash
base64 -i gmail_token.pickle | pbcopy  # macOS
cat gmail_token.pickle | base64 | xclip -selection clipboard  # Linux
```

### Workflow File

Place `.github/workflows/daily-commodity-summary.yml` in your repo. The workflow:

- Runs at **23:50 UTC** (weekdays only)
- Fetches articles published after **18:00 UTC** from the previous day
- Generates summary and sends email
- Can be manually triggered via "Actions" tab

## Configuration

Edit `commodity_summary.py`:

- **CUTOFF_HOUR**: Article collection start time (default: 18 UTC)
- **GMAIL_RECIPIENT**: Email destination (default: bverschuere@gmail.com)
- **RATE_LIMIT_DELAY**: Delay between article fetches (default: 0.5s)

## Output

### Email Format

- **Header**: "LIMINAL COMMODITIES DAILY"
- **Sections**: ENERGY, METALS, SOFT AGs, AGRICULTURAL
- **Format**: `**Commodity**: Price | Daily Return% | Primary Driver`
- **Footer**: Generated timestamp + article count

### JSONBin Storage

```json
{
  "date": "05/27/2026",
  "timestamp": "2026-05-27T23:50:15.123456Z",
  "summary": "# Full commodity summary...",
  "article_count": 17
}
```

## Architecture

```
Barchart RSS Feed
    ↓
Fetch RSS Entries (filter by 18:00 UTC cutoff)
    ↓
Playwright Full Article Scraping (headless Chrome)
    ↓
Claude API Analysis (claude-opus-4-6)
    ↓
Generate Email + Save to JSONBin
    ↓
Gmail API Distribution
```

## Troubleshooting

### SSL Certificate Error

The Barchart endpoint may require certificate handling. Ensure Playwright is up to date:

```bash
pip install --upgrade playwright
playwright install chromium
```

### Gmail API Errors

Regenerate the token if authorization fails:

```bash
rm gmail_token.pickle
python3 gmail_auth.py  # Re-authorize
```

### JSONBin Errors

Verify credentials in GitHub Secrets match your JSONBin account.

## Requirements

- Python 3.9+
- Anthropic API key
- Google OAuth credentials
- JSONBin account
- GitHub account (for Actions)

See `requirements.txt` for package versions.

## License

Proprietary - Liminal Capital

## Contact

info@liminal-capital.com

#!/usr/bin/env python3
import os
import sys
import time
import base64
import pickle
import re
from datetime import datetime, timedelta
import requests
import feedparser
from playwright.sync_api import sync_playwright
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from email.mime.text import MIMEText

BARCHART_RSS_URL = "https://www.barchart.com/news/rss/commodities"
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
JSONBIN_BIN_ID = os.getenv("JSONBIN_BIN_ID")
JSONBIN_MASTER_KEY = os.getenv("JSONBIN_MASTER_KEY")

CUTOFF_HOUR = 18
RATE_LIMIT_DELAY = 0.5
GMAIL_RECIPIENT = "bverschuere@gmail.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


class CommoditySummaryGenerator:
    def __init__(self):
        self.articles = []
        self.summary = None
        self.playwright = None
        self.browser = None
        self.gmail_service = None

    def validate_env(self):
        if not ANTHROPIC_API_KEY:
            print("❌ Missing: ANTHROPIC_API_KEY")
            return False
        print("✅ Environment configured")
        return True

    def init_gmail_service(self):
        """Initialize Gmail API service"""
        print("🔐 Initializing Gmail service...")
        try:
            creds = None
            if os.path.exists('gmail_token.pickle'):
                with open('gmail_token.pickle', 'rb') as token:
                    creds = pickle.load(token)
            
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            
            self.gmail_service = build('gmail', 'v1', credentials=creds)
            print("✅ Gmail service initialized")
            return True
        except Exception as e:
            print(f"❌ Gmail service error: {str(e)}")
            return False

    def init_playwright(self):
        print("🌐 Starting browser...")
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)

    def fetch_rss(self):
        print("📰 Fetching RSS feed...")
        try:
            response = requests.get(BARCHART_RSS_URL, timeout=10, headers=HEADERS)
            response.raise_for_status()
            feed = feedparser.parse(response.content)

            if not feed.entries:
                print("⚠️ No articles found")
                return False

            now = datetime.utcnow()
            cutoff = now.replace(hour=CUTOFF_HOUR, minute=0, second=0, microsecond=0)

            for entry in feed.entries:
                try:
                    pub_date = datetime(*entry.published_parsed[:6])
                    if cutoff <= pub_date <= now:
                        self.articles.append({
                            "title": entry.get("title", ""),
                            "link": entry.get("link", ""),
                            "author": entry.get("author") or entry.get("creator", "Unknown"),
                            "pubDate": entry.get("published", ""),
                            "description": entry.get("summary", ""),
                            "isoDate": pub_date.isoformat() + "Z",
                        })
                except (AttributeError, TypeError):
                    continue

            self.articles.sort(key=lambda x: x["isoDate"], reverse=True)
            print(f"✅ Found {len(self.articles)} articles")
            return len(self.articles) > 0

        except requests.RequestException as e:
            print(f"❌ RSS fetch failed: {str(e)}")
            return False

    def fetch_article_content(self, article):
        try:
            page = self.browser.new_page()
            page.goto(article["link"], wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(2000)
            
            content_selectors = [
                "article",
                "[class*='article-body']",
                "[class*='story-body']",
                "[class*='content-body']",
                "main",
            ]
            
            text = ""
            for selector in content_selectors:
                try:
                    element = page.query_selector(selector)
                    if element:
                        text = element.text_content()
                        break
                except:
                    continue
            
            page.close()
            
            if text:
                text = text.strip()
                text = " ".join(text.split())
                return text[:4000]
            else:
                return article.get("description", "")

        except Exception as e:
            return article.get("description", "")

    def fetch_all_articles(self):
        print(f"📥 Fetching full content for {len(self.articles)} articles...")
        for idx, article in enumerate(self.articles, 1):
            print(f"  [{idx}/{len(self.articles)}] {article['title'][:50]}...", end=" ")
            sys.stdout.flush()
            article["full_text"] = self.fetch_article_content(article)
            print("✅")
            if idx < len(self.articles):
                time.sleep(RATE_LIMIT_DELAY)
        print("✅ All articles fetched")
        return True

    def format_for_claude(self):
        text = f"COMMODITY MARKET SUMMARY - {datetime.now().strftime('%B %d, %Y')}\n"
        text += f"Generated at {datetime.now().strftime('%I:%M %p UTC')}\n"
        text += f"Total Articles: {len(self.articles)}\n\n"
        text += "=" * 80 + "\n\n"

        for idx, article in enumerate(self.articles, 1):
            text += f"{idx}. {article['title']}\n"
            text += f"   Author: {article['author']}\n"
            iso_time = datetime.fromisoformat(article['isoDate'].rstrip('Z'))
            text += f"   Published: {iso_time.strftime('%I:%M %p UTC')}\n"
            text += f"   {article['full_text']}\n\n"
            text += "-" * 80 + "\n\n"

        return text

    def generate_summary(self):
        print("🤖 Sending to Claude...")
        formatted_text = self.format_for_claude()

        payload = {
            "model": "claude-opus-4-6",
            "max_tokens": 4000,
            "system": "You are a commodity analyst for a macro hedge fund. Create a data-driven daily market summary. Lead with QUANTIFIED price moves (%, cents, dollars, contract months). Extract specific numbers. Identify PRIMARY macro drivers (geopolitics, weather, USD, crude, supply). Organize by commodity sector. Highlight inter-commodity correlations and divergences. Keep actionable for portfolio managers. Back every statement with specific price data or evidence.",
            "messages": [{
                "role": "user",
                "content": f"Generate a data-driven summary:\n\n{formatted_text}\n\nAt the end, create a SUMMARY organized by commodity class using simple text format (NOT markdown tables):\n\n## ENERGY\n## METALS\n## SOFT AGs\n## AGRICULTURAL\n\nFor each commodity, use this format:\n**Commodity Name**: Price | Daily Return% | Primary Driver\n\nExample:\n**WTI Crude Oil**: $89.88 | -3.38% | US-Iran peace optimism; 5-week low\n**RBOB Gasoline**: $3.10 | -1.58% | Crude oil drag; 6-week low\n\nFor ENERGY include: Oil, Natural Gas, Gasoline\nFor METALS include: Gold, Silver, Copper\nFor SOFT AGs include: Corn, Soybeans, Wheat\nFor AGRICULTURAL include: Cocoa, Sugar, Coffee, Cotton, Hogs, Cattle\n\nNO MARKDOWN TABLES. Use the simple text format above."
            }]
        }

        headers = {
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json"
        }

        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            self.summary = result.get("content", [{}])[0].get("text", "Failed")
            print("✅ Summary generated")
            return True
        except requests.RequestException as e:
            print(f"❌ Claude API error: {str(e)}")
            return False

    def output_summary(self):
        print("\n" + "=" * 80)
        print("📊 COMMODITY MARKET SUMMARY")
        print("=" * 80 + "\n")
        print(self.summary)
        print("\n" + "=" * 80)

    def clean_summary_for_email(self):
        """Remove redundant headers and format summary for email"""
        lines = self.summary.split('\n')
        cleaned_lines = []
        
        for line in lines:
            # Skip redundant headers
            if any(x in line for x in [
                "# DAILY COMMODITY MARKET SUMMARY",
                "# COMMODITY MARKET DAILY SUMMARY",
                "**Generated:",
                "COMMODITIES MARKET ANALYSIS"
            ]):
                continue
            
            # Skip separator lines
            if line.strip() == "---":
                continue
            
            # Format section headers (## for ENERGY, METALS, etc)
            if line.startswith("## "):
                section_name = line.replace("## ", "").strip()
                cleaned_lines.append(f"<div style='margin-top: 25px; margin-bottom: 15px;'><strong style='font-size: 18px; color: #0a2559; text-transform: uppercase;'>{section_name}</strong></div>")
                continue
            
            # Format subsection headers (###)
            if line.startswith("### "):
                section_name = line.replace("### ", "").strip()
                cleaned_lines.append(f"<div style='margin: 20px 0 15px 0;'><strong style='font-size: 16px; color: #0a2559;'>{section_name}</strong></div>")
                continue
            
            # Format commodity lines with bold
            if line.startswith("**") and ":" in line:
                line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
                cleaned_lines.append(f"<p style='margin: 10px 0; line-height: 1.7; font-size: 13px; color: #333;'>{line}</p>")
            elif line.strip() == "":
                cleaned_lines.append("")
            else:
                # Regular text - format bold
                line = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', line)
                if line.strip():
                    cleaned_lines.append(f"<p style='margin: 12px 0; line-height: 1.7; font-size: 14px; color: #333;'>{line}</p>")
        
        return "\n".join(cleaned_lines)

    def generate_email_html(self):
        """Generate HTML email with commodity summary"""
        cleaned_summary = self.clean_summary_for_email()
        timestamp_str = datetime.now().strftime("%I:%M %p UTC")
        article_count = len(self.articles)
        
        html = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>LIMINAL COMMODITIES DAILY</title>
</head>
<body style="margin: 0; padding: 0; font-family: Arial, Helvetica, sans-serif;">

<table cellpadding="0" cellspacing="0" border="0" width="100%">
<tr><td style="background-color: #0a2559; padding: 20px;">
<h1 style="margin: 0; font-size: 28px; font-weight: bold; color: white; letter-spacing: 1px;">LIMINAL COMMODITIES DAILY</h1>
</td></tr>

<tr><td style="background-color: #f5f5f5; padding: 20px;">

<table cellpadding="0" cellspacing="0" border="0" width="100%">
<tr><td style="font-family: Arial, Helvetica, sans-serif; padding: 0 15px; font-size: 14px; line-height: 1.8; color: #333;">
{cleaned_summary}
</td></tr>
</table>

<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top: 30px; margin-bottom: 20px;">
<tr><td style="padding: 15px; font-family: Arial, Helvetica, sans-serif; font-size: 9px; line-height: 1.4; color: #555555;">
<strong>DISCLAIMER:</strong> This document is for informational purposes only and does not constitute investment advice. The views expressed are subject to change without notice. Past performance is not indicative of future results. All investments involve risk, including potential loss of principal. The information provided is believed to be reliable but accuracy is not guaranteed. Readers should conduct their own research and consult with qualified advisors before making investment decisions. The authors may have positions in securities mentioned. This document may not be reproduced or distributed without written consent. By reading this document, you acknowledge these terms.
</td></tr>
</table>

<table cellpadding="0" cellspacing="0" border="0" width="100%" style="margin-top: 20px; padding-top: 15px; border-top: 1px solid #ddd;">
<tr><td style="padding: 0 15px; font-family: Arial, Helvetica, sans-serif; font-size: 11px; color: #888;">
Generated {timestamp_str} | {article_count} articles analyzed
</td></tr>
</table>

</td></tr>

<tr><td style="background-color: #0a2559; padding: 15px; color: white;">
<div style="font-size: 11px; font-family: Arial, Helvetica, sans-serif; color: white;">
Liminal Capital<br>
2479 East Bayshore Road, Suite 205<br>
Palo Alto, CA 94303<br>
<a href="mailto:info@liminal-capital.com" style="color: white;">info@liminal-capital.com</a>
</div>
<div style="text-align: right; margin-top: 10px; font-family: Arial, Helvetica, sans-serif; font-weight: bold; color: white;">ALPHA REFACTORED</div>
</td></tr>

</table>

</body>
</html>"""
        return html

    def send_email(self):
        """Send email via Gmail API"""
        if not self.gmail_service:
            print("⚠️ Gmail service not initialized, skipping email")
            return False

        print("📧 Sending email via Gmail...")
        try:
            date_str = datetime.now().strftime("%B %d, %Y")
            subject = f"LIMINAL COMMODITIES DAILY — {date_str}"
            html_content = self.generate_email_html()
            
            message = MIMEText(html_content, 'html')
            message['to'] = GMAIL_RECIPIENT
            message['from'] = GMAIL_RECIPIENT
            message['subject'] = subject
            
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            send_message = {'raw': raw_message}
            
            self.gmail_service.users().messages().send(userId='me', body=send_message).execute()
            print(f"✅ Email sent to {GMAIL_RECIPIENT}")
            return True
        except Exception as e:
            print(f"❌ Email send failed: {str(e)}")
            return False

    def save_to_jsonbin(self):
        if not JSONBIN_BIN_ID or not JSONBIN_MASTER_KEY:
            print("⏭️ Skipping JSONBin (env vars not set)")
            return True

        print("💾 Saving to JSONBin...")
        data = {
            "date": datetime.now().strftime("%m/%d/%Y"),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "summary": self.summary,
            "article_count": len(self.articles),
        }

        headers = {
            "X-Master-Key": JSONBIN_MASTER_KEY,
            "Content-Type": "application/json"
        }

        try:
            response = requests.put(
                f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}",
                json=data,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            print("✅ Saved to JSONBin")
            return True
        except requests.RequestException as e:
            print(f"❌ JSONBin save failed: {str(e)}")
            return False

    def cleanup(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()

    def run(self):
        print("\n" + "=" * 80)
        print("🚀 Commodity Market Summary Generator")
        print("=" * 80 + "\n")

        start_time = time.time()

        if not self.validate_env():
            return False

        print()
        if not self.init_gmail_service():
            print("⚠️ Continuing without email (Gmail not configured)")

        print()
        if not self.fetch_rss():
            return False

        self.init_playwright()

        print()
        if not self.fetch_all_articles():
            self.cleanup()
            return False

        self.cleanup()

        print()
        if not self.generate_summary():
            return False

        self.output_summary()
        
        print()
        if self.gmail_service:
            self.send_email()
        
        print()
        self.save_to_jsonbin()

        elapsed = time.time() - start_time
        print(f"\n✅ Completed in {elapsed:.1f}s")
        print(f"📰 Articles processed: {len(self.articles)}")
        return True


def main():
    generator = CommoditySummaryGenerator()
    try:
        success = generator.run()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        generator.cleanup()
        print("\n❌ Interrupted")
        sys.exit(130)
    except Exception as e:
        generator.cleanup()
        print(f"\n❌ Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()

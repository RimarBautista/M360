import socket
import platform
import smtplib
import time
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import pytest
import pytest_asyncio
from playwright.async_api import async_playwright
from pages.login_page import LoginPage
from config.environments import get_environment

# Store browser information globally
BROWSER_NAME = "Chromium"
BROWSER_VERSION = "N/A"

@pytest_asyncio.fixture
async def page():
    global BROWSER_NAME, BROWSER_VERSION
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        BROWSER_NAME = browser.browser_type.name.capitalize()
        BROWSER_VERSION = browser.version
        page = await browser.new_page()
        yield page
        await browser.close()


@pytest_asyncio.fixture
async def logged_in_page(page):
    env = get_environment()
    await page.goto(env["url"])
    login = LoginPage(page)
    await login.login(env["username"], env["password"])
    return page


# Email Configurations
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "qa.m360automation1@gmail.com"
SENDER_PASSWORD = "sdbbqnjdbevfrmso"  # Gmail App Password
RECIPIENT_EMAILS = ["jgulinao@m360.com.ph"]

# Global metrics storage and session guard
session_start_time = 0
test_results = []
_email_already_sent = False


def format_duration(seconds: float) -> str:
    """Formats duration seconds into human-readable string (e.g., 11m 50s or 7.7s)."""
    if seconds >= 60:
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    return f"{seconds:.1f}s"


@pytest.hookimpl(tryfirst=True)
def pytest_sessionstart(session):
    global session_start_time
    session_start_time = time.time()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()

    if report.when == "call":
        # Safe extraction of params from CallSpec2 object
        callspec = getattr(item, "callspec", None)
        params = getattr(callspec, "params", {}) if callspec else {}
        row_info = params.get("row_data", {})

        # Derive Row Number based on callspec indices (1-based index)
        indices = getattr(callspec, "indices", {}) if callspec else {}
        param_index = indices.get("row_data", 0) + 1

        # Extract file path relative to execution
        spec_file_path = str(item.fspath).split("/")[-3:]
        relative_spec_file = "/".join(spec_file_path) if len(spec_file_path) >= 3 else str(item.fspath)

        recipient_to = row_info.get("to", "N/A")
        sender_id = row_info.get("sender_id", "N/A")
        telco = row_info.get("telco", "N/A")
        sender_id_flag = row_info.get("sender_id_flag", "N/A")
        is_optedout = "YES" if row_info.get("is_optedout") else "NO"
        plan_name = row_info.get("portal_plan_name", "N/A")
        remarks = row_info.get("remarks") or row_info.get("remark") or "N/A"

        test_results.append({
            "nodeid": item.nodeid,
            "spec_file": relative_spec_file,
            "row_num": param_index,
            "to": recipient_to,
            "sender_id": sender_id,
            "telco": telco,
            "sender_id_flag": sender_id_flag,
            "is_optedout": is_optedout,
            "plan_name": plan_name,
            "remarks": remarks,
            "outcome": report.outcome,
            "duration": report.duration,
            "error": str(report.longrepr) if report.failed else None,
        })


def pytest_sessionfinish(session, exitstatus):
    global _email_already_sent

    # 1. Prevent duplicate email dispatches across teardowns
    if _email_already_sent:
        return

    # 2. Prevent sending emails for empty or zero-duration runs
    if not test_results:
        print("\n⚠️ No test results captured. Skipping email dispatch.")
        return

    _email_already_sent = True

    total_duration = time.time() - session_start_time
    formatted_total_duration = format_duration(total_duration)
    date_str = datetime.now().strftime("%m/%d/%Y")

    computer_name = socket.gethostname()
    os_info = f"{platform.system()} {platform.release()}"

    passed_count = sum(1 for t in test_results if t["outcome"] == "passed")
    failed_count = sum(1 for t in test_results if t["outcome"] == "failed")
    skipped_count = sum(1 for t in test_results if t["outcome"] == "skipped")
    total_count = len(test_results)

    # Derive running Spec File dynamically
    spec_file_display = test_results[0]["spec_file"] if test_results else "N/A"

    # Build CSV Test Cases HTML Table Rows
    rows_html = ""
    for test in test_results:
        duration_str = format_duration(test["duration"])
        
        if test["outcome"] == "passed":
            status_badge = '<span style="color: #2e7d32; font-weight: bold;">✅ PASSED</span>'
            error_section = ""
        elif test["outcome"] == "failed":
            status_badge = '<span style="color: #d32f2f; font-weight: bold;">❌ FAILED</span>'
            error_msg = test['error'].split('\n')[-1] if test['error'] else "Assertion Error"
            error_section = f"""
            <div style="background-color: #ffebee; color: #c62828; padding: 6px; border-radius: 4px; font-family: monospace; font-size: 11px; margin-top: 4px;">
                {error_msg}
            </div>
            """
        else:
            status_badge = '<span style="color: #f57c00; font-weight: bold;">⚠️ SKIPPED</span>'
            error_section = ""

        rows_html += f"""
        <tr>
            <td style="text-align: center; font-weight: bold;">TCase# {test['row_num']}</td>
            <td>{test['to']}</td>
            <td>{test['sender_id']}</td>
            <td>{test['telco'].upper()} / {test['sender_id_flag'].title()}</td>
            <td style="text-align: center;">{test['is_optedout']}</td>
            <td>{test['plan_name']}</td>
            <td>{test['remarks']}</td>
            <td style="text-align: center;">{status_badge}</td>
            <td style="text-align: center; font-weight: bold;">{duration_str}{error_section}</td>
        </tr>
        """

    # Generate Full HTML Email Body
    html_body = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; color: #333; line-height: 1.5; }}
            h2 {{ color: #222; margin-bottom: 5px; }}
            .summary-title {{ font-size: 14px; font-weight: bold; margin-bottom: 15px; color: #444; }}
            .env-box {{ background-color: #f8f9fa; border: 1px solid #e0e0e0; border-radius: 6px; padding: 12px 16px; margin-bottom: 20px; max-width: 960px; font-size: 13px; }}
            .env-box td {{ padding: 4px 12px; font-size: 13px; border: none; }}
            .summary-table {{ border-collapse: collapse; width: 100%; max-width: 1000px; border: 1px solid #e0e0e0; margin-bottom: 25px; }}
            .summary-table th {{ background-color: #f5f5f5; border: 1px solid #e0e0e0; padding: 10px; text-align: center; font-size: 13px; font-weight: bold; }}
            .summary-table td {{ border: 1px solid #e0e0e0; padding: 10px; font-size: 13px; text-align: center; }}
            .detail-table {{ border-collapse: collapse; width: 100%; max-width: 1000px; border: 1px solid #e0e0e0; }}
            .detail-table th {{ background-color: #e8f0fe; color: #1967d2; border: 1px solid #e0e0e0; padding: 8px; text-align: left; font-size: 12px; font-weight: bold; }}
            .detail-table td {{ border: 1px solid #e0e0e0; padding: 8px; font-size: 12px; vertical-align: top; }}
            .passed-val {{ color: #2e7d32; font-weight: bold; }}
            .failed-val {{ color: #d32f2f; font-weight: bold; }}
            .skipped-val {{ color: #f57c00; font-weight: bold; }}
        </style>
    </head>
    <body>
        <h2>Playwright Test Summary Report</h2>
        <div class="summary-title">Total Run Duration: {formatted_total_duration}</div>

        <!-- Environment Metadata Panel -->
        <div class="env-box">
            <strong style="color: #1967d2; font-size: 14px;">🖥️ Execution Environment</strong>
            <table style="margin-top: 6px; width: 100%;">
                <tr>
                    <td style="width: 50%;"><strong>Computer Name:</strong> {computer_name}</td>
                    <td style="width: 50%;"><strong>Browser:</strong> {BROWSER_NAME}</td>
                </tr>
                <tr>
                    <td><strong>Operating System:</strong> {os_info}</td>
                    <td><strong>Browser Version:</strong> {BROWSER_VERSION}</td>
                </tr>
            </table>
        </div>

        <!-- Overall Summary Table -->
        <table class="summary-table">
            <thead>
                <tr>
                    <th style="text-align: left;">Spec File</th>
                    <th>Total</th>
                    <th>Passed</th>
                    <th>Failed</th>
                    <th>Skipped</th>
                    <th>Duration</th>
                </tr>
            </thead>
            <tbody>
                <tr>
                    <td style="text-align: left; font-weight: bold;">{spec_file_display}</td>
                    <td>{total_count}</td>
                    <td class="passed-val">{passed_count}</td>
                    <td class="failed-val">{failed_count}</td>
                    <td class="skipped-val">{skipped_count}</td>
                    <td>{formatted_total_duration}</td>
                </tr>
            </tbody>
        </table>

        <!-- CSV Row Execution Breakdown Table -->
        <h3>CSV Test Cases Execution Breakdown</h3>
        <table class="detail-table">
            <thead>
                <tr>
                    <th style="text-align: center;">TCases</th>
                    <th>Recipient (To)</th>
                    <th>Sender ID</th>
                    <th>Telco / Flag</th>
                    <th style="text-align: center;">Opted Out?</th>
                    <th>Plan Name</th>
                    <th>Remarks</th>
                    <th style="text-align: center;">Status</th>
                    <th style="text-align: center;">Duration per Row</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>
    </body>
    </html>
    """

    subject = f"Automation Report - {date_str} ({formatted_total_duration})"
    send_email(subject, html_body)


def send_email(subject: str, html_content: str):
    """Sends the formatted HTML report via SMTP."""
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"Playwright Automation <{SENDER_EMAIL}>"
        msg["To"] = ", ".join(RECIPIENT_EMAILS)
        msg["Subject"] = subject

        msg.attach(MIMEText(html_content, "html"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAILS, msg.as_string())
        server.quit()
        print(f"\n📧 Email report sent successfully to {RECIPIENT_EMAILS}")
    except Exception as e:
        print(f"\n❌ Failed to send email report: {e}")
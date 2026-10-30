import csv
import math
import os
import re
import time
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, Page, Playwright, TimeoutError as PlaywrightTimeoutError

# Project directory setup
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / "data" / "recipients_viber.csv"
if not CSV_PATH.exists():
    CSV_PATH_ALT = PROJECT_ROOT / "data" / "recipients_viber_2.csv"
    if CSV_PATH_ALT.exists():
        CSV_PATH = CSV_PATH_ALT

# =============================================================
# CONFIGURATIONS / FEATURE FLAGS
# =============================================================
ENVIRONMENT = "dashboard"

# Dynamic Base URLs constructed from ENVIRONMENT variable
BASE_URL = f"https://{ENVIRONMENT}.m360.com.ph"
LOGIN_URL = f"{BASE_URL}/login"
API_URL = "https://viber.m360.com.ph/v4/viber/send"

# Set to True to check/validate Plan Usage page, or False to skip completely.
PLAN_USAGE = False

# Single Account Configuration
ACCOUNTS = {
    "standard": {
        "USERNAME": "jgmy360plan50k",
        "PASSWORD": "Em360@123!!@",
        "APP_KEY": "p47Q0IlCdxQyzERT",
        "APP_SECRET": "GMS22AdjM8gpneMo3XjJ19yET7R6lLRA",
    }
}


def get_account_config(plan_name: str = "") -> dict:
    """Always resolves to the single standard account."""
    return ACCOUNTS["standard"]


# Dynamic Rate Configurations
RATE_CONFIG = {
    "SMS_Globe_Regular": 0.10,
    "SMS_Globe_Excess": 0.11,
    "SMS_Globe_Premium_Regular": 0.70,
    "SMS_Globe_Premium_Excess": 0.71,
    "SMS_Smart_Regular": 0.20,
    "SMS_Smart_Excess": 0.21,
    "SMS_Smart_Premium_Regular": 0.80,
    "SMS_Smart_Premium_Excess": 0.81,
    "SMS_Dito_Regular": 0.40,
    "SMS_Dito_Excess": 0.41,
    "SMS_Dito_Premium_Regular": 0.90,
    "SMS_Dito_Premium_Excess": 0.91,
    "SMS_Spain_Regular": 11.00,
    "SMS_Spain_Excess": 11.00,
    "SMS_Spain_Premium_Regular": 11.00,
    "SMS_Spain_Premium_Excess": 11.10,
}


def calculate_sms_parts(text: str) -> int:
    """Calculates SMS message parts strictly based on sms_message character length."""
    length = len(text)
    if length == 0:
        return 0
    if length <= 160:
        return 1
    return math.ceil(length / 153)


def get_sms_rate(telco: str, rate_type: str) -> float:
    """Looks up configured SMS rate based on telco and calculated rate_type."""
    formatted_telco = telco.strip().capitalize()
    formatted_flag = rate_type.strip()

    rate_key = f"SMS_{formatted_telco}_{formatted_flag}"

    if rate_key not in RATE_CONFIG and "Premium" in formatted_flag:
        fallback_key = f"SMS_{formatted_telco}_Premium"
        if fallback_key in RATE_CONFIG:
            return RATE_CONFIG[fallback_key]

    if rate_key not in RATE_CONFIG:
        pytest.fail(f"Configured rate key '{rate_key}' was not found in RATE_CONFIG dictionary!")

    return RATE_CONFIG[rate_key]


def determine_rate_type(page: Page, plan_name: str, csv_sender_flag: str) -> str:
    """Determines if deduction uses Regular, Excess, Premium_Regular, or Premium_Excess rate."""
    if not PLAN_USAGE:
        print("  [LOG] PLAN_USAGE=False -> Skipping determine_rate_type navigation. Defaulting to 'Regular'.")
        return "Regular"

    print("  [LOG] Navigating to Plan Usage page to calculate rate type...")
    page.goto(f"{BASE_URL}/plan-usage", wait_until="domcontentloaded")

    try:
        page.wait_for_selector("[data-testid='total-usage'], [data-testid='total-excess-usage']", timeout=15000)
    except PlaywrightTimeoutError:
        page.wait_for_selector("text=Total Consumed", timeout=10000)

    excess_banner = page.locator("div.pb-spiel, div:has-text('excess charges')")
    has_excess_banner = excess_banner.count() > 0 and excess_banner.first.is_visible()

    plan_block = page.locator(
        f"xpath=//*[contains(text(), '{plan_name}')]/ancestor::div[contains(@class, 'v-card') or contains(@class, 'card') or contains(@class, 'row') or contains(@class, 'container') or self::div][1]"
    )

    if plan_block.count() and plan_block.first.is_visible():
        consumables_label = plan_block.locator("xpath=.//*[text()='Consumables' or contains(text(), 'Consumables')]")
    else:
        consumables_label = page.locator("xpath=//*[text()='Consumables' or contains(text(), 'Consumables')]")

    has_consumables = consumables_label.count() > 0 and consumables_label.first.is_visible()
    is_premium = csv_sender_flag.lower() == "premium"

    if not has_excess_banner and has_consumables:
        res = "Premium_Regular" if is_premium else "Regular"
    else:
        res = "Premium_Excess" if is_premium else "Excess"

    print(f"  📊 Rate Condition Match: {res} (Excess Banner: {has_excess_banner} | Consumables: {has_consumables})")
    return res


def get_csv_rows() -> list[dict]:
    """Reads recipient rows and mapped Viber/SMS failover fields from CSV."""
    resolved_csv = CSV_PATH
    if not resolved_csv.exists():
        alt_path = PROJECT_ROOT / "data" / "recipients_viber_2.csv"
        if alt_path.exists():
            resolved_csv = alt_path
        else:
            pytest.fail(f"Required CSV file was not found at: {resolved_csv.resolve()}")

    rows_data = []
    with open(resolved_csv, mode="r", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for row in reader:
            raw_msisdn = (row.get("msisdn") or row.get("to") or "").strip()
            if raw_msisdn:
                recipients_list = [r.strip() for r in raw_msisdn.split(",") if r.strip()]

                try:
                    dcs_val = int(row.get("sms_dcs") or row.get("dcs") or 0)
                except ValueError:
                    dcs_val = 0

                sms_failover_val = (row.get("sms_failover_on") or "no").strip().lower() in ("yes", "true", "1")

                rows_data.append({
                    "to": recipients_list,
                    "recipient_count": len(recipients_list),
                    "viber_service_id": (row.get("viber_serviceID") or row.get("from") or "2way").strip(),
                    "viber_type": (row.get("viber_type") or "promotional").strip().lower(),
                    "viber_broadcast_type": (row.get("viber_broadcast_type") or row.get("viber_campaign_type_remarks") or "text").strip().lower(),
                    "viber_message": (row.get("viber_message") or row.get("content_text") or "").strip(),
                    "viber_doc_url": (row.get("viber_doc_url") or row.get("link") or "").strip(),
                    "viber_file_name": (row.get("viber_file_name") or row.get("file_name") or "").strip(),
                    "viber_image_url": (row.get("viber_image_url") or "").strip(),
                    "viber_video_url": (row.get("viber_video_url") or "").strip(),
                    "viber_thumbnail_url": (row.get("viber_thumbnail_url") or row.get("thumbnail") or "").strip(),
                    "viber_cta_label": (row.get("viber_cta_label") or row.get("caption") or "").strip(),
                    "viber_cta_url": (row.get("viber_cta_url") or row.get("action") or "").strip(),

                    # Failover SMS fields
                    "sms_failover_on": sms_failover_val,
                    "sms_message": (row.get("sms_message") or "").strip(),
                    "sms_sender_id": (row.get("sms_senderID") or row.get("sender_id") or "qareg_moo").strip(),
                    "dcs": dcs_val,
                    "sender_id_flag": (row.get("sms_senderID_flag") or row.get("sender_id_flag") or "regular").strip().lower(),
                    "telco": (row.get("telco") or "smart").strip().lower(),
                    "country": row.get("country", "Philippines").strip(),
                    "is_optedout": (row.get("sms_optedout") or row.get("is_optedout") or "no").strip().lower() in ("yes", "true", "1"),
                    "portal_plan_name": (row.get("SMS_plan_name") or row.get("portal_plan_name") or "MY360 PLAN 50,000 TESTER").strip(),
                    "remarks": (row.get("remarks") or row.get("remark") or "").strip()
                })

    if not rows_data:
        pytest.fail(f"No valid rows found in {resolved_csv}")

    run_row_env = os.getenv("RUN_ROW", "").strip().upper()
    if run_row_env:
        if run_row_env in ("LAST", "-1"):
            return [rows_data[-1]]

        selected_indices = [r.strip() for r in run_row_env.split(",") if r.strip().isdigit()]
        if selected_indices:
            filtered_rows = []
            for idx_str in selected_indices:
                row_idx = int(idx_str) - 1
                if 0 <= row_idx < len(rows_data):
                    filtered_rows.append(rows_data[row_idx])
                else:
                    print(f"⚠️ Warning: Row {idx_str} is out of range (1-{len(rows_data)}). Skipping.")

            if filtered_rows:
                return filtered_rows
            else:
                pytest.fail(f"None of the specified rows in RUN_ROW='{run_row_env}' were within valid CSV range.")

    return rows_data


def build_viber_content_payload(row_data: dict) -> dict:
    """Constructs the content object strictly matching the specified type."""
    raw_type = row_data["viber_broadcast_type"]

    if "text" in raw_type:
        api_type = "text"
    elif "image" in raw_type or "photo" in raw_type:
        api_type = "image"
    elif "doc" in raw_type or "file" in raw_type:
        api_type = "doc"
    elif "video" in raw_type:
        api_type = "video"
    else:
        api_type = "text"

    content = {
        "type": api_type,
        "text": row_data["viber_message"]
    }

    if api_type == "image":
        if row_data["viber_image_url"]:
            content["link"] = row_data["viber_image_url"]
        if row_data["viber_thumbnail_url"]:
            content["thumbnail"] = row_data["viber_thumbnail_url"]
        if row_data["viber_cta_label"]:
            content["caption"] = row_data["viber_cta_label"]
        if row_data["viber_cta_url"]:
            content["action"] = row_data["viber_cta_url"]
    elif api_type == "doc":
        if row_data["viber_doc_url"]:
            content["link"] = row_data["viber_doc_url"]
        if row_data["viber_file_name"]:
            content["file_name"] = row_data["viber_file_name"]
    elif api_type == "video":
        if row_data["viber_video_url"]:
            content["link"] = row_data["viber_video_url"]
        if row_data["viber_thumbnail_url"]:
            content["thumbnail"] = row_data["viber_thumbnail_url"]

    return content


def get_dashboard_metrics(page: Page, target_delivered: int = 0) -> dict:
    """Fetches 'Total Delivered Messages' from Dashboard."""
    print("  [LOG] Fetching Dashboard metrics...")
    page.goto(f"{BASE_URL}/dashboard", wait_until="domcontentloaded")
    page.wait_for_timeout(1000)

    if "/login" in page.url:
        pytest.fail("❌ Redirected to /login while capturing dashboard metrics. Authentication session lost.")

    try:
        page.wait_for_selector("text=Total Delivered Messages", timeout=12000)
    except PlaywrightTimeoutError:
        try:
            page.wait_for_selector("text=Delivered", timeout=5000)
        except PlaywrightTimeoutError:
            page.wait_for_timeout(2000)

    delivered_el = page.locator("[data-testid='total-delivered-messages'], [data-testid='delivered-messages']").first

    if not delivered_el.count() or not delivered_el.is_visible():
        delivered_el = page.locator("xpath=//*[contains(text(), 'Total Delivered')]/following-sibling::*[1]").first

    if not delivered_el.count() or not delivered_el.is_visible():
        card = page.locator("div.v-card, div.card, section, article").filter(has_text=re.compile(r"Total Delivered Messages|Delivered", re.I)).last
        delivered_el = card.locator("span, p, h2, div").filter(has_text=re.compile(r"^\d[\d,]*$")).first

    total_delivered = 0
    for _ in range(6):
        total_delivered_text = delivered_el.inner_text().strip() if (delivered_el.count() and delivered_el.is_visible()) else "0"
        total_numbers = re.findall(r"\b\d+\b", total_delivered_text.replace(",", ""))
        total_delivered = int(total_numbers[0]) if total_numbers else 0
        if target_delivered > 0 and total_delivered >= target_delivered:
            break
        elif target_delivered == 0 and total_delivered > 0:
            break
        time.sleep(1)

    print(f"  [LOG] Dashboard Delivered Count: {total_delivered}")
    return {"total_delivered": total_delivered}


def get_plan_usage_metrics(page: Page, plan_name: str) -> dict:
    """Fetches plan metrics: Consumed Amount, Consumables Limit, Message Transactions, and Excess."""
    if not PLAN_USAGE:
        return {
            "consumed_amount": 0.0,
            "consumables_limit": 0.0,
            "msg_transactions": 0,
            "excess_count": 0,
            "has_consumed": False,
            "has_consumables": False,
            "has_limit": False
        }

    print("  [LOG] Fetching Plan Usage metrics...")
    page.goto(f"{BASE_URL}/plan-usage", wait_until="domcontentloaded")

    try:
        page.wait_for_selector("[data-testid='total-usage'], [data-testid='total-excess'], [data-testid='total-excess-usage']", timeout=15000)
    except PlaywrightTimeoutError:
        page.wait_for_selector("text=Total Consumed", timeout=10000)

    page.wait_for_timeout(2000)

    plan_block = page.locator(f"xpath=//*[contains(text(), '{plan_name}')]/ancestor::div[contains(@class, 'v-card') or contains(@class, 'card') or contains(@class, 'row') or contains(@class, 'container') or self::div][1]")

    def parse_numeric_element(locator_obj):
        if locator_obj and locator_obj.count() and locator_obj.first.is_visible():
            text_val = locator_obj.first.inner_text().strip()
            match = re.search(r"\d+(?:\.\d+)?", text_val.replace(",", ""))
            if match:
                return float(match.group(0)), True
        return 0.0, False

    consumed_el = plan_block.locator("[data-testid='total-usage'], [data-testid='total-consumed']") if plan_block.count() else None
    if not consumed_el or not consumed_el.count() or not consumed_el.first.is_visible():
        consumed_el = page.locator("[data-testid='total-usage'], [data-testid='total-consumed']")
    consumed_amount, has_consumed = parse_numeric_element(consumed_el)

    consumables_el = plan_block.locator("[data-testid='consumables']") if plan_block.count() else None
    if not consumables_el or not consumables_el.count() or not consumables_el.first.is_visible():
        consumables_el = page.locator("[data-testid='consumables']")
    consumables_limit, has_consumables = parse_numeric_element(consumables_el)

    msg_trans_el = None
    if plan_block.count() and plan_block.first.is_visible():
        msg_trans_el = plan_block.locator("span.channels-amount:not([data-testid='total-usage']):not([data-testid='consumables']):not([data-testid='total-excess']):not([data-testid='total-excess-usage'])").first
    if not msg_trans_el or not msg_trans_el.count() or not msg_trans_el.is_visible():
        msg_trans_el = page.locator("span.channels-amount:not([data-testid='total-usage']):not([data-testid='consumables']):not([data-testid='total-excess']):not([data-testid='total-excess-usage'])").first
    msg_transactions_val, _ = parse_numeric_element(msg_trans_el)
    msg_transactions = int(msg_transactions_val)

    excess_el = plan_block.locator("[data-testid='total-excess'], [data-testid='total-excess-usage']") if plan_block.count() else None
    if not excess_el or not excess_el.count() or not excess_el.first.is_visible():
        excess_el = page.locator("[data-testid='total-excess'], [data-testid='total-excess-usage']")
    excess_count_val, _ = parse_numeric_element(excess_el)
    excess_count = int(excess_count_val)

    limit_el = plan_block.locator("[data-testid='limit']") if plan_block.count() else None
    if not limit_el or not limit_el.count() or not limit_el.first.is_visible():
        limit_el = page.locator("xpath=//*[contains(text(), 'Limit') or contains(text(), 'Plan Limit')]")
    has_limit = limit_el.count() > 0 and limit_el.first.is_visible()

    return {
        "consumed_amount": consumed_amount,
        "consumables_limit": consumables_limit,
        "msg_transactions": msg_transactions,
        "excess_count": excess_count,
        "has_consumed": has_consumed,
        "has_consumables": has_consumables,
        "has_limit": has_limit
    }


def get_viber_report_metrics(page: Page) -> dict:
    """Accurately extracts metrics strictly from inside the 'Viber Overview' card."""
    print("  [LOG] Fetching Viber Channel Report metrics...")
    if "/reports/channel/viber" not in page.url:
        page.goto(f"{BASE_URL}/reports/channel/viber", wait_until="domcontentloaded")

    try:
        page.wait_for_selector("text=Viber Overview", timeout=15000)
    except PlaywrightTimeoutError:
        page.wait_for_timeout(2000)

    overview_card = page.locator(
        "xpath=//*[contains(text(), 'Viber Overview')]/ancestor::div[contains(@class, 'v-card') or contains(@class, 'card') or contains(@class, 'container') or self::div][position()<=3]"
    ).filter(has=page.locator("text=Delivered")).last

    def extract_metric(label: str) -> int:
        if not overview_card.count() or not overview_card.is_visible():
            return 0

        metric_col = overview_card.locator(
            f"xpath=.//*[translate(normalize-space(text()), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')='{label.lower()}']/ancestor::*[self::div or self::td or self::span][1]"
        )

        if metric_col.count() and metric_col.first.is_visible():
            text_val = metric_col.first.inner_text().strip()
            clean_text = re.sub(r"\d+(?:\.\d+)?%", "", text_val)
            nums = re.findall(r"\b\d[\d,]*\b", clean_text)
            if nums:
                return int(nums[0].replace(",", ""))

        card_text = overview_card.inner_text()
        match_above = re.search(rf"(\d[\d,]*)\s*(?:\d+(?:\.\d+)?%)?\s*\n\s*{label}\b", card_text, re.IGNORECASE)
        if match_above:
            return int(match_above.group(1).replace(",", ""))

        match_below = re.search(rf"\b{label}\b\s*\n\s*(\d[\d,]*)\b", card_text, re.IGNORECASE)
        if match_below:
            return int(match_below.group(1).replace(",", ""))

        return 0

    sent = extract_metric("Sent")
    delivered = extract_metric("Delivered")
    seen = extract_metric("Seen")
    failed = extract_metric("Failed")
    received = extract_metric("Received")

    print(f"  [LOG] Viber Overview -> Sent: {sent} | Delivered: {delivered} | Seen: {seen} | Failed: {failed} | Received: {received}")
    return {"sent": sent, "delivered": delivered, "seen": seen, "failed": failed, "received": received}


def get_viber_destination_metrics(page: Page, target_telco: str = "smart") -> dict:
    """
    Parses Sent, Delivered, Seen, and Failed for target telco strictly from 
    the 'Messages by Destination' card.
    """
    print(f"  [LOG] Fetching Viber Messages by Destination for Telco: {target_telco.upper()}...")
    if "/reports/channel/viber" not in page.url:
        page.goto(f"{BASE_URL}/reports/channel/viber", wait_until="domcontentloaded")

    # Scope strictly inside the 'Messages by Destination' section/card
    dest_card = page.locator("xpath=//*[contains(text(), 'Messages by Destination')]/ancestor::div[contains(@class, 'v-card') or contains(@class, 'card') or self::div][1]")
    if not dest_card.count() or not dest_card.first.is_visible():
        dest_card = page.locator("div, section").filter(has=page.locator("text=Messages by Destination")).last

    telco_clean = target_telco.strip().lower()

    def clean_int(text: str) -> int:
        clean = re.sub(r"\d+(?:\.\d+)?%", "", text)
        nums = re.findall(r"\b\d[\d,]*\b", clean)
        return int(nums[0].replace(",", "")) if nums else 0

    row = dest_card.locator("table tbody tr").filter(
        has=page.locator(f"xpath=.//td[1][contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{telco_clean}')]")
    ).first

    if row.count() and row.is_visible():
        cells = row.locator("td")
        col_count = cells.count()
        if col_count >= 5:
            telco_name = cells.nth(0).inner_text().strip()
            country_name = cells.nth(1).inner_text().strip() if col_count >= 6 else "Philippines"
            sent_val = clean_int(cells.nth(2).inner_text())
            delivered_val = clean_int(cells.nth(3).inner_text())
            seen_val = clean_int(cells.nth(4).inner_text())
            failed_val = clean_int(cells.nth(5).inner_text()) if col_count >= 6 else clean_int(cells.nth(4).inner_text())
            received_val = clean_int(cells.nth(6).inner_text()) if col_count > 6 else 0

            print(f"  [LOG] Messages by Destination -> Telco: {telco_name} | Country: {country_name} | Sent: {sent_val} | Delivered: {delivered_val} | Seen: {seen_val} | Failed: {failed_val}")
            return {
                "telco": telco_name,
                "country": country_name,
                "sent": sent_val,
                "delivered": delivered_val,
                "seen": seen_val,
                "failed": failed_val,
                "received": received_val
            }

    print(f"  ⚠️ Warning: Destination row for '{target_telco.upper()}' not found in Messages by Destination table. Defaulting counts to 0.")
    return {"telco": target_telco.capitalize(), "country": "N/A", "sent": 0, "delivered": 0, "seen": 0, "failed": 0, "received": 0}


def get_viber_message_type_metrics(page: Page, target_type: str = "promotional") -> dict:
    """
    Parses Sent, Delivered, Seen, and Failed for the target message type (Transactional or Promotional)
    from the 'Message Type Delivered' table under Viber Channel Report.
    """
    formatted_type = target_type.strip().capitalize()
    print(f"  [LOG] Fetching Viber Message Type Delivered for: {formatted_type}...")
    if "/reports/channel/viber" not in page.url:
        page.goto(f"{BASE_URL}/reports/channel/viber", wait_until="domcontentloaded")

    page.evaluate("window.scrollTo(0, 400)")
    page.wait_for_timeout(800)

    type_clean = target_type.strip().lower()

    def clean_int(text: str) -> int:
        clean = re.sub(r"\d+(?:\.\d+)?%", "", text)
        nums = re.findall(r"\b\d[\d,]*\b", clean)
        return int(nums[0].replace(",", "")) if nums else 0

    row_xpath = f"//tr[td[1][normalize-space()='{formatted_type}' or contains(translate(normalize-space(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{type_clean}')]]"
    row = page.locator(row_xpath).first

    if not row.count():
        for r in page.locator("table tbody tr, tr").all():
            tds = r.locator("td")
            if tds.count() >= 5:
                first_text = tds.nth(0).inner_text().strip().lower()
                if type_clean == first_text or type_clean in first_text:
                    row = r
                    break

    if row and row.count() and row.is_visible():
        cells = row.locator("td")
        if cells.count() >= 5:
            type_name = cells.nth(0).inner_text().strip()
            sent_val = clean_int(cells.nth(1).inner_text())
            delivered_val = clean_int(cells.nth(2).inner_text())
            seen_val = clean_int(cells.nth(3).inner_text())
            failed_val = clean_int(cells.nth(4).inner_text())
            received_val = clean_int(cells.nth(5).inner_text()) if cells.count() > 5 else 0

            print(f"  [LOG] Message Type Delivered -> Message Type: {type_name} | Sent: {sent_val} | Delivered: {delivered_val} | Seen: {seen_val} | Failed: {failed_val} | Received: {received_val}")
            return {
                "message_type": type_name,
                "sent": sent_val,
                "delivered": delivered_val,
                "seen": seen_val,
                "failed": failed_val,
                "received": received_val
            }

    print(f"  ⚠️ Warning: Row for Message Type '{formatted_type}' not found in Message Type Delivered table. Defaulting counts to 0.")
    return {"message_type": formatted_type, "sent": 0, "delivered": 0, "seen": 0, "failed": 0, "received": 0}


def get_sms_report_metrics(page: Page, target_telco: str = "smart", target_country: str = "Philippines") -> dict:
    """Parses Sent, Acknowledged, and Failed counts from the SMS 'Messages by Destination' table."""
    print(f"  [LOG] Fetching SMS Report table metrics for destination: {target_telco.upper()}...")
    try:
        with page.expect_response(
            lambda response: "/reports" in response.url or "/sms" in response.url or response.status == 200,
            timeout=10000
        ):
            page.goto(f"{BASE_URL}/reports/channel/sms", wait_until="domcontentloaded")
    except PlaywrightTimeoutError:
        page.goto(f"{BASE_URL}/reports/channel/sms", wait_until="domcontentloaded")

    try:
        page.wait_for_selector("text=Messages by Destination", timeout=15000)
    except PlaywrightTimeoutError:
        page.wait_for_timeout(2000)

    page.wait_for_timeout(1000)

    telco_search = "international" if target_telco.lower() in ("spain", "international") else target_telco.lower()
    row_xpath = f"//tr[td[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{telco_search}')]]"
    row_locator = page.locator(row_xpath)

    if not row_locator.count():
        row_locator = page.locator(f"xpath=//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{telco_search}')]/ancestor::tr[1]")

    if row_locator.count() and row_locator.first.is_visible():
        cells = row_locator.first.locator("td")
        if cells.count() >= 5:
            def extract_int(text: str) -> int:
                clean = re.sub(r"\d+(?:\.\d+)?%", "", text)
                nums = re.findall(r"\b\d+\b", clean.replace(",", ""))
                return int(nums[0]) if nums else 0

            sent_val = extract_int(cells.nth(2).inner_text())
            ack_val = extract_int(cells.nth(3).inner_text())
            failed_val = extract_int(cells.nth(4).inner_text())

            print(f"  [LOG] Found row '{target_telco.upper()}' -> Sent: {sent_val} | Ack: {ack_val} | Failed: {failed_val}")
            return {"sent": sent_val, "acknowledged": ack_val, "failed": failed_val}

    print(f"  ⚠️ Warning: Destination row for '{target_telco}' not found in table. Defaulting counts to 0.")
    return {"sent": 0, "acknowledged": 0, "failed": 0}


@pytest.mark.parametrize("row_data", get_csv_rows())
def test_send_sms_journey_validation(row_data: dict):
    account = get_account_config(row_data.get("portal_plan_name", ""))
    target_telco = row_data["telco"]
    target_viber_type = row_data.get("viber_type", "promotional")
    sms_failover_enabled = row_data.get("sms_failover_on", False)

    recipients = row_data["to"]
    expected_viber_add = len(recipients)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # -------------------------------------------------------------
        # STEP 1: UI LOGIN
        # -------------------------------------------------------------
        print(f"\n[STEP 1] Logging into m360 Portal ({account['USERNAME']})...")

        try:
            page.goto(LOGIN_URL, timeout=15000, wait_until="domcontentloaded")
        except PlaywrightTimeoutError:
            print(f"  ⚠️ Initial navigation to {LOGIN_URL} timed out. Retrying...")

        user_input = page.locator("input[type='email'], input[name='email'], input[data-cy='username'], input[placeholder*='Email' i]").first
        pass_input = page.locator("input[type='password']").first
        login_btn = page.locator("button:has-text('Log In'), button[type='submit']").first

        login_loaded = False
        login_retries = 3

        while not login_loaded and login_retries > 0:
            try:
                user_input.wait_for(state="visible", timeout=3000)
                login_loaded = True
            except PlaywrightTimeoutError:
                login_retries -= 1
                if login_retries > 0:
                    time.sleep(2)
                    try:
                        page.goto(LOGIN_URL, timeout=10000, wait_until="domcontentloaded")
                    except PlaywrightTimeoutError:
                        pass

        if not login_loaded:
            browser.close()
            pytest.fail("❌ TERMINATING: Login page element failed to load after 3 refresh retries.")

        user_input.fill(account["USERNAME"])
        pass_input.fill(account["PASSWORD"])
        login_btn.click()

        try:
            page.wait_for_url(lambda url: "/login" not in url, timeout=15000)
            page.wait_for_load_state("domcontentloaded")
            print("  [LOG] Successfully authenticated and loaded portal.")
        except PlaywrightTimeoutError:
            browser.close()
            pytest.fail(f"❌ Authentication Failed: Invalid credentials or session kickback for {account['USERNAME']}.")

        # -------------------------------------------------------------
        # STEP 2: CAPTURE PRE-DATA & DETERMINE DYNAMIC RATE TYPE
        # -------------------------------------------------------------
        print(f"\n[STEP 2] Capturing Pre-Data metrics across Portal... (Telco: {target_telco.upper()} | Viber Type: {target_viber_type.capitalize()} | Recipients: {expected_viber_add})")

        pre_dashboard = get_dashboard_metrics(page)
        pre_plan = get_plan_usage_metrics(page, plan_name=row_data["portal_plan_name"])

        page.goto(f"{BASE_URL}/reports/channel/viber", wait_until="domcontentloaded")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)

        pre_viber = get_viber_report_metrics(page)
        pre_viber_type_stats = get_viber_message_type_metrics(page, target_type=target_viber_type)
        pre_viber_dest = get_viber_destination_metrics(page, target_telco=target_telco)

        # Baseline SMS report is NOT fetched here; only retrieved if Condition 2 is triggered
        pre_sms_report = None

        determined_rate_type = determine_rate_type(
            page,
            plan_name=row_data["portal_plan_name"],
            csv_sender_flag=row_data["sender_id_flag"]
        )

        print(f"\n  📋 PRE-METRICS SUMMARY:")
        print(f"  -> Pre-Dashboard Total Delivered           : {pre_dashboard['total_delivered']}")
        print(f"  -> Pre-Viber Overview Delivered            : {pre_viber['delivered']} | Failed: {pre_viber['failed']}")
        print(f"  -> Pre-Viber Destination ({target_telco.upper()}): Sent={pre_viber_dest['sent']} | Delivered={pre_viber_dest['delivered']} | Failed={pre_viber_dest['failed']}")
        print(f"  -> Pre-Viber Message Type ({target_viber_type.capitalize()}): Sent={pre_viber_type_stats['sent']} | Delivered={pre_viber_type_stats['delivered']} | Failed={pre_viber_type_stats['failed']}")

        # -------------------------------------------------------------
        # STEP 3: EXECUTE API REQUEST (Viber + Optional SMS Failover)
        # -------------------------------------------------------------
        print(f"\n[STEP 3] Triggering Viber API POST for {expected_viber_add} recipient(s): {recipients} (Service ID: {row_data['viber_service_id']} | Failover ON: {sms_failover_enabled})...")
        api_context = p.request.new_context()

        content_payload = build_viber_content_payload(row_data)

        payload = {
            "app_key": account["APP_KEY"],
            "app_secret": account["APP_SECRET"],
            "to": recipients,
            "from": row_data["viber_service_id"],
            "is_template": False,
            "is_intl": False,
            "is_session": False,
            "tracking_data": "0",
            "ttl": "60",
            "content": content_payload
        }

        if sms_failover_enabled:
            payload["failover"] = {
                "sms": {
                    "to": recipients,
                    "content": {
                        "text": row_data["sms_message"]
                    },
                    "from": row_data["sms_sender_id"],
                    "dcs": row_data["dcs"]
                }
            }

        response = api_context.post(
            API_URL,
            data=payload,
            headers={"Content-Type": "application/json"}
        )

        try:
            response_json = response.json()
        except Exception:
            response_json = {}

        print(f"  [LOG] API Response Code: {response.status}")
        print(f"  [LOG] Response Body     : {response_json}")

        api_is_success = (response.status in (200, 201) and response_json.get("code") in (200, 201))
        api_context.dispose()

        # -------------------------------------------------------------
        # STEP 4: CHECK VIBER REPORT, TELCO & MESSAGE TYPE DELIVERED FIRST
        # -------------------------------------------------------------
        print(f"\n[STEP 4] Checking Viber Destination ({target_telco.upper()}), Overview, and Message Type stats (Polling for changes)...")
        viber_delivered_incremented = False
        viber_failed_incremented = False
        post_viber = pre_viber
        post_viber_dest = pre_viber_dest
        post_viber_type_stats = pre_viber_type_stats

        expected_overview_delivered = pre_viber["delivered"] + expected_viber_add
        expected_dest_delivered = pre_viber_dest["delivered"] + expected_viber_add
        expected_type_delivered = pre_viber_type_stats["delivered"] + expected_viber_add

        for retry in range(12):
            time.sleep(3)
            page.goto(f"{BASE_URL}/reports/channel/viber", wait_until="domcontentloaded")
            try:
                page.wait_for_load_state("networkidle", timeout=5000)
            except PlaywrightTimeoutError:
                pass
            page.wait_for_timeout(1500)

            post_viber = get_viber_report_metrics(page)
            post_viber_dest = get_viber_destination_metrics(page, target_telco=target_telco)
            post_viber_type_stats = get_viber_message_type_metrics(page, target_type=target_viber_type)

            # Calculate Deltas
            dest_deliv_delta = post_viber_dest["delivered"] - pre_viber_dest["delivered"]
            dest_fail_delta = post_viber_dest["failed"] - pre_viber_dest["failed"]
            over_deliv_delta = post_viber["delivered"] - pre_viber["delivered"]
            over_fail_delta = post_viber["failed"] - pre_viber["failed"]
            type_deliv_delta = post_viber_type_stats["delivered"] - pre_viber_type_stats["delivered"]
            type_fail_delta = post_viber_type_stats["failed"] - pre_viber_type_stats["failed"]

            # Print delta update log on each poll
            print(f"  [LOG] Poll {retry + 1}/12 Current Changes (Pre vs Post):")
            print(f"    -> Destination ({target_telco.upper()}): Delivered {pre_viber_dest['delivered']} -> {post_viber_dest['delivered']} (+{dest_deliv_delta}) | Failed {pre_viber_dest['failed']} -> {post_viber_dest['failed']} (+{dest_fail_delta})")
            print(f"    -> Overview: Delivered {pre_viber['delivered']} -> {post_viber['delivered']} (+{over_deliv_delta}) | Failed {pre_viber['failed']} -> {post_viber['failed']} (+{over_fail_delta})")
            print(f"    -> Type ({target_viber_type.capitalize()}): Delivered {pre_viber_type_stats['delivered']} -> {post_viber_type_stats['delivered']} (+{type_deliv_delta}) | Failed {pre_viber_type_stats['failed']} -> {post_viber_type_stats['failed']} (+{type_fail_delta})")

            # 1. PRIORITY 1: Check if Destination Telco Failed incremented
            if dest_fail_delta >= expected_viber_add or (dest_fail_delta > 0 and retry >= 1):
                viber_failed_incremented = True
                print(f"  ⚠️ [DATA UPDATED] Viber Destination Telco ({target_telco.upper()}) Failed increment confirmed! (+{dest_fail_delta})")
                break

            # 2. PRIORITY 2: Check if Destination Telco Delivered incremented
            if dest_deliv_delta >= expected_viber_add or over_deliv_delta >= expected_viber_add:
                viber_delivered_incremented = True
                print(f"  ✅ [DATA UPDATED] Viber Delivered increment confirmed! (Dest: +{dest_deliv_delta}, Overview: +{over_deliv_delta})")

                for _ in range(3):
                    if post_viber_type_stats["delivered"] >= expected_type_delivered:
                        break
                    time.sleep(2)
                    page.goto(f"{BASE_URL}/reports/channel/viber", wait_until="domcontentloaded")
                    post_viber_dest = get_viber_destination_metrics(page, target_telco=target_telco)
                    post_viber_type_stats = get_viber_message_type_metrics(page, target_type=target_viber_type)
                break

            print(f"  -> Waiting for Viber update... (Target Dest Delivered: {expected_dest_delivered}, Current: {post_viber_dest['delivered']} | Target Dest Failed: +{expected_viber_add}, Current: +{dest_fail_delta})")

        # -------------------------------------------------------------
        # POST-METRICS SUMMARY COMPARISON
        # -------------------------------------------------------------
        print(f"\n  📋 POST-METRICS SUMMARY & COMPARISON:")
        print(f"  -> Viber Overview Delivered            : Pre={pre_viber['delivered']} -> Post={post_viber['delivered']} (Diff: +{post_viber['delivered'] - pre_viber['delivered']})")
        print(f"  -> Viber Overview Failed               : Pre={pre_viber['failed']} -> Post={post_viber['failed']} (Diff: +{post_viber['failed'] - pre_viber['failed']})")
        print(f"  -> Viber Destination ({target_telco.upper()}) Delivered : Pre={pre_viber_dest['delivered']} -> Post={post_viber_dest['delivered']} (Diff: +{post_viber_dest['delivered'] - pre_viber_dest['delivered']})")
        print(f"  -> Viber Destination ({target_telco.upper()}) Failed    : Pre={pre_viber_dest['failed']} -> Post={post_viber_dest['failed']} (Diff: +{post_viber_dest['failed'] - pre_viber_dest['failed']})")
        print(f"  -> Viber Type ({target_viber_type.capitalize()}) Delivered    : Pre={pre_viber_type_stats['delivered']} -> Post={post_viber_type_stats['delivered']} (Diff: +{post_viber_type_stats['delivered'] - pre_viber_type_stats['delivered']})")
        print(f"  -> Viber Type ({target_viber_type.capitalize()}) Failed       : Pre={pre_viber_type_stats['failed']} -> Post={post_viber_type_stats['failed']} (Diff: +{post_viber_type_stats['failed'] - pre_viber_type_stats['failed']})")

        # -------------------------------------------------------------
        # STEP 5: EVALUATE CONDITIONS BASED ON PRE VS POST & CSV
        # -------------------------------------------------------------

        # CONDITION 2 (PRIORITY): Destination Telco Failed incremented & sms_failover_on == yes -> Validate SMS failover stats
        if viber_failed_incremented and sms_failover_enabled:
            print(f"\n[STEP 5] [CONDITION 2] Viber Destination Telco ({target_telco.upper()}) failed stats incremented & sms_failover_on=YES -> Validating SMS failover stats...")

            # Capture SMS baseline report metrics now that Viber has officially failed on destination telco
            if pre_sms_report is None:
                pre_sms_report = get_sms_report_metrics(page, target_telco=target_telco, target_country=row_data.get("country", "Philippines"))

            parts_per_recipient = calculate_sms_parts(row_data["sms_message"])
            total_sms_parts = parts_per_recipient * expected_viber_add
            print(f"  [LOG] Calculated SMS parts from 'sms_message' (length {len(row_data['sms_message'])}): {parts_per_recipient} part(s)/recipient | Total SMS parts: {total_sms_parts}")

            rate_per_part = get_sms_rate(target_telco, determined_rate_type) if PLAN_USAGE else 0.0
            is_cashbus_sender = row_data["sms_sender_id"].strip().lower() == "cashbus"

            expected_msg_trans_add = 0
            expected_excess_add = 0

            if is_cashbus_sender:
                expected_parts_added = 0
                added_cost = 0.0
                expected_sent_add = total_sms_parts
                expected_ack_add = 0
                expected_failed_add = total_sms_parts
            elif row_data["is_optedout"]:
                expected_parts_added = 0
                added_cost = 0.0
                expected_sent_add = 0
                expected_ack_add = 0
                expected_failed_add = 0
            elif api_is_success:
                expected_parts_added = total_sms_parts
                added_cost = round(total_sms_parts * rate_per_part, 2) if PLAN_USAGE else 0.0
                expected_sent_add = total_sms_parts
                expected_ack_add = total_sms_parts
                expected_failed_add = 0

                expected_msg_trans_add = total_sms_parts
                if "excess" in determined_rate_type.lower():
                    expected_excess_add = total_sms_parts
            else:
                expected_parts_added = 0
                added_cost = 0.0
                expected_sent_add = total_sms_parts
                expected_ack_add = 0
                expected_failed_add = total_sms_parts

            expected_total_delivered = pre_dashboard["total_delivered"] + expected_parts_added

            base_consumed = pre_plan["consumed_amount"]
            if pre_plan["consumables_limit"] > 0 and base_consumed >= pre_plan["consumables_limit"]:
                base_consumed = 0.0

            expected_consumed_amount = round(base_consumed + added_cost, 2)
            expected_msg_transactions = pre_plan["msg_transactions"] + expected_msg_trans_add
            expected_excess_count = pre_plan["excess_count"] + expected_excess_add

            expected_report_sent = pre_sms_report["sent"] + expected_sent_add
            expected_report_ack = pre_sms_report["acknowledged"] + expected_ack_add
            expected_report_failed = pre_sms_report["failed"] + expected_failed_add

            post_dashboard = pre_dashboard
            post_plan = pre_plan
            post_sms_report = pre_sms_report

            for retries in range(8, 0, -1):
                print(f"  -> Polling SMS metrics... (Retries left: {retries})")
                post_dashboard = get_dashboard_metrics(page, target_delivered=expected_total_delivered)
                post_plan = get_plan_usage_metrics(page, plan_name=row_data["portal_plan_name"])
                post_sms_report = get_sms_report_metrics(page, target_telco=target_telco, target_country=row_data.get("country", "Philippines"))

                plan_usage_matched = (
                    not PLAN_USAGE or (
                        round(post_plan["consumed_amount"], 2) == round(expected_consumed_amount, 2) and
                        post_plan["msg_transactions"] == expected_msg_transactions and
                        post_plan["excess_count"] == expected_excess_count
                    )
                )

                if (
                    post_dashboard["total_delivered"] == expected_total_delivered and
                    plan_usage_matched and
                    post_sms_report["sent"] == expected_report_sent and
                    post_sms_report["acknowledged"] == expected_report_ack and
                    post_sms_report["failed"] == expected_report_failed
                ):
                    print("  ✨ All expected SMS failover metrics matched!")
                    break
                time.sleep(3)

            assert post_sms_report["sent"] == expected_report_sent, \
                f"SMS Sent Mismatch! Pre={pre_sms_report['sent']}, Expected={expected_report_sent}, Got={post_sms_report['sent']}"
            assert post_sms_report["acknowledged"] == expected_report_ack, \
                f"SMS Acknowledged Mismatch! Pre={pre_sms_report['acknowledged']}, Expected={expected_report_ack}, Got={post_sms_report['acknowledged']}"
            assert post_sms_report["failed"] == expected_report_failed, \
                f"SMS Failed Mismatch! Pre={pre_sms_report['failed']}, Expected={expected_report_failed}, Got={post_sms_report['failed']}"

            if PLAN_USAGE:
                assert round(post_plan["consumed_amount"], 2) == round(expected_consumed_amount, 2), \
                    f"Consumed Amount Mismatch! Expected=₱{expected_consumed_amount:.2f}, Got=₱{post_plan['consumed_amount']:.2f}"
                assert post_plan["msg_transactions"] == expected_msg_transactions, \
                    f"Message Transactions Mismatch! Expected={expected_msg_transactions}, Got={post_plan['msg_transactions']}"
                assert post_plan["excess_count"] == expected_excess_count, \
                    f"Excess Count Mismatch! Expected={expected_excess_count}, Got={post_plan['excess_count']}"

            print("  ✅ Condition 2 passed: SMS failover metrics validated.")

        # CONDITION 1: Viber delivered stats incremented & sms_failover_on == yes -> Skip SMS failover stats
        elif viber_delivered_incremented and sms_failover_enabled:
            print(f"\n[STEP 5] [CONDITION 1] Viber delivered stats incremented & sms_failover_on=YES. Skipping SMS failover verification.")
            assert (post_viber_dest["delivered"] >= expected_dest_delivered) or (post_viber["delivered"] >= expected_overview_delivered), \
                f"Viber delivery did not increment! Dest: Pre={pre_viber_dest['delivered']}, Post={post_viber_dest['delivered']} (Expected >= {expected_dest_delivered}) | Overview: Pre={pre_viber['delivered']}, Post={post_viber['delivered']} (Expected >= {expected_overview_delivered})"
            print(f"  ✅ Condition 1 passed: Viber delivery validated without checking SMS report.")

        # CONDITIONS 3 & 4: sms_failover_on == no -> Skip SMS failover stats
        elif not sms_failover_enabled:
            if viber_failed_incremented:
                print(f"\n[STEP 5] [CONDITION 3/4] Viber Destination Telco ({target_telco.upper()}) failed stats incremented & sms_failover_on=NO -> Skipping SMS failover stats.")
                assert post_viber_dest["failed"] - pre_viber_dest["failed"] >= expected_viber_add, \
                    f"Destination Telco Failed stat did not increment! Dest: Pre={pre_viber_dest['failed']}, Post={post_viber_dest['failed']} (Expected +{expected_viber_add})"
                print(f"  ✅ Condition 3/4 passed: Viber failure for {target_telco.upper()} acknowledged without checking SMS.")
            elif viber_delivered_incremented:
                print(f"\n[STEP 5] [CONDITION 3/4] Viber delivered stats incremented & sms_failover_on=NO -> Skipping SMS failover stats.")
                assert (post_viber_dest["delivered"] >= expected_dest_delivered) or (post_viber["delivered"] >= expected_overview_delivered)
                print("  ✅ Condition 3/4 passed: Viber delivery acknowledged without checking SMS.")
            else:
                pytest.fail("Viber stats did not increment for Delivery or Failure within timeout.")

        else:
            pytest.fail("Viber message did not increment Delivered nor Failed status within the polling timeout.")

        browser.close()
import csv
import math
import os
import re
import time
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright, Page, Playwright, expect, TimeoutError as PlaywrightTimeoutError

# Project directory setup
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / "data" / "recipients_standard.csv"

# =============================================================
# CONFIGURATIONS / FEATURE FLAGS
# =============================================================
# Set environment prefix: e.g., "dashboard" or "preprod-dashboard"
ENVIRONMENT = "stg-portal"

# Dynamic Base URLs constructed from ENVIRONMENT variable
BASE_URL = f"https://{ENVIRONMENT}.m360.com.ph"
LOGIN_URL = f"{BASE_URL}/login"

# Set to True to validate Plan Usage metrics, or False to skip Plan Usage completely.
PLAN_USAGE = False

# Configurable Accounts Dictionary
ACCOUNTS = {
    "standard": {
        "USERNAME": "3806261",
        "PASSWORD": "Em360@123!x",
        "APP_KEY": "J131ErbOQF53oXWn",
        "APP_SECRET": "vJ53pzI3bvGky2JsOx6cbc2xL1vp4TO4",
    },
    "unli": {
        "USERNAME": "qam3customunli",
        "PASSWORD": "gS0Fy65L",
        "APP_KEY": "WFQIIX9cRp4Wm29O",
        "APP_SECRET": "luE9lWjPSulaOUmzvhXhNPbP3qiQ5Cbf",
    }
}


def get_account_config(plan_name: str = "") -> dict:
    """Resolves account credentials based on ACCOUNT_TYPE environment variable or portal_plan_name."""
    env_account = os.getenv("ACCOUNT_TYPE", "").strip().lower()
    if env_account in ACCOUNTS:
        return ACCOUNTS[env_account]

    if "unli" in plan_name.lower():
        return ACCOUNTS["unli"]

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
    """Calculates SMS message parts based on character length."""
    length = len(text)
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

    plan_block = page.locator(f"xpath=//*[contains(text(), '{plan_name}')]/ancestor::div[contains(@class, 'v-card') or contains(@class, 'card') or contains(@class, 'row') or contains(@class, 'container') or self::div][1]")
    
    if plan_block.count() and plan_block.first.is_visible():
        consumables_label = plan_block.locator("xpath=.//*[text()='Consumables' or contains(text(), 'Consumables')]")
    else:
        consumables_label = page.locator("xpath=//*[text()='Consumables' or contains(text(), 'Consumables')]")

    has_consumables = consumables_label.count() > 0 and consumables_label.first.is_visible()

    is_premium = csv_sender_flag.lower() == "premium"

    if not has_excess_banner and has_consumables:
        res = "Premium_Regular" if is_premium else "Regular"
        print(f"  📊 Rate Condition Match: {res} (Excess Banner: NO | Consumables Label: YES)")
        return res

    elif has_excess_banner and has_consumables:
        res = "Premium_Excess" if is_premium else "Excess"
        print(f"  📊 Rate Condition Match: {res} (Excess Banner: YES | Consumables Label: YES)")
        return res

    elif not has_excess_banner and not has_consumables:
        res = "Premium_Excess" if is_premium else "Excess"
        print(f"  📊 Rate Condition Match: {res} (Excess Banner: NO | Consumables Label: NO)")
        return res

    res = "Premium_Excess" if is_premium else "Excess"
    print(f"  📊 Rate Condition Match: Fallback {res} (Excess Banner: {has_excess_banner} | Consumables Label: {has_consumables})")
    return res


def get_csv_rows() -> list[dict]:
    """Reads recipient rows safely. Returns an error dictionary if no data is found to prevent collection crashes."""
    if not CSV_PATH.exists():
        return [{"error": f"Required CSV file was not found at expected path: {CSV_PATH.resolve()}"}]

    rows_data = []

    try:
        with open(CSV_PATH, mode="r", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if not row:
                    continue

                clean_row = {
                    (k or "").strip().lower(): (v or "").strip()
                    for k, v in row.items()
                    if k
                }

                if not any(clean_row.values()):
                    continue

                to_val = clean_row.get("to") or clean_row.get("recipient") or clean_row.get("mobile") or clean_row.get("phone") or ""
                group_val = clean_row.get("group_option") or clean_row.get("group") or clean_row.get("groups") or ""
                tags_val = clean_row.get("tags_option") or clean_row.get("tag_option") or clean_row.get("tags") or clean_row.get("tag") or ""
                upload_val = clean_row.get("upload_csv_option") or clean_row.get("upload_csv") or clean_row.get("csv_option") or clean_row.get("file") or ""

                is_intl_bool = clean_row.get("is_intl", "true").lower() in ("true", "1", "yes")
                try:
                    dcs_val = int(clean_row.get("dcs", 0))
                except ValueError:
                    dcs_val = 0

                rows_data.append({
                    "to": to_val,
                    "group_option": group_val,
                    "tags_option": tags_val,
                    "upload_csv_option": upload_val,
                    "sender_id": (clean_row.get("sender_id") or clean_row.get("from") or clean_row.get("sender") or "qamoo10"),
                    "is_intl": is_intl_bool,
                    "dcs": dcs_val,
                    "text": clean_row.get("content_text") or clean_row.get("text") or clean_row.get("message") or "Hello from QA 1",
                    "sender_id_flag": clean_row.get("sender_id_flag", "regular").lower(),
                    "telco": clean_row.get("telco", "globe").lower(),
                    "country": clean_row.get("country", "Philippines"),
                    "is_optedout": clean_row.get("is_optedout", "no").lower() in ("yes", "true", "1"),
                    "portal_plan_name": clean_row.get("portal_plan_name", "M360 UNLI"),
                    "remarks": clean_row.get("remarks") or clean_row.get("remark") or ""
                })
    except Exception as exc:
        return [{"error": f"Failed to parse CSV file at {CSV_PATH.resolve()}: {exc}"}]

    if not rows_data:
        return [{"error": f"No valid rows found in {CSV_PATH.resolve()}. Ensure the CSV has headers and non-empty rows."}]

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
            
            if filtered_rows:
                return filtered_rows

    return rows_data


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
    return {
        "total_delivered": total_delivered
    }


def get_plan_usage_metrics(page: Page, plan_name: str) -> dict:
    """Fetches plan metrics: Consumed Amount, Consumables Limit, Message Transactions, and Excess."""
    if not PLAN_USAGE:
        print("  [LOG] PLAN_USAGE=False -> Skipping get_plan_usage_metrics fetch.")
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
    if not consumed_el or not consumed_el.count() or not consumed_el.first.is_visible():
        consumed_el = page.locator("xpath=//*[contains(text(), 'Total Consumed') or contains(text(), 'Total Excess Usage')]/following-sibling::*")

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

    print(f"  [LOG] Plan Usage Parsed -> Consumed: ₱{consumed_amount:.2f} | Transactions: {msg_transactions} | Excess: {excess_count}")

    return {
        "consumed_amount": consumed_amount,
        "consumables_limit": consumables_limit,
        "msg_transactions": msg_transactions,
        "excess_count": excess_count,
        "has_consumed": has_consumed,
        "has_consumables": has_consumables,
        "has_limit": has_limit
    }


def get_sms_report_metrics(page: Page, target_telco: str = "globe", target_country: str = "Philippines") -> dict:
    """Parses Sent, Acknowledged, and Failed counts from the 'Messages by Destination' table."""
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

            return {
                "sent": sent_val,
                "acknowledged": ack_val,
                "failed": failed_val
            }

    print(f"  ⚠️ Warning: Destination row for '{target_telco}' not found in table. Defaulting counts to 0.")
    return {"sent": 0, "acknowledged": 0, "failed": 0}


def wait_for_broadcast_status_completed(page: Page, broadcast_name: str, max_retries: int = 20, poll_interval: int = 5) -> None:
    """
    Polls the Broadcast List table, searches for the broadcast by name on each attempt,
    and checks if the status chip displays 'Completed'[cite: 3]. Refreshes and re-searches if still pending.
    """
    print(f"  [LOG] Verifying status 'Completed' for broadcast: '{broadcast_name}'...")
    
    for attempt in range(1, max_retries + 1):
        if "/broadcast" not in page.url:
            page.goto(f"{BASE_URL}/broadcast", wait_until="domcontentloaded")

        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)

        # RE-FILTER/SEARCH BY BROADCAST NAME ON EVERY POLL ATTEMPT
        search_input = page.locator("input[placeholder*='Search by broadcast name' i], input[data-testid='search-broadcast']").first
        if search_input.count() and search_input.is_visible():
            search_input.fill("")
            search_input.fill(broadcast_name)
            search_input.press("Enter")
            page.wait_for_timeout(1500)

        # Locate the specific broadcast row in the filtered Broadcast List table
        row_locator = page.locator("tr[data-cy='common-table-row-item'], table tbody tr").filter(
            has=page.locator(f"xpath=.//td[contains(normalize-space(), '{broadcast_name}')]")
        )

        if row_locator.count() > 0 and row_locator.first.is_visible():
            target_row = row_locator.first
            
            # Column 7 is 'Status' (Column 1: Checkbox, 2: Name, 3: Channel, 4: Date, 5: Success, 6: Bounced, 7: Status)[cite: 3]
            status_chip = target_row.locator(
                "xpath=.//td[7]//*[self::span or self::div or self::button or contains(@class, 'chip') or contains(@class, 'badge')] | .//td[7]"
            ).first

            current_status = status_chip.inner_text().strip() if status_chip.count() else ""

            # Fallback 1: Check specific chips/buttons in the row with status text
            if not current_status or current_status.isdigit():
                named_chip = target_row.locator("span, div, button").filter(
                    has_text=re.compile(r"^(completed|in progress|pending|failed|cancelled|scheduled)$", re.I)
                ).first
                if named_chip.count():
                    current_status = named_chip.inner_text().strip()

            # Fallback 2: Check raw row text
            if not current_status or current_status.isdigit():
                row_text = target_row.inner_text()
                for possible in ["Completed", "In Progress", "Pending", "Failed", "Cancelled"]:
                    if possible.lower() in row_text.lower():
                        current_status = possible
                        break

            print(f"  [LOG] [Attempt {attempt}/{max_retries}] Broadcast '{broadcast_name}' Status: '{current_status}'")

            if current_status.lower() == "completed":
                print(f"  ✅ Broadcast '{broadcast_name}' reached 'Completed' status.")
                return

            if current_status.lower() in ("failed", "cancelled", "error"):
                pytest.fail(f"❌ Broadcast '{broadcast_name}' failed with status: '{current_status}'")
        else:
            print(f"  [LOG] [Attempt {attempt}/{max_retries}] Broadcast row '{broadcast_name}' not yet visible...")

        time.sleep(poll_interval)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(1500)

    pytest.fail(f"❌ Timeout: Broadcast '{broadcast_name}' did not transition to 'Completed' status within {max_retries * poll_interval} seconds.")


@pytest.mark.parametrize("row_data", get_csv_rows())
def test_send_sms_journey_validation(row_data: dict):
    if "error" in row_data:
        pytest.fail(f"❌ CSV Error: {row_data['error']}")

    account = get_account_config(row_data.get("portal_plan_name", ""))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        # -------------------------------------------------------------
        # STEP 1: UI LOGIN (BYPASS NETWORK STALLS)
        # -------------------------------------------------------------
        print(f"\n[STEP 1] Logging into m360 Portal ({account['USERNAME']})...")
        
        login_loaded = False
        for nav_attempt in range(1, 4):
            try:
                page.goto(LOGIN_URL, timeout=20000, wait_until="domcontentloaded")
                user_input = page.locator("input[type='email'], input[name='email'], input[data-cy='username'], input[placeholder*='Email' i]").first
                user_input.wait_for(state="visible", timeout=10000)
                login_loaded = True
                break
            except PlaywrightTimeoutError:
                print(f"  ⚠️ Navigation to login page timed out (Attempt {nav_attempt}/3). Retrying...")
                time.sleep(2)

        if not login_loaded:
            browser.close()
            pytest.fail("❌ TERMINATING: Login page element failed to load after 3 retries.")

        user_input = page.locator("input[type='email'], input[name='email'], input[data-cy='username'], input[placeholder*='Email' i]").first
        pass_input = page.locator("input[type='password']").first
        login_btn = page.locator("button:has-text('Log In'), button[type='submit']").first

        user_input.fill(account["USERNAME"])
        pass_input.fill(account["PASSWORD"])
        login_btn.click()

        try:
            page.wait_for_url(lambda url: "/login" not in url, timeout=20000)
            page.wait_for_load_state("domcontentloaded")
            print("  [LOG] Successfully authenticated and loaded portal.")
        except PlaywrightTimeoutError:
            print(f"❌ Login redirected back to login page. Check credentials for: {account['USERNAME']}")
            browser.close()
            pytest.fail(f"❌ Authentication Failed: Invalid credentials or session kickback for {account['USERNAME']}.")

        # -------------------------------------------------------------
        # STEP 2: CAPTURE PRE-DATA & DETERMINE DYNAMIC RATE TYPE
        # -------------------------------------------------------------
        print(f"\n[STEP 2] Capturing Pre-Data metrics across Portal... (PLAN_USAGE={PLAN_USAGE})")
        
        for pre_attempt in range(3):
            pre_dashboard = get_dashboard_metrics(page)
            pre_plan = get_plan_usage_metrics(page, plan_name=row_data["portal_plan_name"])
            pre_report = get_sms_report_metrics(page, target_telco=row_data["telco"], target_country=row_data.get("country", "Philippines"))

            if pre_report["sent"] > 0 or pre_report["failed"] > 0 or pre_attempt == 2:
                break
            
            print(f"  ⚠️ Pre-data SMS Report captured 0s (Attempt {pre_attempt + 1}/3). Reloading for SPA DOM hydration...")
            time.sleep(2)

        determined_rate_type = determine_rate_type(
            page, 
            plan_name=row_data["portal_plan_name"], 
            csv_sender_flag=row_data["sender_id_flag"]
        )

        print(f"\n  📋 PRE-METRICS SUMMARY:")
        print(f"  -> Pre-Dashboard Total Delivered : {pre_dashboard['total_delivered']}")
        if PLAN_USAGE:
            print(f"  -> Pre-{row_data['portal_plan_name']} Total Consumed: ₱{pre_plan['consumed_amount']:.2f}")
            print(f"  -> Pre-Consumables Limit          : ₱{pre_plan['consumables_limit']:.2f}")
            print(f"  -> Pre-Message Transactions       : {pre_plan['msg_transactions']}")
            print(f"  -> Pre-Excess Count               : {pre_plan['excess_count']}")
        else:
            print("  -> Pre-Plan Usage Metrics        : [SKIPPED - PLAN_USAGE=False]")
        print(f"  -> Pre-SMS Report ({row_data['telco'].upper()}): Sent={pre_report['sent']} | Ack={pre_report['acknowledged']} | Failed={pre_report['failed']}")
        print(f"  -> Determined Rate Type          : {determined_rate_type}")

        # -------------------------------------------------------------
        # STEP 3: CREATE SMS BROADCAST (UI AUTOMATION WITH RETRIES)
        # -------------------------------------------------------------
        broadcast_name = f"dynamic_broadcast_{int(time.time())}"
        print(f"\n[STEP 3] Executing Broadcast Creation for '{broadcast_name}'...")
        
        page.goto(f"{BASE_URL}/broadcast", wait_until="domcontentloaded")
        page.locator("button:has-text('Create New Broadcast'), a:has-text('Create New Broadcast')").first.click()
        page.wait_for_url("**/broadcast/create")

        name_input = page.locator("input[placeholder*='Name' i], input[name='name']").first
        
        name_success = False
        for name_attempt in range(1, 4):
            print(f"  [LOG] Populating Broadcast Name (Attempt {name_attempt}/3)...")
            name_input.fill("")
            name_input.fill(broadcast_name)
            name_input.press("Tab")
            page.wait_for_timeout(500)

            val = name_input.input_value().strip()
            error_el = page.locator("div.v-messages__message, span.error-text").filter(has_text=re.compile(r"required|empty", re.I))
            
            if val == broadcast_name and not (error_el.count() and error_el.first.is_visible()):
                name_success = True
                print(f"  ✅ Broadcast Name verified: '{val}'")
                break
            
            print(f"  ⚠️ Broadcast Name validation issue detected. Retrying...")
            time.sleep(1)

        if not name_success:
            pytest.fail("❌ Failed to set a valid Broadcast Name after 3 attempts.")

        sms_channel = page.locator("text=SMS").first
        if sms_channel.is_visible():
            sms_channel.click()

        target_sender = row_data["sender_id"]
        print(f"  [LOG] Selecting Sender ID: {target_sender}")

        sender_slot = page.locator(".v-select__slot").filter(has=page.locator("[data-testid='sender-id-select-sms']")).first
        if not sender_slot.count() or not sender_slot.is_visible():
            sender_slot = page.locator(".v-select__slot").first

        try:
            sender_slot.scroll_into_view_if_needed(timeout=2000)
        except Exception:
            page.evaluate("el => el.scrollIntoView()", sender_slot.element_handle())

        sender_slot.click(force=True)

        page.wait_for_selector(".v-menu__content .v-list-item", timeout=5000)

        target_option = page.locator(".v-menu__content .v-list-item").filter(has_text=re.compile(rf"^{re.escape(target_sender)}$", re.I)).first

        if target_option.count():
            try:
                target_option.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
            page.wait_for_timeout(300)
            target_option.click(force=True)
            print(f"  ✅ Selected Sender ID: '{target_sender}'")
        else:
            print(f"  ⚠️ Target Sender ID '{target_sender}' not visible immediately. Attempting keyboard scroll navigation...")
            for _ in range(15):
                page.keyboard.press("ArrowDown")
                page.wait_for_timeout(100)
                active_opt = page.locator(".v-menu__content .v-list-item--highlighted, .v-menu__content .v-list-item--active").first
                if active_opt.count() and target_sender.lower() in active_opt.inner_text().lower():
                    page.keyboard.press("Enter")
                    break

        page.wait_for_timeout(300)

        # -------------------------------------------------------------
        # RECIPIENT SELECTION BASED ON CSV OPTIONS
        # -------------------------------------------------------------
        to_recipient = row_data.get("to")
        group_option = row_data.get("group_option")
        tags_option = row_data.get("tags_option")
        upload_csv_option = row_data.get("upload_csv_option")

        # CASE 1: Select from Contact List (Individual Mobile Number)
        if to_recipient:
            print(f"  [LOG] Option 1: Selecting from Contact List for '{to_recipient}'...")
            contact_btn = page.locator("xpath=//*[contains(text(), 'Select from Contact List')]/ancestor::button[1] | //button[descendant::*[contains(text(), 'Select from Contact List')]]").first

            modal_opened = False
            for open_attempt in range(1, 4):
                contact_btn.click(force=True)
                page.wait_for_timeout(300)

                modal_container = page.locator(".select-recipient-modal-container").first
                if not modal_container.is_visible():
                    contact_btn.evaluate("el => el.click()")

                try:
                    modal_container.wait_for(state="visible", timeout=5000)
                    modal_opened = True
                    break
                except PlaywrightTimeoutError:
                    print(f"  ⚠️ Modal not open on attempt {open_attempt}/3. Retrying...")
                    time.sleep(1)

            if not modal_opened:
                pytest.fail("❌ Contact List Modal failed to open.")

            search_input = page.locator(".select-recipient-modal-container [data-testid='search-recipients'] input, .select-recipient-modal-container input[placeholder*='Search']").first
            search_input.wait_for(state="visible", timeout=5000)
            search_input.click()
            search_input.fill("")
            search_input.fill(to_recipient)
            page.wait_for_timeout(1200)

            target_row = page.locator("tr").filter(has_text=to_recipient).first
            if target_row.count():
                target_row.click(force=True)
            else:
                page.locator(".modal-table table tr[data-cy='common-table-row-item'], .modal-table table tr").first.click(force=True)

            page.wait_for_timeout(500)

            add_recipients_btn = page.locator("button:has(span:has-text('Add Recipients'))").first
            if add_recipients_btn.is_disabled():
                checkbox_el = page.locator(f"[data-testid='checkbox-recipient-table-{to_recipient}'], .v-simple-checkbox").first
                checkbox_el.click(force=True)
                page.wait_for_timeout(500)

            expect(add_recipients_btn).to_be_enabled(timeout=5000)
            try:
                add_recipients_btn.click(force=True, timeout=2000)
            except Exception:
                add_recipients_btn.evaluate("el => el.click()")

        # CASE 2: Select from Group
        elif group_option:
            print(f"  [LOG] Option 2: Selecting Group '{group_option}'...")
            
            group_btn = page.locator("button:has-text('Select Contact Groups')").first
            group_btn.click(force=True)

            modal_container = page.locator("div[role='dialog'], .v-dialog, .select-recipient-modal-container").filter(has_text=re.compile(r"Select Recipients|Select Groups|Group", re.I)).first
            expect(modal_container).to_be_visible(timeout=5000)

            search_input = modal_container.locator("input[placeholder*='Search' i]").first
            if search_input.count() and search_input.is_visible():
                search_input.fill(group_option)
                page.wait_for_timeout(500)

            group_row = modal_container.locator("tr[data-cy='common-table-row-item'], tr").filter(has_text=re.compile(rf"^{re.escape(group_option)}$|\b{re.escape(group_option)}\b", re.I)).first
            expect(group_row).to_be_visible(timeout=5000)

            overlay_span = group_row.locator("span.inset-0").first
            if overlay_span.count():
                overlay_span.evaluate("el => el.click()")
            else:
                group_row.evaluate("el => el.click()")

            page.wait_for_timeout(500)

            add_btn = modal_container.locator("button:has-text('Add Recipients')").first
            if add_btn.is_disabled():
                checkbox = group_row.locator("input[type='checkbox'], .v-simple-checkbox").first
                if checkbox.count():
                    checkbox.evaluate("el => el.click()")
                else:
                    group_row.evaluate("el => el.click()")
                page.wait_for_timeout(500)

            expect(add_btn).to_be_enabled(timeout=5000)
            
            try:
                add_btn.click(force=True, timeout=2000)
            except Exception:
                add_btn.evaluate("el => el.click()")

            print(f"  ✅ Group '{group_option}' selected and added successfully.")

        # CASE 3: Select from Tags (SINGLE-CLICK WITH EXTENDED ASYNC ENABLE WAIT)
        elif tags_option:
            print(f"  [LOG] Option 3: Selecting Tag '{tags_option}'...")
            tag_btn = page.locator("button:has-text('Select Contacts by Tags')").first

            modal_container = page.locator("div[role='dialog'], .v-dialog").filter(
                has_text=re.compile(r"Select Recipients|Click to select Tags|Tags", re.I)
            ).first

            modal_opened = False
            for open_attempt in range(1, 4):
                tag_btn.click(force=True)
                page.wait_for_timeout(500)

                if modal_container.count() and modal_container.is_visible():
                    modal_opened = True
                    break
                print(f"  ⚠️ Tags modal not open on attempt {open_attempt}/3. Retrying...")
                time.sleep(1)

            if not modal_opened:
                pytest.fail("❌ Select Contacts by Tags modal failed to open.")

            search_input = modal_container.locator("input[placeholder*='Search' i], input[type='text'], input[role='searchbox']").first
            if search_input.count() and search_input.is_visible():
                search_input.click()
                search_input.fill("")
                search_input.fill(tags_option)
                page.wait_for_timeout(500)

            tag_chip_btn = modal_container.locator("button, div[role='button']").filter(
                has_text=re.compile(rf"^{re.escape(tags_option)}$|\b{re.escape(tags_option)}\b", re.I)
            ).first

            if not tag_chip_btn.count():
                tag_chip_btn = modal_container.locator("button:not(:has-text('Add Recipients')):not(:has-text('Cancel'))").first

            expect(tag_chip_btn).to_be_visible(timeout=5000)

            print(f"  [LOG] Clicking tag chip '{tags_option}'...")
            tag_chip_btn.click(force=True)

            add_btn = modal_container.locator("button:has-text('Add Recipients')").first

            print("  [LOG] Waiting up to 15s for m360 backend recipient calculation to enable 'Add Recipients'...")
            expect(add_btn).to_be_enabled(timeout=15000)

            try:
                add_btn.click(force=True, timeout=2000)
            except Exception:
                add_btn.evaluate("el => el.click()")

            print(f"  ✅ Tag '{tags_option}' selected successfully.")

        # CASE 4: Upload CSV File Option
        elif upload_csv_option:
            print(f"  [LOG] Option 4: Uploading CSV File from '{upload_csv_option}'...")
            file_path = Path(upload_csv_option)
            if not file_path.is_absolute():
                file_path = PROJECT_ROOT / upload_csv_option

            if not file_path.exists():
                pytest.fail(f"❌ Target upload CSV file not found at: {file_path.resolve()}")

            upload_input = page.locator("input[type='file']").first
            upload_input.set_input_files(str(file_path.resolve()))
            page.wait_for_timeout(1000)
            print(f"  ✅ Successfully uploaded file: '{file_path.name}'")

        else:
            pytest.fail("❌ No contact selection option (to, group_option, tags_option, or upload_csv_option) was specified in the CSV row.")

        print("  [LOG] Dismissing toaster notification banner if displayed...")
        toast_container = page.locator("div.v-snack:has-text('added'), div.v-alert:has-text('added'), div:has-text('successfully')").first
        if toast_container.count() and toast_container.is_visible():
            toast_close_btn = toast_container.locator("button, i.v-icon--link, .mdi-close, svg").first
            if toast_close_btn.count() and toast_close_btn.is_visible():
                toast_close_btn.click(force=True)
                page.wait_for_timeout(300)

        try:
            toast_container.wait_for(state="detached", timeout=3000)
            print("  ✅ Toaster banner detached successfully.")
        except PlaywrightTimeoutError:
            print("  ⚠️ Toaster banner state delayed or not rendered.")

        print(f"  [LOG] Entering message content: '{row_data['text']}'")
        message_input = page.locator("textarea, div[contenteditable='true']").first
        message_input.fill(row_data["text"])
        page.wait_for_timeout(1000)

        # -------------------------------------------------------------
        # OPT-OUT FOOTER DETECTION & TEXT EXTRACTION
        # -------------------------------------------------------------
        checkbox_container = page.locator("label:has-text('Include opt-out footer'), div:has-text('Include opt-out footer')").last
        checkbox_input = checkbox_container.locator("input[type='checkbox']")
        
        has_optout_footer = False
        if checkbox_input.count() > 0:
            has_optout_footer = checkbox_input.is_checked()
        else:
            has_optout_footer = page.locator(".v-input--checkbox.v-input--is-label-active, i.mdi-checkbox-marked").count() > 0

        optout_text = ""
        if has_optout_footer:
            footer_dropdown = page.locator(".v-select:has-text('NoMsgs'), div:has-text('NoMsgs? Txt OFF')").last
            if footer_dropdown.count() and footer_dropdown.is_visible():
                raw_text = footer_dropdown.inner_text().strip()
                optout_text = re.sub(r"\s+", " ", raw_text)
            
            if not optout_text:
                dropdown_val = page.locator("input[placeholder*='opt-out' i], .v-select__selection").first
                if dropdown_val.count():
                    optout_text = dropdown_val.inner_text().strip()

            if not optout_text:
                optout_text = f"NoMsgs? Txt OFF {target_sender} to 22565"

            print(f"  [LOG] Opt-Out Footer is CHECKED. Text captured: '{optout_text}'")
        else:
            print("  [LOG] Opt-Out Footer is UNCHECKED. Excluding footer text from parts count.")

        # -------------------------------------------------------------
        # UI PARTS & CHARACTERS COUNTER EXTRACTION
        # -------------------------------------------------------------
        ui_parts_count = 0
        ui_chars_count = 0

        counter_container = page.locator("div:has-text('SMS Parts'), div:has-text('Characters')").last
        if counter_container.count() and counter_container.is_visible():
            counter_raw = counter_container.inner_text()
            
            parts_match = re.search(r"(\d+)\s*/\s*\d+\s*SMS\s*Parts", counter_raw, re.I)
            if parts_match:
                ui_parts_count = int(parts_match.group(1))

            chars_match = re.search(r"(\d+)\s*/\s*\d+\s*Characters", counter_raw, re.I)
            if chars_match:
                ui_chars_count = int(chars_match.group(1))

        print(f"  [LOG] Scraped UI Counters -> Parts: {ui_parts_count} | Chars: {ui_chars_count}")

        print("  [LOG] Waiting for 'Start broadcast' button to be ready...")
        start_btn = page.locator("button.broadcast-start, button:has-text('Start broadcast')").first
        
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        
        expect(start_btn).to_be_visible(timeout=5000)
        expect(start_btn).to_be_enabled(timeout=5000)
        page.wait_for_timeout(500)

        print("  [LOG] Submitting broadcast form...")
        summary_modal_container = page.locator(".broadcast-summary-container").first
        summary_modal_rendered = False

        for submit_retry in range(1, 5):
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            try:
                start_btn.click(force=True, timeout=2000)
            except Exception:
                start_btn.evaluate("el => el.click()")

            try:
                summary_modal_container.wait_for(state="visible", timeout=3000)
                expect(summary_modal_container.locator("h2:has-text('Broadcast Summary')").first).to_be_visible(timeout=3000)
                
                confirm_opt = summary_modal_container.locator("xpath=./ancestor::div[contains(@class, 'v-dialog')][1]//button").filter(has_text=re.compile(r"confirm and start broadcast", re.I)).first
                confirm_opt.wait_for(state="visible", timeout=3000)
                
                summary_modal_rendered = True
                print("  [LOG] Broadcast Summary modal rendered successfully with complete details.")
                break
            except PlaywrightTimeoutError:
                print(f"  ⚠️ Broadcast Summary container incomplete or delayed after 3s (Attempt {submit_retry}/4). Retrying click...")
                time.sleep(1)

        if not summary_modal_rendered:
            pytest.fail("❌ Broadcast Summary modal failed to render completely after 4 attempts.")

        print("  [LOG] Waiting 1s after modal display before confirming broadcast...")
        page.wait_for_timeout(1000)

        confirm_btn = summary_modal_container.locator("xpath=./ancestor::div[contains(@class, 'v-dialog')][1]//button").filter(has_text=re.compile(r"confirm and start broadcast", re.I)).first
        if not confirm_btn.count():
            confirm_btn = page.locator("button").filter(has_text=re.compile(r"confirm and start broadcast", re.I)).first

        expect(confirm_btn).to_be_visible(timeout=5000)
        expect(confirm_btn).to_be_enabled(timeout=5000)
        
        print("  [LOG] Confirming broadcast creation...")
        try:
            with page.expect_response(lambda response: "/broadcast" in response.url or response.status == 200, timeout=12000):
                confirm_btn.click(force=True)
        except Exception:
            confirm_btn.evaluate("el => el.click()")

        try:
            page.locator(".v-dialog--active").wait_for(state="detached", timeout=12000)
        except PlaywrightTimeoutError:
            print("  ⚠️ Summary modal overlay state delayed in detaching.")

        # -------------------------------------------------------------
        # STEP 3.5: WAIT UNTIL BROADCAST STATUS IS 'COMPLETED'
        # -------------------------------------------------------------
        wait_for_broadcast_status_completed(page, broadcast_name=broadcast_name, max_retries=20, poll_interval=5)
        print("  [LOG] Broadcast created successfully and verified in Broadcast List.")

        # -------------------------------------------------------------
        # STEP 4: CALCULATE EXPECTED METRIC INCREMENTS
        # -------------------------------------------------------------
        print("\n[STEP 4] Calculating Expected Metric Increments...")
        
        if has_optout_footer and optout_text:
            full_content_text = f"{row_data['text']}\n{optout_text}"
        else:
            full_content_text = row_data["text"]

        char_count = ui_chars_count if ui_chars_count > 0 else len(full_content_text)
        parts_count = ui_parts_count if ui_parts_count > 0 else calculate_sms_parts(full_content_text)
        rate_per_part = get_sms_rate(row_data["telco"], determined_rate_type) if PLAN_USAGE else 0.0

        print(f"  [LOG] Content Parts Calc -> Text: '{full_content_text}' | Length: {char_count} chars -> Parts: {parts_count} (UI Counter: {ui_parts_count})")

        is_cashbus_sender = row_data["sender_id"].strip().lower() == "cashbus"

        expected_msg_trans_add = 0
        expected_excess_add = 0

        if is_cashbus_sender:
            print("  ❌ Priority 1 Match: CASHBUS SENDER ID DETECTED.")
            expected_parts_added = 0
            added_cost = 0.0
            expected_sent_add = parts_count
            expected_ack_add = 0
            expected_failed_add = parts_count

            expected_broadcast_success = 0
            expected_broadcast_bounced = parts_count

        elif row_data["is_optedout"]:
            print("  ⚠️ Priority 2 Match: RECIPIENT IS OPTED OUT (NO DELIVERED OR PLAN DEDUCTION, INCREMENTING FAILED & BOUNCED STATS).")
            expected_parts_added = 0
            added_cost = 0.0
            expected_sent_add = parts_count
            expected_ack_add = 0
            expected_failed_add = parts_count

            expected_broadcast_success = 0
            expected_broadcast_bounced = parts_count

            expected_msg_trans_add = 0
            expected_excess_add = 0

        else:
            print("  ✅ Priority 3 Match: SUCCESSFUL TRANSACTION ASSUMPTION.")
            expected_parts_added = parts_count
            added_cost = round(parts_count * rate_per_part, 2) if PLAN_USAGE else 0.0
            expected_sent_add = parts_count
            expected_ack_add = parts_count
            expected_failed_add = 0

            expected_broadcast_success = parts_count
            expected_broadcast_bounced = 0

            has_consumed = pre_plan["has_consumed"]
            has_consumables = pre_plan["has_consumables"]
            has_limit = pre_plan["has_limit"]
            total_consumed = pre_plan["consumed_amount"]
            consumables = pre_plan["consumables_limit"]

            if has_consumed and has_consumables and (total_consumed <= consumables) and has_limit:
                expected_msg_trans_add = parts_count
                expected_excess_add = 0
            elif has_consumed and has_consumables and (total_consumed > consumables) and has_limit:
                expected_msg_trans_add = parts_count
                expected_excess_add = parts_count
            elif not has_consumed and not has_consumables and has_limit:
                expected_msg_trans_add = parts_count
                expected_excess_add = 0
            else:
                expected_msg_trans_add = parts_count
                expected_excess_add = 0

        expected_total_delivered = pre_dashboard["total_delivered"] + expected_parts_added

        base_consumed = pre_plan["consumed_amount"]
        if pre_plan["consumables_limit"] > 0 and base_consumed >= pre_plan["consumables_limit"]:
            print(f"  🔄 Consumables limit reached (₱{pre_plan['consumables_limit']:.2f}). Resetting base to ₱0.00.")
            base_consumed = 0.0

        expected_consumed_amount = round(base_consumed + added_cost, 2)
        expected_msg_transactions = pre_plan["msg_transactions"] + expected_msg_trans_add
        expected_excess_count = pre_plan["excess_count"] + expected_excess_add

        expected_report_sent = pre_report["sent"] + expected_sent_add
        expected_report_ack = pre_report["acknowledged"] + expected_ack_add
        expected_report_failed = pre_report["failed"] + expected_failed_add

        print(f"  [LOG] Expected Targets -> Delivered: {expected_total_delivered} | Consumed: ₱{expected_consumed_amount:.2f} | Sent: {expected_report_sent} | Ack: {expected_report_ack} | Failed: {expected_report_failed}")
        print(f"  [LOG] Expected Broadcast Stats -> Success: {expected_broadcast_success} | Bounced: {expected_broadcast_bounced}")

        # -------------------------------------------------------------
        # STEP 5: CAPTURE POST-DATA & VALIDATE
        # -------------------------------------------------------------
        print(f"\n[STEP 5] Fetching Post-Data with sync polling... (PLAN_USAGE={PLAN_USAGE})")

        def stats_match(dash: dict, plan: dict, rep: dict) -> bool:
            plan_usage_matched = (
                not PLAN_USAGE or (
                    round(plan["consumed_amount"], 2) == round(expected_consumed_amount, 2) and
                    plan["msg_transactions"] == expected_msg_transactions and
                    plan["excess_count"] == expected_excess_count
                )
            )
            return (
                dash["total_delivered"] == expected_total_delivered and
                plan_usage_matched and
                rep["sent"] == expected_report_sent and
                rep["acknowledged"] == expected_report_ack and
                rep["failed"] == expected_report_failed
            )

        retries = 8
        while retries > 0:
            print(f"  -> Polling cycle... (Retries left: {retries})")
            
            post_dashboard = get_dashboard_metrics(page, target_delivered=expected_total_delivered)
            post_plan = get_plan_usage_metrics(page, plan_name=row_data["portal_plan_name"])
            post_report = get_sms_report_metrics(page, target_telco=row_data["telco"], target_country=row_data.get("country", "Philippines"))

            if stats_match(post_dashboard, post_plan, post_report):
                print("  ✨ All expected portal metrics matched! Terminating retries immediately.")
                break

            print(f"     [Pending Sync] Delivered: {post_dashboard['total_delivered']}/{expected_total_delivered} | Failed: {post_report['failed']}/{expected_report_failed}")
            time.sleep(3)
            retries -= 1

        # -------------------------------------------------------------
        # STEP 6: VALIDATE BROADCAST PAGE & DETAILS METRICS
        # -------------------------------------------------------------
        print("\n[STEP 6] Validating Broadcast List and Inner Details Page...")

        page.goto(f"{BASE_URL}/broadcast", wait_until="domcontentloaded")
        page.wait_for_selector("table.table-wrapper, table", timeout=15000)

        # Filter by broadcast name before reading row stats
        search_broadcast = page.locator("input[placeholder*='Search by broadcast name' i]").first
        if search_broadcast.count() and search_broadcast.is_visible():
            search_broadcast.fill(broadcast_name)
            search_broadcast.press("Enter")
            page.wait_for_timeout(1000)

        broadcast_row = page.locator("tr[data-cy='common-table-row-item'], table tbody tr").filter(
            has=page.locator(f"[data-testid='row-broadcastName']:has-text('{broadcast_name}'), td:has-text('{broadcast_name}')")
        ).first
        expect(broadcast_row).to_be_visible(timeout=10000)

        outer_success_text = broadcast_row.locator("[data-testid='row-success'], td:nth-child(5)").inner_text().strip()
        outer_bounced_text = broadcast_row.locator("[data-testid='row-bounced'], td:nth-child(6)").inner_text().strip()

        outer_success = int(outer_success_text) if outer_success_text.isdigit() else 0
        outer_bounced = int(outer_bounced_text) if outer_bounced_text.isdigit() else 0

        print(f"  [LOG] Broadcast List Row Stats -> Success: {outer_success} | Bounced: {outer_bounced}")

        broadcast_row.locator("a.inset-0, button, td:last-child").first.click()
        page.wait_for_selector(".broadcast-details-container", timeout=15000)

        inner_sent_text = page.locator(".card-broadcast-sent h1 span").first.inner_text().strip()
        inner_ack_text = page.locator(".card-broadcast-sent .detail p").first.inner_text().strip()
        inner_bounced_text = page.locator(".card-broadcast-bounced h1 span").first.inner_text().strip()

        inner_sent = int(inner_sent_text) if inner_sent_text.isdigit() else 0
        inner_ack = int(inner_ack_text) if inner_ack_text.isdigit() else 0
        inner_bounced = int(inner_bounced_text) if inner_bounced_text.isdigit() else 0

        print(f"  [LOG] Broadcast Details Page Stats -> Total Sent: {inner_sent} | Ack: {inner_ack} | Bounced: {inner_bounced}")

        print("\n--- METRIC COMPARISON SUMMARY ---")
        print(f"  Text Length              : {char_count} characters ({parts_count} part(s))")
        print(f"  Target Telco             : {row_data['telco'].upper()}")
        print(f"  Plan Usage Flag Config   : {PLAN_USAGE}")
        print(f"  Total Delivered Messages : Pre={pre_dashboard['total_delivered']} | Post={post_dashboard['total_delivered']} (Expected: {expected_total_delivered})")
        if PLAN_USAGE:
            print(f"  Total Consumed Amount    : Pre=₱{pre_plan['consumed_amount']:.2f} | Post=₱{post_plan['consumed_amount']:.2f} (Expected: ₱{expected_consumed_amount:.2f})")
            print(f"  Message Transactions     : Pre={pre_plan['msg_transactions']} | Post={post_plan['msg_transactions']} (Expected: {expected_msg_transactions})")
            print(f"  Excess Count             : Pre={pre_plan['excess_count']} | Post={post_plan['excess_count']} (Expected: {expected_excess_count})")
        else:
            print("  Plan Usage Metrics       : [SKIPPED - PLAN_USAGE=False]")
        print(f"  SMS Report - Sent        : Pre={pre_report['sent']} | Post={post_report['sent']} (Expected: {expected_report_sent})")
        print(f"  SMS Report - Acknowledged: Pre={pre_report['acknowledged']} | Post={post_report['acknowledged']} (Expected: {expected_report_ack})")
        print(f"  SMS Report - Failed      : Pre={pre_report['failed']} | Post={post_report['failed']} (Expected: {expected_report_failed})")
        print(f"  Broadcast List Success   : Got={outer_success} | Expected={expected_broadcast_success}")
        print(f"  Broadcast List Bounced   : Got={outer_bounced} | Expected={expected_broadcast_bounced}")
        print(f"  Broadcast Details Sent   : Got={inner_sent} | Expected={expected_sent_add}")
        print(f"  Broadcast Details Bounced: Got={inner_bounced} | Expected={expected_broadcast_bounced}")
        print("---------------------------------\n")

        print("  [LOG] Performing final assertion validations...")
        assert post_dashboard["total_delivered"] == expected_total_delivered, \
            f"Delivered Count Mismatch! Pre={pre_dashboard['total_delivered']}, Expected={expected_total_delivered}, Got={post_dashboard['total_delivered']}"

        if PLAN_USAGE:
            assert round(post_plan["consumed_amount"], 2) == round(expected_consumed_amount, 2), \
                f"Consumed Amount Mismatch! Pre=₱{pre_plan['consumed_amount']:.2f}, Expected=₱{expected_consumed_amount:.2f}, Got=₱{post_plan['consumed_amount']:.2f}"

            assert post_plan["msg_transactions"] == expected_msg_transactions, \
                f"Message Transactions Mismatch! Pre={pre_plan['msg_transactions']}, Expected={expected_msg_transactions}, Got={post_plan['msg_transactions']}"

            assert post_plan["excess_count"] == expected_excess_count, \
                f"Excess Count Mismatch! Pre={pre_plan['excess_count']}, Expected={expected_excess_count}, Got={post_plan['excess_count']}"
        else:
            print("  ⚠️ Skipping Plan Usage assertions (PLAN_USAGE is set to False).")

        assert post_report["sent"] == expected_report_sent, \
            f"Report Sent Count Mismatch! Pre={pre_report['sent']}, Expected={expected_report_sent}, Got={post_report['sent']}"

        assert post_report["acknowledged"] == expected_report_ack, \
            f"Report Acknowledged Count Mismatch! Pre={pre_report['acknowledged']}, Expected={expected_report_ack}, Got={post_report['acknowledged']}"

        assert post_report["failed"] == expected_report_failed, \
            f"Report Failed Count Mismatch! Pre={pre_report['failed']}, Expected={expected_report_failed}, Got={post_report['failed']}"

        assert outer_success == expected_broadcast_success, \
            f"Broadcast List Outer Success Mismatch! Expected={expected_broadcast_success}, Got={outer_success}"

        assert outer_bounced == expected_broadcast_bounced, \
            f"Broadcast List Outer Bounced Mismatch! Expected={expected_broadcast_bounced}, Got={outer_bounced}"

        assert inner_sent == expected_sent_add, \
            f"Broadcast Details Inner Total Sent Mismatch! Expected={expected_sent_add}, Got={inner_sent}"

        assert inner_bounced == expected_broadcast_bounced, \
            f"Broadcast Details Inner Bounced Mismatch! Expected={expected_broadcast_bounced}, Got={inner_bounced}"

        print("✅ All Dashboard, Plan Usage, SMS Report, Broadcast List, and Broadcast Details validations passed successfully!")
        browser.close()
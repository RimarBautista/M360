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
CSV_PATH = PROJECT_ROOT / "data" / "recipients_standard_intl.csv"

# =============================================================
# CONFIGURATIONS / FEATURE FLAGS
# =============================================================
ENVIRONMENT = "dashboard"

# Dynamic Base URLs constructed from ENVIRONMENT variable
BASE_URL = f"https://{ENVIRONMENT}.m360.com.ph"
LOGIN_URL = f"{BASE_URL}/login"
API_URL = "https://api.m360.com.ph/v3/api/broadcast"

# Set to True to validate Plan Usage metrics, or False to skip Plan Usage completely.
PLAN_USAGE = True

# Configurable Accounts Dictionary
ACCOUNTS = {
    "standard1": {
        "USERNAME": "jgmy360plan50k",
        "PASSWORD": "Em360@123!!@",
        "APP_KEY": "p47Q0IlCdxQyzERT",
        "APP_SECRET": "GMS22AdjM8gpneMo3XjJ19yET7R6lLRA",
    },
    "standard2": {
        "USERNAME": "jgmy360plan50k2",
        "PASSWORD": "Em360@123!",
        "APP_KEY": "60UVob2GIJBy708z",
        "APP_SECRET": "clkDlCr8A7Ah9TM6zoPJ4vCzRVMmzWqb",
    },
    "unli": {
        "USERNAME": "qam3customunli",
        "PASSWORD": "gS0Fy65L",
        "APP_KEY": "WFQIIX9cRp4Wm29O",
        "APP_SECRET": "luE9lWjPSulaOUmzvhXhNPbP3qiQ5Cbf",
    }
}


def get_account_config(plan_name: str = "", intl_platform_enable: str = "") -> dict:
    """Resolves account credentials based on intl_platform_enable, ACCOUNT_TYPE env var, or portal_plan_name."""
    env_account = os.getenv("ACCOUNT_TYPE", "").strip().lower()
    if env_account in ACCOUNTS:
        return ACCOUNTS[env_account]

    intl_flag = str(intl_platform_enable).strip().lower()
    if intl_flag in ("yes", "true", "1"):
        return ACCOUNTS["standard1"]
    elif intl_flag in ("no", "false", "0"):
        return ACCOUNTS["standard2"]

    if "unli" in plan_name.lower():
        return ACCOUNTS["unli"]

    return ACCOUNTS["standard1"]


def is_ph_telco(telco: str, country: str = "Philippines") -> bool:
    """Checks if recipient is a standard PH telco (Globe, Smart, DITO)."""
    t_clean = telco.strip().lower()
    c_clean = country.strip().lower()

    if t_clean in ("spain", "international") or c_clean not in ("philippines", "ph"):
        return False
    return t_clean in ("globe", "dito", "smart", "sun", "tnt")


def is_postman_level_error(status_code: int, response_json: dict) -> bool:
    """
    Determines if an API response is an error at the API/Postman level.
    Postman-level errors typically return non-200/201 HTTP statuses or root error codes.
    """
    if status_code not in (200, 201):
        return True
    
    root_code = response_json.get("code")
    if root_code is not None and int(root_code) not in (200, 201):
        return True

    return False


def get_expected_scenario(row_data: dict) -> dict:
    """
    Evaluates scenario rules against CSV fields.
    Returns expected non-BAU error metadata, or {'is_bau': True} to proceed with full stats/deductions validation.
    """
    intl_enable = str(row_data.get("intl_platform_enable", "no")).strip().lower() in ("yes", "true", "1")
    is_intl = row_data.get("is_intl", False)
    is_ph = is_ph_telco(row_data.get("telco", ""), row_data.get("country", "Philippines"))

    # =========================================================
    # INTERNATIONAL (NON-PH RECIPIENT) VALIDATION RULES
    # =========================================================
    if not is_ph:
        if is_intl and intl_enable:
            return {"is_bau": True}

        if not is_intl and intl_enable:
            return {
                "is_bau": False,
                "expected_type": "error",
                "expected_status": 400,
                "expected_json": {
                    "code": 400,
                    "name": "Bad Request",
                    "message": "Unauthorized to send to international (non-PH) mobile number."
                }
            }

        if is_intl and not intl_enable:
            return {
                "is_bau": False,
                "expected_type": "error",
                "expected_status": 401,
                "expected_json": {
                    "code": 401,
                    "name": "Unauthorized",
                    "message": "International transactions is not allowed."
                }
            }

        if not is_intl and not intl_enable:
            return {
                "is_bau": False,
                "expected_type": "error",
                "expected_status": 400,
                "expected_json": {
                    "code": 400,
                    "name": "Bad Request",
                    "message": "Unauthorized to send to international (non-PH) mobile number."
                }
            }

    # =========================================================
    # PH RECIPIENT RULES
    # =========================================================
    if is_ph and is_intl and not intl_enable:
        return {
            "is_bau": False,
            "expected_type": "error",
            "expected_status": 401,
            "expected_json": {
                "code": 401,
                "name": "Unauthorized",
                "message": "International transactions is not allowed."
            }
        }

    return {"is_bau": True}


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
    "SMS_Spain_Excess": 11.10,
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

    print("  [LOG] Navigating to Plan Usage page to calculate dynamic rate type...")
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
    """Reads recipient rows and mapped fields from CSV, handling positional duplicates safely."""
    if not CSV_PATH.exists():
        pytest.fail(f"Required CSV file was not found at expected path: {CSV_PATH.resolve()}")

    rows_data = []
    with open(CSV_PATH, mode="r", encoding="utf-8") as file:
        reader = csv.reader(file)
        headers = next(reader, None)

        if headers:
            is_intl_indices = [i for i, h in enumerate(headers) if h.strip() == "is_intl"]
            target_is_intl_idx = is_intl_indices[0] if is_intl_indices else None

            for row in reader:
                if not row:
                    continue

                row_dict = {headers[i].strip(): row[i].strip() for i in range(min(len(headers), len(row)))}

                to_val = row_dict.get("to", "")
                if to_val:
                    if target_is_intl_idx is not None and target_is_intl_idx < len(row):
                        is_intl_raw = row[target_is_intl_idx].strip()
                    else:
                        is_intl_raw = row_dict.get("is_intl", "true").strip()

                    is_intl_bool = is_intl_raw.lower() in ("true", "1", "yes")

                    try:
                        dcs_val = int(row_dict.get("dcs", 0))
                    except ValueError:
                        dcs_val = 0

                    rows_data.append({
                        "to": to_val,
                        "sender_id": (row_dict.get("sender_id") or row_dict.get("from") or "qamoo10").strip(),
                        "is_intl": is_intl_bool,
                        "dcs": dcs_val,
                        "text": row_dict.get("content_text", "Hello from QA 1").strip(),
                        "sender_id_flag": row_dict.get("sender_id_flag", "regular").strip().lower(),
                        "telco": row_dict.get("telco", "globe").strip().lower(),
                        "country": row_dict.get("country", "Philippines").strip(),
                        "is_optedout": row_dict.get("is_optedout", "no").strip().lower() in ("yes", "true", "1"),
                        "portal_plan_name": row_dict.get("portal_plan_name", "M360 UNLI").strip(),
                        "intl_platform_enable": row_dict.get("intl_platform_enable", "no").strip(),
                        "remarks": (row_dict.get("remarks") or row_dict.get("remark") or "").strip()
                    })

    if not rows_data:
        pytest.fail(f"No valid rows found in {CSV_PATH}")

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


def get_dashboard_metrics(page: Page, target_delivered: int = 0) -> dict:
    """Fetches 'Total Delivered Messages' from Dashboard, ensuring SPA network hydration finishes."""
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
    """Fetches plan metrics including Consumed, Consumables, Message Transactions, and Excess."""
    if not PLAN_USAGE:
        print("  [LOG] PLAN_USAGE=False -> Skipping get_plan_usage_metrics fetch.")
        return {
            "consumed_amount": 0.0,
            "consumables_limit": 0.0,
            "msg_transactions": 0,
            "excess_count": 0,
            "has_consumed": False,
            "has_consumables": False,
            "has_limit": False,
        }

    print("  [LOG] Fetching Plan Usage metrics...")
    page.goto(f"{BASE_URL}/plan-usage", wait_until="domcontentloaded")
    
    try:
        page.wait_for_selector("[data-testid='total-usage'], [data-testid='total-excess'], [data-testid='total-excess-usage']", timeout=15000)
    except PlaywrightTimeoutError:
        page.wait_for_selector("text=Total Consumed", timeout=10000)
        
    page.wait_for_timeout(2000)

    plan_block = page.locator(
        f"xpath=//*[contains(text(), '{plan_name}')]/ancestor::div[contains(@class, 'v-card') or contains(@class, 'card') or contains(@class, 'row') or contains(@class, 'container') or self::div][1]"
    )

    def parse_numeric_element(locator_obj):
        if locator_obj and locator_obj.count() and locator_obj.first.is_visible():
            text_val = locator_obj.first.inner_text().strip()
            match = re.search(r"\d+(?:\.\d+)?", text_val.replace(",", ""))
            match_val = float(match.group(0)) if match else 0.0
            return match_val, True
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
        "has_limit": has_limit,
    }


def get_sms_report_metrics(page: Page, target_telco: str = "globe", target_country: str = "Philippines") -> dict:
    """Parses Sent, Acknowledged, and Failed counts from the 'Messages by Destination' table matching Telco and Country."""
    print(f"  [LOG] Fetching SMS Report metrics for destination: {target_telco.upper()} ({target_country})...")
    page.goto(f"{BASE_URL}/reports/channel/sms", wait_until="domcontentloaded")
    
    try:
        page.wait_for_selector("text=Messages by Destination", timeout=15000)
        page.wait_for_selector("table tbody tr, tr td", timeout=12000)
    except PlaywrightTimeoutError:
        page.wait_for_timeout(2000)

    telco_clean = target_telco.strip().lower()
    country_clean = target_country.strip().lower()

    if telco_clean in ("spain", "international") or country_clean != "philippines":
        telco_search = "international"
        country_search = telco_clean if telco_clean != "international" else country_clean
    else:
        telco_search = telco_clean
        country_search = country_clean

    row_xpath = (
        f"//tr["
        f"td[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{telco_search}')] "
        f"and td[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{country_search}')]"
        f"]"
    )
    fallback_xpath = (
        f"//tr["
        f".//text()[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{telco_search}')] "
        f"and .//text()[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{country_search}')]"
        f"]"
    )

    row_locator = page.locator(f"xpath={row_xpath}").first
    row_found = False

    try:
        row_locator.wait_for(state="visible", timeout=8000)
        row_found = True
    except PlaywrightTimeoutError:
        row_locator = page.locator(f"xpath={fallback_xpath}").first
        try:
            row_locator.wait_for(state="visible", timeout=5000)
            row_found = True
        except PlaywrightTimeoutError:
            row_found = False

    if row_found and row_locator.is_visible():
        cells = row_locator.locator("td")
        if cells.count() >= 5:
            def extract_int(text: str) -> int:
                clean = re.sub(r"\d+(?:\.\d+)?%", "", text)
                nums = re.findall(r"\b\d+\b", clean.replace(",", ""))
                return int(nums[0]) if nums else 0

            sent_val = extract_int(cells.nth(2).inner_text())
            ack_val = extract_int(cells.nth(3).inner_text())
            failed_val = extract_int(cells.nth(4).inner_text())

            print(f"  [LOG] Found row '{target_telco.upper()} | {target_country}' -> Sent: {sent_val} | Ack: {ack_val} | Failed: {failed_val}")

            return {
                "sent": sent_val,
                "acknowledged": ack_val,
                "failed": failed_val
            }

    print(f"  ⚠️ Warning: Destination row for '{target_telco} ({target_country})' not found in table. Defaulting counts to 0.")
    return {"sent": 0, "acknowledged": 0, "failed": 0}


@pytest.mark.parametrize("row_data", get_csv_rows())
def test_send_sms_journey_validation(row_data: dict):
    account = get_account_config(
        plan_name=row_data.get("portal_plan_name", ""),
        intl_platform_enable=row_data.get("intl_platform_enable", "")
    )

    scenario_result = get_expected_scenario(row_data)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context()
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
                        print(f"  ⚠️ Login form not rendered within 3s. Waiting 2s before refresh... (Retries left: {login_retries})")
                        time.sleep(2)
                        try:
                            page.goto(LOGIN_URL, timeout=10000, wait_until="domcontentloaded")
                        except PlaywrightTimeoutError:
                            print("  ⚠️ Refresh attempt timed out. Continuing to next retry attempt...")

            if not login_loaded:
                print(f"\n❌ CRITICAL: Login page failed to render properly after 3 refresh retries.")
                pytest.fail("❌ TERMINATING: Login page element failed to load after 3 refresh retries.")

            user_input.fill(account["USERNAME"])
            pass_input.fill(account["PASSWORD"])
            login_btn.click()

            try:
                page.wait_for_url(lambda url: "/login" not in url, timeout=15000)
                page.wait_for_load_state("domcontentloaded")
                print("  [LOG] Authentication successful. Logged into portal session.")
            except PlaywrightTimeoutError:
                print(f"❌ Login redirected back to login page. Check credentials for: {account['USERNAME']}")
                pytest.fail(f"❌ Authentication Failed: Invalid credentials or session kickback for {account['USERNAME']}.")

            # -------------------------------------------------------------
            # STEP 2: CAPTURE PRE-DATA & DETERMINE DYNAMIC RATE TYPE (BAU ONLY)
            # -------------------------------------------------------------
            if scenario_result["is_bau"]:
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
                print(f"  -> Pre-SMS Destination ({row_data['telco'].upper()} | {row_data.get('country', 'Philippines')}): Sent={pre_report['sent']} | Ack={pre_report['acknowledged']} | Failed={pre_report['failed']}")
                print(f"  -> Determined Rate Type          : {determined_rate_type}")
            else:
                print("\n[STEP 2] [SKIPPED] Non-BAU / API Response scenario detected. Stats capture skipped.")

            # -------------------------------------------------------------
            # STEP 3: EXECUTE API REQUEST (v3 BROADCAST SCHEMA)
            # -------------------------------------------------------------
            print(f"\n[STEP 3] Triggering Broadcast SMS API POST payload to: {API_URL}")
            print(f"  -> Recipient: {row_data['to']} (Sender ID: {row_data['sender_id']})...")
            
            api_context = p.request.new_context()

            payload = {
                "app_key": account["APP_KEY"],
                "app_secret": account["APP_SECRET"],
                "msisdn": row_data["to"],
                "content": row_data["text"],
                "shortcode_mask": row_data["sender_id"],
                "rcvd_transid": "TRANSIDCODE_1",
                "is_intl": row_data["is_intl"],
                "dcs": row_data["dcs"],
                "udh": 0
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
            # CHECK FOR POSTMAN / API LEVEL ERROR (OR NON-BAU SCENARIO)
            # -------------------------------------------------------------
            has_postman_error = is_postman_level_error(response.status, response_json)

            if not scenario_result["is_bau"] or has_postman_error:
                if not scenario_result["is_bau"]:
                    expected_status = scenario_result["expected_status"]

                    print("\n--- NON-BAU RESPONSE VALIDATION ---")
                    print(f"  Expected Status Code : {expected_status}")
                    print(f"  Actual Status Code   : {response.status}")
                    print(f"  Actual JSON          : {response_json}")
                    print("-------------------------------------\n")

                    assert response.status == expected_status, \
                        f"Status Code Mismatch! Expected: {expected_status}, Got: {response.status}"

                    expected_json = scenario_result["expected_json"]
                    assert response_json.get("code") == expected_json.get("code"), \
                        f"Response JSON 'code' Mismatch! Expected: {expected_json.get('code')}, Got: {response_json.get('code')}"

                    assert response_json.get("message") == expected_json.get("message"), \
                        f"Response JSON 'message' Mismatch! Expected: '{expected_json.get('message')}', Got: '{response_json.get('message')}'"

                    print("✅ Non-BAU Error API response successfully validated!")
                else:
                    print(f"✅ Postman-level API error recorded (Status: {response.status}, Code: {response_json.get('code')}). Stats checks bypassed.")

                return

            # -------------------------------------------------------------
            # STEP 4: CALCULATE EXPECTED METRIC INCREMENTS (BAU ONLY)
            # -------------------------------------------------------------
            print("\n[STEP 4] Calculating Expected Metric Increments...")
            char_count = len(row_data["text"])
            parts_count = calculate_sms_parts(row_data["text"])
            rate_per_part = get_sms_rate(row_data["telco"], determined_rate_type) if PLAN_USAGE else 0.0

            is_cashbus_sender = row_data["sender_id"].strip().lower() == "cashbus"

            expected_msg_trans_add = 0
            expected_excess_add = 0

            # Priority 1: Cashbus Sender ID
            if is_cashbus_sender:
                print("  ❌ Priority 1 Match: CASHBUS SENDER ID DETECTED.")
                api_is_success = False
                expected_parts_added = 0
                added_cost = 0.0
                expected_sent_add = parts_count
                expected_ack_add = 0
                expected_failed_add = parts_count

            # Priority 2: Opted Out Recipient
            elif row_data["is_optedout"]:
                print("  ⚠️ Priority 2 Match: RECIPIENT IS OPTED OUT.")
                expected_parts_added = 0
                added_cost = 0.0
                expected_sent_add = 0
                expected_ack_add = 0
                expected_failed_add = 0

            # Priority 3: Successful Transaction
            elif api_is_success:
                print("  ✅ Priority 3 Match: SUCCESSFUL TRANSACTION.")
                expected_parts_added = parts_count
                added_cost = round(parts_count * rate_per_part, 2) if PLAN_USAGE else 0.0
                expected_sent_add = parts_count
                expected_ack_add = parts_count
                expected_failed_add = 0

                expected_msg_trans_add = parts_count

                if "excess" in determined_rate_type.lower():
                    expected_excess_add = parts_count
                else:
                    expected_excess_add = 0

            # Priority 4: Generic API Failures
            else:
                print("  ❌ Priority 4 Match: API TRANSACTION FAILED.")
                expected_parts_added = 0
                added_cost = 0.0
                expected_sent_add = parts_count
                expected_ack_add = 0
                expected_failed_add = parts_count

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

            # -------------------------------------------------------------
            # STEP 5: CAPTURE POST-DATA & VALIDATE (BAU ONLY)
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

            retries = 4
            while retries > 0:
                print(f"  -> Polling cycle... (Retries left: {retries})")
                
                post_dashboard = get_dashboard_metrics(page, target_delivered=expected_total_delivered)
                post_plan = get_plan_usage_metrics(page, plan_name=row_data["portal_plan_name"])
                post_report = get_sms_report_metrics(page, target_telco=row_data["telco"], target_country=row_data.get("country", "Philippines"))

                if stats_match(post_dashboard, post_plan, post_report):
                    print("  ✨ All expected portal metrics matched! Terminating retries immediately.")
                    break

                print(f"     [Pending Sync] Delivered: {post_dashboard['total_delivered']}/{expected_total_delivered} | Failed: {post_report['failed']}/{expected_failed_add}")
                time.sleep(3)
                retries -= 1

            print("\n--- METRIC COMPARISON SUMMARY ---")
            print(f"  Text Length              : {char_count} characters ({parts_count} part(s))")
            print(f"  Target Telco             : {row_data['telco'].upper()}")
            print(f"  Transaction Status       : {'SUCCESS' if api_is_success else 'FAILED'}")
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

            print("✅ All Dashboard, Plan Usage, and SMS Report validations passed successfully!")

        finally:
            browser.close()
import argparse
import os
import random
import string
import sys
import time
import urllib.request
import urllib.error

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    StaleElementReferenceException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from compare_utils import DEFAULT_COMPARE_ENDPOINTS, compare_endpoints

ENTRY_MODE = "ai"
ENTRY_TEXT = None


def rand_string(min_len=6, max_len=12):
    length = random.randint(min_len, max_len)
    return "".join(random.choices(string.ascii_letters, k=length))


def rand_email():
    return f"{rand_string(5, 8).lower()}@example.com"


def rand_phone():
    return f"555{random.randint(1000000, 9999999)}"


def rand_number(min_val=1, max_val=100):
    return str(random.randint(min_val, max_val))


def rand_date():
    return f"2024-{random.randint(1,12):02d}-{random.randint(1,28):02d}"


def safe_clear_and_type(el, value):
    try:
        el.clear()
    except Exception:
        pass
    el.send_keys(value)


def fill_input(el):
    el_type = (el.get_attribute("type") or "text").lower()
    name = (el.get_attribute("name") or "").lower()
    placeholder = (el.get_attribute("placeholder") or "").lower()

    if el_type in {"hidden", "submit", "button", "reset", "image", "file"}:
        return

    if el_type in {"checkbox"}:
        if random.random() > 0.5 and not el.is_selected():
            el.click()
        return

    if el_type in {"radio"}:
        if not el.is_selected():
            el.click()
        return

    if "entry-input" in (el.get_attribute("id") or "").lower():
        value = get_entry_text()
    elif "email" in name or "email" in placeholder or el_type == "email":
        value = rand_email()
    elif "phone" in name or "phone" in placeholder or el_type == "tel":
        value = rand_phone()
    elif el_type == "number":
        value = rand_number()
    elif el_type == "date":
        value = rand_date()
    elif "name" in name or "name" in placeholder:
        value = rand_string(4, 10).title()
    elif "city" in name or "city" in placeholder:
        value = "Austin"
    elif "zip" in name or "postal" in placeholder:
        value = rand_number(10000, 99999)
    else:
        value = rand_string()

    safe_clear_and_type(el, value)


def fill_textarea(el):
    safe_clear_and_type(el, f"Notes {rand_string(8, 15)}")


def fill_select(el):
    options = el.find_elements(By.TAG_NAME, "option")
    if not options:
        return
    candidates = [opt for opt in options if opt.get_attribute("value") or opt.text.strip()]
    if not candidates:
        return
    choice = random.choice(candidates)
    choice.click()


def safe_click(driver, element):
    try:
        element.click()
        return True
    except ElementClickInterceptedException:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
            driver.execute_script("arguments[0].click();", element)
            return True
        except Exception:
            return False
    except ElementNotInteractableException:
        return False
    except Exception:
        return False


def submit_form(form, driver):
    submit_selectors = [
        "input[type='submit']",
        "button[type='submit']",
        "button",
    ]
    for selector in submit_selectors:
        buttons = form.find_elements(By.CSS_SELECTOR, selector)
        if buttons:
            for btn in buttons:
                if safe_click(driver, btn):
                    return


def submit_row(row, driver):
    buttons = row.find_elements(By.CSS_SELECTOR, "button")
    if not buttons:
        return
    for btn in buttons:
        if btn.is_enabled():
            if safe_click(driver, btn):
                return
    safe_click(driver, buttons[0])


def fill_form(form):
    elements = form.find_elements(By.CSS_SELECTOR, "input, textarea, select")
    for el in elements:
        try:
            tag = el.tag_name.lower()
            if tag == "input":
                fill_input(el)
            elif tag == "textarea":
                fill_textarea(el)
            elif tag == "select":
                fill_select(el)
        except (ElementNotInteractableException, StaleElementReferenceException):
            continue


def fill_row(row):
    elements = row.find_elements(By.CSS_SELECTOR, "input, textarea, select")
    for el in elements:
        try:
            tag = el.tag_name.lower()
            if tag == "input":
                fill_input(el)
            elif tag == "textarea":
                fill_textarea(el)
            elif tag == "select":
                fill_select(el)
        except (ElementNotInteractableException, StaleElementReferenceException):
            continue


def create_driver(headless):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=options)


def load_env(path=".env"):
    if not os.path.exists(path):
        return
    try:
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip("\"'") 
                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError:
        pass


def set_entry_text(value):
    global ENTRY_TEXT
    ENTRY_TEXT = value


def clear_entry_text():
    global ENTRY_TEXT
    ENTRY_TEXT = None


def get_entry_text():
    load_env()
    if ENTRY_TEXT is not None:
        return ENTRY_TEXT
    if ENTRY_MODE == "local":
        return random.choice(
            [
                "A short walk outside helped clear my head today.",
                "I finished a tough task and felt relieved afterward.",
                "I paused for a deep breath and noticed the sunlight.",
                "A kind message from a friend lifted my mood.",
                "I cooked something simple and felt grounded.",
                "I focused for 25 minutes and made good progress.",
                "I listened to music and felt more present.",
            ]
        )
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return random.choice(
            [
                "A short walk outside helped clear my head today.",
                "I finished a tough task and felt relieved afterward.",
                "I paused for a deep breath and noticed the sunlight.",
                "A kind message from a friend lifted my mood.",
                "I cooked something simple and felt grounded.",
                "I focused for 25 minutes and made good progress.",
                "I listened to music and felt more present.",
            ]
        )

    payload = (
        "{"
        "\"model\":\"gpt-4o-mini\","
        "\"messages\":["
        "{\"role\":\"system\",\"content\":\"Write a single short, uplifting daily note (max 140 chars).\"},"
        "{\"role\":\"user\",\"content\":\"Generate a fresh, human-sounding entry.\"}"
        "],"
        "\"temperature\":0.8"
        "}"
    ).encode("utf-8")

    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError):
        return random.choice(
            [
                "I took a mindful pause and reset my focus.",
                "Small progress today felt meaningful.",
                "A calm moment made the day feel lighter.",
            ]
        )

    try:
        marker = "\"content\":\""
        start = raw.find(marker)
        if start == -1:
            return "A simple moment brought me peace today."
        start += len(marker)
        end = raw.find("\"", start)
        text = raw[start:end]
        return text.replace("\\n", " ").strip()
    except Exception:
    return "I appreciated a quiet moment and felt grateful."


def generate_entry_text(entry_mode="ai", seed=None):
    global ENTRY_MODE
    ENTRY_MODE = entry_mode
    if seed is not None:
        random.seed(seed)
    return get_entry_text()


def run_fill_session(
    url,
    mode="all",
    iterations=1,
    min_wait=60,
    max_wait=180,
    headless=False,
    seed=None,
    entry_mode="ai",
    entry_text=None,
    log_cb=None,
):
    if seed is not None:
        random.seed(seed)

    global ENTRY_MODE
    ENTRY_MODE = entry_mode
    if entry_text is not None:
        set_entry_text(entry_text)

    driver = create_driver(headless)
    wait = WebDriverWait(driver, 10)
    log = log_cb or (lambda message: None)

    try:
        for idx in range(max(iterations, 1)):
            log(f"Loading {url}")
            driver.get(url)
            wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            forms = driver.find_elements(By.TAG_NAME, "form")

            if forms:
                targets = forms if mode == "all" else [random.choice(forms)]
                log(f"Found {len(forms)} form(s); filling {len(targets)}.")
                for form in targets:
                    fill_form(form)
                    submit_form(form, driver)
                    log("Submitted form.")
                    time.sleep(1)
                continue

            rows = driver.find_elements(By.CSS_SELECTOR, ".input-row")
            if not rows:
                log("No forms or input rows found on page.")
                return

            targets = rows if mode == "all" else [random.choice(rows)]
            log(f"Found {len(rows)} input row(s); filling {len(targets)}.")
            for row in targets:
                fill_row(row)
                time.sleep(0.2)
                submit_row(row, driver)
                log("Submitted row.")
                time.sleep(1)

            if idx < iterations - 1:
                wait_seconds = random.randint(min_wait, max_wait)
                log(f"Waiting {wait_seconds}s before next iteration.")
                time.sleep(wait_seconds)
    finally:
        if entry_text is not None:
            clear_entry_text()
        driver.quit()


def main():
    parser = argparse.ArgumentParser(description="Fill multiple forms with random data using Selenium.")
    parser.add_argument("--url", default=os.environ.get("FORM_URL", ""), required=False)
    parser.add_argument("--mode", choices=["all", "random"], default="all")
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--min-wait", type=int, default=60)
    parser.add_argument("--max-wait", type=int, default=180)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--entry-mode", choices=["ai", "local"], default=os.environ.get("ENTRY_MODE", "ai"))
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--baseline-url", default=os.environ.get("BASELINE_URL", ""))
    parser.add_argument("--target-url", default=os.environ.get("TARGET_URL", ""))
    parser.add_argument(
        "--compare-endpoints",
        default=os.environ.get(
            "COMPARE_ENDPOINTS", ",".join(DEFAULT_COMPARE_ENDPOINTS),
        ),
    )
    args = parser.parse_args()

    default_base = "http://a218f40cdece3464687b8c8c7d8addf2-557072703.us-east-1.elb.amazonaws.com/"
    url = args.url or default_base
    baseline_url = args.baseline_url or default_base
    target_url = args.target_url

    if args.compare:
        if not target_url:
            print("Error: --compare requires --target-url (or TARGET_URL).")
            sys.exit(2)
        endpoints = [item for item in args.compare_endpoints.split(",") if item.strip()]
        ok, results = compare_endpoints(baseline_url, target_url, endpoints)
        for result in results:
            endpoint = result["endpoint"]
            status = result["status"]
            if status == "match":
                print(f"[{endpoint}] match")
            elif status == "error":
                print(
                    f"[{endpoint}] error baseline={result.get('baseline_error') or 'ok'} "
                    f"target={result.get('target_error') or 'ok'}"
                )
            elif "missing_count" in result:
                print(
                    f"[{endpoint}] mismatch rows missing={result.get('missing_count', 0)} "
                    f"extra={result.get('extra_count', 0)}"
                )
            else:
                print(f"[{endpoint}] mismatch payloads")
        sys.exit(0 if ok else 2)

    run_fill_session(
        url=url,
        mode=args.mode,
        iterations=args.iterations,
        min_wait=args.min_wait,
        max_wait=args.max_wait,
        headless=args.headless,
        seed=args.seed,
        entry_mode=args.entry_mode,
    )


if __name__ == "__main__":
    main()

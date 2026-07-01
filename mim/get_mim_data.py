import os
import time
from pathlib import Path

import psycopg2
from bs4 import BeautifulSoup
from dotenv import dotenv_values
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

if not hasattr(__import__("paramiko"), "DSSKey"):
    import paramiko
    paramiko.DSSKey = paramiko.RSAKey

from sshtunnel import SSHTunnelForwarder

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

LOGIN_URL = "https://www.careet.net/user/login"
DICTIONARY_URL = "https://www.careet.net/Dictionary"
LAST_PAGE = 69


def load_env() -> dict:
    env = {**dotenv_values(_ENV_PATH), **os.environ}
    missing = [k for k in ("CAREET_EMAIL", "CAREET_PASSWORD") if not env.get(k)]
    if missing:
        raise RuntimeError(f".env에 다음 값이 없습니다: {missing}")
    if not env.get("DATABASE_URL"):
        required = ["SSH_HOST", "SSH_PORT", "SSH_USER", "SSH_PEM_PATH",
                    "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]
        missing = [k for k in required if not env.get(k)]
        if missing:
            raise RuntimeError(f"DATABASE_URL이 없고 SSH 접속 정보도 부족합니다: {missing}")
    return env


def connect_db(env: dict):
    if env.get("DATABASE_URL"):
        return psycopg2.connect(env["DATABASE_URL"]), None

    tunnel = SSHTunnelForwarder(
        (env["SSH_HOST"], int(env["SSH_PORT"])),
        ssh_username=env["SSH_USER"],
        ssh_pkey=env["SSH_PEM_PATH"],
        remote_bind_address=(env["DB_HOST"], int(env["DB_PORT"])),
    )
    tunnel.start()
    conn = psycopg2.connect(
        host="127.0.0.1",
        port=tunnel.local_bind_port,
        dbname=env["DB_NAME"],
        user=env["DB_USER"],
        password=env["DB_PASSWORD"],
    )
    return conn, tunnel


def upsert_terms(conn, rows: list[dict]):
    sql = """
        INSERT INTO public.mim_terms (word, definition)
        VALUES (%(word)s, %(definition)s)
        ON CONFLICT (word) DO UPDATE SET
            definition = EXCLUDED.definition;
    """
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
    conn.commit()


def build_driver():
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)


def login(driver, email: str, password: str):
    driver.get(LOGIN_URL)
    wait = WebDriverWait(driver, 15)

    email_input = wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, "input[type='email'], input[name='email'], input[id='email']")
    ))
    email_input.clear()
    email_input.send_keys(email)

    driver.find_element(By.CSS_SELECTOR, "input[type='password']").send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']").click()

    try:
        wait.until(EC.url_changes(LOGIN_URL))
    except TimeoutException:
        raise RuntimeError("로그인 실패: 이메일/비밀번호를 확인하세요.")

    print(f"로그인 성공 (현재 URL: {driver.current_url})")


def crawl_pages(driver) -> list[dict]:
    driver.get(DICTIONARY_URL)
    time.sleep(5)

    results = []
    current_page = 1
    print(f"1페이지부터 {LAST_PAGE}페이지까지 수집 시작...")

    while True:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        page_count = 0
        for item in soup.select('li.footnote-key__item'):
            try:
                word = item.select_one('em.footnote-key').text.strip()
                definition = item.select_one('p.text').text.strip()
                results.append({'word': word, 'definition': definition})
                page_count += 1
            except AttributeError:
                continue

        print(f"{current_page}페이지 완료 (이번: {page_count}개 / 누적: {len(results)}개)")

        if current_page == LAST_PAGE:
            print(f"{LAST_PAGE}페이지까지 수집 완료.")
            break

        next_page = current_page + 1
        try:
            next_btn = driver.find_element(
                By.XPATH,
                f"//div[contains(@class, 'pagination')]//a[normalize-space(text())='{next_page}']"
            )
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_btn)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", next_btn)
            time.sleep(3)
            current_page = next_page

        except NoSuchElementException:
            try:
                arrow = driver.find_element(
                    By.XPATH,
                    "//div[contains(@class, 'pagination')]//a[contains(@class, 'next') or contains(text(), '>')]"
                )
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", arrow)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", arrow)
                time.sleep(3)
                current_page = next_page

            except NoSuchElementException:
                print(f"마지막 페이지 도달. ({current_page}페이지)")
                break

    return results


def crawl_careet_dictionary():
    env = load_env()

    driver = build_driver()
    try:
        login(driver, env["CAREET_EMAIL"], env["CAREET_PASSWORD"])
        rows = crawl_pages(driver)
    finally:
        driver.quit()

    if not rows:
        print("수집된 데이터가 없습니다.")
        return

    conn, tunnel = connect_db(env)
    try:
        upsert_terms(conn, rows)
        print(f"DB 저장 완료: {len(rows)}건 -> public.mim_terms")
    finally:
        conn.close()
        if tunnel:
            tunnel.stop()


if __name__ == "__main__":
    crawl_careet_dictionary()

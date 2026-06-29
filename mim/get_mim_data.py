import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

def crawl_careet_dictionary():
    options = webdriver.ChromeOptions()
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        # 1. 로그인
        print("💡 브라우저가 열렸습니다. 60초 안에 직접 로그인을 완료해주세요.")
        driver.get("https://www.careet.net/user/login")
        time.sleep(60)

        # 2. 딕셔너리 페이지 이동
        print("💡 딕셔너리 페이지로 이동합니다...")
        driver.get("https://www.careet.net/Dictionary")
        time.sleep(5)

        dictionary_data = []
        current_page = 1

        print("💡 1페이지부터 69페이지까지만 데이터 수집을 시작합니다...")

        # 3. 페이지를 넘겨가며 반복 수집
        while True:
            # 현재 페이지 데이터 파싱
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            items = soup.select('li.footnote-key__item') 

            page_count = 0
            for item in items:
                try:
                    title = item.select_one('em.footnote-key').text.strip()
                    description = item.select_one('p.text').text.strip()
                    dictionary_data.append({'단어': title, '뜻': description})
                    page_count += 1
                except AttributeError:
                    continue 
            
            print(f"✅ {current_page}페이지 수집 완료! (수집된 단어: {page_count}개 / 누적: {len(dictionary_data)}개)")

            # ⭐ 🎯 [추가된 부분] 69페이지까지 다 긁었으면 반복문을 빠져나갑니다.
            if current_page == 69:
                print(f"🏁 목표한 69페이지까지 모두 수집 완료하여 종료합니다.")
                break

            # 4. 다음 페이지 번호 클릭 로직
            next_page = current_page + 1
            try:
                # 다음 페이지 번호에 해당하는 버튼(a 태그)을 찾습니다.
                next_btn_xpath = f"//div[contains(@class, 'pagination')]//a[normalize-space(text())='{next_page}']"
                next_button = driver.find_element(By.XPATH, next_btn_xpath)
                
                # 버튼이 있는 곳으로 화면을 부드럽게 스크롤
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_button)
                time.sleep(1) 
                
                # 자바스크립트로 다음 페이지 클릭
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(3) # 다음 페이지가 로딩될 때까지 대기
                
                current_page = next_page

            except NoSuchElementException:
                # 다음 번호가 당장 안 보인다면 화살표(다음 블록) 버튼 클릭 시도
                try:
                    next_arrow = driver.find_element(By.XPATH, "//div[contains(@class, 'pagination')]//a[contains(@class, 'next') or contains(text(), '>')]")
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", next_arrow)
                    time.sleep(1)
                    driver.execute_script("arguments[0].click();", next_arrow)
                    time.sleep(3)
                    
                    current_page = next_page

                except NoSuchElementException:
                    # 번호도 없고 화살표도 없다면 끝 페이지인 것으로 간주
                    print(f"🏁 더 이상 넘어갈 페이지가 없어 수집을 종료합니다. (현재 {current_page}페이지)")
                    break

        # 5. CSV 파일로 저장
        if dictionary_data:
            df = pd.DataFrame(dictionary_data)
            df.to_csv("careet_dictionary_69.csv", index=False, encoding="utf-8-sig")
            print(f"🎉 성공! 총 {len(dictionary_data)}개의 단어를 'careet_dictionary_69.csv' 파일로 저장했습니다.")
        else:
            print("⚠️ 데이터를 추출하지 못했습니다.")

    except Exception as e:
        print(f"에러가 발생했습니다: {e}")

    finally:
        driver.quit()

if __name__ == "__main__":
    crawl_careet_dictionary()
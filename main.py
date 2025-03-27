from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service
from selenium.webdriver.common.action_chains import ActionChains
import json
import threading
import time
from difflib import SequenceMatcher
import datetime as dt


class JobScraper(object):
    def __init__(self, inputs):
        self.inputs = inputs
        options = Options()

        options.add_experimental_option("detach", True)
        options.add_argument("--no-sandbox")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--incognito")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option('useAutomationExtension', False)
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_argument("disable-infobars")

        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.246")

        service = Service(executable_path="C:/Users/vpr16/PythonProjects/JobMiner/edgedriver_win64/msedgedriver.exe")

        self.driver = webdriver.Edge(options=options, service=service)
        self.actions = ActionChains(self.driver)
        self.valid_jobs = []

    def scroll_to_bottom(self, times):
        window_height = self.driver.get_window_size()["height"]
        for i in range(times):
            print("scroll: " + str(i))
            self.driver.execute_script(f"window.scrollTo(0, {window_height})")
            time.sleep(1.25)

    def get_valid_jobs(self):
        now_date = dt.datetime.now()

        self.valid_jobs.clear()
        job_list = self.driver.find_element(By.XPATH, "//ul[@class='jobs-search__results-list']")
        job_elements = job_list.find_elements(By.XPATH, "./li")
        print(f"Parsing {len(job_elements)} jobs...")
        for job_element in job_elements:
            job_div = job_element.find_element(By.XPATH, "./div[1]")

            url = job_div.find_element(By.XPATH, "./a[1]").get_attribute("href")

            info_div = job_div.find_element(By.XPATH, "./div[@class='base-search-card__info']")
            title = info_div.find_element(By.XPATH, "./h3[1]").text
            company = info_div.find_element(By.XPATH, "./h4[1]").text
            if self.inputs["requirements"]["company"] is not None:
                company_similarity = SequenceMatcher(None, company, self.inputs["requirements"]["company"]).ratio()
                if company_similarity < self.inputs["similarity_threshold"]:
                    continue

            metadata_div = info_div.find_element(By.XPATH, "./div[@class='base-search-card__metadata']")
            datetime = metadata_div.find_element(By.XPATH, "./time[1]").get_attribute("datetime")
            if self.inputs["requirements"]["recency"] is not None:
                date = dt.datetime.strptime(datetime, "%Y-%m-%d")
                if (now_date - date).days > int(self.inputs["requirements"]["recency"].split(" ")[0]):
                    continue

            location = metadata_div.find_element(By.XPATH, "./span[1]").text
            if self.inputs["requirements"]["location"] is not None:
                location_similarity = SequenceMatcher(None, location, self.inputs["requirements"]["location"]).ratio()
                if location_similarity < self.inputs["similarity_threshold"]:
                    continue

            if self.inputs["requirements"]["degree"] is not None:
                self.driver.execute_script(f"window.open('{url}', '_blank');")
                self.driver.switch_to.window(self.driver.window_handles[1])
                job_description = self.driver.find_element(By.XPATH, "//section[@class='show-more-less-html']").find_element(By.XPATH, "./div[1]").text
                print(job_description)
                self.driver.switch_to.window(self.driver.window_handles[0])

            self.valid_jobs.append({"url": url, "title": title, "company": company, "location": location, "posted": datetime})

        print(self.valid_jobs)

    def start(self):
        print("Starting...")

        self.driver.get(f"https://www.linkedin.com/jobs/search?keywords={inputs['query'].replace(' ', '%20')}")

        time.sleep(2)

        try:
            dismiss_button = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, "//button[@data-tracking-control-name='public_jobs_contextual-sign-in-modal_modal_dismiss']"))
            )
        except Exception as e:
            print(e)
            dismiss_button = None

        if dismiss_button is not None:
            self.actions.move_to_element(dismiss_button).perform()
            time.sleep(0.5)
            dismiss_button.click()

        time.sleep(1)

        self.scroll_to_bottom(self.inputs["num_scrolls"])

        self.get_valid_jobs()

    def stop(self):
        print("Stopping...")
        self.driver.quit()


if __name__ == '__main__':
    print("Starting...")

    with open('inputs.json') as f:
        inputs = json.load(f)
        if inputs["query"] is None:
            exit("Please enter a query")

    scraper = JobScraper(inputs)
    threading.Thread(target=scraper.start).start()

    while True:
        user_input = input("\n---'quit' to stop---\n")
        if user_input == "quit":
            scraper.stop()
            break
        elif user_input == "jobs":
            scraper.get_valid_jobs()
import csv
import os
import random
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
import re
from groq import Groq

SAVE_PATH = os.path.dirname(__file__) + "/scraped_jobs.csv"


class DescriptionExtractor(object):
    def __init__(self, api_key):
        self.client = Groq(api_key=api_key)

    def extract_llm(self, description):
        system_prompt = (
            "Extract the following information from this job description. "
            "Format the output to fill in the following JSON structure: "
            "{\"field\": \"X\", \"degree\": 0, \"start_date\": \"YYYY-MM-DD\", \"duration\": \"X days/weeks/months\", \"requirements\": [\"X\", \"X\", \"X\"]}. "
            "For the \"field\" field, use \"Computer Science\" for Computer Science, \"Business\" for Business, "
            "\"Mathematics\" for Mathematics, \"Journalism\" for Journalism, or whatever career field you feel summarizes the job description. "
            "For the \"degree\" field, use 0 for no degree, 1 for associate's, 2 for bachelor's, 3 for master's, and 4 for doctorate. "
            "For the \"requirements\" field, include any required skills/attributes in list format, but exclude skills/attributes labeled \"recommended\", \"optional\", or similar. "
            "If you cannot find relevant information to fill a field, use null for that field. "
            "For the rest of the fields, use the formatting provided in the example JSON structure above. "
            "Do not include any other text in the output, reply with the JSON template."
        )

        #print("Description:", description)

        response = self.client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "user", "content": system_prompt},
                {"role": "user", "content": description}
            ]
        )

        content = response.choices[0].message.content.strip()
        #print("Raw result:", content)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            print("Failed to parse JSON:", content)
            return None

    def extract(self, description):
        result = {}

        description = description.replace("\n", " ")
        description = description.replace("\t", " ")
        description = description.replace("<br>", " ")
        description = description.replace("</strong>", "")
        description = description.replace("  ", " ")

        for match in re.finditer("<ul>(.*?)</ul>", description):
            i = match.start() - 1
            title = ""
            while i >= 0:
                if description[i] == ">" or (len(title) > 1 and description[i] == "."):
                    break
                title += description[i]
                i -= 1
            unordered_list = match[1]
            items = re.findall("<li>(.*?)</li>", unordered_list)

            title = title[::-1].strip()

            result[title] = items

        #entities = self.extractor(description)

        return result


class JobScraper(object):
    def __init__(self, settings):
        self.settings = settings
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
        self.extractor = DescriptionExtractor(settings["api_key"])

    def scroll_to_bottom(self, times):
        window_height = self.driver.get_window_size()["height"]
        for i in range(times):
            self.driver.execute_script(f"window.scrollTo(0, {window_height * (i + 1)});")
            time.sleep(0.35)

    def get_valid_jobs(self):
        if not os.path.exists(SAVE_PATH):
            self.make_csv(["URL", "Title", "Company", "Location", "Date Posted",
                           "Field", "Degree", "Start Date", "Duration", "Requirements"], SAVE_PATH)
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

            metadata_div = info_div.find_element(By.XPATH, "./div[@class='base-search-card__metadata']")
            datetime = metadata_div.find_element(By.XPATH, "./time[1]").get_attribute("datetime")
            location = metadata_div.find_element(By.XPATH, "./span[1]").text

            if self.settings["requirements"]["recency"] is not None:
                date = dt.datetime.strptime(datetime, "%Y-%m-%d")
                if (now_date - date).days > int(self.settings["requirements"]["recency"].split(" ")[0]):
                    continue

            if self.settings["requirements"]["locations"] is not None:
                for required_location in self.settings["requirements"]["locations"]:
                    location_similarity = SequenceMatcher(None, location, required_location).ratio()
                    if location_similarity > self.settings["similarity_threshold"]:
                        break
                else:
                    continue

            if self.settings["requirements"]["companies"] is not None:
                for required_company in self.settings["requirements"]["companies"]:
                    company_similarity = SequenceMatcher(None, company, required_company).ratio()
                    if company_similarity > self.settings["similarity_threshold"]:
                        break
                else:
                    continue

            # Use LLM to extract info from job description
            self.driver.execute_script(f"window.open('{url}', '_blank');")
            self.driver.switch_to.window(self.driver.window_handles[-1])
            job_description = self.driver.find_element(By.XPATH, "//section[@class='show-more-less-html']").find_element(By.XPATH, "./div[1]")

            description_html = job_description.get_attribute("innerHTML")
            attributes = self.extractor.extract_llm(description_html)
            #print("JSON result:", attributes)

            self.driver.close()
            self.driver.switch_to.window(self.driver.window_handles[0])
            time.sleep(random.uniform(0.75, 2.0))  # Avoid getting blocked by LinkedIn

            self.valid_jobs.append({"url": url, "title": title, "company": company, "location": location, "posted": datetime} | attributes)
            self.save_to_csv(self.valid_jobs[-1].values(), SAVE_PATH, mode="a")
            #print(self.valid_jobs[-1])
        print(f"Found {len(self.valid_jobs)} valid jobs and saved to {SAVE_PATH}")

    def start(self):
        print("Starting...")

        self.driver.get(f"https://www.linkedin.com/jobs/search?keywords={self.settings['query'].replace(' ', '%20')}")

        try:
            dismiss_button = WebDriverWait(self.driver, 5).until(
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

        self.scroll_to_bottom(self.settings["num_scrolls"])

        self.get_valid_jobs()

    def stop(self):
        print("Stopping...")
        self.driver.quit()

    @staticmethod
    def make_csv(header, path, mode="w"):
        with open(path, mode, newline="") as f:
            writer = csv.writer(f)
            writer.writerow(header)

    @staticmethod
    def save_to_csv(data, path, mode="w"):
        with open(path, mode, newline="") as f:
            writer = csv.writer(f)
            if mode == "a":
                writer.writerow(data)
            else:
                writer.writerows(data)


if __name__ == '__main__':
    print("Starting...")

    with open('settings.json') as f:
        settings = json.load(f)
        if settings["query"] is None:
            exit("Please enter a query")

    scraper = JobScraper(settings)
    threading.Thread(target=scraper.start).start()

    while True:
        user_input = input("\n---'quit' to stop---\n")
        if user_input == "quit":
            scraper.stop()
            break
        elif user_input == "jobs":
            scraper.get_valid_jobs()

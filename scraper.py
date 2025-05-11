from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from bs4 import BeautifulSoup
import psycopg2
import time
from pydantic import ValidationError
from src.models.campground import Campground, CampgroundLinks

def retry_request(func, retries=3, delay=5):
    for attempt in range(retries):
        try:
            return func()
        except Exception as e:
            print(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt < retries - 1:
                time.sleep(delay)
            else:
                print("All attempts failed.")
                return None

options = Options()
options.add_argument("--start-maximized")

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

def load_page():
    driver.get("https://thedyrt.com/search?searchQuery=United%20States")
    WebDriverWait(driver, 180).until(
        EC.presence_of_element_located((By.CLASS_NAME, "SearchCampgrounds_active-campground-card__title__uYfau"))
    )

retry_request(load_page)

SCROLL_PAUSE_TIME = 3
last_height = driver.execute_script("return document.body.scrollHeight")

for _ in range(20):
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(SCROLL_PAUSE_TIME)
    new_height = driver.execute_script("return document.body.scrollHeight")
    if new_height == last_height:
        break
    last_height = new_height

WebDriverWait(driver, 10).until(
    EC.presence_of_all_elements_located((By.CLASS_NAME, "SearchCampgrounds_active-campground-card__title__uYfau"))
)

camp_cards = driver.find_elements(By.CLASS_NAME, "SearchCampgrounds_active-campground-card__title__uYfau")
actions = ActionChains(driver)

for card in camp_cards:
    try:
        actions.move_to_element(card).perform()
        time.sleep(0.5)
    except:
        continue

soup = BeautifulSoup(driver.page_source, "html.parser")
campground_names = soup.find_all("h3", class_="SearchCampgrounds_active-campground-card__title__uYfau")

conn = psycopg2.connect(
    dbname="case_study",
    user="user",
    password="password",
    host="localhost",
    port="5432"
)
cur = conn.cursor()

for name in campground_names:
    campground_name = name.get_text(strip=True)

    try:
        latitude = driver.execute_script("return arguments[0].getAttribute('data-lat');", card)
        longitude = driver.execute_script("return arguments[0].getAttribute('data-lng');", card)

        if latitude is None or longitude is None:
            latitude = 0.0  
            longitude = 0.0  

        photos = card.find_elements(By.TAG_NAME, 'img')
        photos_count = len(photos)

        # Pydantic ile dogrulama
        campground_data = Campground(
            id=f"{campground_name}_{latitude}_{longitude}",  
            type="campground",  
            links=CampgroundLinks(self="https://thedyrt.com"),  
            name=campground_name,
            latitude=float(latitude),  
            longitude=float(longitude),  
            #administrative_area=None,  
            #nearest_city_name=None,  
            accommodation_type_names=["tent", "RV"],  
            bookable=True,  
            camper_types=["RV", "Tent"],  
            #photo_url=None,  
            #photo_urls=[],  
            photos_count=photos_count,
            #rating=None,  
            #reviews_count=0,
            #slug=None,   
            #price_low=None,   
            #price_high=None,   
            #availability_updated_at=None  
        )

        # Veriyi PostgreSQLe kaydet
        cur.execute("INSERT INTO campgrounds (name, latitude, longitude, photos_count) VALUES (%s, %s, %s, %s)",
                    (campground_data.name, campground_data.latitude, campground_data.longitude, campground_data.photos_count))
        print(f"Kaydedildi: {campground_data.name}")

    except ValidationError as e:
        print(f"Hata: {e}")

conn.commit()
cur.close()
conn.close()

driver.quit()
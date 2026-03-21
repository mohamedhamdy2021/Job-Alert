import requests
import feedparser
import json
import os
import time
import hashlib
from datetime import datetime, timedelta, timezone
import calendar
from bs4 import BeautifulSoup

# --- إعدادات تليجرام ---
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

def send_telegram_message(message):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram tokens not set.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown',
        'disable_web_page_preview': True
    }
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

STATE_FILE = "job_bot_state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

class JobAlertBot:
    def __init__(self):
        self.profile = {
            "name": "Mohamed Hamdy",
            "title": "Embedded Software Engineer / AUTOSAR Developer",
            "experience_years": 3,
            "location": "Alexandria, Egypt",
            "willing_to_relocate": ["Cairo", "Remote", "Germany", "UAE", "KSA"]
        }
        
        # كلمات البحث المخصوصة لبروفايلك
        self.search_queries = [
            "AUTOSAR",
            "Classic AUTOSAR",
            "Classical Autosar",
            "Autosar Classic",
            "Autosar classical",
            "Embedded Software Engineer",
            "Embedded C developer",
            "automotive software engineer",
            "Embedded software developer",
            "CANoe",
            "Davinci configurator",
            "firmware engineer",
            "Vector tools",
            "automotive engineer",
            "visa sponsorship",
            "AUTOSAR engineer"
        ]
        
        self.sent_jobs = set()
        self.load_state()

    def load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    data = json.load(f)
                    self.sent_jobs = set(data.get("sent_jobs", []))
                print(f"📂 State Loaded: {len(self.sent_jobs)} jobs already sent")
            except Exception as e:
                print(f"Error loading state: {e}")

    def save_state(self):
        recent_jobs = list(self.sent_jobs)[-1000:]
        data = {"sent_jobs": recent_jobs}
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(data, f)
        except Exception as e:
            print(f"Error saving state: {e}")

    def generate_job_hash(self, title, source):
        raw = f"{title}{source}".lower().strip()
        return hashlib.md5(raw.encode()).hexdigest()

    def is_within_24h(self, published_parsed):
        """Check if an RSS entry's published date is within the last 24 hours"""
        if not published_parsed:
            return True  # لو مفيش تاريخ نديها فرصة
        try:
            pub_timestamp = calendar.timegm(published_parsed)
            pub_dt = datetime.fromtimestamp(pub_timestamp, tz=timezone.utc)
            now_utc = datetime.now(tz=timezone.utc)
            age = now_utc - pub_dt
            return age <= timedelta(hours=24)
        except Exception:
            return True  # لو حصل أي مشكلة في التاريخ نعديها

    def get_age_text(self, published_parsed):
        """Convert published_parsed to human-readable age like '3h ago'"""
        if not published_parsed:
            return "Recent"
        try:
            pub_timestamp = calendar.timegm(published_parsed)
            pub_dt = datetime.fromtimestamp(pub_timestamp, tz=timezone.utc)
            now_utc = datetime.now(tz=timezone.utc)
            age = now_utc - pub_dt
            hours = int(age.total_seconds() / 3600)
            if hours < 1:
                mins = int(age.total_seconds() / 60)
                return f"{mins}m ago"
            elif hours < 24:
                return f"{hours}h ago"
            else:
                days = hours // 24
                return f"{days}d ago"
        except Exception:
            return "Recent"

    def is_relevant_job(self, title, description=""):
        text = (title + " " + description).lower()
        
        must_have = [
            "embedded", "autosar", "automotive", "firmware", "ecu",
            "can ", "canoe", "davinci", "vector", "bsw",
            "c programmer", "c developer", "c engineer",
            "software engineer", "python", "automation",
            "rtos", "microcontroller", "arm", "stm32",
            "valeo", "continental", "bosch", "aptiv", "denso"
        ]
        
        exclude = [
            "senior manager", "director", "vp ", "vice president",
            "10+ years", "15+ years", "principal",
            "java developer", "react developer", "angular", "frontend developer",
            "data scientist", "machine learning engineer",
            "php developer", "ruby", "swift developer", "ios developer", "ios"
            "android", "full stack", "devops", "cloud architect" , "linux" , "full stack" , 
        ]
        
        for word in exclude:
            if word in text:
                return False
        
        for word in must_have:
            if word in text:
                return True
                
        return False

    def score_job(self, title, description=""):
        text = (title + " " + description).lower()
        score = 0
        
        high_match = ["autosar", "bsw", "davinci", "canoe", "vector", "ecu", "valeo", "volkswagen", "vw", "visa sponsorship", "relocation"]
        for word in high_match:
            if word in text: score += 2
        
        mid_match = ["embedded", "automotive", "firmware", "misra", "can protocol", "rtos", "continental", "bosch"]
        for word in mid_match:
            if word in text: score += 1
        
        low_match = ["c programming", "python", "automation", "testing", "software engineer"]
        for word in low_match:
            if word in text: score += 0.5
        
        location_bonus = ["egypt", "cairo", "alexandria", "remote", "germany", "munich", "stuttgart", "dubai", "uae", "saudi", "usa", "uk", "canada", "netherlands", "sweden", "japan", "visa", "sponsor", "relocation package", "relocation support"]
        for loc in location_bonus:
            if loc in text: score += 1
        
        if score >= 8: return 5
        elif score >= 6: return 4
        elif score >= 4: return 3
        elif score >= 2: return 2
        return 1

    # ==================== مصادر البحث ====================

    def search_linkedin(self):
        """بحث في LinkedIn عن وظائف عبر صفحة الوظائف العامة"""
        found_jobs = []
        # LinkedIn بتسمح بأول 3-4 كلمات بحث قبل ما تعمل Rate Limit
        linkedin_queries = [
            "AUTOSAR developer",
            "embedded software engineer automotive",
            "automotive software engineer Egypt",
            "embedded C engineer",
            "firmware engineer"
        ]
        
        for query in linkedin_queries:
            try:
                # f_TPR=r86400 = last 24 hours, no location filter = worldwide
                url = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={query.replace(' ', '%20')}&start=0&f_TPR=r86400"
                response = requests.get(url, headers=HEADERS, timeout=10)
                
                if response.status_code != 200:
                    url2 = f"https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords={query.replace(' ', '%20')}&start=0&f_TPR=r604800"
                    response = requests.get(url2, headers=HEADERS, timeout=10)
                    if response.status_code != 200:
                        continue
                
                soup = BeautifulSoup(response.text, "html.parser")
                job_cards = soup.find_all("div", class_="base-card")
                
                if not job_cards:
                    job_cards = soup.find_all("li")
                
                for card in job_cards[:5]:
                    title_tag = card.find("h3") or card.find("a", class_="base-card__full-link")
                    title = title_tag.get_text(strip=True) if title_tag else ""
                    
                    link_tag = card.find("a", href=True)
                    link = link_tag["href"] if link_tag else ""
                    
                    company_tag = card.find("h4") or card.find("a", class_="hidden-nested-link")
                    company = company_tag.get_text(strip=True) if company_tag else "Unknown"
                    
                    location_tag = card.find("span", class_="job-search-card__location")
                    location = location_tag.get_text(strip=True) if location_tag else ""
                    
                    if not title or not link:
                        continue
                        
                    full_text = f"{title} {company} {location}"
                    if not self.is_relevant_job(title, full_text):
                        continue
                    
                    job_hash = self.generate_job_hash(title, "linkedin")
                    if job_hash in self.sent_jobs:
                        continue
                    
                    stars = self.score_job(title, full_text)
                    
                    found_jobs.append({
                        'title': f"{title} @ {company}",
                        'link': link.split("?")[0] if link else "",
                        'source': '💼 LinkedIn',
                        'location': location,
                        'stars': stars,
                        'hash': job_hash,
                        'posted_ago': 'Today'
                    })
                    
                time.sleep(2)  # ثانيتين بين كل طلب عشان LinkedIn متعملش بان
                    
            except Exception as e:
                print(f"  [LinkedIn] Error searching '{query}': {e}")
        
        return found_jobs

    def search_glassdoor(self):
        """بحث في Glassdoor عن وظائف"""
        found_jobs = []
        glassdoor_queries = [
            "embedded-software-engineer",
            "autosar-developer",
            "automotive-software-engineer",
            "firmware-engineer",
        ]
        
        for query in glassdoor_queries:
            try:
                # fromAge=1 = last 1 day filter on Glassdoor
                url = f"https://www.glassdoor.com/Job/{query}-jobs-SRCH_KO0,{len(query.replace('-', ' '))}.htm?fromAge=1"
                response = requests.get(url, headers=HEADERS, timeout=10)
                
                if response.status_code != 200:
                    continue
                
                soup = BeautifulSoup(response.text, "html.parser")
                
                # Glassdoor job cards
                job_cards = soup.find_all("li", class_="react-job-listing") or soup.find_all("div", attrs={"data-test": "jobListing"})
                
                # Fallback: بنحاول نلاقي أي job titles
                if not job_cards:
                    job_links = soup.find_all("a", {"data-test": "job-link"}) or soup.find_all("a", class_="jobLink")
                    for link_tag in job_links[:5]:
                        title = link_tag.get_text(strip=True)
                        href = link_tag.get("href", "")
                        if href and not href.startswith("http"):
                            href = f"https://www.glassdoor.com{href}"
                        
                        if not title:
                            continue
                        
                        if not self.is_relevant_job(title):
                            continue
                        
                        job_hash = self.generate_job_hash(title, "glassdoor")
                        if job_hash in self.sent_jobs:
                            continue
                        
                        stars = self.score_job(title)
                        
                        found_jobs.append({
                            'title': title,
                            'link': href,
                            'source': '🟢 Glassdoor',
                            'location': '',
                            'stars': stars,
                            'hash': job_hash,
                            'posted_ago': 'Today'
                        })
                
                for card in job_cards[:5]:
                    title_tag = card.find("a", {"data-test": "job-link"}) or card.find("a", class_="jobLink")
                    title = title_tag.get_text(strip=True) if title_tag else ""
                    
                    link = ""
                    if title_tag and title_tag.get("href"):
                        link = title_tag["href"]
                        if not link.startswith("http"):
                            link = f"https://www.glassdoor.com{link}"
                    
                    employer_tag = card.find("span", class_="EmployerProfile") or card.find("div", {"data-test": "employer-short-name"})
                    employer = employer_tag.get_text(strip=True) if employer_tag else ""
                    
                    if not title:
                        continue
                    
                    full_text = f"{title} {employer}"
                    if not self.is_relevant_job(title, full_text):
                        continue
                    
                    job_hash = self.generate_job_hash(title, "glassdoor")
                    if job_hash in self.sent_jobs:
                        continue
                    
                    stars = self.score_job(title, full_text)
                    display_title = f"{title} @ {employer}" if employer else title
                    
                    found_jobs.append({
                        'title': display_title,
                        'link': link,
                        'source': '🟢 Glassdoor',
                        'location': '',
                        'stars': stars,
                        'hash': job_hash,
                        'posted_ago': 'Today'
                    })
                    
                time.sleep(2)
                    
            except Exception as e:
                print(f"  [Glassdoor] Error searching '{query}': {e}")
        
        return found_jobs

    def search_google_jobs(self):
        """بحث عبر Google News RSS"""
        found_jobs = []
        
        for query in self.search_queries:
            try:
                feed_url = f"https://news.google.com/rss/search?q={query.replace(' ', '+')}+jobs+hiring&hl=en"
                feed = feedparser.parse(feed_url)
                
                for entry in feed.entries[:5]:
                    # فلتر الـ 24 ساعة: لو الوظيفة أقدم من يوم نتخطاها
                    if not self.is_within_24h(entry.get('published_parsed')):
                        continue
                    title = entry.get('title', '')
                    link = entry.get('link', '')
                    description = entry.get('summary', '')
                    
                    if not self.is_relevant_job(title, description):
                        continue
                    
                    job_hash = self.generate_job_hash(title, "google")
                    if job_hash in self.sent_jobs:
                        continue
                    
                    stars = self.score_job(title, description)
                    
                    found_jobs.append({
                        'title': title,
                        'link': link,
                        'source': '🔍 Google',
                        'location': '',
                        'stars': stars,
                        'hash': job_hash,
                        'posted_ago': self.get_age_text(entry.get('published_parsed'))
                    })
                    
            except Exception as e:
                print(f"  [Google] Error searching '{query}': {e}")
        
        return found_jobs

    def search_remoteok(self):
        """بحث في RemoteOK عن وظائف ريموت"""
        found_jobs = []
        remote_queries = ["embedded", "firmware", "python", "c-programming"]
        
        for query in remote_queries:
            try:
                feed_url = f"https://remoteok.com/remote-{query}-jobs.rss"
                feed = feedparser.parse(feed_url)
                
                for entry in feed.entries[:5]:
                    # فلتر الـ 24 ساعة: لو الوظيفة أقدم من يوم نتخطاها
                    if not self.is_within_24h(entry.get('published_parsed')):
                        continue
                    title = entry.get('title', '')
                    link = entry.get('link', '')
                    description = entry.get('summary', '')
                    
                    if not self.is_relevant_job(title, description):
                        continue
                    
                    job_hash = self.generate_job_hash(title, "remoteok")
                    if job_hash in self.sent_jobs:
                        continue
                    
                    stars = self.score_job(title, description)
                    
                    found_jobs.append({
                        'title': title,
                        'link': link,
                        'source': '🌍 Remote',
                        'location': 'Remote',
                        'stars': stars,
                        'hash': job_hash,
                        'posted_ago': self.get_age_text(entry.get('published_parsed'))
                    })
                    
            except Exception as e:
                print(f"  [RemoteOK] Error searching '{query}': {e}")
        
        return found_jobs

    # ==================== التنسيق والتشغيل ====================

    def format_job_message(self, job):
        stars_display = "⭐" * job['stars'] + "☆" * (5 - job['stars'])
        location_line = f"\n📍 *Location:* `{job['location']}`" if job.get('location') else ""
        posted = job.get('posted_ago', 'Recent')
        
        msg = (f"💼 *New Job Alert!*\n"
               f"📋 *{job['title'][:120]}*\n"
               f"🏢 *Source:* {job['source']}"
               f"{location_line}\n"
               f"🕐 *Posted:* `{posted}`\n"
               f"🎯 *Match:* {stars_display}\n"
               f"🔗 [Apply Here]({job['link']})")
        
        return msg

    def run_search(self):
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 🔍 Hunting for jobs across 4 platforms...")
        
        all_jobs = []
        
        # 1. LinkedIn
        print("  Searching LinkedIn...")
        linkedin_jobs = self.search_linkedin()
        all_jobs.extend(linkedin_jobs)
        print(f"  ✓ LinkedIn: {len(linkedin_jobs)} new jobs")
        
        # 2. Glassdoor
        print("  Searching Glassdoor...")
        glassdoor_jobs = self.search_glassdoor()
        all_jobs.extend(glassdoor_jobs)
        print(f"  ✓ Glassdoor: {len(glassdoor_jobs)} new jobs")
        
        # 3. Google
        print("  Searching Google...")
        google_jobs = self.search_google_jobs()
        all_jobs.extend(google_jobs)
        print(f"  ✓ Google: {len(google_jobs)} new jobs")
        
        # 4. RemoteOK
        print("  Searching RemoteOK...")
        remote_jobs = self.search_remoteok()
        all_jobs.extend(remote_jobs)
        print(f"  ✓ RemoteOK: {len(remote_jobs)} new jobs")
        
        # ترتيب حسب التقييم (الأعلى أولاً)
        all_jobs.sort(key=lambda x: x['stars'], reverse=True)
        
        # إزالة التكرارات (نفس العنوان من مصادر مختلفة)
        seen_titles = set()
        unique_jobs = []
        for job in all_jobs:
            title_normalized = job['title'].lower().strip()[:50]
            if title_normalized not in seen_titles:
                seen_titles.add(title_normalized)
                unique_jobs.append(job)
        
        # إرسال أعلى 100 وظيفة مرتبين بالنجوم
        sent_count = 0
        for job in unique_jobs[:100]:
            msg = self.format_job_message(job)
            print(f"  → {job['title'][:60]}... ({job['source']}) {'⭐' * job['stars']}")
            send_telegram_message(msg)
            self.sent_jobs.add(job['hash'])
            sent_count += 1
            time.sleep(1)
        
        if sent_count == 0:
            print("  No new matching jobs found this round.")
        else:
            # ملخص
            summary = (f"📊 *Job Search Summary*\n"
                       f"🔍 *Scanned:* 4 platforms\n"
                       f"📋 *New Jobs Found:* `{len(unique_jobs)}`\n"
                       f"📨 *Sent to you:* `{sent_count}` (Top matches)\n"
                       f"⏰ *Next scan in:* 1 hour")
            send_telegram_message(summary)
            print(f"\n  ✅ Sent {sent_count} job alerts!")
        
        self.save_state()
        print("-" * 60)

if __name__ == "__main__":
    bot = JobAlertBot()
    print(f"🤖 Job Alert Bot Ready for: {bot.profile['name']}")
    print(f"🔍 Tracking {len(bot.search_queries)} queries across 4 platforms")
    print(f"📡 Sources: LinkedIn | Glassdoor | Google | RemoteOK")
    
    if os.getenv('GITHUB_ACTIONS'):
        bot.run_search()
    else:
        while True:
            bot.run_search()
            print("Waiting 15 mins for next job scan... ⏳")
            time.sleep(900)

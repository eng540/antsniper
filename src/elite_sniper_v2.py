"""
Elite Sniper v3.3 - Production-Grade Multi-Session Appointment Booking System

Integrates best features from:
- Elite Sniper: Multi-session architecture, Scout/Attacker pattern, Scheduled activation
- KingSniperV12: State Machine, Soft Recovery, Safe Captcha Check, Debug utilities

Refactored for:
- [FIX] Targeted Scope (Offsets 2, 3, 4 only) -> Months 3, 4, 5
- [FIX] Robust Submit (Click instead of Enter)
- Anti-Zombie memory management
- 100% Local OCR logic integration
"""

import time
import random
import datetime
import logging
import os
import sys
import re
from typing import List, Tuple, Optional, Dict, Any
from threading import Thread, Event, Lock
from dataclasses import asdict

import pytz
from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser

try:
    from .config import Config
except ImportError:
    from config import Config
from .ntp_sync import NTPTimeSync
from .session_state import (
    SessionState, SessionStats, SystemState, SessionHealth, 
    SessionRole, Incident, IncidentManager, IncidentType, IncidentSeverity
)
from .captcha import EnhancedCaptchaSolver
from .notifier import send_alert, send_photo, send_success_notification, send_status_update
from .debug_utils import DebugManager
from .page_flow import PageFlowDetector
from .diagnostic import ForensicMonitor, OperationTracker, TelegramReporter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s.%(msecs)03d [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'elite_sniper_v2.log'), encoding='utf-8')
    ]
)
logger = logging.getLogger("EliteSniperV2")


class EliteSniperV2:
    VERSION = "3.3.0-TARGET-345"
    
    def __init__(self, run_mode: str = "AUTO"):
        self.run_mode = run_mode
        
        logger.info("=" * 70)
        logger.info(f"[INIT] ELITE SNIPER V{self.VERSION} - INITIALIZING")
        logger.info(f"[MODE] Running Mode: {self.run_mode}")
        logger.info("=" * 70)
        
        self._validate_config()
        
        self.session_id = f"elite_v3_{int(time.time())}_{random.randint(1000, 9999)}"
        self.start_time = datetime.datetime.now()
        
        self.system_state = SystemState.STANDBY
        self.stop_event = Event()      
        self.slot_event = Event()      
        self.target_url: Optional[str] = None  
        self.lock = Lock()              
        self.screenshot_requested = Event()  

        try:
            from .telegram_c2 import TelegramCommander
            self.c2 = TelegramCommander(bot_instance=self)
            self.c2.start()
        except Exception as e:
            logger.error(f"[C2] Failed to start Telegram Commander: {e}")
            self.c2 = None
            
        self.mode = Config.EXECUTION_MODE
        logger.info(f"[MODE] Execution Strategy: {self.mode}")
        
        self.solver = EnhancedCaptchaSolver(mode=self.mode, c2_instance=self.c2)
        
        self.debug_manager = DebugManager(self.session_id, Config.EVIDENCE_DIR)
        self.incident_manager = IncidentManager()
        self.ntp_sync = NTPTimeSync(Config.NTP_SERVERS, Config.NTP_SYNC_INTERVAL)
        self.page_flow = PageFlowDetector()  
        self.paused = Event() 
        
        self.monitor = ForensicMonitor(base_dir="debug", enabled=True)
        self.tracker = OperationTracker()
        self.telegram_reporter = TelegramReporter(enabled=True)
        
        self.base_url = self._prepare_base_url(Config.TARGET_URL)
        self.timezone = pytz.timezone(Config.TIMEZONE)
        
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ]
        
        self.proxies = self._load_proxies()
        self.global_stats = SessionStats()
        
        self.ntp_sync.start_background_sync()
        
        logger.info(f"[ID] Session ID: {self.session_id}")
        logger.info(f"[URL] Base URL: {self.base_url[:60]}...")
        logger.info(f"[TZ] Timezone: {self.timezone}")
        logger.info(f"[OK] Initialization complete")
    
    def request_screenshot(self):
        self.screenshot_requested.set()

    def set_mode(self, new_mode: str): 
        valid_modes = ["AUTO", "MANUAL", "HYBRID"] 
        if new_mode.upper() in valid_modes: 
            self.mode = new_mode.upper() 
            self.run_mode = new_mode.upper() 
            if hasattr(self, 'solver'): 
                self.solver.mode = self.mode 
            logger.info(f"[MODE] Switched to {self.mode}") 
            return True 
        return False

    def pause_execution(self): 
        if not self.paused.is_set(): 
            self.paused.set() 
            logger.info("⏸️ System PAUSED by user")

    def resume_execution(self): 
        if self.paused.is_set(): 
            self.paused.clear() 
            logger.info("▶️ System RESUMED by user")

    def get_status_report(self) -> str:
        stats = self.global_stats
        status = "🟢 Running" if not self.paused.is_set() else "⏸ Paused"
        return (
            f"📊 <b>System Status</b>\n"
            f"Mode: {self.run_mode}\n"
            f"State: {status}\n\n"
            f"📉 <b>Statistics</b>:\n"
            f"Days Found: {stats.days_found}\n"
            f"Slots Found: {stats.slots_found}\n"
            f"Forms Filled: {stats.forms_filled}\n"
            f"Captchas: {stats.captchas_solved}/{stats.captchas_solved + stats.captchas_failed}\n"
        )
    
    def force_screenshot(self) -> Optional[str]:
        try:
            if hasattr(self, 'current_page') and self.current_page:
                try:
                    timestamp = int(time.time())
                    filename = f"c2_shot_{timestamp}.jpg"
                    path = os.path.join(Config.EVIDENCE_DIR, filename)
                    self.current_page.screenshot(path=path)
                    return path
                except Exception as e:
                    logger.error(f"[C2] Screenshot failed: {e}")
            return None
        except Exception as e:
            logger.error(f"[C2] Force screenshot error: {e}")
            return None

    def _validate_config(self):
        required = ['TARGET_URL', 'LAST_NAME', 'FIRST_NAME', 'EMAIL', 'PASSPORT', 'PHONE']
        missing = [field for field in required if not getattr(Config, field, None)]
        if missing:
            raise ValueError(f"[ERR] Missing configuration: {', '.join(missing)}")
        logger.info("[OK] Configuration validated")
    
    def cleanup(self):
        logger.info("[CLEANUP] Initiating robust shutdown...")
        self.stop_event.set()
        try:
            if hasattr(self, 'ntp_sync'):
                self.ntp_sync.stop_background_sync()
        except: pass
        try:
            if hasattr(self, 'c2') and self.c2:
                self.c2.stop()
        except: pass
        logger.info("[CLEANUP] Resources released")
    
    def _prepare_base_url(self, url: str) -> str:
        if "request_locale" not in url:
            separator = "&" if "?" in url else "?"
            return f"{url}{separator}request_locale=en"
        return url
    
    def _load_proxies(self) -> List[Optional[str]]:
        proxies = []
        if hasattr(Config, 'PROXIES') and Config.PROXIES:
            proxies.extend([p for p in Config.PROXIES if p])
        try:
            if os.path.exists("proxies.txt"):
                with open("proxies.txt") as f:
                    file_proxies = [line.strip() for line in f if line.strip()]
                    proxies.extend(file_proxies)
        except Exception as e:
            logger.warning(f"⚠️ Failed to load proxies.txt: {e}")
        while len(proxies) < 3:
            proxies.append(None)
        return proxies[:3] 
    
    def get_current_time_aden(self) -> datetime.datetime:
        corrected_utc = self.ntp_sync.get_corrected_time()
        aden_time = corrected_utc.replace(tzinfo=pytz.UTC).astimezone(self.timezone)
        return aden_time
    
    def is_pre_attack(self) -> bool:
        now = self.get_current_time_aden()
        return (now.hour == 1 and 
                now.minute == Config.PRE_ATTACK_MINUTE and 
                now.second >= Config.PRE_ATTACK_SECOND)
    
    def is_attack_time(self) -> bool:
        now = self.get_current_time_aden()
        return now.hour == Config.ATTACK_HOUR
    
    def get_sleep_interval(self) -> float:
        if self.is_attack_time():
            return 30.0
        elif self.is_pre_attack():
            return Config.PRE_ATTACK_SLEEP
        else:
            now = self.get_current_time_aden()
            if now.hour == 1 and now.minute >= 45:
                return Config.WARMUP_SLEEP
            current_minute = now.minute
            current_second = now.second
            if current_minute < 20: target_minute = 20
            elif current_minute < 40: target_minute = 40
            else: target_minute = 60 
            minutes_to_wait = target_minute - current_minute - 1
            seconds_to_wait = 60 - current_second
            total_wait = (minutes_to_wait * 60) + seconds_to_wait
            final_wait = max(10.0, total_wait - 5.0)
            return final_wait
    
    def get_mode(self) -> str:
        if self.is_attack_time(): return "ATTACK"
        elif self.is_pre_attack(): return "PRE_ATTACK"
        else:
            now = self.get_current_time_aden()
            if now.hour == 1 and now.minute >= 45: return "WARMUP"
            return "PATROL"
    
    def create_context(self, browser: Browser, worker_id: int, proxy: Optional[str] = None) -> Tuple[BrowserContext, Page, SessionState]:
        try:
            role = SessionRole.SCOUT if worker_id == 1 else SessionRole.ATTACKER
            user_agent = random.choice(self.user_agents)
            viewport_width = 1366 + random.randint(0, 50)
            viewport_height = 768 + random.randint(0, 30)
            
            context_options = {
                "user_agent": user_agent,
                "viewport": {"width": viewport_width, "height": viewport_height},
                "locale": "en-US", 
                "timezone_id": "Asia/Aden", 
                "ignore_https_errors": True,
                "record_video_dir": "debug/videos",
                "record_video_size": {"width": 1280, "height": 720}
            }
            
            if proxy:
                context_options["proxy"] = {"server": proxy}
            
            context = browser.new_context(**context_options)
            page = context.new_page()
            
            page.add_init_script(f"""
                Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
                Object.defineProperty(navigator, 'plugins', {{ get: () => [1, 2, 3, 4, 5] }});
                Object.defineProperty(navigator, 'languages', {{ get: () => ['en-US', 'en'] }});
                setInterval(() => {{ fetch(location.href, {{ method: 'HEAD' }}).catch(()=>{{}}); }}, {Config.HEARTBEAT_INTERVAL * 1000});
            """)
            
            context.set_default_timeout(45000)
            context.set_default_navigation_timeout(120000)
            
            def route_handler(route):
                resource_type = route.request.resource_type
                if resource_type in ["image", "media", "font", "stylesheet"]:
                    route.abort()
                else:
                    route.continue_()
            
            page.route("**/*", route_handler)
            
            session_state = SessionState(
                session_id=f"{self.session_id}_w{worker_id}",
                role=role,
                worker_id=worker_id,
                max_age=300,  
                max_idle=Config.SESSION_MAX_IDLE,
                max_failures=Config.MAX_CONSECUTIVE_ERRORS,
                max_captcha_attempts=Config.MAX_CAPTCHA_ATTEMPTS
            )
            
            with self.lock:
                self.global_stats.rebirths += 1
            
            return context, page, session_state
            
        except Exception as e:
            logger.error(f"[ERR] [W{worker_id}] Context creation failed: {e}")
            raise
    
    def validate_session_health(self, page: Page, session: SessionState, location: str = "UNKNOWN") -> bool:
        worker_id = session.worker_id
        
        if session.is_expired():
            self.incident_manager.create_incident(session.session_id, IncidentType.SESSION_EXPIRED, IncidentSeverity.CRITICAL, "Session expired")
            return False
        
        if session.should_terminate():
            self.incident_manager.create_incident(session.session_id, IncidentType.SESSION_POISONED, IncidentSeverity.CRITICAL, "Session poisoned")
            return False
        
        if session.captcha_solved:
            has_captcha, _ = self.solver.safe_captcha_check(page, location)
            if has_captcha:
                session.health = SessionHealth.POISONED
                self.incident_manager.create_incident(session.session_id, IncidentType.DOUBLE_CAPTCHA, IncidentSeverity.CRITICAL, "Double captcha")
                return False
        
        if location == "POST_SUBMIT":
            try:
                if page.locator("input[name='lastname']").count() > 0:
                    return False
            except: pass
        
        if location == "FORM":
            try:
                if page.locator("form#appointment_captcha_month").count() > 0:
                    return False
            except: pass
        
        session.touch()
        return True
    
    def generate_month_urls(self) -> List[str]:
        try:
            today = datetime.datetime.now().date()
            base_clean = self.base_url.split("&dateStr=")[0] if "&dateStr=" in self.base_url else self.base_url
            urls = []
            # [CONFIGURED SCOPE] Search Months 3, 4, 5 only
            priority_offsets = [2, 3, 4] 
            
            for offset in priority_offsets:
                future_date = today + datetime.timedelta(days=30 * offset)
                date_str = f"15.{future_date.month:02d}.{future_date.year}" 
                url = f"{base_clean}&dateStr={date_str}"
                urls.append(url)
            return urls
        except Exception as e:
            return []
    
    def select_category_by_value(self, page: Page) -> bool:
        try:
            selects = page.locator("select").all()
            if not selects: return False
            
            all_options = []
            for select in selects:
                try:
                    options = select.locator("option").all()
                    for option in options:
                        text = option.inner_text().strip()
                        value = option.get_attribute("value")
                        if text and value:
                            all_options.append({
                                "select": select, "option": option,
                                "text": text, "text_lower": text.lower(), "value": value
                            })
                except Exception: continue
            
            for priority, keyword in enumerate(Config.TARGET_KEYWORDS, start=1):
                keyword_lower = keyword.lower()
                for opt in all_options:
                    if keyword_lower in opt["text_lower"]:
                        try:
                            opt["select"].select_option(value=opt["value"])
                            page.evaluate("""
                                const selects = document.querySelectorAll('select');
                                selects.forEach(s => {
                                    s.dispatchEvent(new Event('input', { bubbles: true }));
                                    s.dispatchEvent(new Event('change', { bubbles: true }));
                                });
                            """)
                            return True
                        except Exception: continue
            
            valid_options = [opt for opt in all_options if opt["value"]]
            if len(valid_options) >= 2:
                fallback_opt = valid_options[1] 
                try:
                    fallback_opt["select"].select_option(value=fallback_opt["value"])
                    page.evaluate("""
                        const selects = document.querySelectorAll('select');
                        selects.forEach(s => {
                            s.dispatchEvent(new Event('input', { bubbles: true }));
                            s.dispatchEvent(new Event('change', { bubbles: true }));
                        });
                    """)
                    return True
                except Exception: pass
            return False
        except Exception:
            return False

    def _fill_booking_form(self, page: Page, session: SessionState, worker_logger) -> bool:
        try:
            worker_logger.info("📝 Filling form (Human Mode)...")
            fields = [
                ("input[name='lastname']", Config.LAST_NAME),
                ("input[name='firstname']", Config.FIRST_NAME),
                ("input[name='email']", Config.EMAIL),
                ("input[name='emailrepeat']", Config.EMAIL),
                ("input[name='emailRepeat']", Config.EMAIL), 
                ("input[name='fields[0].content']", Config.PASSPORT),
                ("input[name='fields[1].content']", Config.PHONE.replace("+", "00").strip())
            ]
            
            for selector, value in fields:
                try:
                    if page.locator(selector).count() > 0:
                        page.focus(selector)
                        page.fill(selector, "")
                        page.type(selector, value, delay=10) 
                        page.evaluate(f"document.querySelector(\"{selector}\").blur()")
                except Exception: continue

            if not self.select_category_by_value(page):
                try:
                    page.evaluate("""
                        const s = document.querySelector('select');
                        if(s) { s.selectedIndex = 1; s.dispatchEvent(new Event('change')); }
                    """)
                except Exception: pass

            self.global_stats.forms_filled += 1
            return True
        except Exception:
            return False

    def _submit_form(self, page: Page, session: SessionState, worker_logger, initial_code: Optional[str] = None) -> bool:
        worker_logger.info(f"🚀 STARTING SMART SYNCHRONIZED SUBMISSION...")
        
        INPUT_ID = "appointment_newAppointmentForm_captchaText"
        SUBMIT_ID = "appointment_newAppointmentForm_appointment_addAppointment"

        worker_logger.info("🧠 Requesting exact 6-char captcha from local OCR...")
        captcha_code = self.solver.get_valid_captcha_turbo(page, "TURBO_SYNC")
        
        if not captcha_code:
            worker_logger.error("❌ Failed to get valid 6-char captcha. Aborting submission.")
            return False

        worker_logger.info(f"✅ Captcha ready: {captcha_code}. Verifying form DOM state...")
        
        is_form_filled = page.evaluate("""
            () => {
                const lname = document.querySelector("input[name='lastname']");
                const cat = document.querySelector("select");
                return (lname && lname.value.length > 0) && (cat && cat.value !== "");
            }
        """)

        if not is_form_filled:
            worker_logger.critical("🛑 DOM Desync Detected! Form data is missing in UI. Re-injecting...")
            self._fill_booking_form(page, session, worker_logger)
            time.sleep(0.2) 

        worker_logger.critical(f"⚡ ALL SYSTEMS GO! Injecting Captcha '{captcha_code}' and striking!")
        
        page.evaluate(f"""
            document.getElementById('{INPUT_ID}').value = '{captcha_code}';
            document.getElementById('{SUBMIT_ID}').click();
        """)

        worker_logger.info("📡 Waiting for server resolution...")
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            pass

        try:
            content = page.content().lower()
            
            if "appointment number" in content or "termin nummer" in content or "erfolgreich" in content:
                worker_logger.critical("🏆 TARGET DESTROYED (SUCCESS)! Booking markers confirmed!")
                self.global_stats.success = True
                self.debug_manager.save_critical_screenshot(page, "VICTORY_CONFIRMED", session.worker_id)
                self.stop_event.set()
                return True
                
            elif "wrong" in content or "falsch" in content:
                worker_logger.warning("❌ Server rejected captcha. Retrying...")
                return False
                
            elif page.locator("input[name='lastname']").count() > 0:
                worker_logger.warning("❌ Soft rejection - Form still present.")
                return False
                
        except Exception as e:
            worker_logger.warning(f"⚠️ Resolution check failed: {e}")
            
        return False

    def _analyze_page_state(self, page: Page, logger) -> str:
        try:
            try: page.wait_for_load_state("domcontentloaded", timeout=3000)
            except: pass
            
            time.sleep(0.3)  
            content = page.content().lower()
            
            try:
                if page.locator("a[href*='appointment_showDay']").count() > 0:
                    return "SLOTS_FOUND"
            except: pass
            
            if "unfortunately, there are no appointments available" in content or "keine termine" in content:
                return "EMPTY_CALENDAR"
            if "no appointments" in content and "appointment_showDay" not in content:
                return "EMPTY_CALENDAR"
            
            if "entered text was wrong" in content: return "WRONG_CODE"
            try:
                if page.locator("div.global-error").is_visible(timeout=300): return "WRONG_CODE"
            except: pass
            
            try:
                if page.locator("#appointment_captcha_month").is_visible(timeout=300): return "CAPTCHA"
            except: pass
            
            try:
                if page.locator("input[name='captchaText']").is_visible(timeout=300): return "CAPTCHA"
            except: pass

            return "UNKNOWN"
        except:
            return "UNKNOWN"

    def check_session_health(self, page: Page, session: SessionState, logger) -> bool:
        try:
            if page.locator("#appointment_captcha_month").is_visible(timeout=500): pass
            if page.locator("#appointment_newAppointmentForm_captchaText").is_visible(timeout=500): pass
            if page.locator("div.global-error").is_visible(timeout=500): pass
            return True
        except:
            return True 

    def _process_month_page(self, page: Page, session: SessionState, url: str, logger) -> bool:
        try:
            if not self.check_session_health(page, session, logger):
                return False

            max_nav_retries = 2
            for nav_attempt in range(max_nav_retries):
                try:
                    page.evaluate(f"window.location.href = '{url}';")
                    try: page.wait_for_load_state("domcontentloaded", timeout=30000)
                    except: pass
                    break
                except Exception as nav_e:
                    if nav_attempt < max_nav_retries - 1:
                        time.sleep(5)
                        continue
                    else: return False
            
            session.current_url = url
            session.touch()
            self.global_stats.pages_loaded += 1
            
            if not self.check_session_health(page, session, logger):
                return False

            max_attempts = 5  
            consecutive_failures = 0
            
            for attempt in range(max_attempts):
                state = self._analyze_page_state(page, logger)
                
                if state == "SLOTS_FOUND":
                    day_links = page.locator("a[href*='appointment_showDay']").all()
                    if day_links:
                         target_day = day_links[0]
                         day_href = target_day.get_attribute("href")
                         if day_href:
                            base_domain = self.base_url.split("/extern")[0]
                            day_url = f"{base_domain}/{day_href}" if not day_href.startswith("http") else day_href
                            return self._process_day_page(page, session, day_url, logger)
                    return False

                elif state == "EMPTY_CALENDAR":
                    return False

                elif state == "WRONG_CODE" or state == "CAPTCHA":
                    is_wrong_code = (state == "WRONG_CODE")
                    if is_wrong_code:
                        consecutive_failures += 1
                        self.global_stats.captchas_failed += 1
                        if consecutive_failures >= 5:
                             time.sleep(60)
                             return False

                    success, code, status = self.solver.solve_from_page(page, f"MONTH_{attempt}")
                    
                    if not success:
                        if not is_wrong_code: consecutive_failures += 1
                        if consecutive_failures >= 5:
                             time.sleep(60)
                             return False 
                        try:
                            refresh = page.locator("#appointment_newAppointmentForm_form_newappointment_refreshcaptcha")
                            if refresh.is_visible(): refresh.click()
                            else: self.solver.reload_captcha(page)
                            time.sleep(1.0)
                        except: pass
                        continue
                        
                    # [FIX] Robust Submission: Try clicking the button first, then Enter as fallback
                    try:
                        submit_btn = page.locator("input[type='submit'], button[type='submit']").first
                        if submit_btn.is_visible():
                            submit_btn.click(timeout=3000)
                        else:
                            page.keyboard.press("Enter")
                    except:
                        page.keyboard.press("Enter")
                        
                    try:
                        page.wait_for_selector("div.global-error, a[href*='appointment_showDay'], h2:has-text('Please select')", timeout=8000)
                    except:
                        try: page.wait_for_load_state("networkidle", timeout=5000)
                        except: pass
                    time.sleep(0.5)  
                else:
                    return False
            
            return False

        except Exception as e:
            return False

    def _process_day_page(self, page: Page, session: SessionState, url: str, logger) -> bool:
        try:
            page.goto(url, timeout=20000, wait_until="domcontentloaded")
            slot_links = page.locator("a.arrow[href*='appointment_showForm'], a[href*='appointment_showForm']").all()
            if not slot_links: return False
                
            self.global_stats.slots_found += len(slot_links)
            target_slot = slot_links[0]
            slot_href = target_slot.get_attribute("href")
            
            if slot_href:
                base_domain = self.base_url.split("/extern")[0]
                form_url = f"{base_domain}/{slot_href}" if not slot_href.startswith("http") else slot_href
                page.goto(form_url, timeout=20000, wait_until="domcontentloaded")
                time.sleep(2)
                return self._process_booking_form(page, session, form_url, logger)
            
            return False
        except Exception:
            return False

    def _process_booking_form(self, page: Page, session: SessionState, url: str, logger) -> bool:
        try:
            try:
                page.wait_for_selector("input[name='lastname']", timeout=5000)
            except:
                page.goto(url, timeout=20000, wait_until="domcontentloaded")
            
            if not self._fill_booking_form(page, session, logger):
                return False
                
            if Config.DRY_RUN:
                self.debug_manager.save_critical_screenshot(page, "DRY_RUN_SUCCESS", session.worker_id)
                time.sleep(5) 
                return True 
                
            return self._submit_form(page, session, logger)
            
        except Exception:
            return False

    def _run_single_session(self, browser: Browser, worker_id: int = 1):
        worker_logger = logging.getLogger(f"Worker-{worker_id}")
        
        try:
            proxy = Config.PROXIES[worker_id % len(Config.PROXIES)] if Config.PROXIES else None
        except: proxy = None
        
        try:
            context, page, session = self.create_context(self.browser, worker_id, proxy)
            self.current_page = page 
            session.role = SessionRole.SCOUT
            
            max_cycles = 1000  
            
            for cycle in range(max_cycles):
                if self.stop_event.is_set(): break
                
                if self.paused.is_set():
                    while self.paused.is_set() and not self.stop_event.is_set(): time.sleep(1)
                
                try:
                    month_urls = self.generate_month_urls()
                    
                    for url in month_urls:
                        if self.stop_event.is_set(): break
                        if self._process_month_page(page, session, url, worker_logger): return True  
                        if getattr(session, 'consecutive_network_failures', 0) >= 2: break
                        time.sleep(random.uniform(0.5, 1.5))
                    
                    sleep_time = self.get_sleep_interval()
                    time.sleep(sleep_time)
                    
                    if session.age() > Config.SESSION_MAX_AGE or getattr(session, 'consecutive_network_failures', 0) >= 2:
                        try: 
                            page.close()
                            context.close()
                        except: pass
                        context, page, session = self.create_context(browser, worker_id, proxy)
                        self.current_page = page  
                        session.role = SessionRole.SCOUT
                        
                except Exception as cycle_error:
                    try:
                        page.close()
                        context.close()
                    except: pass
                    context, page, session = self.create_context(browser, worker_id, proxy)
                    self.current_page = page  
                    session.role = SessionRole.SCOUT

        except Exception as e:
            worker_logger.error(f"❌ Critical Session Error: {e}", exc_info=True)
            return False
            
        finally:
            worker_logger.info("🧹 Final cleanup of single session...")
            try: 
                if 'page' in locals() and page: page.close()
                if 'context' in locals() and context: context.close()
            except: pass
            
        return False  

    def run(self) -> bool:
        logger.info("=" * 70)
        logger.info(f"[ELITE SNIPER V{self.VERSION}] - STARTING EXECUTION")
        logger.info("=" * 70)
        
        try:
            send_alert(f"[Elite Sniper v{self.VERSION} Started]")
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=Config.HEADLESS, args=Config.BROWSER_ARGS, timeout=90000)
                self.browser = browser  
                worker_id = 1  
                
                try:
                    self._run_single_session(browser, worker_id=worker_id)
                except Exception as e:
                    logger.error(f"[SESSION ERROR] {e}")
                
                self.ntp_sync.stop_background_sync()
                browser.close()
                
                final_stats = self.global_stats.to_dict()
                self.debug_manager.save_stats(final_stats, "final_stats.json")
                self.debug_manager.create_session_report(final_stats)
                
                if self.global_stats.success:
                    logger.info("[SUCCESS] MISSION ACCOMPLISHED")
                    return True
                else:
                    return False
                
        except KeyboardInterrupt:
            self.stop_event.set()
            self.ntp_sync.stop_background_sync()
            return False
        except Exception as e:
            return False
        finally:
            self.cleanup()

if __name__ == "__main__":
    sniper = EliteSniperV2()
    success = sniper.run()
    sys.exit(0 if success else 1)
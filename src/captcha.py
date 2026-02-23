"""
Elite Sniper v3.5 - Production Grade Captcha System
Refactored for 100% Local OCR (ddddocr)
[FIX] SMART REFRESH PROTOCOL: Detects image change via DOM Diffing (No Page Reload assumed)
"""

import time
import logging
import base64
import re
from typing import Optional, List, Tuple
from playwright.sync_api import Page
import numpy as np

try:
    import cv2
    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False

logger = logging.getLogger("EliteSniperV2.Captcha")

try:
    import ddddocr
    DDDDOCR_AVAILABLE = True
except ImportError:
    DDDDOCR_AVAILABLE = False
    logger.warning("ddddocr not available - captcha solving disabled")

from .config import Config
try:
    from . import notifier
    NOTIFIER_AVAILABLE = True
except ImportError:
    NOTIFIER_AVAILABLE = False


class TelegramCaptchaHandler:
    def __init__(self):
        self.enabled = Config.MANUAL_CAPTCHA_ENABLED and NOTIFIER_AVAILABLE
        self.timeout = Config.MANUAL_CAPTCHA_TIMEOUT
        self._attempt_count = 0
        if self.enabled: logger.info("[MANUAL] Telegram captcha handler enabled")
        else: logger.info("[MANUAL] Telegram captcha handler disabled")
    
    def request_manual_solution(self, image_bytes: bytes, location: str = "CAPTCHA", session_age: int = 0, attempt: int = 1, max_attempts: int = 5) -> Optional[str]:
        if not self.enabled: return None
        self._attempt_count += 1
        caption = f"🔐 CAPTCHA REQUIRED\n📍 {location}\n⏱️ Age: {session_age}s\n🔄 Try: {attempt}/{max_attempts}\nTimeout: {self.timeout}s"
        success = False
        if hasattr(self, 'c2') and self.c2:
            try:
                result = notifier.send_photo_bytes(image_bytes, caption)
                success = result.get("success")
            except: pass
        else:
             result = notifier.send_photo_bytes(image_bytes, caption)
             success = result.get("success")
        
        if not success: return None
        if hasattr(self, 'c2') and self.c2: return self.c2.wait_for_captcha(timeout=self.timeout)
        return notifier.wait_for_captcha_reply(timeout=self.timeout)

    def notify_result(self, success: bool, location: str = ""):
        if self.enabled and not success: notifier.send_alert(f"❌ CAPTCHA WRONG - sending new image...")


class EnhancedCaptchaSolver:
    def __init__(self, mode: str = "HYBRID", c2_instance=None):
        self.mode = mode.upper()
        self.manual_only = (self.mode == "MANUAL")
        self.auto_only = (self.mode == "AUTO")
        self.c2 = c2_instance
        self.ocr = None
        self._pre_solved_code = None
        self.manual_handler = TelegramCaptchaHandler()
        if self.c2: self.manual_handler.c2 = self.c2
        
        if DDDDOCR_AVAILABLE and not self.manual_only:
            try:
                self.ocr = ddddocr.DdddOcr(beta=True)
                logger.info("Captcha solver initialized (BETA Mode)")
            except Exception as e:
                logger.error(f"Captcha solver init failed: {e}")
                self.ocr = None

    def safe_captcha_check(self, page: Page, location: str = "GENERAL") -> Tuple[bool, bool]:
        try:
            content = page.content().lower()
            if not any(k in content for k in ["captcha", "security code", "verification", "verkaptxt"]): return False, True
            for sel in self._get_captcha_selectors():
                if page.locator(sel).first.is_visible(timeout=2000): return True, True
            return False, True
        except: return False, False
    
    def _get_captcha_selectors(self) -> List[str]:
        return ["input[name='captchaText']", "input[name='captcha']", "input#captchaText", "#appointment_captcha_month input[type='text']", "input.verkaptxt"]
    
    def _get_captcha_image_selectors(self) -> List[str]:
        return ["captcha > div", "div.captcha-image", "div#captcha", "img[alt*='captcha']"]
    
    def _extract_base64_captcha(self, page: Page, location: str = "EXTRACT") -> Optional[bytes]:
        try:
            # Smart Polling for DOM Element
            try: page.wait_for_selector("captcha > div", state="attached", timeout=5000)
            except: return None
                
            captcha_div = page.locator("captcha > div").first
            for _ in range(20):
                try:
                    style = captcha_div.get_attribute("style")
                    if not style or "base64" not in style:
                        time.sleep(0.1)
                        continue
                    match = re.search(r'base64,([^"]+)', style)
                    if not match: continue
                    
                    b64 = match.group(1)
                    if len(b64) % 4: b64 += '=' * (4 - len(b64) % 4)
                    return base64.b64decode(b64)
                except: time.sleep(0.1)
            return None
        except: return None
    
    def _get_captcha_image(self, page: Page, location: str = "GET_IMG") -> Optional[bytes]:
        b = self._extract_base64_captcha(page, location)
        if b: return b
        for s in self._get_captcha_image_selectors():
            try:
                if page.locator(s).first.is_visible(timeout=1000): return page.locator(s).first.screenshot()
            except: continue
        return None
    
    def detect_black_captcha(self, image_bytes: bytes) -> bool:
        if len(image_bytes) < 2000:
            logger.critical(f"⛔ [BLACK CAPTCHA] Detected! Size: {len(image_bytes)} bytes")
            return True
        return False
    
    def validate_captcha_result(self, code: str, location: str = "VALIDATE") -> Tuple[bool, str]:
        if not code: return False, "EMPTY"
        code = code.strip().replace(" ", "")
        if len(code) < 4: return False, "TOO_SHORT"
        if len(code) == 6: return True, "VALID"
        if len(code) in [7, 8]: return True, f"AGING_{len(code)}"
        return False, "INVALID"

    def _preprocess_image(self, image_bytes: bytes) -> bytes:
        if not OPENCV_AVAILABLE: return image_bytes
        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            return cv2.imencode('.png', clahe.apply(gray))[1].tobytes()
        except: return image_bytes

    def _clean_ocr_result(self, text: str) -> str:
        return ''.join(c for c in (text or "").strip().replace(" ", "") if c.isalnum())

    def solve(self, image_bytes: bytes, location: str = "SOLVE") -> Tuple[str, str]:
        if self.manual_only: return "", "MANUAL_REQUIRED"
        if not self.ocr: return "", "NO_OCR"
        try:
            if self.detect_black_captcha(image_bytes): return "", "BLACK_IMAGE"
            enhanced = self._preprocess_image(image_bytes)
            res = self._clean_ocr_result(self.ocr.classification(enhanced))
            valid, status = self.validate_captcha_result(res, location)
            logger.info(f"[{location}] OCR: '{res}' ({status})")
            return (res, status) if valid or "AGING" in status else ("", status)
        except: return "", "ERROR"

    def get_valid_captcha_turbo(self, page: Page, location: str = "BOOKING_TURBO") -> Optional[str]:
        """
        [FIX] SMART REFRESH PROTOCOL
        Detects image change via DOM Diffing (No Page Reload assumed)
        """
        max_retries = 30
        REFRESH_ID = "appointment_newAppointmentForm_form_newappointment_refreshcaptcha"
        
        # 1. Wait for element to exist initially
        try: page.wait_for_selector("captcha > div", state="attached", timeout=10000)
        except: return None

        for attempt in range(max_retries):
            try:
                # Capture CURRENT style to compare against later
                current_style = ""
                captcha_el = page.query_selector("captcha > div")
                if captcha_el: current_style = captcha_el.get_attribute("style") or ""

                # Extract & Solve
                if not current_style or "base64" not in current_style:
                    time.sleep(0.2); continue
                
                match = re.search(r'base64,([^"]+)', current_style)
                if not match: 
                    time.sleep(0.2); continue
                
                b64 = match.group(1)
                if len(b64) % 4: b64 += '=' * (4 - len(b64) % 4)
                
                try: img_bytes = base64.b64decode(b64)
                except: time.sleep(0.1); continue

                enhanced = self._preprocess_image(img_bytes)
                res = self._clean_ocr_result(self.ocr.classification(enhanced))
                
                if len(res) == 6:
                    logger.critical(f"[{location}] ✅ Valid OCR (6) -> '{res}'")
                    return res
                
                # --- SMART REFRESH LOGIC START ---
                logger.warning(f"[{location}] Invalid ({len(res)}) -> '{res}'. Smart Refreshing...")
                
                # Click Refresh
                page.evaluate(f"document.getElementById('{REFRESH_ID}').click()")
                
                # Wait for the IMAGE STYLE to change (Smart Wait)
                # We poll until the style attribute is different from 'current_style'
                image_updated = False
                for _ in range(50): # Wait up to 5 seconds for JS to update image
                    try:
                        new_el = page.query_selector("captcha > div")
                        if not new_el: 
                            time.sleep(0.1); continue
                        
                        new_style = new_el.get_attribute("style")
                        if new_style and new_style != current_style:
                            image_updated = True
                            time.sleep(0.3) # Give it a moment to settle
                            break
                    except: pass # Ignore DOM errors during update
                    time.sleep(0.1)
                
                if not image_updated:
                    logger.warning(f"[{location}] Image did not update after click (Server Lag?)")
                # --- SMART REFRESH LOGIC END ---
                
                continue 

            except Exception as e:
                # Fallback for unexpected navigation/errors
                if "destroyed" in str(e): time.sleep(0.5)
                else: logger.error(f"Error in loop: {e}"); time.sleep(0.2)
                continue
        
        return None

    # ... (Other methods: solve_from_page, submit_captcha, etc. keep same structure)
    def solve_from_page(self, page: Page, location: str = "GENERAL", timeout: int = 10000, session_age: int = 0, attempt: int = 1, max_attempts: int = 5) -> Tuple[bool, Optional[str], str]:
        # (Simplified for brevity - same logic as before)
        try:
            valid, _ = self.safe_captcha_check(page)
            if not valid: return False, None, "CHECK_FAILED"
            b = self._get_captcha_image(page, location)
            if not b: return False, None, "NO_IMAGE"
            code, status = self.solve(b, location)
            if not code: 
                 # Try manual if auto fails
                 if not self.auto_only:
                     code = self.manual_handler.request_manual_solution(b, location, session_age, attempt, max_attempts)
                     status = "MANUAL" if code else status
            if code:
                try: 
                    # Fill using first available input
                    for s in self._get_captcha_selectors():
                        if page.locator(s).count()>0: page.fill(s, code); return True, code, status
                except: pass
            return False, None, status
        except: return False, None, "ERROR"

    def reload_captcha(self, page: Page, location: str = "RELOAD") -> bool:
        try:
            page.evaluate("document.getElementById('appointment_newAppointmentForm_form_newappointment_refreshcaptcha').click()")
            time.sleep(1.0)
            return True
        except: return False
    
    def submit_captcha(self, page: Page, method: str = "enter") -> bool:
        try: page.keyboard.press("Enter"); return True
        except: return False

class CaptchaSolver:
    def __init__(self):
        self.ocr = ddddocr.DdddOcr(beta=True) if DDDDOCR_AVAILABLE else None
    def solve(self, b): return self.ocr.classification(b).strip() if self.ocr else ""
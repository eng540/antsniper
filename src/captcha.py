"""
Elite Sniper v3.1 - Production Grade Captcha System
Refactored for 100% Local OCR (ddddocr) & State-Aware Synchronization
[HOTFIX] Applied non-destructive OpenCV preprocessing 
[HOTFIX] Patient Sniper Protocol (Extended Wait for Booking Captcha)
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
    """
    Handle manual captcha solving via Telegram.
    Sends captcha image to user and waits for reply.
    """
    
    def __init__(self):
        self.enabled = Config.MANUAL_CAPTCHA_ENABLED and NOTIFIER_AVAILABLE
        self.timeout = Config.MANUAL_CAPTCHA_TIMEOUT
        self._attempt_count = 0
        
        if self.enabled:
            logger.info("[MANUAL] Telegram captcha handler enabled")
        else:
            logger.info("[MANUAL] Telegram captcha handler disabled")
    
    def request_manual_solution(
        self, 
        image_bytes: bytes, 
        location: str = "CAPTCHA",
        session_age: int = 0,
        attempt: int = 1,
        max_attempts: int = 5
    ) -> Optional[str]:
        if not self.enabled:
            logger.warning("[MANUAL] Telegram captcha disabled")
            return None
        
        self._attempt_count += 1
        
        caption = (
            f"🔐 CAPTCHA REQUIRED\n\n"
            f"📍 Location: {location}\n"
            f"⏱️ Session Age: {session_age}s\n"
            f"🔄 Attempt: {attempt}/{max_attempts}\n\n"
            f"Reply with the 6 characters you see.\n"
            f"Timeout: {self.timeout} seconds"
        )
        
        logger.info(f"[MANUAL] Sending captcha to Telegram for manual solving...")
        
        success = False
        if hasattr(self, 'c2') and self.c2:
            try:
                result = notifier.send_photo_bytes(image_bytes, caption)
                success = result.get("success")
            except:
                pass
        else:
             result = notifier.send_photo_bytes(image_bytes, caption)
             success = result.get("success")
        
        if not success:
            logger.error("[MANUAL] Failed to send captcha to Telegram")
            return None
        
        logger.info(f"[MANUAL] Waiting for reply (timeout: {self.timeout}s)...")
        
        if hasattr(self, 'c2') and self.c2:
            return self.c2.wait_for_captcha(timeout=self.timeout)
            
        logger.warning("⚠️ C2 not active - falling back to direct polling (may conflict)")
        return notifier.wait_for_captcha_reply(timeout=self.timeout)

    def notify_result(self, success: bool, location: str = ""):
        if not self.enabled:
            return
        
        if success:
            notifier.send_alert(f"🎯 CAPTCHA SUCCESS! Moving to {location}...")
        else:
            notifier.send_alert(f"❌ CAPTCHA WRONG - sending new image...")


class EnhancedCaptchaSolver:
    """
    Enhanced captcha solver with:
    - 100% Local OCR Execution (No External APIs, No Threading)
    - Safe checking without failures
    - Black captcha detection
    - Strict length validation for Turbo Booking
    - [HOTFIX] Non-destructive OpenCV filtering to fix TOO_SHORT errors
    - [HOTFIX] Extended Base64 DOM polling & Patient Sniper Protocol
    """
    
    def __init__(self, mode: str = "HYBRID", c2_instance=None):
        self.mode = mode.upper()
        self.manual_only = (self.mode == "MANUAL")
        self.auto_only = (self.mode == "AUTO")
        self.c2 = c2_instance
        
        self.ocr = None
        self._pre_solved_code: Optional[str] = None
        self._pre_solved_time: float = 0.0
        self._pre_solve_timeout: float = 30.0
        
        self.manual_handler = TelegramCaptchaHandler()
        if self.c2:
            self.manual_handler.c2 = self.c2
        
        if self.mode == "MANUAL":
             logger.info("[CAPTCHA] Initialized in MANUAL MODE (OCR Disabled)")
        elif self.mode == "AUTO":
             logger.info("[CAPTCHA] Initialized in AUTO MODE (Manual Fallback Disabled)")
        else:
             logger.info("[CAPTCHA] Initialized in HYBRID MODE (Balanced)")
        
        if DDDDOCR_AVAILABLE and not self.manual_only:
            try:
                self.ocr = ddddocr.DdddOcr(beta=True)
                logger.info("Captcha solver initialized (BETA Mode - High Accuracy)")
            except Exception as e:
                logger.error(f"Captcha solver init failed: {e}")
                self.ocr = None
        elif not DDDDOCR_AVAILABLE and not self.manual_only:
            logger.warning("ddddocr not available - captcha solving disabled")
    
    def safe_captcha_check(self, page: Page, location: str = "GENERAL") -> Tuple[bool, bool]:
        try:
            page_content = page.content().lower()
            captcha_keywords = [
                "captcha", 
                "security code", 
                "verification", 
                "human check",
                "verkaptxt"
            ]
            
            has_captcha_text = any(keyword in page_content for keyword in captcha_keywords)
            
            if not has_captcha_text:
                logger.debug(f"[{location}] No captcha keywords found")
                return False, True
            
            captcha_selectors = self._get_captcha_selectors()
            for selector in captcha_selectors:
                try:
                    if page.locator(selector).first.is_visible(timeout=3000):
                        logger.info(f"[{location}] Captcha found: {selector}")
                        return True, True
                except:
                    continue
            
            logger.warning(f"[{location}] Captcha text found but NO INPUT VISIBLE")
            return False, True
            
        except Exception as e:
            logger.error(f"[{location}] Captcha check error: {e}")
            return False, False
    
    def _get_captcha_selectors(self) -> List[str]:
        return [
            "input[name='captchaText']",
            "input[name='captcha']",
            "input#captchaText",
            "input#captcha",
            "input[type='text'][placeholder*='code']",
            "input[type='text'][placeholder*='Code']",
            "#appointment_captcha_month input[type='text']",
            "input.verkaptxt",
            "input.captcha-input",
            "input[id*='captcha']",
            "input[name*='captcha']",
            "form[id*='captcha'] input[type='text']"
        ]
    
    def _get_captcha_image_selectors(self) -> List[str]:
        return [
            "captcha > div",
            "div.captcha-image",
            "div#captcha",
            "img[alt*='captcha']",
            "img[alt*='CAPTCHA']",
            "canvas.captcha"
        ]
    
    def _extract_base64_captcha(self, page: Page, location: str = "EXTRACT") -> Optional[bytes]:
        try:
            try:
                page.wait_for_selector("captcha > div", timeout=5000)
            except:
                logger.debug(f"[{location}] Captcha div did not appear in DOM within timeout.")
                return None
                
            captcha_div = page.locator("captcha > div").first
            
            max_attempts = 20
            for attempt in range(max_attempts):
                style = captcha_div.get_attribute("style")
                
                if not style or "base64" not in style:
                    time.sleep(0.2)
                    continue
                
                pattern = r"url\(['\"]?data:image/[^;]+;base64,([A-Za-z0-9+/=]+)['\"]?\)"
                match = re.search(pattern, style)
                
                if not match:
                    time.sleep(0.2)
                    continue
                
                base64_data = match.group(1)
                
                padding_needed = len(base64_data) % 4
                if padding_needed:
                    base64_data += '=' * (4 - padding_needed)
                
                try:
                    image_bytes = base64.b64decode(base64_data)
                except Exception as decode_err:
                    logger.warning(f"[{location}] Base64 decode failed: {decode_err}")
                    time.sleep(0.2)
                    continue
                
                if len(image_bytes) < 2000:
                    time.sleep(0.2)
                    continue
                
                logger.info(f"[{location}] ✅ Extracted captcha from base64 ({len(image_bytes)} bytes)")
                return image_bytes
            
            logger.warning(f"[{location}] ⚠️ Polling timeout - base64 string never fully loaded")
            return None
            
        except Exception as e:
            logger.warning(f"[{location}] Base64 extraction failed: {e}")
            return None
    
    def _get_captcha_image(self, page: Page, location: str = "GET_IMG") -> Optional[bytes]:
        image_bytes = self._extract_base64_captcha(page, location)
        if image_bytes:
            return image_bytes
        
        for img_selector in self._get_captcha_image_selectors():
            try:
                element = page.locator(img_selector).first
                if element.is_visible(timeout=1000):
                    image_bytes = element.screenshot(timeout=5000)
                    logger.info(f"[{location}] Got captcha via screenshot: {img_selector}")
                    return image_bytes
            except:
                continue
        
        logger.warning(f"[{location}] Could not get captcha image by any method")
        return None
    
    def detect_black_captcha(self, image_bytes: bytes) -> bool:
        if len(image_bytes) < 2000:
            logger.critical(f"⛔ [BLACK CAPTCHA] Detected! Size: {len(image_bytes)} bytes - Session POISONED!")
            return True
        return False
    
    def validate_captcha_result(self, code: str, location: str = "VALIDATE") -> Tuple[bool, str]:
        if not code:
            return False, "EMPTY"
        
        code = code.strip().replace(" ", "")
        code_len = len(code)
        
        black_patterns = ["4333", "333", "444", "1111", "0000", "4444", "3333"]
        is_all_same = len(set(code)) == 1
        if code in black_patterns or is_all_same:
            logger.critical(f"[{location}] BLACK CAPTCHA pattern detected: '{code}'")
            return False, "BLACK_DETECTED"
        
        if code_len < 4:
            return False, "TOO_SHORT"
        
        if code_len == 6:
            return True, "VALID"
        
        if code_len == 7:
            return True, "AGING_7"
        
        if code_len == 8:
            return True, "AGING_8"
        
        if code_len > 8:
            return False, "TOO_LONG"
        
        if code_len in [4, 5]:
            return False, "TOO_SHORT"
            
        return False, "INVALID"

    def _preprocess_image(self, image_bytes: bytes) -> bytes:
        if not OPENCV_AVAILABLE:
            return image_bytes

        try:
            nparr = np.frombuffer(image_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            img = cv2.resize(img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
            
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
            enhanced = clahe.apply(gray)
            
            _, encoded_img = cv2.imencode('.png', enhanced)
            return encoded_img.tobytes()
            
        except Exception as e:
            logger.debug(f"Image preprocessing failed: {e}")
            return image_bytes

    def _clean_ocr_result(self, text: str) -> str:
        if not text:
            return ""
        text = text.strip().replace(" ", "")
        allowed_chars = set('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789')
        cleaned = ''.join(c for c in text if c in allowed_chars)
        return cleaned

    def solve(self, image_bytes: bytes, location: str = "SOLVE") -> Tuple[str, str]:
        if self.manual_only:
             logger.info(f"[{location}] Manual Mode active - Skipping OCR")
             return "", "MANUAL_REQUIRED"

        if not self.ocr:
            logger.error("[OCR] Engine not initialized")
            return "", "NO_OCR"
        
        try:
            if self.detect_black_captcha(image_bytes):
                return "", "BLACK_IMAGE"
            
            enhanced_bytes = self._preprocess_image(image_bytes)
            
            logger.info(f"[{location}] 🧠 توجيه الصورة لمحرك ddddocr المحلي...")
            result = self.ocr.classification(enhanced_bytes)
            result = result.replace(" ", "").strip().lower()
            result = self._clean_ocr_result(result)
            
            is_valid, status = self.validate_captcha_result(result, location)
            
            if is_valid or status in ["AGING_7", "AGING_8"]:
                logger.info(f"[{location}] Local OCR solved: '{result}' - Status: {status}")
                return result, status
                        
            logger.warning(f"[{location}] Local OCR failed: '{result}' - Status: {status}")
            return "", status

        except Exception as e:
            logger.error(f"[{location}] Captcha solve error: {e}")
            return "", "ERROR"
            
    def pre_solve(self, page: Page, location: str = "PRE_SOLVE") -> Tuple[bool, Optional[str], str]:
        try:
            has_captcha, check_ok = self.safe_captcha_check(page, location)
            
            if not check_ok:
                return False, None, "CHECK_FAILED"
            
            if not has_captcha:
                return True, None, "NO_CAPTCHA"
            
            image_bytes = self._get_captcha_image(page, location)
            
            if not image_bytes:
                return False, None, "NO_IMAGE"
            
            code, status = self.solve(image_bytes, location)
            
            if not code:
                return False, None, status
            
            self._pre_solved_code = code
            self._pre_solved_time = time.time()
            self._pre_solved_status = status
            
            logger.info(f"[{location}] Pre-solved captcha: '{code}' - Status: {status}")
            return True, code, status
            
        except Exception as e:
            logger.error(f"[{location}] Pre-solve error: {e}")
            return False, None, "ERROR"
    
    def get_pre_solved(self) -> Optional[str]:
        if not self._pre_solved_code:
            return None
        
        age = time.time() - self._pre_solved_time
        if age > self._pre_solve_timeout:
            logger.warning("Pre-solved captcha expired")
            self._pre_solved_code = None
            return None
        
        return self._pre_solved_code
    
    def clear_pre_solved(self):
        self._pre_solved_code = None
        self._pre_solved_time = 0.0
    
    def solve_from_page(
        self, 
        page: Page, 
        location: str = "GENERAL",
        timeout: int = 10000,
        session_age: int = 0,
        attempt: int = 1,
        max_attempts: int = 5
    ) -> Tuple[bool, Optional[str], str]:
        try:
            has_captcha, check_ok = self.safe_captcha_check(page, location)
            
            if not check_ok:
                return False, None, "CHECK_FAILED"
            
            if not has_captcha:
                return True, None, "NO_CAPTCHA"
            
            input_selector = None
            for selector in self._get_captcha_selectors():
                try:
                    if page.locator(selector).first.is_visible(timeout=1000):
                        input_selector = selector
                        break
                except:
                    continue
            
            if not input_selector:
                return False, None, "NO_INPUT"
            
            code = self.get_pre_solved()
            status = getattr(self, '_pre_solved_status', 'VALID')
            
            if code:
                logger.info(f"[{location}] Using pre-solved captcha: '{code}'")
                self.clear_pre_solved()
            else:
                internal_max_retries = 3
                for internal_attempt in range(internal_max_retries):
                    
                    image_bytes = self._get_captcha_image(page, location)
                    
                    if not image_bytes:
                        return False, None, "NO_IMAGE"
                    
                    code, status = self.solve(image_bytes, location)
                    
                    if self.auto_only:
                        if status == "TOO_SHORT":
                            logger.warning(f"[{location}] Result TOO_SHORT in AUTO mode - RELOADING ({internal_attempt+1}/{internal_max_retries})...")
                            if internal_attempt < internal_max_retries - 1:
                                self.reload_captcha(page, f"{location}_RELOAD_{internal_attempt}")
                                continue
                            else:
                                logger.warning(f"[{location}] Max internal retries reached for TOO_SHORT")
                        
                        if not code or status in ["TOO_SHORT", "TOO_LONG", "NO_OCR", "MANUAL_REQUIRED"]:
                            return False, None, f"AUTO_SKIP_{status}"
                        break
                    
                    if not code or status in ["TOO_SHORT", "TOO_LONG", "NO_OCR", "MANUAL_REQUIRED"]:
                        logger.info(f"[{location}] OCR failed ({status}), trying manual Telegram...")
                    
                    manual_code = self.manual_handler.request_manual_solution(
                        image_bytes=image_bytes,
                        location=location,
                        session_age=session_age,
                        attempt=attempt,
                        max_attempts=max_attempts
                    )
                    
                    if manual_code:
                        code = manual_code
                        status = "MANUAL"
                        logger.info(f"[{location}] Using manual solution: '{code}'")
                        break
                    else:
                        return False, None, "MANUAL_TIMEOUT"
            
            try:
                page.fill(input_selector, code, timeout=3000, force=True)
                logger.info(f"[{location}] Captcha filled: '{code}' - Status: {status}")
                return True, code, status
            except Exception as e:
                logger.error(f"[{location}] Failed to fill captcha: {e}")
                return False, None, "FILL_ERROR"
            
        except Exception as e:
            logger.error(f"[{location}] Captcha solving workflow error: {e}")
            return False, None, "ERROR"
    
    def submit_captcha(self, page: Page, method: str = "enter") -> bool:
        try:
            page.keyboard.press("Enter")
            time.sleep(0.3)
            return True
        except Exception as e:
            logger.error(f"[CAPTCHA] Submit error: {e}")
            return False
    
    def verify_captcha_solved(self, page: Page, location: str = "VERIFY") -> Tuple[bool, str]:
        start_time = time.time()
        timeout = 10.0 if getattr(self, 'manual_only', False) else 5.0
        
        while time.time() - start_time < timeout:
            try:
                current_url = page.url
                try:
                    content = page.content().lower()
                except Exception:
                    time.sleep(0.5)
                    continue

                if "appointment_showday" in current_url.lower() or page.locator("a.arrow").count() > 0:
                     return True, "DAY_PAGE"
                
                if "appointment_showform" in current_url.lower():
                    return True, "FORM_PAGE"

                if "security code" in content and ("valid" in content or "match" in content or "nicht korrekt" in content):
                     return False, "WRONG_CAPTCHA"

            except Exception as e:
                pass
            
            time.sleep(0.5)
            
        has_captcha, _ = self.safe_captcha_check(page, location)
        if has_captcha:
             return False, "CAPTCHA_STILL_PRESENT"
             
        return True, "UNKNOWN_PAGE"

    def reload_captcha(self, page: Page, location: str = "RELOAD") -> bool:
        try:
            reload_selectors = [
                "#appointment_newAppointmentForm_form_newappointment_refreshcaptcha",
                "input[name='action:appointment_refreshCaptcha']",
                "input[name*='refreshCaptcha']",
                "#appointment_captcha_month_refreshcaptcha",
                "input[name='action:appointment_refreshCaptchamonth']",
                "input[value='Load another picture']",
                "input[value='Bild laden']"
            ]
            
            for selector in reload_selectors:
                try:
                    button = page.locator(selector).first
                    if button.is_visible(timeout=3000):
                        try:
                            button.click(timeout=2000)
                        except:
                            page.evaluate(f'document.querySelector("{selector}")?.click()')
                        
                        logger.info(f"[{location}] Clicked reload button - waiting for new captcha...")
                        page.wait_for_timeout(1500)
                        return True
                except:
                    continue
            
            try:
                result = page.evaluate("""
                    const buttons = Array.from(document.querySelectorAll('input[type="submit"], button'));
                    for(const btn of buttons) {
                        const val = (btn.value || btn.textContent || '').toLowerCase();
                        if(val.includes('another') || val.includes('refresh') || val.includes('reload') || val.includes('anderes')) {
                            btn.click();
                            return true;
                        }
                    }
                    return false;
                """)
                if result:
                    logger.info(f"[{location}] Clicked reload via JS fallback")
                    page.wait_for_timeout(1500)
                    return True
            except:
                pass
            
            return False
            
        except Exception as e:
            logger.error(f"[{location}] Reload captcha error: {e}")
            return False
    
    def solve_form_captcha_with_retry(
        self, 
        page: Page, 
        location: str = "FORM_RETRY",
        max_attempts: int = 5,
        session_age: int = 0
    ) -> Tuple[bool, Optional[str], str]:
        if self.manual_only:
            max_attempts = 1000
            
        for attempt in range(max_attempts):
            attempt_num = attempt + 1
            
            success, code, status = self.solve_from_page(
                page, 
                f"{location}_A{attempt_num}",
                session_age=session_age,
                attempt=attempt_num,
                max_attempts=1
            )
            
            if success and code:
                return True, code, status
            
            if attempt < max_attempts - 1:
                if session_age > 1800:
                     return False, None, "SESSION_TOO_OLD"

                if not self.reload_captcha(page, f"{location}_RELOAD"):
                    return False, None, "RELOAD_FAILED"
                
                time.sleep(1.0)
        
        return False, None, "MAX_ATTEMPTS_REACHED"

    def get_valid_captcha_turbo(self, page: Page, location: str = "BOOKING_TURBO") -> Optional[str]:
        """
        [FACT-BASED FIX: Patient Sniper Protocol]
        ينتظر بذكاء حتى يتم تحميل الـ Base64 في الـ DOM ولا يستسلم بعد ثانية واحدة.
        """
        max_retries = 25
        REFRESH_ID = "appointment_newAppointmentForm_form_newappointment_refreshcaptcha"
        
        try:
            page.wait_for_selector("captcha > div", timeout=10000)
        except Exception as e:
            logger.error(f"[{location}] Captcha element did not render in DOM: {e}")
            return None

        for attempt in range(max_retries):
            try:
                element = page.query_selector("captcha > div")
                if not element:
                    time.sleep(0.2)
                    continue

                style = element.get_attribute("style")
                if not style or "base64" not in style:
                    time.sleep(0.3) 
                    continue
                
                match = re.search(r'base64,([^"]+)', style)
                if not match:
                    time.sleep(0.2)
                    continue
                    
                base64_data = match.group(1)
                padding_needed = len(base64_data) % 4
                if padding_needed:
                    base64_data += '=' * (4 - padding_needed)

                try:
                    image_bytes = base64.b64decode(base64_data)
                except Exception as decode_error:
                    logger.warning(f"[{location}] Base64 decode error - retrying...")
                    time.sleep(0.2)
                    continue
                
                enhanced_bytes = self._preprocess_image(image_bytes)
                result = self.ocr.classification(enhanced_bytes)
                result = self._clean_ocr_result(result)
                
                if len(result) != 6:
                    logger.warning(f"[{location}] Invalid Length ({len(result)}) -> '{result}'. REFRESHING.")
                    page.evaluate(f"document.getElementById('{REFRESH_ID}').click()")
                    time.sleep(1.0) 
                    continue
                
                logger.critical(f"[{location}] ✅ Valid OCR (6) -> '{result}'. Returning to Commander.")
                return result
                
            except Exception as e:
                logger.error(f"[{location}] Error in turbo loop: {e}")
                time.sleep(0.3)
                continue
        
        return None


class CaptchaSolver:
    """Original captcha solver for backward compatibility"""
    
    def __init__(self):
        if DDDDOCR_AVAILABLE:
            self.ocr = ddddocr.DdddOcr(beta=True)
        else:
            self.ocr = None
    
    def solve(self, image_bytes: bytes) -> str:
        if not self.ocr:
            return ""
        try:
            res = self.ocr.classification(image_bytes)
            res = res.replace(" ", "").strip()
            return res
        except Exception as e:
            return ""
#END
"""
Forensic Diagnostic System for EliteSniperV2
Captures screenshots, HTML dumps, and provides comprehensive monitoring
Author: EliteSniperV2 Team
"""

import os
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from playwright.sync_api import Page

logger = logging.getLogger("EliteSniperV2.Diagnostic")


class ForensicMonitor:
    """
    Comprehensive forensic monitoring system
    Captures screenshots, HTML dumps, and tracks all operations
    """
    
    def __init__(self, base_dir: str = "debug", enabled: bool = True):
        """
        Initialize forensic monitor
        
        Args:
            base_dir: Base directory for all diagnostic files
            enabled: Enable/disable monitoring (for performance)
        """
        self.enabled = enabled
        if not self.enabled:
            logger.info("🔕 Forensic monitoring DISABLED")
            return
        
        self.base_dir = Path(base_dir)
        self.screenshot_dir = self.base_dir / "screenshots"
        self.html_dir = self.base_dir / "html"
        
        # Create directories
        for directory in [self.screenshot_dir, self.html_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        self.operation_counter = 0
        logger.info(f"🔍 Forensic monitoring ENABLED → {self.base_dir}")
    
    def capture(
        self, 
        page: Page, 
        operation: str, 
        category: str = "general",
        save_screenshot: bool = True,
        save_html: bool = True
    ) -> Dict[str, Any]:
        """
        Capture complete diagnostic snapshot
        
        Args:
            page: Playwright page object
            operation: Operation description
            category: Category (captcha, navigation, error, success)
            save_screenshot: Whether to save screenshot
            save_html: Whether to save HTML dump
            
        Returns:
            dict with paths to captured files and metadata
        """
        if not self.enabled:
            return {}
        
        self.operation_counter += 1
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        operation_id = f"{timestamp}_{self.operation_counter:04d}"
        
        result = {
            "operation_id": operation_id,
            "operation": operation,
            "category": category,
            "timestamp": timestamp,
            "screenshot": None,
            "html": None
        }
        
        # 1. Screenshot capture
        if save_screenshot:
            screenshot_path = self.screenshot_dir / f"{category}_{operation_id}.png"
            try:
                page.screenshot(path=str(screenshot_path), full_page=True)
                result["screenshot"] = str(screenshot_path)
                logger.info(f"📸 [{operation_id}] Screenshot: {screenshot_path.name}")
            except Exception as e:
                logger.warning(f"⚠️ Screenshot failed: {e}")
        
        # 2. HTML dump
        if save_html:
            html_path = self.html_dir / f"{category}_{operation_id}.html"
            try:
                html_content = page.content()
                html_path.write_text(html_content, encoding='utf-8')
                result["html"] = str(html_path)
                logger.debug(f"📄 HTML dump: {html_path.name}")
            except Exception as e:
                logger.warning(f"⚠️ HTML dump failed: {e}")
        
        # 3. Log entry
        logger.info(f"🔍 [{operation_id}] {category.upper()}: {operation}")
        
        return result
    
    def quick_capture(self, page: Page, operation: str, category: str = "general") -> Dict[str, Any]:
        """
        Quick capture - screenshot only (no HTML for performance)
        """
        return self.capture(page, operation, category, save_screenshot=True, save_html=False)
    
    def error_capture(self, page: Page, error_msg: str) -> Dict[str, Any]:
        """
        Capture error state with full diagnostic info
        """
        return self.capture(page, f"ERROR: {error_msg}", category="error", save_screenshot=True, save_html=True)
    
    def success_capture(self, page: Page, success_msg: str) -> Dict[str, Any]:
        """
        Capture success state
        """
        return self.capture(page, f"SUCCESS: {success_msg}", category="success", save_screenshot=True, save_html=False)


class OperationTracker:
    """
    Track operations with timing, steps, and context
    Provides structured logging for complex workflows
    """
    
    def __init__(self):
        """Initialize operation tracker"""
        self.operations = []
        self.current_operation = None
    
    def start(self, operation: str, context: Dict[str, Any] = None) -> str:
        """
        Start tracking an operation
        
        Args:
            operation: Operation name/description
            context: Additional context data
            
        Returns:
            operation_id: Unique ID for this operation
        """
        op_id = f"{int(time.time() * 1000)}"
        self.current_operation = {
            "id": op_id,
            "name": operation,
            "start_time": time.time(),
            "context": context or {},
            "steps": [],
            "end_time": None,
            "success": None,
            "result": None
        }
        
        context_str = f" ({context})" if context else ""
        logger.info(f"▶️  START [{op_id}]: {operation}{context_str}")
        return op_id
    
    def step(self, step_name: str, data: Dict[str, Any] = None):
        """
        Log a step in current operation
        
        Args:
            step_name: Step description
            data: Additional step data
        """
        if not self.current_operation:
            logger.warning("⚠️ No active operation to add step to")
            return
        
        step_entry = {
            "name": step_name,
            "time": time.time(),
            "data": data or {}
        }
        self.current_operation["steps"].append(step_entry)
        
        data_str = f" → {data}" if data else ""
        logger.info(f"  ├─ {step_name}{data_str}")
    
    def end(self, success: bool = True, result: Any = None):
        """
        End current operation
        
        Args:
            success: Whether operation succeeded
            result: Operation result/output
        """
        if not self.current_operation:
            logger.warning("⚠️ No active operation to end")
            return
        
        self.current_operation["end_time"] = time.time()
        self.current_operation["success"] = success
        self.current_operation["result"] = result
        
        duration = self.current_operation["end_time"] - self.current_operation["start_time"]
        status = "✅ SUCCESS" if success else "❌ FAILED"
        
        logger.info(f"◀️  END [{self.current_operation['id']}]: {status} ({duration:.2f}s)")
        
        if result:
            logger.info(f"  └─ Result: {result}")
        
        # Archive operation
        self.operations.append(self.current_operation)
        self.current_operation = None
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about all tracked operations
        
        Returns:
            dict with stats (total, successful, failed, avg duration)
        """
        total = len(self.operations)
        successful = sum(1 for op in self.operations if op.get("success"))
        failed = total - successful
        
        durations = [
            op["end_time"] - op["start_time"] 
            for op in self.operations 
            if op.get("end_time")
        ]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        return {
            "total_operations": total,
            "successful": successful,
            "failed": failed,
            "success_rate": successful / total if total > 0 else 0,
            "avg_duration": avg_duration
        }


class TelegramReporter:
    """
    Enhanced Telegram reporting with screenshots and detailed status
    Sends real-time updates via Telegram
    """
    
    def __init__(self, enabled: bool = True):
        """
        Initialize Telegram reporter
        
        Args:
            enabled: Enable/disable Telegram reporting
        """
        self.enabled = enabled
        
        # Import notifier functions
        try:
            from .notifier import send_alert, send_photo, send_status_update
            self.send_alert = send_alert
            self.send_photo = send_photo
            self.send_status_update = send_status_update
        except ImportError:
            try:
                from notifier import send_alert, send_photo, send_status_update
                self.send_alert = send_alert
                self.send_photo = send_photo
                self.send_status_update = send_status_update
            except ImportError:
                logger.warning("⚠️ Notifier module not available - Telegram disabled")
                self.enabled = False
        
        if not self.enabled:
            logger.info("📱 Telegram reporting DISABLED")
        else:
            logger.info("📱 Telegram reporting ENABLED")
    
    def send_message(self, message: str):
        """Send simple text message"""
        if not self.enabled:
            return
        
        try:
            self.send_alert(message)
            logger.debug(f"📱 Telegram sent: {message[:50]}...")
        except Exception as e:
            logger.warning(f"⚠️ Telegram send failed: {e}")
    
    def send_with_image(self, message: str, image_path: str):
        """Send message with attached image"""
        if not self.enabled:
            return
        
        try:
            # Use send_photo which accepts image path and caption
            self.send_photo(image_path, caption=message)
            logger.debug(f"📱 Telegram sent with photo: {message[:50]}...")
        except Exception as e:
            logger.warning(f"⚠️ Telegram image send failed: {e}")
    
    def report_captcha_attempt(self, code: str, screenshot_path: Optional[str], success: bool):
        """Report captcha attempt with screenshot"""
        status = "✅ Accepted" if success else "❌ Rejected"
        message = f"""🔐 Captcha Attempt
Code: {code}
Status: {status}
Time: {datetime.now().strftime('%H:%M:%S')}"""
        
        if screenshot_path and os.path.exists(screenshot_path):
            self.send_with_image(message, screenshot_path)
        else:
            self.send_message(message)
    
    def report_error(self, error_type: str, screenshot_path: Optional[str] = None):
        """Report error with context"""
        message = f"""⚠️ ERROR DETECTED
Type: {error_type}
Time: {datetime.now().strftime('%H:%M:%S')}"""
        
        if screenshot_path and os.path.exists(screenshot_path):
            self.send_with_image(message, screenshot_path)
        else:
            self.send_message(message)
    
    def report_slot_found(self, screenshot_path: Optional[str] = None):
        """Report slot discovery - HIGH PRIORITY"""
        message = f"""🎯 SLOT FOUND! 🎯
Time: {datetime.now().strftime('%H:%M:%S')}
Action: Proceeding with booking..."""
        
        if screenshot_path and os.path.exists(screenshot_path):
            self.send_with_image(message, screenshot_path)
        else:
            self.send_message(message)
    
    def report_session_start(self):
        """Report session start"""
        message = f"""🚀 Session Started
Time: {datetime.now().strftime('%H:%M:%S')}
Mode: Persistent Settlement"""
        self.send_message(message)
    
    def report_session_stats(self, stats: Dict[str, Any]):
        """Report session statistics"""
        message = f"""📊 Session Statistics
Total Operations: {stats.get('total_operations', 0)}
Successful: {stats.get('successful', 0)}
Failed: {stats.get('failed', 0)}
Success Rate: {stats.get('success_rate', 0):.1%}
Avg Duration: {stats.get('avg_duration', 0):.2f}s"""
        self.send_message(message)

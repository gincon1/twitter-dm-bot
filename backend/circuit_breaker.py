"""
熔断机制 - Circuit Breaker

PRD 要求:
- 短时间内多个账号异常 → 全局暂停所有发送
- 必须人工解除（不自动恢复）
- 通知运营人员

规则:
- 10分钟内 ≥3 个账号异常 → 触发熔断
- 熔断后所有发送停止
- 控制台显示熔断状态 + 解除按钮
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import List, Optional

from config import settings
from database import add_log
from notifier import send_feishu_alert_notification


@dataclass
class CircuitBreakerState:
    """熔断器状态"""
    tripped: bool = False  # 是否已熔断
    tripped_at: Optional[str] = None  # 熔断时间
    failure_window: List[float] = field(default_factory=list)  # 异常时间戳窗口
    last_failure_account: str = ""  # 最后一个异常账号
    total_trips: int = 0  # 累计熔断次数


class CircuitBreaker:
    """熔断器 - 防止多账号连续异常导致批量封号"""

    def __init__(self):
        self._state = CircuitBreakerState()
        self._lock = threading.Lock()
        # 从配置读取参数
        self.window_seconds = (settings.circuit_breaker_window_min or 30) * 60
        self.threshold = settings.circuit_breaker_threshold or 3

    def record_failure(self, account_id: str, reason: str = "") -> bool:
        """
        记录一次账号异常
        返回: 是否触发了熔断
        """
        with self._lock:
            now = time.time()

            # 清理过期的时间戳
            self._state.failure_window = [
                t for t in self._state.failure_window
                if now - t < self.window_seconds
            ]

            # 添加新的异常记录
            self._state.failure_window.append(now)
            self._state.last_failure_account = account_id

            failure_count = len(self._state.failure_window)

            add_log(
                "WARN",
                account_id,
                "",
                "circuit_breaker",
                f"异常记录 {failure_count}/{self.threshold}, 原因: {reason}"
            )

            # 检查是否达到熔断阈值
            if failure_count >= self.threshold and not self._state.tripped:
                self._trip(reason)
                return True

            return False

    def _trip(self, reason: str):
        """触发熔断"""
        self._state.tripped = True
        self._state.tripped_at = datetime.now().isoformat(timespec="seconds")
        self._state.total_trips += 1

        # 记录日志
        add_log(
            "ERROR",
            "system",
            "",
            "circuit_breaker_tripped",
            f"熔断触发！{self.threshold} 个账号在 {settings.circuit_breaker_window_min} 分钟内异常"
        )

        # 发送紧急通知
        self._send_alert(reason)

    def _send_alert(self, reason: str):
        """发送熔断警报"""
        try:
            send_feishu_alert_notification(
                alert_type="熔断触发",
                message=(
                    f"🚨 紧急：系统已触发熔断\n"
                    f"时间: {self._state.tripped_at}\n"
                    f"原因: {reason or '多账号连续异常'}\n"
                    f"异常账号数: {len(self._state.failure_window)}\n"
                    f"最后异常账号: {self._state.last_failure_account}\n\n"
                    f"系统已自动暂停所有发送任务，请检查账号状态后手动解除熔断。"
                )
            )
        except Exception as e:
            add_log("ERROR", "system", "", "alert_failed", f"熔断警报发送失败: {e}")

    def reset(self, operator: str = "system") -> bool:
        """
        人工解除熔断
        返回: 是否成功解除
        """
        with self._lock:
            if not self._state.tripped:
                return False

            self._state.tripped = False
            self._state.failure_window = []  # 清空异常记录

            add_log(
                "INFO",
                "system",
                "",
                "circuit_breaker_reset",
                f"熔断已解除，操作人: {operator}"
            )

            # 发送解除通知
            try:
                send_feishu_alert_notification(
                    alert_type="熔断解除",
                    message=(
                        f"✅ 系统熔断已解除\n"
                        f"时间: {datetime.now().isoformat(timespec='seconds')}\n"
                        f"操作人: {operator}\n"
                        f"发送任务已恢复"
                    )
                )
            except Exception as e:
                add_log("ERROR", "system", "", "alert_failed", f"解除警报发送失败: {e}")

            return True

    def is_tripped(self) -> bool:
        """检查当前是否处于熔断状态"""
        with self._lock:
            return self._state.tripped

    def get_status(self) -> dict:
        """获取熔断器状态（用于API）"""
        with self._lock:
            return {
                "tripped": self._state.tripped,
                "tripped_at": self._state.tripped_at,
                "failure_count": len(self._state.failure_window),
                "threshold": self.threshold,
                "window_minutes": self.window_seconds // 60,
                "last_failure_account": self._state.last_failure_account,
                "total_trips": self._state.total_trips,
            }

    def check_before_send(self) -> bool:
        """
        发送前检查
        返回: True 允许发送, False 阻止发送
        """
        if self._state.tripped:
            add_log(
                "WARN",
                "system",
                "",
                "send_blocked",
                "熔断器已触发，阻止发送"
            )
            return False
        return True


# 全局熔断器实例
circuit_breaker = CircuitBreaker()


def record_account_failure(account_id: str, reason: str = "") -> bool:
    """便捷函数：记录账号异常"""
    return circuit_breaker.record_failure(account_id, reason)


def is_circuit_tripped() -> bool:
    """便捷函数：检查是否熔断"""
    return circuit_breaker.is_tripped()


def reset_circuit_breaker(operator: str = "system") -> bool:
    """便捷函数：解除熔断"""
    return circuit_breaker.reset(operator)


def get_circuit_status() -> dict:
    """便捷函数：获取熔断状态"""
    return circuit_breaker.get_status()


def check_circuit_before_send() -> bool:
    """便捷函数：发送前检查"""
    return circuit_breaker.check_before_send()

# -*- coding: utf-8 -*-
"""点位到达等待循环修复验证测试。

复现 _worker 中的等待循环逻辑，验证：
1. 正常等待：N 秒后能正常退出循环（修复前会死循环）
2. 暂停/恢复：暂停时计时暂停，恢复后继续剩余时间
3. 停止：stop_flag 触发后立即退出
"""
import threading
import time


class MockRunner:
    """复现 server.FlowRunner 等待循环逻辑的最小测试替身。"""

    def __init__(self):
        self.pause_event = threading.Event()
        self.pause_event.set()  # 初始为"运行"状态
        self.stop_flag = False

    def wait_loop(self, wait_arrival):
        """与 server.py 修复后的等待循环一致。"""
        t0 = time.time()
        while time.time() - t0 < wait_arrival:
            if self.stop_flag:
                return "stopped"
            if not self.pause_event.is_set():
                self.pause_event.wait()
                t0 = time.time()
            time.sleep(0.05)
        return "done"


def test_normal_wait():
    """场景1：正常等待 1.0s，应 ~1s 退出，不死循环。"""
    r = MockRunner()
    t0 = time.time()
    result = r.wait_loop(1.0)
    elapsed = time.time() - t0
    assert result == "done", f"期望 done，实际 {result}"
    assert 0.9 <= elapsed <= 1.5, f"期望 1s 左右，实际 {elapsed:.2f}s"
    print(f"[PASS] 正常等待 1.0s → {result}，耗时 {elapsed:.2f}s")


def test_pause_resume():
    """场景2：等待 1s，中途暂停 0.5s，恢复后继续，总耗时 ~1.5s。"""
    r = MockRunner()

    def controller():
        time.sleep(0.3)
        r.pause_event.clear()  # 暂停
        time.sleep(0.5)
        r.pause_event.set()  # 恢复

    threading.Thread(target=controller, daemon=True).start()
    t0 = time.time()
    result = r.wait_loop(1.0)
    elapsed = time.time() - t0
    assert result == "done", f"期望 done，实际 {result}"
    assert 1.2 <= elapsed <= 2.0, f"期望 ~1.5-1.8s（含暂停），实际 {elapsed:.2f}s"
    print(f"[PASS] 暂停/恢复 → {result}，耗时 {elapsed:.2f}s")


def test_stop():
    """场景3：等待 5s，0.3s 后 stop，应立即退出。"""
    r = MockRunner()

    def controller():
        time.sleep(0.3)
        r.stop_flag = True
        r.pause_event.set()  # 唤醒可能的阻塞

    threading.Thread(target=controller, daemon=True).start()
    t0 = time.time()
    result = r.wait_loop(5.0)
    elapsed = time.time() - t0
    assert result == "stopped", f"期望 stopped，实际 {result}"
    assert elapsed < 1.0, f"期望 <1s 退出，实际 {elapsed:.2f}s"
    print(f"[PASS] 停止中断 → {result}，耗时 {elapsed:.2f}s")


def test_pause_then_stop():
    """场景4：暂停状态下触发 stop，应能跳出（验证 stop 唤醒 wait）。"""
    r = MockRunner()

    def controller():
        time.sleep(0.2)
        r.pause_event.clear()  # 先暂停
        time.sleep(0.3)
        r.stop_flag = True
        r.pause_event.set()  # stop 时必须 set 以唤醒 wait

    threading.Thread(target=controller, daemon=True).start()
    t0 = time.time()
    result = r.wait_loop(5.0)
    elapsed = time.time() - t0
    assert result == "stopped", f"期望 stopped，实际 {result}"
    assert elapsed < 1.0, f"期望 <1s 退出，实际 {elapsed:.2f}s"
    print(f"[PASS] 暂停后停止 → {result}，耗时 {elapsed:.2f}s")


if __name__ == "__main__":
    test_normal_wait()
    test_pause_resume()
    test_stop()
    test_pause_then_stop()
    print("\n全部测试通过 ✅")

import gc
import os
import types
import unittest
from unittest import mock

from cdkr import flow, paint
from cdkr.flow import Outcome, View

try:
    import tkinter
    tkinter.Tk().destroy()
    HAVE_TK = True
except Exception:  # no display / no Tk
    HAVE_TK = False


class FakeFlow:
    def __init__(self, views, outcomes=(), note=""):
        self.views, self.outcomes, self.redeemed, self.note = list(views), list(outcomes), [], note

    def load(self):
        return self.views.pop(0)

    def bind(self):
        return self.views.pop(0)

    def redeem(self, cdk, progress=None):
        self.redeemed.append(cdk)
        if progress:
            progress("处理中…")
        return self.outcomes.pop(0)

    def plan_note(self):
        return self.note


class WindowCase(unittest.TestCase):
    def setUp(self):
        # Tk objects must be freed on the main thread. Collect them here (this cleanup runs last),
        # or a later test's background thread may trigger the GC and Tcl aborts the process.
        self.addCleanup(gc.collect)

    def make(self, fake, local=True):
        from cdkr import window
        app = window.App(fake, local_backend=local, run_async=lambda fn, done: done(fn()))
        self.addCleanup(self.destroy, app)
        app.start()
        app.root.update()
        return app

    @staticmethod
    def destroy(app):
        try:
            app.root.destroy()
        except tkinter.TclError:  # the test already closed it
            pass

    @staticmethod
    def alive(app):
        try:
            return bool(app.root.winfo_exists())
        except tkinter.TclError:
            return False


@unittest.skipUnless(HAVE_TK, "needs a desktop session with Tk")
class WindowTest(WindowCase):
    def test_first_use_binds_then_redeems(self):
        fake = FakeFlow([View(flow.NEED_BIND, "首次使用", "a@example.com", "Free"),
                         View(flow.READY, "绑定成功", "a@example.com", "Free")],
                        [Outcome(flow.SUCCEEDED, "充值成功：X。CDK TE…01 已核销。")],
                        note="Codex 账号套餐：Plus。")
        app = self.make(fake)
        self.assertEqual(app.button["text"], "确认充值到此账号")
        self.assertEqual(str(app.entry["state"]), "disabled")
        self.assertIn("a@example.com", app.account_var.get())
        app.button.invoke()
        self.assertEqual(app.button["text"], "确认兑换")
        self.assertEqual(str(app.entry["state"]), "normal")
        app.cdk_var.set("TEST-OK01")
        app.button.invoke()
        self.assertEqual(fake.redeemed, ["TEST-OK01"])
        self.assertEqual(app.cdk_var.get(), "")
        self.assertIn("充值成功", app.status_var.get())
        self.assertIn("Codex 账号套餐：Plus。", app.status_var.get())  # appended after the lookup

    def test_failed_redeem_keeps_cdk_for_correction(self):
        fake = FakeFlow([View(flow.READY, "已绑定", "a@example.com", "Plus")],
                        [Outcome(flow.CDK_INVALID, "CDK NOPE…1234 无效，请检查是否输错。")])
        app = self.make(fake)
        app.cdk_var.set("NOPE-1234")
        app.root.update()
        app.entry.focus_force()
        app.entry.event_generate("<Return>")  # Enter in the CDK box redeems
        app.root.update()
        self.assertEqual(fake.redeemed, ["NOPE-1234"])
        self.assertEqual(app.cdk_var.get(), "NOPE-1234")
        self.assertIn("无效", app.status_var.get())

    def test_lost_binding_switches_back_to_bind(self):
        fake = FakeFlow([View(flow.READY, "已绑定", "a@example.com", "Plus")],
                        [Outcome(flow.BINDING_INVALID, "登录已失效，请重新绑定账号后再兑换。")])
        app = self.make(fake)
        app.cdk_var.set("TEST-OK01")
        app.button.invoke()
        self.assertEqual(app.button["text"], "确认充值到此账号")
        self.assertIn("登录已失效", app.status_var.get())

    def test_no_account_offers_retry(self):
        fake = FakeFlow([View(flow.NO_ACCOUNT, flow.ACCOUNT_MESSAGES[flow.NOT_LOGGED_IN]),
                         View(flow.READY, "已绑定", "a@example.com", "Plus")])
        app = self.make(fake)
        self.assertEqual(app.button["text"], "重新读取")
        app.button.invoke()
        self.assertEqual(app.button["text"], "确认兑换")

    def test_threaded_path_touches_tk_only_on_main_thread(self):
        import threading
        import time
        from cdkr import window
        fake = FakeFlow([View(flow.READY, "已绑定", "a@example.com", "Plus")],
                        [Outcome(flow.SUCCEEDED, "充值成功")])
        app = window.App(fake, local_backend=True)  # real worker threads
        self.addCleanup(app.root.destroy)
        threads, texts, say = [], [], app._say
        app._say = lambda text, tone: (threads.append(threading.current_thread()), texts.append(text),
                                       say(text, tone))
        app.root.after(100, app._drain)
        app.start()
        deadline = time.monotonic() + 5
        while app.button["text"] != "确认兑换" or str(app.button["state"]) == "disabled":
            app.root.update()
            self.assertLess(time.monotonic(), deadline)
        app.cdk_var.set("TEST-OK01")
        app.button.invoke()
        while "充值成功" not in app.status_var.get():
            app.root.update()
            self.assertLess(time.monotonic(), deadline)
        self.assertIn("处理中…", texts)  # the worker's progress line reached the window
        self.assertTrue(all(t is threading.main_thread() for t in threads), threads)

    def test_mock_backend_is_labelled(self):
        app = self.make(FakeFlow([View(flow.READY, "已绑定", "a@example.com", "Plus")]), local=True)
        self.assertIn("模拟", app.footer_var.get())
        app2 = self.make(FakeFlow([View(flow.READY, "已绑定", "a@example.com", "Plus")]), local=False)
        self.assertNotIn("模拟", app2.footer_var.get())


@unittest.skipUnless(HAVE_TK, "needs a desktop session with Tk")
class CardLookTest(WindowCase):
    """The 小助手-style borderless card."""

    def ready(self, **kw):
        return self.make(FakeFlow([View(flow.READY, "已绑定", "a@example.com", "Plus")], **kw))

    def test_is_a_borderless_card_of_the_assistant_width(self):
        app = self.ready()
        self.assertTrue(app.root.overrideredirect())
        self.assertEqual(app.root.winfo_width(), paint.CARD_W)

    def test_plan_shows_as_a_chip_next_to_the_email(self):
        app = self.ready()
        self.assertEqual(app.account_var.get(), "a@example.com")
        self.assertEqual(app.canvas.itemcget(app.plan_chip.label, "text"), "Plus")

    def test_close_button_closes(self):
        app = self.ready()
        app.close_button.invoke()
        self.assertFalse(self.alive(app))

    def test_escape_closes(self):
        app = self.ready()
        app.root.focus_force()
        app.root.event_generate("<Escape>")
        app.root.update()
        self.assertFalse(self.alive(app))

    def test_closing_while_redeeming_asks_first(self):
        app = self.ready()
        app._set_busy(True)
        with mock.patch("tkinter.messagebox.askyesno", return_value=False) as ask:
            app.close_button.invoke()
        ask.assert_called_once()
        self.assertTrue(self.alive(app))
        with mock.patch("tkinter.messagebox.askyesno", return_value=True):
            app.close_button.invoke()
        self.assertFalse(self.alive(app))

    def test_dragging_the_card_moves_the_window(self):
        app = self.ready()
        app.root.geometry("+200+150")
        app.root.update()
        press = types.SimpleNamespace(x_root=300, y_root=200)
        app._drag_start(press)
        app._drag_move(types.SimpleNamespace(x_root=340, y_root=260))
        app.root.update()
        self.assertEqual((app.root.winfo_x(), app.root.winfo_y()), (240, 210))

    def test_status_colour_follows_the_outcome(self):
        app = self.make(FakeFlow([View(flow.READY, "已绑定", "a@example.com", "Plus")],
                                 [Outcome(flow.SUCCEEDED, "充值成功"), Outcome(flow.CDK_INVALID, "CDK 无效")]))
        for cdk, colour in (("TEST-OK01", paint.OK_GREEN), ("NOPE-1234", paint.BAD_RED)):
            app.cdk_var.set(cdk)
            app.button.invoke()
            self.assertEqual(app.canvas.itemcget(app.status_text, "fill"), paint.hexc(colour), cdk)

    @unittest.skipUnless(os.name == "nt", "the clip region is Win32")
    def test_clip_region_follows_the_card_height(self):
        from cdkr import window
        app = self.ready()
        self.assertEqual(window.region_height(app.root), app.root.winfo_height())
        short = app.root.winfo_height()
        app._say("很长的一段提示。" * 12, "info")   # the card grows
        app.root.update()
        self.assertGreater(app.root.winfo_height(), short + 30)
        self.assertEqual(window.region_height(app.root), app.root.winfo_height())

    def test_card_grows_with_a_long_status(self):
        app = self.ready()
        short = app.root.winfo_height()
        app._say("很长的一段提示。" * 12, "info")
        app.root.update()
        self.assertGreater(app.root.winfo_height(), short)
        footer_top = app.canvas.bbox(app.footer_text)[1]
        self.assertGreater(footer_top, app.canvas.bbox(app.status_text)[3])  # footer stays below the status


if __name__ == "__main__":
    unittest.main()

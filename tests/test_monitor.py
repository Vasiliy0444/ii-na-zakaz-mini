"""Тесты мониторинга: python3 -m unittest discover -s tests -p 'test_*.py' (из корня репозитория)."""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import monitor as m  # noqa: E402

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
GOOD_PAGE = f"<html>fbq('init', '{m.PIXEL_ID}'); ym(12345678, 'init')</html>"
GOOD_JS = f"const BOT_USERNAME = '{m.BOT_USERNAME}';"


def rdap(ns: list[str], expires: datetime) -> str:
    return json.dumps({
        "nameservers": [{"ldhName": n} for n in ns],
        "events": [{"eventAction": "expiration", "eventDate": expires.strftime("%Y-%m-%dT%H:%M:%SZ")}],
    })


def make_fetch(routes: dict[str, object]):
    """routes: url → Response или исключение."""
    def fetch(url: str) -> m.Response:
        val = routes[url]
        if isinstance(val, Exception):
            raise val
        return val
    return fetch


def healthy_routes(**override) -> dict[str, object]:
    routes = {
        m.RDAP_URL: m.Response(200, rdap(["ns1.dns-parking.com", "ns2.dns-parking.com"], NOW + timedelta(days=300))),
        m.SITE: m.Response(200, GOOD_PAGE),
        m.SITE + "js/main.js": m.Response(200, GOOD_JS),
    }
    routes.update(override)
    return routes


def no_sleep(_: float) -> None:
    return None


class RegistryTest(unittest.TestCase):
    def test_healthy_domain_has_no_problems(self):
        self.assertEqual(m.check_registry(make_fetch(healthy_routes()), NOW), ([], True))

    def test_suspended_nameservers_are_down(self):
        routes = healthy_routes(**{m.RDAP_URL: m.Response(200, rdap(
            ["NS1.VERIFICATION-HOLD.DNS-SUSPENDED.COM", "NS2.VERIFICATION-HOLD.DNS-SUSPENDED.COM"],
            NOW + timedelta(days=300)))})
        problems, ok = m.check_registry(make_fetch(routes), NOW)
        self.assertTrue(ok)
        self.assertEqual([(p.key, p.level) for p in problems], [("domain_suspended", m.DOWN)])
        self.assertIn("подтверди почту", problems[0].text)

    def test_domain_expiring_soon_is_warning(self):
        routes = healthy_routes(**{m.RDAP_URL: m.Response(200, rdap(["ns1.dns-parking.com"], NOW + timedelta(days=10)))})
        problems, _ = m.check_registry(make_fetch(routes), NOW)
        self.assertEqual([(p.key, p.level) for p in problems], [("domain_expiring", m.WARN)])

    def test_rdap_outage_is_incomplete_not_an_alert(self):
        routes = healthy_routes(**{m.RDAP_URL: OSError("timeout"), m.DOH_NS_URL: OSError("timeout")})
        self.assertEqual(m.check_registry(make_fetch(routes), NOW), ([], False))

    def test_rdap_outage_falls_back_to_public_dns(self):
        doh = json.dumps({"Answer": [{"data": "ns1.verification-hold.dns-suspended.com."}]})
        routes = healthy_routes(**{m.RDAP_URL: m.Response(429, ""), m.DOH_NS_URL: m.Response(200, doh)})
        problems, ok = m.check_registry(make_fetch(routes), NOW)
        self.assertFalse(ok)
        self.assertEqual([p.key for p in problems], ["domain_suspended"])


class PageTest(unittest.TestCase):
    def test_healthy_page(self):
        self.assertEqual(m.check_page(make_fetch(healthy_routes()), "12345678", no_sleep), [])

    def test_connection_error_is_down(self):
        problems = m.check_page(make_fetch(healthy_routes(**{m.SITE: ConnectionResetError("reset")})), "", no_sleep)
        self.assertEqual([p.key for p in problems], ["site_down"])

    def test_http_500_is_down(self):
        problems = m.check_page(make_fetch(healthy_routes(**{m.SITE: m.Response(500, "")})), "", no_sleep)
        self.assertEqual([p.key for p in problems], ["site_down"])

    def test_retry_recovers_from_one_blip(self):
        calls = {"n": 0}
        base = make_fetch(healthy_routes())

        def flaky(url: str) -> m.Response:
            if url == m.SITE:
                calls["n"] += 1
                if calls["n"] == 1:
                    raise TimeoutError("blip")
            return base(url)

        self.assertEqual(m.check_page(flaky, "", no_sleep), [])

    def test_missing_pixel_is_down(self):
        problems = m.check_page(make_fetch(healthy_routes(**{m.SITE: m.Response(200, "<html></html>")})), "", no_sleep)
        self.assertEqual([(p.key, p.level) for p in problems], [("pixel_missing", m.DOWN)])

    def test_missing_metrika_only_checked_when_id_set(self):
        page = m.Response(200, f"fbq('init', '{m.PIXEL_ID}')")
        fetch = make_fetch(healthy_routes(**{m.SITE: page}))
        self.assertEqual(m.check_page(fetch, "", no_sleep), [])
        self.assertEqual([p.key for p in m.check_page(fetch, "87654321", no_sleep)], ["metrika_missing"])

    def test_missing_bot_is_down(self):
        problems = m.check_page(make_fetch(healthy_routes(**{m.SITE + "js/main.js": m.Response(200, "")})), "", no_sleep)
        self.assertEqual([p.key for p in problems], ["bot_link_missing"])


class CertTest(unittest.TestCase):
    def test_fresh_cert_ok(self):
        self.assertEqual(m.check_cert(lambda _: NOW + timedelta(days=60), NOW), ([], True))

    def test_expiring_cert_is_warning(self):
        self.assertEqual([p.key for p in m.check_cert(lambda _: NOW + timedelta(days=3), NOW)[0]], ["cert_expiring"])

    def test_cert_error_is_ignored(self):
        def boom(_: str) -> datetime:
            raise OSError("no tls")
        self.assertEqual(m.check_cert(boom, NOW), ([], False))


class RunChecksTest(unittest.TestCase):
    def test_suspension_hides_follow_up_failures(self):
        routes = healthy_routes(**{
            m.RDAP_URL: m.Response(200, rdap(["ns1.verification-hold.dns-suspended.com"], NOW + timedelta(days=300))),
            m.SITE: ConnectionResetError("reset"),
        })
        problems, ok = m.run_checks(make_fetch(routes), lambda _: NOW + timedelta(days=60), "", NOW)
        self.assertTrue(ok)
        self.assertEqual([p.key for p in problems], ["domain_suspended"])

    def test_all_good(self):
        self.assertEqual(
            m.run_checks(make_fetch(healthy_routes()), lambda _: NOW + timedelta(days=60), "12345678", NOW), ([], True))


class DecideTest(unittest.TestCase):
    down = [m.Problem("site_down", m.DOWN, "Сайт не открывается.")]
    warn = [m.Problem("domain_expiring", m.WARN, "Домен истекает.")]
    t0 = NOW.timestamp()

    def test_quiet_when_all_good(self):
        text, state = m.decide({}, [], self.t0)
        self.assertIsNone(text)
        self.assertEqual(state["problems"], [])

    def test_alert_on_first_failure(self):
        text, state = m.decide({}, self.down, self.t0)
        self.assertIn("НЕ РАБОТАЕТ", text)
        self.assertEqual(state, {"problems": ["site_down"], "last_alert": self.t0, "since": self.t0})

    def test_no_repeat_within_three_hours(self):
        prev = {"problems": ["site_down"], "last_alert": self.t0, "since": self.t0}
        text, state = m.decide(prev, self.down, self.t0 + 3600)
        self.assertIsNone(text)
        self.assertEqual(state["last_alert"], self.t0)

    def test_reminder_after_three_hours(self):
        prev = {"problems": ["site_down"], "last_alert": self.t0, "since": self.t0}
        text, _ = m.decide(prev, self.down, self.t0 + m.REPEAT_DOWN_SEC + 1)
        self.assertIn("напоминание", text)

    def test_warning_repeats_daily_not_every_three_hours(self):
        prev = {"problems": ["domain_expiring"], "last_alert": self.t0, "since": self.t0}
        self.assertIsNone(m.decide(prev, self.warn, self.t0 + m.REPEAT_DOWN_SEC + 1)[0])
        self.assertIsNotNone(m.decide(prev, self.warn, self.t0 + m.REPEAT_WARN_SEC + 1)[0])

    def test_recovery_message(self):
        prev = {"problems": ["site_down"], "last_alert": self.t0, "since": self.t0}
        text, state = m.decide(prev, [], self.t0 + 60)
        self.assertIn("снова работает", text)
        self.assertEqual(state["problems"], [])

    def test_new_problem_alerts_immediately(self):
        prev = {"problems": ["domain_expiring"], "last_alert": self.t0, "since": self.t0}
        text, _ = m.decide(prev, self.warn + self.down, self.t0 + 60)
        self.assertIn("НЕ РАБОТАЕТ", text)

    def test_prev_state_not_mutated(self):
        prev = {"problems": ["site_down"], "last_alert": self.t0, "since": self.t0}
        snapshot = dict(prev)
        m.decide(prev, [], self.t0 + 60)
        self.assertEqual(prev, snapshot)


class PlanAlertTest(unittest.TestCase):
    t0 = NOW.timestamp()
    prev = {"problems": ["domain_suspended"], "last_alert": NOW.timestamp(), "since": NOW.timestamp()}
    site_down = [m.Problem("site_down", m.DOWN, "Сайт не открывается.")]

    def test_incomplete_run_holds_previous_state(self):
        # реестр мигнул: вместо блокировки видим «сайт не открывается» — не шлём ложное сообщение
        text, state = m.plan_alert(self.prev, self.site_down, False, self.t0 + 600)
        self.assertIsNone(text)
        self.assertEqual(state["problems"], ["domain_suspended"])
        self.assertEqual(state["held_since"], self.t0 + 600)

    def test_incomplete_run_does_not_fake_recovery(self):
        text, _ = m.plan_alert(self.prev, [], False, self.t0 + 600)
        self.assertIsNone(text)

    def test_hold_expires_after_six_hours(self):
        held = {**self.prev, "held_since": self.t0}
        text, state = m.plan_alert(held, self.site_down, False, self.t0 + m.MAX_HOLD_SEC + 1)
        self.assertIn("НЕ РАБОТАЕТ", text)
        self.assertNotIn("held_since", state)

    def test_incomplete_run_still_alerts_from_clean_state(self):
        text, _ = m.plan_alert({}, self.site_down, False, self.t0)
        self.assertIn("НЕ РАБОТАЕТ", text)


class MainSavesAfterSendTest(unittest.TestCase):
    def test_state_not_saved_when_telegram_fails(self):
        import os
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            env = {"MONITOR_STATE": str(state_path), "TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"}
            down = [m.Problem("site_down", m.DOWN, "Сайт не открывается.")]
            with mock.patch.dict(os.environ, env), \
                    mock.patch.object(m, "run_checks", return_value=(down, True)), \
                    mock.patch.object(m, "send_telegram", side_effect=SystemExit("502")):
                with self.assertRaises(SystemExit):
                    m.main([])
            self.assertFalse(state_path.exists())  # следующий запуск отправит сообщение снова

    def test_state_saved_after_successful_send(self):
        import os
        import tempfile
        from unittest import mock

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            env = {"MONITOR_STATE": str(state_path), "TELEGRAM_BOT_TOKEN": "t", "TELEGRAM_CHAT_ID": "1"}
            down = [m.Problem("site_down", m.DOWN, "Сайт не открывается.")]
            with mock.patch.dict(os.environ, env), \
                    mock.patch.object(m, "run_checks", return_value=(down, True)), \
                    mock.patch.object(m, "send_telegram") as send:
                m.main([])
            send.assert_called_once()
            self.assertEqual(json.loads(state_path.read_text())["problems"], ["site_down"])


if __name__ == "__main__":
    unittest.main()

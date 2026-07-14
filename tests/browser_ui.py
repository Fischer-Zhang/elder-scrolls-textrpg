"""Playwright desktop browser regressions for the production Web UI.

This suite deliberately sits outside tests/test_*.py: tests/run_all.py remains the
stdlib-only unit suite, while check.sh invokes this file as a separate hard gate.
The fixture serves the real index.html through the production HTTP/SSE handler and
injects deterministic frames, so Chromium exercises rendering and /input end to end.
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright
except ImportError as exc:  # pragma: no cover - exercised by developer setup failures
    raise SystemExit(
        "Playwright 未安裝。請安裝 dev 依賴後執行: "
        "python3 -m playwright install --with-deps chromium"
    ) from exc

from tesrpg.web.backend import WebBackend
from tesrpg.web.server import _make_handler


def _hud() -> dict:
    return {
        "name": "伊蓮娜",
        "level": 18,
        "gold": 742,
        "time": "4E 201 · 霜落 12日 14時",
        "hp": [118, 140],
        "mp": [82, 110],
        "fp": [96, 130],
        "statuses": ["中毒"],
        "buffs": [{"label": "橡木護甲", "remain": 2}],
        "party": [{"name": "莉迪亞", "hp": [94, 120], "downed": False}],
        "allies": [],
        "can_level": True,
    }


def _combat_data(enemy_hp: int = 86) -> dict:
    return {
        "me": {
            "name": "伊蓮娜",
            "hp": [118, 140],
            "mp": [82, 110],
            "fp": [96, 130],
            "tags": [{"s": "護甲2", "good": True}],
        },
        "allies": [
            {"name": "莉迪亞", "hp": [94, 120], "mp": [0, 0], "fp": [70, 100], "tags": []}
        ],
        "enemies": [
            {
                "name": "寒霜蜘蛛",
                "idx": 1,
                "hp": [enemy_hp, 120],
                "mp": [0, 0],
                "fp": [60, 60],
                "tags": [{"s": "燃燒2", "good": False}],
                "key": "0",
            },
            {
                "name": "雪地巨魔",
                "idx": 2,
                "hp": [164, 210],
                "mp": [0, 0],
                "fp": [80, 80],
                "tags": [],
                "key": "1",
            },
        ],
    }


def _combat_prompt() -> dict:
    return {
        "type": "grouped",
        "title": "你的回合",
        "groups": [
            {
                "header": "攻擊",
                "options": [
                    {"key": "repeat", "label": "↻ 再攻:寒霜蜘蛛"},
                    {"key": "attack", "label": "攻擊", "note": "攻擊（鋼長劍 · 盾擊)"},
                ],
            },
            {
                "header": "架式",
                "options": [
                    {
                        "key": "guard",
                        "label": "重盾掩體",
                        "chips": [{"text": "攻擊變緩·卸力-38%·元素-26%·回氣+2/回"}],
                        "note": "重盾掩體（攻擊變緩 · 卸力-38% · 元素-26% · 回氣+2/回)",
                    }
                ],
            },
            {
                "header": "應變",
                "options": [
                    {
                        "key": "vanish",
                        "label": "隱遁再襲",
                        "chips": [{"text": "偷襲·不閃避·70%·剩3次"}],
                        "note": "隱遁再襲（重獲偷襲·不閃避·成功率 70%,剩 3 次)",
                    },
                    {"key": "item", "label": "🧪 用藥", "note": "🧪 用藥（喝下藥水 · 耗一回合)"},
                ],
            },
            {"header": "脫戰", "options": [{"key": "flee", "label": "逃跑"}]},
        ],
        "extra_keys": [],
        "cta_keys": [],
    }


def _dense_combat_prompt() -> dict:
    return {
        "type": "grouped",
        "title": "你的回合",
        "groups": [
            {
                "header": "攻擊",
                "options": [
                    {"key": "repeat", "label": "↻ 再攻:寒霜蜘蛛"},
                    {
                        "key": "attack",
                        "label": "攻擊",
                        "chips": [{"text": "鋼長劍·盾擊"}],
                        "note": "攻擊（鋼長劍 · 盾擊)",
                    },
                    {"key": "aimed", "label": "瞄準射", "chips": [{"text": "強擊·額外耗體"}]},
                    {"key": "volley", "label": "箭雨", "chips": [{"text": "全體60%·倍耗體"}]},
                ],
            },
            {
                "header": "威能·戰技",
                "options": [
                    {"key": "cast", "label": "施法", "note": "施法（選擇法術)"},
                    {"key": "power", "label": "星座之力", "chips": [{"text": "龍吼:不卸之力"}]},
                    {"key": "racial_power", "label": "種族之力", "chips": [{"text": "先祖之怒"}]},
                ],
            },
            {
                "header": "架式",
                "options": [
                    {
                        "key": "guard",
                        "label": "重盾掩體",
                        "chips": [{"text": "攻擊變緩·卸力-38%·元素-26%·回氣+2/回"}],
                        "note": "重盾掩體（攻擊變緩 · 卸力-38% · 元素-26% · 回氣+2/回)",
                    },
                    {
                        "key": "wall",
                        "label": "盾牆",
                        "chips": [{"text": "減傷·嘲諷·護同袍·每回合耗6體"}],
                        "note": "盾牆（減傷 · 嘲諷 · 保護同伴 · 每回合耗 6 體力)",
                    },
                ],
            },
            {
                "header": "應變",
                "options": [
                    {
                        "key": "vanish",
                        "label": "隱遁再襲",
                        "chips": [{"text": "偷襲·不閃避·70%·剩3次"}],
                        "note": "隱遁再襲（重獲偷襲·不閃避·成功率 70%,剩 3 次)",
                    },
                    {"key": "deathmark", "label": "死亡標記", "chips": [{"text": "標記一敵·耗15體"}]},
                    {
                        "key": "item",
                        "label": "🧪 用藥",
                        "chips": [{"text": "喝藥·耗1回合"}],
                        "note": "🧪 用藥（喝下藥水 · 耗一回合)",
                    },
                    {
                        "key": "rest",
                        "label": "喘息",
                        "chips": [{"text": "回體~18·耗1回合·解架式"}],
                        "note": "喘息（回復體力 · 耗一回合 · 解除架式)",
                    },
                ],
            },
            {"header": "脫戰", "options": [{"key": "flee", "label": "逃跑"}]},
        ],
        "extra_keys": [],
        "cta_keys": [],
    }


def _map_data() -> dict:
    def node(node_id, name, x, y, province, *, here=False, guild=None, services=(), hops=None, hours=None):
        svc = [guild] if guild else []
        return {
            "id": node_id,
            "name": name,
            "type": "city",
            "type_cn": "城市",
            "pos": [x, y],
            "province": province,
            "here": here,
            "visited": True,
            "danger": 1,
            "quest": False,
            "reinfested": False,
            "svc": svc,
            "svc_all": svc + list(services),
            "hops": hops,
            "hours": hours,
        }

    return {
        "provinces": [{"name": "天際"}, {"name": "西羅帝爾"}],
        "grid": {
            "cols": 40,
            "rows": 24,
            "nodes": [
                node("whiterun", "白漫城", 9, 12, "天際", here=True, guild="戰士公會", services=("鐵匠",)),
                node("winterhold", "冬堡", 19, 5, "天際", guild="法師公會", services=("旅店",), hops=2, hours=12),
                node("dawnstar", "晨星城", 13, 7, "天際", services=("商人",), hops=1, hours=5),
                node("bruma", "布魯瑪", 16, 17, "西羅帝爾", guild="盜賊公會", services=("商人",), hops=1, hours=7),
            ],
            "edges": [
                {"a": "whiterun", "b": "winterhold", "h": 6},
                {"a": "whiterun", "b": "dawnstar", "h": 5},
                {"a": "whiterun", "b": "bruma", "h": 7},
            ],
        },
    }


class _FixtureServer:
    def __init__(self) -> None:
        self.backend = WebBackend()
        index_html = (ROOT / "tesrpg" / "web" / "static" / "index.html").read_bytes()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self.backend, index_html))
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.httpd.server_address
        self.url = f"http://{host}:{port}/"

    def emit(self, *, blocks: list, prompt: dict, hud=None, resend: bool = False) -> dict:
        with self.backend._lock:
            self.backend.seq += 1
            self.backend.prompt_id += 1
            frame = {
                "seq": self.backend.seq,
                "prompt_id": self.backend.prompt_id,
                "blocks": blocks,
                "prompt": prompt,
                "hud": hud,
                "resend": resend,
            }
            self.backend.last_frame = frame
            self.backend.awaiting = True
        self.backend.outbound.put(frame)
        return frame

    def answer(self, timeout: float = 3.0):
        return self.backend.inbound.get(timeout=timeout)

    def close(self) -> None:
        self.backend.new_generation()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=3)


class BrowserRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(headless=True)
        except PlaywrightError as exc:
            cls.playwright.stop()
            raise RuntimeError(
                "Chromium 無法啟動。請執行: "
                "python3 -m playwright install --with-deps chromium"
            ) from exc

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self) -> None:
        self.server = _FixtureServer()
        self.context = self.browser.new_context(
            viewport={"width": 1280, "height": 800},
            color_scheme="dark",
            locale="zh-TW",
        )
        self.page = self.context.new_page()
        self.page_errors = []
        self.page.on("pageerror", lambda exc: self.page_errors.append(str(exc)))

    def tearDown(self) -> None:
        self.context.close()
        self.server.close()
        if self.page_errors:
            self.fail("瀏覽器 JavaScript 例外:\n" + "\n".join(self.page_errors))

    def _open(self, wait_for: str) -> None:
        self.page.goto(self.server.url, wait_until="domcontentloaded")
        self.page.locator(wait_for).wait_for(state="visible")

    def test_desktop_combat_render_submit_and_scroll(self) -> None:
        narrative = [
            {"kind": "log", "html": f"<span>旅程紀錄 {i:02d}:風雪仍未止息。</span>"}
            for i in range(1, 19)
        ]
        self.server.emit(
            blocks=[
                {"kind": "view", "name": "combat", "data": _combat_data()},
                {"kind": "log", "html": "<span>寒霜蜘蛛撲了上來。</span>", "ephemeral": True},
                {"kind": "log", "html": "<span>莉迪亞擋下了利爪。</span>", "ephemeral": True},
                *narrative,
            ],
            prompt=_combat_prompt(),
            hud=_hud(),
        )
        self._open(".combat-flow")

        self.assertTrue(self.page.locator("body").evaluate("el => el.classList.contains('playing')"))
        self.assertEqual(self.page.locator("#masthead").evaluate("el => getComputedStyle(el).display"), "none")
        self.assertTrue(self.page.locator("#hud").is_visible())
        self.assertEqual(self.page.locator(".combat-flow .ghead").count(), 0)
        self.assertEqual(self.page.locator(".combat-flow button.opt").count(), 6)
        self.assertIn("寒霜蜘蛛撲了上來", self.page.locator("#turnlog").inner_text())
        self.assertIn("旅程紀錄 18", self.page.locator("#log").inner_text())

        order = self.page.evaluate(
            """() => {
              const ids = [...document.querySelector('#app').children].map(e => e.id);
              return [ids.indexOf('screen'), ids.indexOf('turnlog'), ids.indexOf('prompt'), ids.indexOf('log')];
            }"""
        )
        self.assertEqual(order, sorted(order), "戰況、本回合、操作、故事日誌的閱讀順序錯置")

        layout = self.page.locator(".combat-flow button.opt").evaluate_all(
            "els => els.map(e => { const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,right:r.right}; })"
        )
        flow_width = self.page.locator(".combat-flow").bounding_box()["width"]
        self.assertTrue(any(abs(a["y"] - b["y"]) < 1 for i, a in enumerate(layout) for b in layout[i + 1:]))
        self.assertLess(max(item["w"] for item in layout), flow_width * 0.75, "內容寬按鈕退化成整列寬")
        self.assertTrue(all(item["right"] <= 1280 for item in layout), "戰鬥按鈕超出桌面 viewport")
        self.assertTrue(
            self.page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"),
            "桌面畫面出現水平溢出",
        )

        vanish = self.page.locator(".combat-flow button.opt").filter(has_text="隱遁再襲")
        self.assertIn("隱遁再襲", vanish.inner_text())
        self.assertNotIn("70%", vanish.inner_text())
        self.assertNotIn("不閃避", vanish.inner_text())
        self.assertIsNone(vanish.get_attribute("title"))
        vanish.locator("xpath=..").locator("button.combat-info").click()
        note = self.page.locator("#combat-action-note")
        self.assertIn("70%", note.inner_text())
        self.assertIn("不閃避", note.inner_text())
        self.assertEqual(vanish.locator("xpath=..").locator("button.combat-info").get_attribute("aria-expanded"), "true")
        self.page.keyboard.press("Escape")
        self.assertEqual(note.count(), 0)

        self.page.locator(".combat-flow button.opt").evaluate_all(
            "els => els.find(e => e._key === 'attack').click()"
        )
        self.assertEqual(self.server.answer(), "attack")
        self.assertTrue(self.page.locator("#prompt").evaluate("el => el.classList.contains('locked')"))

        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.assertGreater(self.page.evaluate("window.scrollY"), 0)
        self.server.emit(
            blocks=[
                {"kind": "view", "name": "combat", "data": _combat_data(enemy_hp=61)},
                {"kind": "log", "html": "<span>第二回合:鋼長劍命中寒霜蜘蛛。</span>", "ephemeral": True},
            ],
            prompt=_combat_prompt(),
            hud=_hud(),
        )
        self.page.locator("#turnlog").filter(has_text="第二回合").wait_for()
        self.page.wait_for_function("window.scrollY === 0")
        self.assertIn("61/120", self.page.locator(".cbt.foe").first.inner_text())

    def test_dense_action_menu_shortcuts_and_pending_input(self) -> None:
        prompt = _dense_combat_prompt()
        self.server.emit(
            blocks=[
                {"kind": "view", "name": "combat", "data": _combat_data()},
                {"kind": "log", "html": "<span>巨魔正準備下一次猛擊。</span>", "ephemeral": True},
            ],
            prompt=prompt,
            hud=_hud(),
        )
        self._open(".combat-flow")

        buttons = self.page.locator(".combat-flow button.opt")
        self.assertEqual(buttons.count(), 14)
        self.assertEqual(buttons.locator(".opt-chips").count(), 0)
        self.assertEqual(self.page.locator(".combat-flow button.combat-info").count(), 12)
        groups = buttons.evaluate_all("els => [...new Set(els.map(e => e.dataset.group))]")
        self.assertEqual(groups, ["攻擊", "威能·戰技", "架式", "應變", "脫戰"])
        self.assertEqual(buttons.nth(4).get_attribute("data-group"), "威能·戰技")
        self.assertIn("威能·戰技", buttons.nth(4).get_attribute("aria-label"))
        self.assertNotIn("攻擊變緩", buttons.filter(has_text="重盾掩體").inner_text())
        guard_info = buttons.filter(has_text="重盾掩體").locator("xpath=..").locator("button.combat-info")
        guard_info.click()
        self.assertIn("攻擊變緩", self.page.locator("#combat-action-note").inner_text())
        self.assertIn("卸力-38%", self.page.locator("#combat-action-note").inner_text())
        with self.assertRaises(queue.Empty, msg="資訊按鈕誤送出戰鬥動作"):
            self.server.answer(timeout=0.2)
        self.page.locator(".combat-note-close").click()
        guard_info.evaluate("el => el.blur()")
        rows = buttons.evaluate_all(
            "els => [...new Set(els.map(e => Math.round(e.getBoundingClientRect().y)))]"
        )
        self.assertLessEqual(len(rows), 5, "獨立資訊按鈕加入後，14 個動作仍應維持緊湊配置")
        self.assertTrue(
            self.page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"),
            "密集動作選單出現水平溢出",
        )
        combat_geometry = self.page.locator(".combat").evaluate(
            """el => {
              const r=el.getBoundingClientRect(), sides=[...el.querySelectorAll('.cside')].map(x=>x.getBoundingClientRect());
              return {display:getComputedStyle(el).display,height:r.height,left:sides[0].left,right:sides[1].left};
            }"""
        )
        self.assertEqual(combat_geometry["display"], "grid")
        self.assertLess(combat_geometry["height"], 240, "桌面戰況仍以垂直重複佔用過多首屏")
        self.assertLess(combat_geometry["left"], combat_geometry["right"], "敵我兩欄未左右分列")
        last_action_bottom = buttons.last.evaluate("el => el.getBoundingClientRect().bottom")
        self.assertLessEqual(last_action_bottom, 800, "1280×800 首屏未完整容納密集動作選單")
        self.assertLessEqual(
            self.page.locator("#foot").evaluate("el => el.getBoundingClientRect().bottom"),
            800,
            "1280×800 首屏未完整容納動作快捷提示",
        )
        help_text = self.page.locator("#foot").inner_text()
        self.assertIn("1–14", help_text)
        self.assertIn("Enter 確認", help_text)
        self.assertIn("Enter 再次", help_text)
        self.assertNotIn("1–9", help_text)

        self.page.keyboard.press("Enter")
        self.assertEqual(self.server.answer(), "repeat", "常用的再次行動不應承受多位數等待")

        self.server.emit(blocks=[], prompt=prompt, hud=_hud())
        self.page.wait_for_function("!document.querySelector('#prompt').classList.contains('locked')")
        self.page.keyboard.press("1")
        self.page.keyboard.press("0")
        self.assertEqual(self.server.answer(), "vanish", "第 10 項的多位數快捷鍵失效")

        self.server.emit(blocks=[], prompt=prompt, hud=_hud())
        self.page.wait_for_function("!document.querySelector('#prompt').classList.contains('locked')")
        self.page.keyboard.press("1")
        buttons.evaluate_all("els => els.find(e => e._key === 'attack').click()")
        self.assertEqual(self.server.answer(), "attack")

        self.server.emit(blocks=[], prompt=prompt, hud=_hud())
        self.page.wait_for_function("!document.querySelector('#prompt').classList.contains('locked')")
        with self.assertRaises(queue.Empty, msg="滑鼠送出後殘留的數字緩衝跨回合誤觸"):
            self.server.answer(timeout=0.6)

        buttons.evaluate_all("els => els.find(e => e._key === 'attack').focus()")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.server.answer(), "attack", "焦點按鈕的原生 Enter 被全域『再次』搶走")

        self.server.emit(blocks=[], prompt=prompt, hud=_hud())
        self.page.wait_for_function("!document.querySelector('#prompt').classList.contains('locked')")
        self.page.keyboard.press("1")
        self.server.emit(blocks=[], prompt=prompt, hud=_hud())
        with self.assertRaises(queue.Empty, msg="新畫面沿用了舊畫面的未完成數字快捷鍵"):
            self.server.answer(timeout=0.6)

    def test_interaction_state_pending_focus_and_fallback(self) -> None:
        first = self.server.emit(
            blocks=[{"kind": "view", "name": "combat", "data": _combat_data()}],
            prompt=_combat_prompt(),
            hud=_hud(),
        )
        self._open(".combat-flow")
        requests = []
        self.page.on("request", lambda req: requests.append(req.url) if req.url.endswith("/input") else None)
        attack = self.page.locator(".combat-flow button.opt").filter(has_text="攻擊").last
        attack.click()
        self.assertEqual(self.server.answer(), "attack")

        prompt = self.page.locator("#prompt")
        self.assertEqual(prompt.get_attribute("aria-busy"), "true")
        self.assertTrue(prompt.evaluate("el => el.inert"))
        self.assertTrue(self.page.locator("#screen").evaluate("el => el.inert"))
        self.assertEqual(self.page.locator(".pending-spinner").count(), 1)
        self.assertIn("處理中", self.page.get_by_role("status").inner_text())
        attack.evaluate("el => el.click()")
        self.page.wait_for_timeout(100)
        self.assertEqual(len(requests), 1, "pending 期間仍送出了重複 /input")

        next_frame = self.server.emit(
            blocks=[{"kind": "view", "name": "combat", "data": _combat_data(enemy_hp=72)}],
            prompt=_combat_prompt(),
            hud=_hud(),
        )
        self.assertGreater(next_frame["seq"], first["seq"])
        self.page.wait_for_function("document.querySelector('#prompt').getAttribute('aria-busy') === 'false'")
        self.assertFalse(prompt.evaluate("el => el.inert"))
        self.assertEqual(self.page.locator(".pending-spinner").count(), 0)
        self.assertEqual(self.page.evaluate("document.activeElement._key"), "attack")
        self.assertEqual(self.page.evaluate("window.scrollY"), 0)

        focused = self.page.locator(".combat-flow button.opt").filter(has_text="攻擊").last
        focused.click()
        self.assertEqual(self.server.answer(), "attack")
        self.server.emit(
            blocks=[],
            prompt={
                "type": "menu",
                "title": "戰鬥結束",
                "options": [{"key": "continue", "label": "繼續"}],
                "allow_back": False,
            },
            hud=_hud(),
        )
        self.page.get_by_text("戰鬥結束", exact=True).wait_for()
        self.assertEqual(self.page.evaluate("document.activeElement.className"), "ptitle")

    def test_http_409_resyncs_without_unlocking_stale_frame(self) -> None:
        frame = self.server.emit(
            blocks=[{"kind": "view", "name": "combat", "data": _combat_data()}],
            prompt=_combat_prompt(),
            hud=_hud(),
        )
        self._open(".combat-flow")
        self.assertTrue(self.server.backend.submit(frame["prompt_id"], "already-accepted"))

        self.page.locator(".combat-flow button.opt").filter(has_text="攻擊").last.click()
        status = self.page.get_by_role("status")
        status.filter(has_text="畫面同步中").wait_for()
        self.assertEqual(self.page.locator("#prompt").get_attribute("aria-busy"), "false")
        self.assertTrue(self.page.locator("#prompt").evaluate("el => el.inert"))
        self.page.wait_for_timeout(150)
        self.assertTrue(self.page.locator("#prompt").evaluate("el => el.inert"), "重送舊 last_frame 誤解鎖")

        self.server.emit(blocks=[], prompt=_combat_prompt(), hud=_hud())
        self.page.wait_for_function("!document.querySelector('#prompt').inert")
        self.assertEqual(self.page.evaluate("document.activeElement._key"), "attack")

    def test_preserved_screen_rows_are_unwired_before_focus_fallback(self) -> None:
        self.server.emit(
            blocks=[{
                "kind": "view",
                "name": "inventory",
                "data": {
                    "items": [{"key": "old", "label": "舊物品", "kind": "misc", "tier": "common"}],
                    "weight": 1,
                    "max": 100,
                    "over": False,
                    "gold": 10,
                },
            }],
            prompt={
                "type": "menu",
                "title": "舊動作",
                "options": [{"key": "old", "label": "使用舊物品"}],
                "allow_back": False,
            },
            hud=_hud(),
        )
        self._open('.inv-row[data-key="old"]')
        old_row = self.page.locator('.inv-row[data-key="old"]')
        old_row.click()
        self.assertEqual(self.server.answer(), "old")

        self.server.emit(
            blocks=[],
            prompt={
                "type": "menu",
                "title": "新動作",
                "options": [{"key": "new", "label": "執行新動作"}],
                "allow_back": False,
            },
            hud=_hud(),
        )
        self.page.get_by_text("新動作", exact=True).wait_for()
        self.assertEqual(self.page.evaluate("document.activeElement.className"), "ptitle")
        self.assertNotIn("tappable", old_row.get_attribute("class"))
        self.assertIsNone(old_row.get_attribute("tabindex"))
        self.page.keyboard.press("Enter")
        with self.assertRaises(queue.Empty, msg="已失效的舊 data-key 列仍向新 prompt 送值"):
            self.server.answer(timeout=0.3)

    def test_focus_restores_persistent_cta_and_back_buttons(self) -> None:
        cta_prompt = {
            "type": "grouped",
            "title": "角色選單",
            "groups": [{
                "header": "系統",
                "options": [
                    {"key": "levelup", "label": "升級"},
                    {"key": "sheet", "label": "角色卡"},
                ],
            }],
            "extra_keys": [],
            "cta_keys": ["levelup"],
        }
        self.server.emit(blocks=[], prompt=cta_prompt, hud=_hud())
        self._open("button.cta")
        self.page.locator("button.cta").click()
        self.assertEqual(self.server.answer(), "levelup")
        self.server.emit(blocks=[], prompt=cta_prompt, hud=_hud())
        self.page.wait_for_function("document.activeElement && document.activeElement._key === 'levelup'")

        back_prompt = {
            "type": "menu",
            "title": "子選單",
            "options": [{"key": "inspect", "label": "查看"}],
            "allow_back": True,
        }
        self.server.emit(blocks=[], prompt=back_prompt, hud=_hud())
        back = self.page.locator("button.back")
        back.wait_for()
        back.click()
        self.assertIsNone(self.server.answer())
        self.server.emit(blocks=[], prompt=back_prompt, hud=_hud())
        self.page.wait_for_function("document.activeElement && document.activeElement._key === null")
        self.assertIn("back", self.page.evaluate("document.activeElement.className"))

    def test_input_network_failure_and_timeout_are_retryable(self) -> None:
        self.server.emit(
            blocks=[{"kind": "view", "name": "combat", "data": _combat_data()}],
            prompt=_combat_prompt(),
            hud=_hud(),
        )
        self._open(".combat-flow")
        attack = self.page.locator(".combat-flow button.opt").filter(has_text="攻擊").last

        self.page.route("**/input", lambda route: route.abort("failed"), times=1)
        attack.click()
        self.page.get_by_role("status").filter(has_text="未收到送出確認").wait_for()
        self.assertFalse(self.page.locator("#prompt").evaluate("el => el.inert"))
        self.assertEqual(self.page.locator(".pending-spinner").count(), 0)
        attack.click()
        self.assertEqual(self.server.answer(), "attack", "網路失敗解除後不能重試")
        self.server.emit(blocks=[], prompt=_combat_prompt(), hud=_hud())
        self.page.wait_for_function("!document.querySelector('#prompt').inert")

        def accept_then_drop_response(route) -> None:
            route.fetch()   # 正式 /input 已由後端接受，但不把 200 回應交給頁面。
            route.abort("failed")

        self.page.route("**/input", accept_then_drop_response, times=1)
        self.page.locator(".combat-flow button.opt").filter(has_text="攻擊").last.click()
        self.assertEqual(self.server.answer(), "attack", "故障注入沒有先讓後端接受輸入")
        self.page.get_by_role("status").filter(has_text="未收到送出確認").wait_for()
        self.server.emit(blocks=[], prompt=_combat_prompt(), hud=_hud())
        self.page.wait_for_function("document.querySelector('#status').dataset.state === 'ok'")
        self.assertEqual(self.page.evaluate("document.activeElement._key"), "attack")

        self.page.clock.install()
        self.page.evaluate(
            """() => {
              window.__tesRealFetch = window.fetch;
              window.fetch = function (url, options) {
                if (String(url).endsWith('/input')) {
                  return new Promise(function (_, reject) {
                    options.signal.addEventListener('abort', function () {
                      reject(new DOMException('Aborted', 'AbortError'));
                    }, {once:true});
                  });
                }
                return window.__tesRealFetch(url, options);
              };
            }"""
        )
        self.page.locator(".combat-flow button.opt").filter(has_text="攻擊").last.click()
        self.assertEqual(self.page.locator("#prompt").get_attribute("aria-busy"), "true")
        self.page.clock.fast_forward(8100)
        self.page.get_by_role("status").filter(has_text="未收到送出確認").wait_for()
        self.assertFalse(self.page.locator("#prompt").evaluate("el => el.inert"))
        self.page.evaluate("window.fetch = window.__tesRealFetch; delete window.__tesRealFetch")
        self.page.locator(".combat-flow button.opt").filter(has_text="攻擊").last.click()
        self.assertEqual(self.server.answer(), "attack", "逾時解除後不能重試")

    def test_offline_status_inert_reconnect_and_geometry(self) -> None:
        self.page.add_init_script(
            """window.__NativeEventSource = window.EventSource;
            window.__eventSourceCount = 0;
            window.__eventSourceOpenCount = 0;
            window.EventSource = class extends window.__NativeEventSource {
              constructor(url, options) {
                super(url, options);
                window.__eventSourceCount += 1;
                this.addEventListener('open', function () { window.__eventSourceOpenCount += 1; });
                window.__testEventSource = this;
              }
            };"""
        )
        self.server.emit(
            blocks=[{"kind": "view", "name": "combat", "data": _combat_data()}]
            + [
                {"kind": "log", "html": f"<span>長頁斷線測試紀錄 {i:02d}</span>"}
                for i in range(24)
            ],
            prompt=_combat_prompt(),
            hud=_hud(),
        )
        self._open(".combat-flow")
        status = self.page.get_by_role("status")

        self.page.route("**/events", lambda route: route.abort("failed"), times=1)
        self.page.route(
            "**/input",
            lambda route: route.fulfill(status=409, content_type="application/json", body='{"accepted":false}'),
            times=1,
        )
        self.page.locator(".combat-flow button.opt").filter(has_text="攻擊").last.click()
        self.page.wait_for_function("window.__eventSourceCount >= 2")
        status.filter(has_text="重新連線中").wait_for(timeout=10_000)
        self.assertNotEqual(self.page.evaluate("window.__testEventSource.readyState"), 1)
        self.assertTrue(status.is_visible())
        self.assertTrue(self.page.locator("#prompt").evaluate("el => el.inert"))
        self.assertFalse(self.page.locator("#gear").evaluate("el => el.inert"), "斷線時設定按鈕不應被鎖")

        def assert_status_geometry() -> None:
            boxes = self.page.evaluate(
                """() => {
                  const s=document.querySelector('#status').getBoundingClientRect();
                  const g=document.querySelector('#gear').getBoundingClientRect();
                  const h=document.querySelector('#hud').getBoundingClientRect();
                  return {s:{l:s.left,r:s.right,t:s.top,b:s.bottom},g:{l:g.left,r:g.right,t:g.top,b:g.bottom},
                    h:{l:h.left,r:h.right,t:h.top,b:h.bottom},vh:innerHeight,
                    overflow:document.documentElement.scrollWidth > document.documentElement.clientWidth};
                }"""
            )
            gear_overlap = not (
                boxes["s"]["r"] <= boxes["g"]["l"]
                or boxes["g"]["r"] <= boxes["s"]["l"]
                or boxes["s"]["b"] <= boxes["g"]["t"]
                or boxes["g"]["b"] <= boxes["s"]["t"]
            )
            hud_overlap = not (boxes["s"]["b"] <= boxes["h"]["t"] or boxes["h"]["b"] <= boxes["s"]["t"])
            self.assertFalse(gear_overlap, "連線狀態列與設定按鈕重疊")
            self.assertFalse(hud_overlap, "連線狀態列與 sticky HUD 重疊")
            self.assertFalse(boxes["overflow"], "連線狀態列造成水平溢出")
            self.assertGreaterEqual(boxes["s"]["t"], 0, "連線狀態列捲出 viewport 上緣")
            self.assertLessEqual(boxes["s"]["b"], boxes["vh"], "連線狀態列超出 viewport 下緣")

        assert_status_geometry()
        self.page.set_viewport_size({"width": 390, "height": 844})
        self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        self.assertGreater(self.page.evaluate("window.scrollY"), 0)
        assert_status_geometry()

        self.server.emit(blocks=[], prompt=_combat_prompt(), hud=_hud())
        self.page.wait_for_function("window.__eventSourceOpenCount >= 2", timeout=10_000)
        self.page.wait_for_function("!document.querySelector('#prompt').inert", timeout=10_000)
        status_el = self.page.locator("#status")
        self.assertEqual(status_el.get_attribute("data-state"), "ok")
        self.assertFalse(status_el.is_visible(), "遊戲中已同步狀態列應收起")

    def test_preserved_map_action_is_disabled_for_new_prompt(self) -> None:
        self.server.emit(
            blocks=[{"kind": "view", "name": "map", "data": _map_data()}],
            prompt={
                "type": "grouped",
                "title": "世界地圖",
                "groups": [{"header": "操作", "options": [{"key": "back", "label": "返回"}]}],
                "extra_keys": ["route:winterhold"],
                "cta_keys": [],
            },
            hud=_hud(),
        )
        self._open(".mapstage")
        self.page.get_by_role("button", name="法師公會", exact=True).click()
        old_go = self.page.locator(".msvc-find .msf-go")
        old_go.click()
        self.assertEqual(self.server.answer(), "route:winterhold")

        self.server.emit(
            blocks=[],
            prompt={"type": "confirm", "prompt": "接受途中事件？"},
            hud=_hud(),
        )
        self.page.get_by_text("接受途中事件？", exact=True).wait_for()
        self.assertTrue(old_go.is_disabled())
        self.assertEqual(self.page.evaluate("document.activeElement.className"), "ptitle")
        old_go.evaluate("el => el.click()")
        with self.assertRaises(queue.Empty, msg="失效的舊地圖前往按鈕向 confirm 送入 route 字串"):
            self.server.answer(timeout=0.3)
        self.page.get_by_role("button", name="盜賊公會", exact=True).click()
        new_go = self.page.locator(".msvc-find .msf-go")
        self.assertTrue(new_go.is_disabled(), "新建的地圖前往按鈕未立即反映目前 prompt 不允許 route")

    def test_bad_sse_message_restarts_and_recovers_last_frame(self) -> None:
        self.page.add_init_script(
            """window.__NativeEventSource = window.EventSource;
            window.__eventSourceCount = 0;
            window.EventSource = class extends window.__NativeEventSource {
              constructor(url, options) {
                super(url, options);
                window.__eventSourceCount += 1;
                window.__testEventSource = this;
              }
            };"""
        )
        self.server.emit(
            blocks=[{"kind": "view", "name": "combat", "data": _combat_data()}],
            prompt=_combat_prompt(),
            hud=_hud(),
        )
        self._open(".combat-flow")
        self.page.evaluate(
            "window.__testEventSource.dispatchEvent(new MessageEvent('message', {data:'{broken'}))"
        )
        self.page.get_by_role("status").filter(has_text="畫面同步失敗").wait_for()
        self.assertTrue(self.page.locator("#prompt").evaluate("el => el.inert"))
        self.page.wait_for_function("window.__eventSourceCount >= 2")
        self.page.wait_for_function("!document.querySelector('#prompt').inert")
        self.assertEqual(self.page.locator("#status").get_attribute("data-state"), "ok")

    def test_sync_failure_cannot_bypass_409_sync_floor(self) -> None:
        self.page.add_init_script(
            """window.__NativeEventSource = window.EventSource;
            window.__eventSourceCount = 0;
            window.EventSource = class extends window.__NativeEventSource {
              constructor(url, options) {
                super(url, options);
                window.__eventSourceCount += 1;
                window.__testEventSource = this;
              }
            };"""
        )
        frame = self.server.emit(
            blocks=[{"kind": "view", "name": "combat", "data": _combat_data()}],
            prompt=_combat_prompt(),
            hud=_hud(),
        )
        self._open(".combat-flow")
        self.page.route(
            "**/input",
            lambda route: route.fulfill(status=409, content_type="application/json", body='{"accepted":false}'),
            times=1,
        )
        self.page.locator(".combat-flow button.opt").filter(has_text="攻擊").last.click()
        self.page.wait_for_function("window.__eventSourceCount >= 2")
        self.page.wait_for_function("document.querySelector('#prompt').inert")
        self.page.evaluate(
            """frame => {
              const es = window.__testEventSource;
              es.dispatchEvent(new MessageEvent('message', {data:'{broken'}));
              es.dispatchEvent(new MessageEvent('message', {data:JSON.stringify(frame)}));
            }""",
            frame,
        )
        self.page.wait_for_timeout(100)
        self.assertTrue(
            self.page.locator("#prompt").evaluate("el => el.inert"),
            "同步失敗後的舊 last_frame 越過 409 syncFloor 誤解鎖",
        )
        self.page.wait_for_function("window.__eventSourceCount >= 3")
        self.server.emit(blocks=[], prompt=_combat_prompt(), hud=_hud())
        self.page.wait_for_function("!document.querySelector('#prompt').inert")

    def test_reduced_motion_os_and_setting_cover_transitions_and_spinner(self) -> None:
        self.server.emit(
            blocks=[{"kind": "view", "name": "combat", "data": _combat_data()}],
            prompt=_combat_prompt(),
            hud=_hud(),
        )
        self.page.emulate_media(reduced_motion="reduce")
        self._open(".combat-flow")
        attack = self.page.locator(".combat-flow button.opt").filter(has_text="攻擊").last
        attack.click()
        self.assertEqual(self.server.answer(), "attack")
        spinner = self.page.locator(".pending-spinner")
        self.assertEqual(spinner.evaluate("el => getComputedStyle(el).animationName"), "none")
        self.assertEqual(attack.evaluate("el => getComputedStyle(el).transitionDuration"), "0s")
        self.assertEqual(self.page.locator(".combat .m-fill").first.evaluate("el => getComputedStyle(el).transitionDuration"), "0s")
        self.assertEqual(self.page.locator("html").evaluate("el => getComputedStyle(el).scrollBehavior"), "auto")
        self.server.emit(blocks=[], prompt=_combat_prompt(), hud=_hud())
        self.page.wait_for_function("!document.querySelector('#prompt').inert")

        self.page.emulate_media(reduced_motion="no-preference")
        self.assertNotEqual(
            self.page.locator(".combat .m-fill").first.evaluate("el => getComputedStyle(el).transitionDuration"),
            "0s",
            "no-preference/動態開啟時的計量條基線本來就沒有 transition，測試無法防回歸",
        )
        self.page.locator("#gear").click()
        self.page.get_by_role("button", name="關", exact=True).click()
        self.page.keyboard.press("Escape")
        manual_attack = self.page.locator(".combat-flow button.opt").filter(has_text="攻擊").last
        manual_attack.click()
        self.assertEqual(self.server.answer(), "attack")
        manual_spinner = self.page.locator(".pending-spinner")
        self.assertEqual(manual_spinner.evaluate("el => getComputedStyle(el).animationName"), "none")
        self.assertEqual(manual_attack.evaluate("el => getComputedStyle(el).transitionDuration"), "0s")
        self.assertEqual(self.page.locator(".combat .m-fill").first.evaluate("el => getComputedStyle(el).transitionDuration"), "0s")
        self.assertEqual(self.page.locator("html").evaluate("el => getComputedStyle(el).scrollBehavior"), "auto")

    def test_desktop_combat_geometry_breakpoints_and_large_text(self) -> None:
        self.server.emit(
            blocks=[
                {"kind": "view", "name": "combat", "data": _combat_data()},
                {"kind": "log", "html": "<span>寒風掠過交戰雙方。</span>", "ephemeral": True},
            ],
            prompt=_dense_combat_prompt(),
            hud=_hud(),
        )
        self._open(".combat-flow")
        self.page.set_viewport_size({"width": 1024, "height": 768})

        def assert_no_horizontal_overflow(message: str) -> None:
            self.assertTrue(
                self.page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"),
                message,
            )

        assert_no_horizontal_overflow("1024×768 桌面戰況或動作選單水平溢出")
        sides = self.page.locator(".combat .cside").evaluate_all(
            "els => els.map(e => { const r=e.getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top}; })"
        )
        self.assertEqual(len(sides), 2)
        self.assertLess(sides[0]["right"], sides[1]["left"], "1024px 寬度下敵我欄互相重疊")
        self.assertAlmostEqual(sides[0]["top"], sides[1]["top"], delta=1)
        self.assertLessEqual(
            self.page.locator(".combat-flow button.opt").last.evaluate("el => el.getBoundingClientRect().bottom"),
            768,
            "1024×768 首屏未容納完整動作選單",
        )

        self.page.set_viewport_size({"width": 800, "height": 900})
        assert_no_horizontal_overflow("800px 最窄桌面斷點出現水平溢出")
        edge_sides = self.page.locator(".combat .cside").evaluate_all(
            "els => els.map(e => { const r=e.getBoundingClientRect(); return {left:r.left,right:r.right}; })"
        )
        self.assertEqual(self.page.locator(".combat").evaluate("el => getComputedStyle(el).display"), "grid")
        self.assertLess(edge_sides[0]["right"], edge_sides[1]["left"], "最窄桌面斷點的敵我欄互相重疊")

        self.page.locator("html").evaluate("el => el.setAttribute('data-fs', 'xl')")
        assert_no_horizontal_overflow("800px 最窄桌面搭配特大字級造成水平溢出")
        self.assertEqual(self.page.locator(".combat").evaluate("el => getComputedStyle(el).display"), "grid")
        self.assertTrue(
            self.page.locator(".combat-flow button.opt").evaluate_all(
                "els => els.every(e => e.scrollWidth <= e.clientWidth && e.getBoundingClientRect().right <= innerWidth)"
            ),
            "最窄桌面的特大字級動作文字或按鈕超出容器",
        )

    def test_settings_persist_and_trap_focus(self) -> None:
        self.server.emit(
            blocks=[],
            prompt={
                "type": "menu",
                "title": "主選單",
                "options": [{"key": "new", "label": "開始新遊戲"}],
                "allow_back": False,
            },
        )
        self._open("#gear")
        self.assertTrue(self.page.locator("#masthead").is_visible())
        self.assertEqual(self.page.locator("#gear").evaluate("el => getComputedStyle(el).position"), "fixed")

        self.page.locator("#gear").click()
        dialog = self.page.get_by_role("dialog", name="設定")
        dialog.wait_for(state="visible")
        self.assertTrue(self.page.locator("#app").evaluate("el => el.inert"))
        self.assertEqual(self.page.evaluate("document.activeElement.className"), "set-close")

        self.page.get_by_role("button", name="特大", exact=True).click()
        self.page.get_by_role("button", name="高對比", exact=True).click()
        self.page.get_by_role("button", name="關", exact=True).click()
        self.assertEqual(self.page.locator("html").get_attribute("data-fs"), "xl")
        self.assertEqual(self.page.locator("html").get_attribute("data-theme"), "contrast")
        self.assertEqual(self.page.locator("html").get_attribute("data-motion"), "off")

        saved = json.loads(self.page.evaluate("localStorage.getItem('tesrpg_settings')"))
        self.assertEqual(saved, {"fs": "xl", "theme": "contrast", "motion": "off"})
        self.page.keyboard.press("Escape")
        self.assertFalse(dialog.is_visible())
        self.assertEqual(self.page.evaluate("document.activeElement.id"), "gear")
        self.assertFalse(self.page.locator("#app").evaluate("el => el.inert"))

        self.page.reload(wait_until="domcontentloaded")
        self.page.locator("#gear").wait_for(state="visible")
        self.assertEqual(self.page.locator("html").get_attribute("data-fs"), "xl")
        self.assertEqual(self.page.locator("html").get_attribute("data-theme"), "contrast")
        self.assertEqual(self.page.locator("html").get_attribute("data-motion"), "off")

    def test_world_map_service_filter_and_route_submission(self) -> None:
        self.server.emit(
            blocks=[{"kind": "view", "name": "map", "data": _map_data()}],
            prompt={
                "type": "grouped",
                "title": "世界地圖",
                "groups": [{"header": "操作", "options": [{"key": "back", "label": "返回"}]}],
                "extra_keys": ["route:winterhold", "route:bruma"],
                "cta_keys": [],
            },
            hud=_hud(),
        )
        self._open(".mapstage")

        self.page.get_by_role("button", name="法師公會", exact=True).click()
        find = self.page.locator(".msvc-find")
        self.assertIn("冬堡", find.inner_text())
        self.assertIn("2 段", find.inner_text())
        self.assertEqual(
            self.page.locator('.mmark[data-id="winterhold"]').evaluate("el => getComputedStyle(el).opacity"),
            "1",
        )
        self.assertEqual(
            self.page.locator('.mmark[data-id="whiterun"]').evaluate("el => getComputedStyle(el).opacity"),
            "0.9",
        )
        self.assertEqual(
            self.page.locator('.mmark[data-id="dawnstar"]').evaluate("el => getComputedStyle(el).opacity"),
            "0.22",
        )
        self.assertEqual(
            self.page.get_by_role("button", name="法師公會", exact=True).get_attribute("aria-pressed"),
            "true",
        )
        self.assertTrue(
            self.page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"),
            "世界地圖在桌面 viewport 水平溢出",
        )

        find.get_by_role("button", name="前往", exact=True).click()
        self.assertEqual(self.server.answer(), "route:winterhold")


if __name__ == "__main__":
    unittest.main(verbosity=2)

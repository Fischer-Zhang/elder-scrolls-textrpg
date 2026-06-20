"""紅線靜態守門:成長/夾限只用 base_*、加成走獨立疊加層、**絕不寫 base**(R01/R05 最高紅線)。

把「絕不寫 base」從人工守變**機器守**:AST 掃 tesrpg/**/*.py,找對 base 儲存
(char.skills / char.attributes / char.base_max_health)的**寫入**,斷言只在白名單模組發生。
零執行期開銷、跑在測試套件、未來違規即紅。疊加層(*_bonus/*_penalty)名稱不同 → 天然不誤判。
"""

import ast
import pathlib

# base 儲存的三個欄位(疊加層用 equip_skill_bonus / mastery_attr_bonus / disease_skill_penalty… 不同名)
_BASE_ATTRS = {"skills", "attributes", "base_max_health"}

# 合法寫 base 的模組(經 AST 全掃確認;各自為何合法見下):
#   creation.py            — 創角初始化 base_max_health
#   systems/progression.py — ensure_all_skills 補欄 + 升級 use_skill/apply_level_up 寫 base skills/attributes
#   systems/stats.py       — ensure_base_health 舊檔遷移
_ALLOWLIST = {"creation.py", "systems/progression.py", "systems/stats.py"}

_TESRPG = pathlib.Path(__file__).resolve().parent.parent / "tesrpg"


def _base_write_sites(tree: ast.AST) -> list[tuple[int, str]]:
    """回傳此 AST 中所有「寫入 base 儲存」的 (lineno, attr)(整屬性或下標賦值)。"""
    out: list[tuple[int, str]] = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign):
            targets = n.targets
        elif isinstance(n, ast.AugAssign):
            targets = [n.target]
        else:
            continue
        for t in targets:
            if isinstance(t, ast.Attribute) and t.attr in _BASE_ATTRS:
                out.append((n.lineno, t.attr))                       # x.skills = … / x.base_max_health = …
            elif (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Attribute)
                  and t.value.attr in _BASE_ATTRS):
                out.append((n.lineno, t.value.attr))                 # x.skills[k] = … / x.attributes[k] = …
    return out


def _scan() -> dict[str, list[tuple[int, str]]]:
    """{相對模組名: [(lineno, attr)…]} —— 整個 tesrpg/ 的 base 寫入點。"""
    found: dict[str, list[tuple[int, str]]] = {}
    for p in sorted(_TESRPG.rglob("*.py")):
        hits = _base_write_sites(ast.parse(p.read_text()))
        if hits:
            found[str(p.relative_to(_TESRPG))] = hits
    return found


def test_base_writes_only_in_allowlist():
    """🔴 最高紅線機器守:base 儲存只准白名單模組寫;其餘模組寫 base = 紅線違規。"""
    violations = {m: h for m, h in _scan().items() if m not in _ALLOWLIST}
    assert not violations, (
        "偵測到非白名單模組寫入 base(鐵律:成長/夾限只用 base_*、加成走疊加層、絕不寫 base):\n"
        + "\n".join(f"  {m}: {h}" for m, h in violations.items()))


def test_allowlist_is_not_stale():
    """白名單每個模組確實仍在寫 base(否則應從白名單剔除以收緊守門,別放寬紅線)。"""
    found = _scan()
    stale = [m for m in _ALLOWLIST if m not in found]
    assert not stale, f"白名單模組已不再寫 base → 應移除以收緊守門:{stale}"


def test_scanner_actually_catches_violations():
    """反向驗證:scanner 對白名單外的假 base 寫入確實會抓到(證明守門非空轉),且不誤判疊加層。"""
    bad = "def f(char):\n    char.skills['blade'] = 99\n    char.base_max_health = 1\n    char.attributes['strength'] += 5\n"
    attrs = {a for _, a in _base_write_sites(ast.parse(bad))}
    assert attrs == {"skills", "base_max_health", "attributes"}        # 三類寫入皆被抓
    safe = "def f(char):\n    char.equip_skill_bonus['blade'] = 5\n    char.mastery_attr_bonus['strength'] = 2\n    char.disease_skill_penalty = {}\n"
    assert _base_write_sites(ast.parse(safe)) == []                    # 疊加層不誤判


def run():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()


if __name__ == "__main__":
    run()
    print("✓ test_redline_base")

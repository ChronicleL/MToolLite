"""In-game modifier & QoL plugin (Phase 5) for RPG Maker MV / MZ."""

from __future__ import annotations

import shutil
from pathlib import Path

from .detector import GameInfo, detect_engine
from .injector_mvmz import BACKUP_SUFFIX, _format_plugins_js, _parse_plugins_js

CHEAT_PLUGIN_NAME = "MToolLite_Cheat"

_CHEAT_PLUGIN_JS = r"""//=============================================================================
// MToolLite_Cheat.js
//=============================================================================
/*:
 * @target MZ
 * @plugindesc Built-in QoL & Game Modifier overlay (Press F9 to toggle).
 * @author MToolLite
 */

(() => {
    "use strict";

    let speedMultiplier = 1;
    let noClip = false;
    let noEncounter = false;
    let panelVisible = false;
    let panelEl = null;

    // 1. Speed multiplier hook
    const _SceneManager_updateMain = SceneManager.updateMain;
    SceneManager.updateMain = function() {
        _SceneManager_updateMain.call(this);
        for (let i = 1; i < speedMultiplier; i++) {
            if (this._scene) {
                this.updateScene();
            }
        }
    };

    // 2. No-clip hook
    const _Game_Player_isThrough = Game_Player.prototype.isThrough;
    Game_Player.prototype.isThrough = function() {
        return noClip || _Game_Player_isThrough.call(this);
    };

    // 3. No-encounter hook
    const _Game_Player_executeEncounter = Game_Player.prototype.executeEncounter;
    Game_Player.prototype.executeEncounter = function() {
        if (noEncounter) return false;
        return _Game_Player_executeEncounter.call(this);
    };

    function createBtn(label, onClick) {
        const btn = document.createElement("button");
        btn.textContent = label;
        btn.style.cssText =
            "background:#2b3142;color:#f1f5f9;border:1px solid #475569;border-radius:6px;" +
            "padding:5px 8px;font-size:12px;cursor:pointer;text-align:left;";
        btn.onmouseenter = () => { btn.style.background = "#3b4258"; };
        btn.onmouseleave = () => { btn.style.background = "#2b3142"; };
        btn.onclick = (e) => {
            e.stopPropagation();
            onClick(btn);
        };
        return btn;
    }

    function ensurePanel() {
        if (panelEl || typeof document === "undefined") return;
        panelEl = document.createElement("div");
        panelEl.id = "mtoollite-cheat-panel";
        panelEl.style.cssText =
            "position:fixed;top:16px;right:16px;z-index:99999;width:240px;" +
            "background:rgba(15,23,42,0.92);color:#e2e8f0;border:1px solid #475569;" +
            "border-radius:10px;padding:12px;font-family:sans-serif;font-size:12px;" +
            "box-shadow:0 8px 24px rgba(0,0,0,0.45);display:none;";

        const title = document.createElement("div");
        title.textContent = "MToolLite 修改器 (F9 开关)";
        title.style.cssText = "font-weight:bold;margin-bottom:8px;color:#38bdf8;font-size:13px;";
        panelEl.appendChild(title);

        const grid = document.createElement("div");
        grid.style.cssText = "display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:8px;";

        grid.appendChild(createBtn("金币 +10000", () => {
            if (typeof $gameParty !== "undefined" && $gameParty) $gameParty.gainGold(10000);
        }));

        grid.appendChild(createBtn("全队满状态", () => {
            if (typeof $gameParty !== "undefined" && $gameParty) {
                $gameParty.members().forEach((a) => a.recoverAll());
            }
        }));

        grid.appendChild(createBtn("穿墙: 关", (b) => {
            noClip = !noClip;
            b.textContent = "穿墙: " + (noClip ? "开" : "关");
        }));

        grid.appendChild(createBtn("不遇敌: 关", (b) => {
            noEncounter = !noEncounter;
            b.textContent = "不遇敌: " + (noEncounter ? "开" : "关");
        }));

        grid.appendChild(createBtn("倍速: 1x", (b) => {
            const levels = [1, 2, 3, 5];
            const idx = (levels.indexOf(speedMultiplier) + 1) % levels.length;
            speedMultiplier = levels[idx];
            b.textContent = "倍速: " + speedMultiplier + "x";
        }));

        grid.appendChild(createBtn("强制存档", () => {
            if (typeof SceneManager !== "undefined" && typeof Scene_Save !== "undefined") {
                SceneManager.push(Scene_Save);
            }
        }));

        grid.appendChild(createBtn("战斗秒杀", () => {
            if (typeof $gameTroop !== "undefined" && $gameTroop && $gameParty && $gameParty.inBattle()) {
                $gameTroop.members().forEach((e) => e.setHp(0));
            }
        }));

        grid.appendChild(createBtn("关闭面板", () => {
            togglePanel(false);
        }));

        panelEl.appendChild(grid);

        // Variable / Switch quick editor
        const row = document.createElement("div");
        row.style.cssText = "display:flex;gap:4px;align-items:center;margin-top:6px;";
        const idInput = document.createElement("input");
        idInput.type = "number";
        idInput.placeholder = "ID";
        idInput.style.cssText = "width:54px;padding:3px;background:#1e293b;color:#fff;border:1px solid #475569;border-radius:4px;";
        const valInput = document.createElement("input");
        valInput.type = "number";
        valInput.placeholder = "值";
        valInput.style.cssText = "width:64px;padding:3px;background:#1e293b;color:#fff;border:1px solid #475569;border-radius:4px;";

        const setVarBtn = createBtn("改变量", () => {
            const id = parseInt(idInput.value, 10);
            const val = parseInt(valInput.value, 10);
            if (!isNaN(id) && !isNaN(val) && typeof $gameVariables !== "undefined" && $gameVariables) {
                $gameVariables.setValue(id, val);
            }
        });
        const setSwBtn = createBtn("开开关", () => {
            const id = parseInt(idInput.value, 10);
            if (!isNaN(id) && typeof $gameSwitches !== "undefined" && $gameSwitches) {
                $gameSwitches.setValue(id, !$gameSwitches.value(id));
            }
        });

        row.appendChild(idInput);
        row.appendChild(valInput);
        row.appendChild(setVarBtn);
        row.appendChild(setSwBtn);
        panelEl.appendChild(row);

        document.body.appendChild(panelEl);
    }

    function togglePanel(force) {
        ensurePanel();
        if (!panelEl) return;
        panelVisible = typeof force === "boolean" ? force : !panelVisible;
        panelEl.style.display = panelVisible ? "block" : "none";
    }

    if (typeof window !== "undefined") {
        window.addEventListener("keydown", (e) => {
            if (e.key === "F9") {
                e.preventDefault();
                togglePanel();
            }
        });
    }
})();
"""


def mount_cheat_mvmz(target: str | Path | GameInfo) -> dict[str, Path]:
    """Mount MToolLite_Cheat.js into an RPG Maker MV/MZ game."""
    info = target if isinstance(target, GameInfo) else detect_engine(target)
    if not info.is_mvmz or info.js_dir is None:
        raise ValueError(f"Target is not a valid RPG Maker MV/MZ game: {info.root_dir} ({info.engine})")

    plugins_js = info.js_dir / "plugins.js"
    if not plugins_js.is_file():
        raise FileNotFoundError(f"plugins.js not found at: {plugins_js}")

    backup_js = info.js_dir / f"plugins.js{BACKUP_SUFFIX}"
    if not backup_js.exists():
        shutil.copy2(plugins_js, backup_js)

    plugin_dir = info.js_dir / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / f"{CHEAT_PLUGIN_NAME}.js"
    plugin_file.write_text(_CHEAT_PLUGIN_JS, encoding="utf-8")

    plugins = _parse_plugins_js(plugins_js.read_text(encoding="utf-8-sig"))
    plugins = [p for p in plugins if p.get("name") != CHEAT_PLUGIN_NAME]
    plugins.append(
        {
            "name": CHEAT_PLUGIN_NAME,
            "status": True,
            "description": "Built-in QoL & Game Modifier overlay (Press F9 to toggle).",
            "parameters": {},
        }
    )
    plugins_js.write_text(_format_plugins_js(plugins), encoding="utf-8")

    return {
        "plugin": plugin_file,
        "plugins_js": plugins_js,
        "backup": backup_js,
    }


def unmount_cheat_mvmz(target: str | Path | GameInfo) -> bool:
    """Unmount MToolLite_Cheat.js from an RPG Maker MV/MZ game."""
    info = target if isinstance(target, GameInfo) else detect_engine(target)
    if not info.is_mvmz or info.js_dir is None:
        raise ValueError(f"Target is not a valid RPG Maker MV/MZ game: {info.root_dir} ({info.engine})")

    plugins_js = info.js_dir / "plugins.js"
    backup_js = info.js_dir / f"plugins.js{BACKUP_SUFFIX}"
    plugin_file = info.js_dir / "plugins" / f"{CHEAT_PLUGIN_NAME}.js"

    changed = False
    if plugins_js.is_file():
        plugins = _parse_plugins_js(plugins_js.read_text(encoding="utf-8-sig"))
        filtered = [p for p in plugins if p.get("name") != CHEAT_PLUGIN_NAME]
        if len(filtered) != len(plugins):
            has_translator = any(p.get("name") == "MToolLite_Translator" for p in filtered)
            if not has_translator and backup_js.is_file():
                shutil.move(str(backup_js), str(plugins_js))
            else:
                plugins_js.write_text(_format_plugins_js(filtered), encoding="utf-8")
            changed = True

    if plugin_file.is_file():
        plugin_file.unlink()
        changed = True

    return changed

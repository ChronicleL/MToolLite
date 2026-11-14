"""Non-destructive runtime translation plugin injector for RPG Maker MV / MZ."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from .detector import GameInfo, detect_engine

PLUGIN_NAME = "MToolLite_Translator"
BACKUP_SUFFIX = ".mtoollite.bak"

_PLUGIN_JS_TEMPLATE = r"""//=============================================================================
// MToolLite_Translator.js
//=============================================================================
/*:
 * @target MZ
 * @plugindesc Non-destructive runtime dictionary translator (Phase 2).
 * @author MToolLite
 *
 * @param captureUntranslated
 * @text Capture Untranslated Text
 * @type boolean
 * @default false
 */

(() => {
    "use strict";
    const pluginName = "MToolLite_Translator";
    const params = PluginManager.parameters(pluginName);
    const captureUntranslated = String(params["captureUntranslated"] || "false") === "true";

    let dict = {};
    const captured = {};

    function loadDictionarySync() {
        const candidates = ["data/ManualTransFile.json", "www/data/ManualTransFile.json", "ManualTransFile.json"];
        if (typeof require === "function" && Utils.isNwjs()) {
            const fs = require("fs");
            const path = require("path");
            const base = path.dirname(process.mainModule.filename);
            for (const rel of candidates) {
                const full = path.join(base, rel);
                if (fs.existsSync(full)) {
                    try {
                        const raw = fs.readFileSync(full, "utf8").replace(/^\uFEFF/, "");
                        dict = JSON.parse(raw);
                        return;
                    } catch (e) {
                        console.error("[MToolLite] Failed to parse dictionary:", full, e);
                    }
                }
            }
        }
        // Browser / XHR fallback
        for (const rel of ["data/ManualTransFile.json", "ManualTransFile.json"]) {
            try {
                const xhr = new XMLHttpRequest();
                xhr.open("GET", rel, false);
                xhr.send(null);
                if (xhr.status === 200 || xhr.status === 0) {
                    dict = JSON.parse(xhr.responseText.replace(/^\uFEFF/, ""));
                    return;
                }
            } catch (_) {
                // ignore
            }
        }
    }

    function saveCaptured() {
        if (!captureUntranslated || typeof require !== "function" || !Utils.isNwjs()) return;
        try {
            const fs = require("fs");
            const path = require("path");
            const base = path.dirname(process.mainModule.filename);
            const out = path.join(base, "untranslated_capture.json");
            fs.writeFileSync(out, JSON.stringify(captured, null, 2), "utf8");
        } catch (_) {}
    }

    function tr(text) {
        if (typeof text !== "string" || !text) return text;
        if (Object.prototype.hasOwnProperty.call(dict, text)) {
            const val = dict[text];
            if (typeof val === "string" && val.length > 0 && val !== "__FILTERED__") return val;
        }
        if (captureUntranslated && /[^\x00-\x7F]/.test(text) && !Object.prototype.hasOwnProperty.call(captured, text)) {
            captured[text] = "";
            saveCaptured();
        }
        return text;
    }

    function translateArrayStrings(arr) {
        if (!Array.isArray(arr)) return;
        for (let i = 0; i < arr.length; i++) {
            if (typeof arr[i] === "string") arr[i] = tr(arr[i]);
        }
    }

    function translateRecordFields(records, fields) {
        if (!Array.isArray(records)) return;
        for (const rec of records) {
            if (!rec || typeof rec !== "object") continue;
            for (const f of fields) {
                if (typeof rec[f] === "string") rec[f] = tr(rec[f]);
            }
        }
    }

    function translateSystem(sys) {
        if (!sys || typeof sys !== "object") return;
        if (typeof sys.gameTitle === "string") {
            sys.gameTitle = tr(sys.gameTitle);
            if (typeof document !== "undefined") document.title = sys.gameTitle;
        }
        if (typeof sys.currencyUnit === "string") sys.currencyUnit = tr(sys.currencyUnit);
        for (const k of ["elements", "equipTypes", "skillTypes", "weaponTypes", "armorTypes"]) {
            translateArrayStrings(sys[k]);
        }
        if (sys.terms && typeof sys.terms === "object") {
            for (const k of ["basic", "commands", "params"]) {
                translateArrayStrings(sys.terms[k]);
            }
            if (sys.terms.messages && typeof sys.terms.messages === "object") {
                for (const mk of Object.keys(sys.terms.messages)) {
                    if (typeof sys.terms.messages[mk] === "string") {
                        sys.terms.messages[mk] = tr(sys.terms.messages[mk]);
                    }
                }
            }
        }
    }

    loadDictionarySync();

    const _DataManager_onLoad = DataManager.onLoad;
    DataManager.onLoad = function(object) {
        _DataManager_onLoad.call(this, object);
        if (object === $dataSystem) translateSystem(object);
        else if (object === $dataActors) translateRecordFields(object, ["name", "nickname", "profile"]);
        else if (object === $dataClasses) translateRecordFields(object, ["name"]);
        else if (object === $dataSkills) translateRecordFields(object, ["name", "description", "message1", "message2"]);
        else if (object === $dataItems || object === $dataWeapons || object === $dataArmors) {
            translateRecordFields(object, ["name", "description"]);
        } else if (object === $dataEnemies) translateRecordFields(object, ["name"]);
        else if (object === $dataStates) {
            translateRecordFields(object, ["name", "description", "message1", "message2", "message3", "message4"]);
        } else if (object === $dataMap && object && typeof object.displayName === "string") {
            object.displayName = tr(object.displayName);
        }
    };

    const _Game_Message_add = Game_Message.prototype.add;
    Game_Message.prototype.add = function(text) {
        return _Game_Message_add.call(this, tr(text));
    };

    const _Game_Message_setChoices = Game_Message.prototype.setChoices;
    Game_Message.prototype.setChoices = function(choices, defaultType, cancelType) {
        const translated = Array.isArray(choices) ? choices.map(tr) : choices;
        return _Game_Message_setChoices.call(this, translated, defaultType, cancelType);
    };

    if (Game_Message.prototype.setSpeakerName) {
        const _Game_Message_setSpeakerName = Game_Message.prototype.setSpeakerName;
        Game_Message.prototype.setSpeakerName = function(speakerName) {
            return _Game_Message_setSpeakerName.call(this, tr(speakerName));
        };
    }

    const _Window_Base_convertEscapeCharacters = Window_Base.prototype.convertEscapeCharacters;
    Window_Base.prototype.convertEscapeCharacters = function(text) {
        return _Window_Base_convertEscapeCharacters.call(this, tr(text));
    };

    if (typeof Window_Command !== "undefined" && Window_Command.prototype && Window_Command.prototype.addCommand) {
        const _Window_Command_addCommand = Window_Command.prototype.addCommand;
        Window_Command.prototype.addCommand = function(name, symbol, enabled, ext) {
            return _Window_Command_addCommand.call(this, tr(name), symbol, enabled, ext);
        };
    }
})();
"""


def _parse_plugins_js(content: str) -> list[dict]:
    match = re.search(r"var\s+\$plugins\s*=\s*(\[[\s\S]*\])\s*;?", content)
    if not match:
        raise ValueError("Unable to parse $plugins array from plugins.js")
    return json.loads(match.group(1))


def _format_plugins_js(plugins: list[dict]) -> str:
    body = json.dumps(plugins, ensure_ascii=False, indent=4)
    return (
        "// Generated by RPG Maker.\n"
        "// Do not edit this file directly.\n"
        f"var $plugins =\n{body};\n"
    )


def mount_mvmz(
    target: str | Path | GameInfo,
    dict_path: str | Path | None = None,
    capture_untranslated: bool = False,
) -> dict[str, Path]:
    """Mount MToolLite_Translator.js into an RPG Maker MV/MZ game non-destructively."""
    info = target if isinstance(target, GameInfo) else detect_engine(target)
    if not info.is_mvmz or info.js_dir is None or info.data_dir is None:
        raise ValueError(f"Target is not a valid RPG Maker MV/MZ game: {info.root_dir} ({info.engine})")

    plugins_js = info.js_dir / "plugins.js"
    if not plugins_js.is_file():
        raise FileNotFoundError(f"plugins.js not found at: {plugins_js}")

    backup_js = info.js_dir / f"plugins.js{BACKUP_SUFFIX}"
    if not backup_js.exists():
        shutil.copy2(plugins_js, backup_js)

    # 1. Write plugin file
    plugin_dir = info.js_dir / "plugins"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    plugin_file = plugin_dir / f"{PLUGIN_NAME}.js"
    plugin_file.write_text(_PLUGIN_JS_TEMPLATE, encoding="utf-8")

    # 2. Copy dictionary if supplied (sanitizing __FILTERED__ tags so game never displays literal __FILTERED__)
    target_dict = info.data_dir / "ManualTransFile.json"
    if dict_path is not None:
        src_dict = Path(dict_path)
        if not src_dict.is_file():
            raise FileNotFoundError(f"Dictionary file not found: {src_dict}")
        try:
            raw_dict = json.loads(src_dict.read_text(encoding="utf-8-sig"))
            clean_dict = {k: ("" if v == "__FILTERED__" else v) for k, v in raw_dict.items()}
            target_dict.write_text(json.dumps(clean_dict, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            if src_dict.resolve() != target_dict.resolve():
                shutil.copy2(src_dict, target_dict)
    elif not target_dict.exists():
        target_dict.write_text("{}", encoding="utf-8")

    # 3. Update plugins.js
    plugins = _parse_plugins_js(plugins_js.read_text(encoding="utf-8-sig"))
    plugins = [p for p in plugins if p.get("name") != PLUGIN_NAME]
    plugins.insert(
        0,
        {
            "name": PLUGIN_NAME,
            "status": True,
            "description": "Non-destructive runtime dictionary translator (Phase 2).",
            "parameters": {"captureUntranslated": "true" if capture_untranslated else "false"},
        },
    )
    plugins_js.write_text(_format_plugins_js(plugins), encoding="utf-8")

    return {
        "plugin": plugin_file,
        "plugins_js": plugins_js,
        "backup": backup_js,
        "dictionary": target_dict,
    }


def unmount_mvmz(target: str | Path | GameInfo) -> bool:
    """Unmount MToolLite_Translator.js and restore original plugins.js."""
    info = target if isinstance(target, GameInfo) else detect_engine(target)
    if not info.is_mvmz or info.js_dir is None:
        raise ValueError(f"Target is not a valid RPG Maker MV/MZ game: {info.root_dir} ({info.engine})")

    plugins_js = info.js_dir / "plugins.js"
    backup_js = info.js_dir / f"plugins.js{BACKUP_SUFFIX}"
    plugin_file = info.js_dir / "plugins" / f"{PLUGIN_NAME}.js"

    restored = False
    if backup_js.is_file():
        shutil.move(str(backup_js), str(plugins_js))
        restored = True
    elif plugins_js.is_file():
        plugins = _parse_plugins_js(plugins_js.read_text(encoding="utf-8-sig"))
        filtered = [p for p in plugins if p.get("name") != PLUGIN_NAME]
        if len(filtered) != len(plugins):
            plugins_js.write_text(_format_plugins_js(filtered), encoding="utf-8")
            restored = True

    if plugin_file.is_file():
        plugin_file.unlink()
        restored = True

    return restored

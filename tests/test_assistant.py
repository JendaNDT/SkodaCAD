"""AI asistent: nástroje nad modelem, rozhovor se skutečnou knihovnou anthropic bez sítě
(přehrané odpovědi), jedno Zpět, chyby česky, nastavení a cena."""

import math

import pytest

from skodacad.assistant import (
    DEFAULT_MODEL,
    FALLBACK_BETA,
    AssistantError,
    AssistantSettings,
    Cancelled,
    ModelTools,
    Usage,
    build_report,
    make_client,
    new_assistant,
    offline_client,
    system_prompt,
)
from skodacad.session import ModelSession


def text(value):
    return {"type": "text", "text": value}


def tool(name, data, tool_id="toolu_1"):
    return {"type": "tool_use", "id": tool_id, "name": name, "input": data}


def opened(examples_dir, name="priruba"):
    session = ModelSession()
    session.open(examples_dir / f"{name}.json")
    return session


def conversation(session, turns, examples_dir=None, look=None, settings=None):
    requests = []
    tools = ModelTools(session, look)
    assistant = new_assistant(settings or AssistantSettings(), tools, examples_dir,
                              client=offline_client(turns, requests))
    return assistant, tools, requests


def ask(assistant, tools, session, prompt, events=None, run_tool=None):
    session.begin_group()
    try:
        return assistant.ask(prompt, session.document.to_dict(), build_report(session),
                             run_tool or tools.run,
                             (lambda kind, value: events.append((kind, value)))
                             if events is not None else None,
                             lambda: session.document.to_dict())
    finally:
        session.end_group()


def test_parameter_change_is_checked_by_rebuild_and_undone_in_one_step(examples_dir):
    session = opened(examples_dir)
    assistant, tools, requests = conversation(session, [
        ([text("Zvětším přírubu."), tool("set_parameters", {"values": {"D": 200, "t": "20"}})],
         "tool_use"),
        ([text("Hotovo – D 200 mm, tloušťka 20 mm.")], "end_turn"),
    ], examples_dir)
    events = []
    answer = ask(assistant, tools, session, "zvětši přírubu na D 200 a tloušťku 20", events)
    assert answer == "Hotovo – D 200 mm, tloušťka 20 mm."
    assert session.document.parameters["D"] == 200 and session.document.parameters["t"] == 20
    assert ("tool", "Nastavuji parametry: D = 200, t = 20") in events
    assert ("result", "✓ Parametry nastaveny.") in events

    first = requests[0]["body"]
    assert first["model"] == DEFAULT_MODEL and first["max_tokens"] == 64000
    assert first["output_config"] == {"effort": "high"}
    assert first["fallbacks"] == "default" and first["cache_control"] == {"type": "ephemeral"}
    assert FALLBACK_BETA in requests[0]["headers"]["anthropic-beta"]
    assert all(t["eager_input_streaming"] for t in first["tools"])
    assert "view_part" not in {t["name"] for t in first["tools"]}  # bez okna obrázky nejsou
    assert "<model>" in first["messages"][0]["content"]
    assert first["messages"][0]["content"].endswith("Požadavek uživatele: zvětši přírubu na D "
                                                     "200 a tloušťku 20")
    result = requests[1]["body"]["messages"][-1]["content"][0]  # souhrn přepočtu pro Claude
    assert result["tool_use_id"] == "toolu_1" and "is_error" not in result
    assert "Přepočet: v pořádku" in result["content"] and "X -100.00…100.00" in result["content"]

    session.undo()  # celá odpověď = jeden krok Zpět
    assert session.document.parameters["D"] == 165 and session.document.parameters["t"] == 18
    assert assistant.usage.input == 2000 and assistant.usage.output == 100


def test_new_part_from_description_and_feature_edits(examples_dir):
    session = ModelSession()
    session.new_document()
    box = {"name": "Krabička", "material": "PETG", "parameters": {"A": 60, "B": 40, "H": 20},
           "features": [
               {"id": "obrys", "type": "sketch", "plane": "XY",
                "elements": [{"shape": "rectangle", "width": "A", "height": "B"}]},
               {"id": "kvadr", "type": "extrude", "sketch": "obrys", "distance": "H"}]}
    hole = {"id": "dira", "type": "hole", "name": "Díra M4", "kind": "clearance", "size": "M4",
            "plane": "top", "positions": [[0, 0]], "through_all": True}
    assistant, tools, requests = conversation(session, [
        ([tool("replace_model", {"model": box}, "t1")], "tool_use"),
        ([tool("add_feature", {"feature": hole}, "t2"),
          tool("update_feature", {"id": "kvadr", "changes": {"name": "Kvádr"}}, "t3")],
         "tool_use"),
        ([tool("delete_feature", {"id": "obrys"}, "t4"),
          tool("update_feature", {"id": "dira", "changes": {"type": "sketch"}}, "t5"),
          tool("add_feature", {"feature": {**hole, "positions": [[10, 0]]}}, "t6")],
         "tool_use"),
        ([text("Krabička je hotová.")], "end_turn"),
    ])
    ask(assistant, tools, session, "udělej krabičku 60 × 40 × 20 s dírou M4")
    document = session.document
    assert document.name == "Krabička" and document.material == "PETG"
    assert [f["id"] for f in document.features] == ["obrys", "kvadr", "dira"]
    assert document.features[1]["name"] == "Kvádr"
    clearance = 4.5  # ISO 273 střední řada M4
    assert session.properties.volume_mm3 == pytest.approx(
        60 * 40 * 20 - math.pi * clearance**2 / 4 * 20)
    third = requests[3]["body"]["messages"][-1]["content"]  # odpovědi na chybné kroky
    assert [r.get("is_error", False) for r in third] == [True, True, True]
    assert "používá" in third[0]["content"]  # skicu potřebuje vysunutí
    assert "id ani typ" in third[1]["content"]
    assert "už v modelu je" in third[2]["content"]
    session.undo()
    assert session.document.features == []  # celý nový díl je jeden krok Zpět


def test_model_is_sent_again_only_when_user_changed_it(examples_dir):
    session = opened(examples_dir)
    assistant, tools, requests = conversation(session, [
        ([text("Příruba má 4 díry.")], "end_turn"),
        ([text("Objem je 311 cm³.")], "end_turn"),
        ([text("Teď má 6 děr.")], "end_turn"),
    ])
    ask(assistant, tools, session, "kolik má děr?")
    ask(assistant, tools, session, "jaký má objem?")
    second = requests[1]["body"]["messages"]
    assert second[-1] == {"role": "user", "content": "jaký má objem?"}
    session.set_parameter("n", "6")  # uživatel změnil model mezi dotazy
    ask(assistant, tools, session, "a teď?")
    last = requests[2]["body"]["messages"][-1]["content"]
    assert "Uživatel mezitím model změnil" in last and '"n": 6' in last
    assistant.reset()
    assert assistant.messages == [] and assistant.seen is None


def test_refusal_and_truncated_answer_are_czech_errors(examples_dir):
    session = opened(examples_dir)
    assistant, tools, _ = conversation(session, [([], "refusal")])
    with pytest.raises(AssistantError, match="odmítl"):
        ask(assistant, tools, session, "něco")
    assistant, tools, requests = conversation(session, [
        ([tool("set_parameters", {"values": {"D": 300}})], "max_tokens"),
        ([text("Zkusím to jinak.")], "end_turn"),
    ])
    with pytest.raises(AssistantError, match="useknula"):
        ask(assistant, tools, session, "zvětši")
    assert session.document.parameters["D"] == 165  # useknutý nástroj se nespustil
    ask(assistant, tools, session, "znovu")  # historie zůstala platná (tool_result doplněný)
    closed = requests[1]["body"]["messages"][2]["content"][0]
    assert closed["is_error"] and "useknutá" in closed["content"]


def test_stop_skips_remaining_tools(examples_dir):
    session = opened(examples_dir)
    assistant, tools, _ = conversation(session, [
        ([tool("set_parameters", {"values": {"D": 180}}, "a"),
          tool("set_parameters", {"values": {"t": 25}}, "b")], "tool_use"),
    ])

    def run_and_stop(name, data):
        output = tools.run(name, data)
        assistant.cancel()  # uživatel klikl Zastavit během prvního kroku
        return output

    with pytest.raises(Cancelled):
        ask(assistant, tools, session, "zvětši", run_tool=run_and_stop)
    assert session.document.parameters["D"] == 180 and session.document.parameters["t"] == 18
    last = assistant.messages[-1]["content"]
    assert last[1]["is_error"] and "zastavil" in last[1]["content"]


def test_view_tool_sends_png_only_when_window_can_render(examples_dir):
    session = opened(examples_dir)
    tools = ModelTools(session, look=lambda view: b"\x89PNG-test" if view == "iso" else None)
    assert "view_part" in {t["name"] for t in tools.definitions}
    image = tools.run("view_part", {"view": "iso"})
    assert image.content[0]["type"] == "image"
    assert image.content[0]["source"]["media_type"] == "image/png"
    assert tools.run("view_part", {"view": "current"}).is_error
    assert tools.run("view_part", {"view": "zboku"}).is_error


def test_tool_inputs_are_validated(examples_dir):
    session = opened(examples_dir)
    tools = ModelTools(session)
    assert tools.run("set_parameters", {"values": {"D": True}}).is_error
    assert tools.run("set_parameters", {}).is_error
    assert tools.run("add_feature", {"feature": {}}).is_error
    assert tools.run("move_feature", {"id": "deska", "after": 5}).is_error
    assert tools.run("set_part_info", {}).is_error
    assert tools.run("set_part_info", {"material": "kryptonit"}).is_error
    assert tools.run("neznamy", {}).is_error
    assert tools.run("get_model", "x").is_error
    assert session.can_undo is False  # nic z toho model nezměnilo
    moved = tools.run("move_feature", {"id": "sraz_otvor", "after": "deska"})
    assert not moved.is_error
    assert [f["id"] for f in session.document.features][:3] == ["obrys", "deska", "sraz_otvor"]
    model = tools.run("get_model", {})
    assert '"format": "skodacad"' in model.content and "Přepočet:" in model.content


def test_report_shows_errors_and_missing_part(examples_dir):
    session = ModelSession()
    session.new_document()
    assert "Díl zatím nemá žádné těleso" in build_report(session)
    session = opened(examples_dir)
    session.update_feature("deska", {**session.feature("deska"), "sketch": "neni"})
    report = build_report(session)
    assert "NĚKTERÉ PRVKY MAJÍ CHYBU" in report and "✕ [deska]" in report
    assert "– přeskočeno" in report or "CHYBA:" in report


def test_settings_are_saved_in_profile_and_key_from_environment(tmp_path, monkeypatch):
    import json

    path = tmp_path / "nastaveni.json"
    path.write_text(json.dumps({"jine": 1}), encoding="utf-8")
    AssistantSettings(api_key="sk-test", model="claude-sonnet-5-5", effort="low").save(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["jine"] == 1 and data["ai"]["model"] == "claude-sonnet-5-5"
    loaded = AssistantSettings.load(path)
    assert (loaded.api_key, loaded.model, loaded.effort) == ("sk-test", "claude-sonnet-5-5",
                                                             "low")
    assert AssistantSettings.load(tmp_path / "neni.json") == AssistantSettings()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    assert AssistantSettings().key() == "sk-env"
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(AssistantError, match="Chybí API klíč"):
        make_client(AssistantSettings())
    assert make_client(AssistantSettings(api_key="sk-x")).api_key == "sk-x"


def test_usage_cost_estimate():
    usage = Usage(input=10_000, output=2_000, cache_read=100_000, cache_write=20_000)
    # Opus 5.5: 4 $/M vstup, 20 $/M výstup, 0,20 $/M čtení, 5 $/M zápis do mezipaměti
    assert usage.cost_usd("claude-opus-5-5") == pytest.approx(0.04 + 0.04 + 0.02 + 0.1)
    assert usage.cost_usd("claude-sonnet-5-5") < usage.cost_usd("claude-opus-5-5")
    assert usage.describe("claude-opus-5-5") == "132 000 tokenů, orientačně 4,60 Kč"


def test_system_prompt_describes_whole_format(examples_dir):
    from skodacad.features import FEATURE_TYPES
    from skodacad.materials import DENSITIES_G_CM3

    prompt = system_prompt(examples_dir)
    assert "## Formát modelu" in prompt and "### Výběr hran" in prompt  # z README
    for feature_type in FEATURE_TYPES:
        assert f"- {feature_type} – " in prompt
    assert "- steel – Ocelový profil" in prompt
    assert all(material in prompt for material in DENSITIES_G_CM3)
    assert '<priklad soubor="priruba.json">' in prompt
    assert "Pro vývoj" not in prompt  # jen část o formátu

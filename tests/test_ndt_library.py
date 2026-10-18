"""Etapa 08: knihovna sond a materiálů, původ hodnot a přenos úhlu mezi materiály."""

import json
import math
from dataclasses import replace

import pytest

from skodacad.ndt.devices import DeviceError, Probe
from skodacad.ndt.library import (
    BUILTIN,
    MATERIALS,
    PROBES,
    USER_LIBRARY,
    LibraryError,
    Material,
    check_angle,
    describe,
    find_material,
    load_user_library,
    save_user_material,
    save_user_probe,
    transfer_angle,
    transferred,
    user_library_path,
)
from skodacad.ndt.ut import BeamError


def snell(beta, c_from, c_to):
    return math.degrees(math.asin(c_to / c_from * math.sin(math.radians(beta))))


@pytest.mark.parametrize("beta,material,expected", [
    (45, "hlinik", 43.09), (70, "hlinik", 65.2), (70, "nerez", 64.81), (45, "med", 29.55),
    (70, "med", 40.95), (60, "mosaz", 34.52)])
def test_angle_transfer_from_steel_follows_snell(beta, material, expected):
    found = transfer_angle(beta, MATERIALS["ocel"].c_t, MATERIALS[material].c_t)
    assert found == pytest.approx(snell(beta, 3240, MATERIALS[material].c_t))
    assert found == pytest.approx(expected, abs=0.01)
    # zpět do oceli = původní úhel (stejná předsádka)
    assert transfer_angle(found, MATERIALS[material].c_t, 3240) == pytest.approx(beta)


@pytest.mark.parametrize("args,message", [((80, 3000, 3240), "totální odraz"),
                                          ((45, 50, 3240), "100–20000"),
                                          ((0, 3240, 3130), "mezi 0° a 90°")])
def test_angle_transfer_refuses_impossible_cases_in_czech(args, message):
    with pytest.raises(BeamError, match=message):
        transfer_angle(*args)


def test_builtin_materials_have_sources_and_never_claim_verification():
    assert set(MATERIALS) == {"ocel", "nerez", "hlinik", "med", "mosaz"}
    for key, material in MATERIALS.items():
        assert material.profile == key and material.source.count(",") >= 1  # aspoň 2 zdroje
        assert 0 < material.c_t < material.c_l
        assert find_material(material.name) is material
    assert find_material("litina") is None and find_material("Hliník") is MATERIALS["hlinik"]
    texts = [p.name for p in PROBES.values()] + [m.note for m in MATERIALS.values()]
    assert not any(word in text.lower() for text in texts
                   for word in ("certifik", "ověřen", "kalibrovan"))


def test_generic_probe_profiles_keep_todays_default():
    assert len(PROBES) == 11 and all(p.name.startswith("Obecná") for p in PROBES.values())
    standard = PROBES["uhlova-standardni-45"].probe
    geometry = {k: v for k, v in standard.to_dict().items()
                if k not in ("profile", "library", "origins", "angle_material")}
    assert geometry == Probe.angle().to_dict()  # profil 45° = dnešní výchozí sonda
    assert standard.library == BUILTIN and standard.origin("beam_angle") == "profile"
    straight = PROBES["prima-10"].probe
    assert straight.to_dict()["diameter"] == 10 and not straight.angle_material
    assert straight.wave_mode == "longitudinal" and standard.wave_mode == "shear"


def test_probe_metadata_round_trip_and_old_records_unchanged():
    assert set(Probe.angle().to_dict()) == {"kind", "length", "width", "front", "beam_angle",
                                            "height", "bounces", "max_gap", "reserve"}
    probe = Probe.angle(beam_angle=70, origins={"beam_angle": "measured", "front": "measured"},
                        angle_material="ocel", frequency_mhz=4, crystal_mm=8,
                        source="blok č. 1, 18. 10. 2026")
    again = Probe.from_dict(json.loads(json.dumps(probe.to_dict())))
    assert again == probe and hash(again) == hash(probe)
    assert again.origin("front") == "measured" and again.origin("width") == ""


@pytest.mark.parametrize("extra,message", [
    ({"origins": {"diameter": "measured"}}, "taková hodnota"),
    ({"origins": {"beam_angle": "certified"}}, "musí být jeden z"),
    ({"origins": ["beam_angle"]}, "musí být objekt"),
    ({"frequency_mhz": 200}, "0 \\(neuvedeno\\)"),
    ({"wave": "surface"}, "Druh vlny"),
    ({"profile": 5}, "musí být text")])
def test_probe_metadata_is_checked(extra, message):
    with pytest.raises(DeviceError, match=message):
        Probe.from_dict({"kind": "angle", **extra})
    with pytest.raises(DeviceError, match="jen u úhlové"):
        Probe.from_dict({"kind": "straight", "angle_material": "ocel"})


def test_angle_check_states_and_explicit_transfer():
    probe = PROBES["uhlova-standardni-70"].probe
    assert check_angle(Probe.angle(), MATERIALS["med"]).state == "none"  # úhel přímo v dílu
    assert check_angle(probe, None, "ocel").state == "ok"
    assert check_angle(probe, MATERIALS["ocel"]).state == "ok"
    unknown = check_angle(probe, None, "hliník")
    assert unknown.state == "unknown" and "materiál pro UT není zvolený" in unknown.text
    custom = Material("litina GG25", 4600, 0, "měření na vzorku")
    assert "neznám" in check_angle(probe, custom).text
    found = check_angle(probe, MATERIALS["hlinik"])
    assert found.state == "differs" and found.beta_to == pytest.approx(65.2, abs=0.01)
    assert "Přepočítej úhel" in found.text and probe.beam_angle == 70  # nic se nezměnilo samo
    moved = transferred(probe, found)
    assert moved.beam_angle == 65.2 and moved.angle_material == "hliník"
    assert moved.origin("beam_angle") == "transferred" and "Snellův zákon" in moved.angle_note
    assert check_angle(moved, MATERIALS["hlinik"]).state == "ok"
    with pytest.raises(BeamError):
        transferred(moved, check_angle(moved, MATERIALS["hlinik"]))
    steep = replace(probe, beam_angle=80)
    fast = Material("rychlý", 9000, 4000, "zkouška")
    assert check_angle(steep, fast).state == "error"


def test_describe_lists_profile_origins_material_and_info_only_when_set():
    assert describe(Probe.angle()) == []
    probe = replace(PROBES["uhlova-standardni-70"].probe, frequency_mhz=4, crystal_mm=8)
    check = check_angle(probe, MATERIALS["hlinik"])
    text = "\n".join(describe(probe, MATERIALS["hlinik"], check))
    assert "Profil sondy: Obecná úhlová standardní" in text and BUILTIN in text
    assert "obecný profil – " in text and "Materiál pro UT: hliník – podélná 6320 m/s" in text
    assert "Orientační hodnoty" in text and check.text in text
    assert "Frekvence 4 MHz, měnič Ø 8 mm – jen informativně" in text
    own = Material("ocel S355", 5900, 3230, "měření na vzorku")
    assert "Orientační" not in "\n".join(describe(probe, own))


def test_material_record_checks():
    assert Material.from_dict(MATERIALS["ocel"].to_dict()) == MATERIALS["ocel"]
    for bad, message in [({"name": "x", "c_l": 5000, "c_t": 6000, "source": "s"}, "menší"),
                         ({"name": "x", "c_l": 50, "c_t": 0, "source": "s"}, "100–20000"),
                         ({"name": "x", "c_l": 0, "c_t": 0, "source": "s"}, "aspoň jednu"),
                         ({"name": "x", "c_l": 5000, "c_t": 3000, "source": ""}, "zdroj"),
                         ({"name": "x", "c_l": 5000, "density": 7}, "neznámá")]:
        with pytest.raises(LibraryError, match=message):
            Material.from_dict(bad)


def test_user_library_save_load_and_damaged_file(tmp_path):
    path = user_library_path(tmp_path)
    assert load_user_library(path).probes == {} and not path.exists()
    probe = replace(PROBES["uhlova-mala-60"].probe, origins={"beam_angle": "measured"},
                    beam_angle=61.5, source="blok č. 2")
    stored = save_user_probe(path, "Moje malá 60°", probe)
    assert stored.profile == "Moje malá 60°" and stored.library == USER_LIBRARY
    save_user_material(path, Material("ocel S355", 5900, 3230, "měření na vzorku"))
    save_user_probe(path, "Moje malá 60°", replace(probe, beam_angle=61.0))  # přepíše
    library = load_user_library(path)
    assert list(library.probes) == ["Moje malá 60°"] and library.problems == []
    assert library.probes["Moje malá 60°"].beam_angle == 61.0
    assert library.probes["Moje malá 60°"].origin("beam_angle") == "measured"
    assert find_material("ocel s355", library.materials).c_t == 3230
    data = json.loads(path.read_text(encoding="utf-8"))
    data["probes"].append({"name": "vadná", "device": {"kind": "angle", "length": -1}})
    data["materials"].append({"name": "bez zdroje", "c_l": 5000})
    path.write_text(json.dumps(data), encoding="utf-8")
    library = load_user_library(path)
    assert list(library.probes) == ["Moje malá 60°"] and len(library.problems) == 2
    assert "sonda č. 2 vynechána" in library.problems[0]
    for content in ("{nesmysl", json.dumps({"format": "jiný"}),
                    json.dumps({"format": "skodacad-ndt-knihovna", "version": 99})):
        path.write_text(content, encoding="utf-8")
        assert load_user_library(path).problems
        with pytest.raises(LibraryError):
            save_user_probe(path, "nová", probe)  # poškozený soubor se nepřepíše
        assert path.read_text(encoding="utf-8") == content

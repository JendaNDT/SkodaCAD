# P7.72–P7.74 – texty a pořadí karty díry podle rámu 2a

*Navazuje na [P7.68–P7.71](p7-68-karta-prvku-rez-a-skicar.md) (PR #136, `a70e9c3`, ověřeně
vydané). Pokyn autora „ok, udělej to“ (9. 11. 2026) na doporučení srovnat názvy voleb
s návrhem. Změna mění i formulář úprav, proto byla předem odsouhlasená.*

## Co se změnilo

- **P7.72 Krátké texty voleb.** Nabídky ve formulářích prvků ukazují krátký text s velkým
  počátečním písmenem:
  - druh díry: „Válcové zahloubení“ místo „válcové zahloubení pro imbus (ISO 4762)“,
    „Kuželové zahloubení 90°“, „Závitová“, „Průchozí pro šroub“, „3D tisk – šroub do plastu“;
  - plocha: „Horní plocha“ místo „horní plocha dílu“ (stejně spodní, přední, zadní, pravá,
    levá);
  - ostatní volby jen s velkým písmenem („Nové těleso“, „Plocha vybraná ve 3D …“).
  - Celý původní popis je v bublině položky i nabídky.
  - U díry se pole jmenuje „Na ploše“ (dřív „Rovina“) a polohy „Polohy děr“ (dřív „Středy
    děr“), jako v návrhu.
- **P7.73 Pořadí.** Zaškrtávátko „Skrz celý díl“ je nad polohami děr, jako v rámu 2a.
  Polohy jsou ve formuláři díry až za volbami hloubky a závitu.
- **P7.74 Popisek pod hlavičkou.** Řádek „**Díra** (upinani)“ je při prohlížení jen šedý
  menší popisek „Díra · upinani“. Název prvku je v hlavičce karty. Barvu bere ze vzhledu,
  takže sedí i v tmavém.
- Uložený model, popis prvku ve stromu, příkazová řádka (`skodacad`), AI ani výpočty se
  nemění: mění se jen texty v okně. Formát souborů zůstává 34.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_model_card.py` (+1, upravený 1) | `choice_text`: zkrácení a velké písmeno; skutečný výběr díry: „Válcové zahloubení“ s plným popisem v bublině a daty `counterbore`, „Na ploše: Horní plocha“ (`top`), „Skrz celý díl“ nad sekcí „Polohy děr  4“, šedý popisek „Díra · upinani“ bez tučného písma |
| `tests/test_gui.py` (upravený 1) | rovina skici vybraná ve 3D: „Plocha vybraná ve 3D (u bodu …)“ |
| testy okna, karet, náhledů a schématu (Linux) | viz PR |
| self-test „Levá karta“ (Linux Xvfb, skutečné 3D) | „Válcové zahloubení · Na ploše: Horní plocha“, sekce „Polohy děr  4“; celý self-test viz PR |
| skript responzivity (5 velikostí × 7 rámů) | viz PR |

Srovnání s návrhem (Linux Xvfb, 1440 × 900):
[2a světlý](p7-72-srovnani/2a-model-svetly-srovnani.png),
[2b tmavý](p7-72-srovnani/2b-model-tmavy-srovnani.png).

## Meze

- Karta prvku dál ukazuje hodnoty jen pro čtení s tlačítkem *Upravit prvek* (P7.6); návrh
  kreslí rovnou úpravu se Zrušit / Potvrdit.
- Návrh má „Řez skrz celý díl“ a sbalený „Vlastní průměr · podle tabulky“; aplikace má
  „Skrz celý díl“ a „Další volby“ se všemi nevyplněnými volbami (P7.69).
- Zkrácené jsou jen druhy díry a plochy dílu. Ostatní volby mají jen velké písmeno.

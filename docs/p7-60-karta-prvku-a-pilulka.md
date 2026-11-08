# P7.60 – tabulka poloh, čitelné hodnoty a pilulka „Vybráno“ (rám 2a)

*Navazuje na [P7.59](p7-59-strom-a-karta-prvku.md) (PR #132, `c85a561`, ověřeně vydané).
Pokračování na pokyn autora „ok, pokračuj“ (8. 11. 2026).*

## Co se změnilo

- **Polohy jako číslovaná tabulka.** Při prohlížení prvku ukazuje karta „**Středy děr** · 4“
  a pod tím řádky „1 · A/2 - e · B/2 - e“ písmem se stejně širokými znaky, jako v rámu 2a.
  Textové pole s polohami zůstává v kartě skryté. Úprava přes *Upravit prvek* ho ukáže
  jako dřív.
- **Hodnoty jen pro čtení běžnou barvou.** Rozbalovací pole a zaškrtávátka v prohlížecí
  kartě dál nejdou změnit, ale už nejsou šedá. Po přepnutí vzhledu (světlý/tmavý) se barva
  obnoví.
- **Pilulka „Vybráno: …“.** Když okno zrovna nic nehlásí a ve stromu je vybraný prvek,
  pilulka ukáže například „Vybráno: Upínání · M6 ×4“. Hlášení okna (třeba „Uloženo“) má
  přednost. Bez výběru je tam dál odkaz „F1: zkratky a ovládání myší“.
- Model, formát souborů (34), `ModelSession` ani výpočty se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_model_card.py` (+1) | výběr řádku „Upínání“: pilulka „Vybráno: Upínání · M6 ×4“, tabulka se 4 číslovanými řádky, skryté pole poloh beze změny, rozbalovací pole neaktivní, ale s běžnou barvou textu; hlášení má přednost, po zrušení výběru zase „F1: …“ |
| `tests/test_gui.py` (upravený 1) | zápis poloh Tabem se zkouší v plném formuláři (`set_compact(False)`), prohlížecí karta ukazuje tabulku |
| testy okna, karet, pilulky, náhledů, skicáře, stromu a formulářů (Linux) | 192 + 424 úspěšných, 0 chyb; `ruff check src tests` bez nálezů |
| self-test „Levá karta“ (Linux Xvfb, skutečné 3D) | skutečný klik na řádek: tabulka „Středy děr · 4“, pole „Druh“ neaktivní v běžné barvě, pilulka „Vybráno: Upínání · M6 ×4“, karta 302 px; celý self-test OK |

Srovnání s návrhem (Linux Xvfb, 1440 × 900):
[2a světlý](p7-60-srovnani/2a-model-svetly-srovnani.png),
[2b tmavý](p7-60-srovnani/2b-model-tmavy-srovnani.png).

## Meze

- Pilulka ukazuje stejný krátký údaj jako strom („M6 ×4“). V návrhu je text „4 díry M6“.
- Sekce „Vlastní průměr“ se nevykresluje sbalená. Nevyplněné volby jsou jen spočítané
  v závěrečné větě.
- Dlouhý druh díry se v 304 px ořízne („válcové zahloubení pro imbus (IS…“).
- Šířku a zalomení se skutečným písmem Windows a macOS ověří až self-test na GitHubu.

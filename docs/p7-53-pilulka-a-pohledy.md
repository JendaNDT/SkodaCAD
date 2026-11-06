# P7.53 – stavová pilulka a přepínač pohledů (vydání B, krok 3)

*Součást [plánu nového okna](p7-48-plan-noveho-okna.md); rozhodnutí R5 (zprávy
v pilulce, nápověda k myši pod F1) schválil autor 6. 11. 2026.*

## Co se změnilo

- **Stavová pilulka** (dole uprostřed 3D, výška 32 px, 12 px, `gui/status_pill.py`):
  - vlevo stav „✓ Spočítáno“ (`--ok`), „✕ Chyba v modelu“ (`--err`) nebo „Bez dílu“;
  - při přepočtu místo stavu „⏳ Přepočítávám… 3 s“ s běžícím pruhem a Zastavit
    (dřív ve stavovém řádku);
  - za oddělovačem poslední zpráva okna (výběr, uložení, chyby zadání). Dlouhá zpráva
    se zkrátí „…“ a celá je v bublině.
- **Stavový řádek Qt je skrytý (R5).** Zprávy do něj okno zapisuje dál (`statusBar()`),
  pilulka je jen čte. Místo dlouhé nápovědy k myši pilulka ukazuje „F1: zkratky
  a ovládání myší“ a celá nápověda je v bublině a pod F1 (P7.45/P7.46). 3D pohled
  je o výšku stavového řádku vyšší.
- **Přepínač pohledů** (vpravo dole): Izo | Zepředu | Shora | Celý díl.
  - Jsou to tytéž akce jako v nabídce a zkratky 0/1/7/F.
  - Naposledy zvolený pohled je zvýrazněný (`--accentbg`, `--accent`, 600), i když
    byl zvolen zkratkou nebo z nabídky.
  - Když pravá karta sahá až dolů, přepínač se posune vlevo vedle ní a nepřekryje ji.
- **„Celý díl“** nově obchází i pilulku a přepínač dole, takže díl se vejde mezi karty,
  pod paletu a nad pilulku.
- Model, výpočty ani formát se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_status_pill.py` (4) | stavy, zkrácení dlouhé zprávy s bublinou, ukazatel přepočtu místo stavu; zprávy okna v pilulce, skrytý stavový řádek, nápověda → „F1…“; přepočet a Zastavit v pilulce; chybný model → „✕ Chyba v modelu“; poloha dole uprostřed a vpravo dole bez překryvu; tlačítka pohledů spouští akce a zvýraznění sleduje i zkratky; dostupnost bez přepsání krátkých názvů; přepínač vedle vysoké pravé karty; dolní okraj pro „Celý díl“ |
| `tests/test_floating.py`, `tests/test_viewer_surface.py` | okraje karet a „Celý díl“ se čtyřmi okraji |
| testy okna, pozadí (přepočet, Zastavit), filtrů, sestavy | viz PR |
| self-test „Pilulka a pohledy“ (Linux Xvfb) | stavový řádek skrytý, „✓ Spočítáno | F1…“, obě karty dole uvnitř 3D bez překryvu; skutečný klik na Shora natočí kameru OCCT na +Z; po Celý díl leží nejnižší roh dílu nad pilulkou (648 < 782 px) |

Snímek: [okno s pilulkou a přepínačem](p7-48-snimky/okno-pilulka.png).

## Meze

- Okno sestavy má svůj stavový řádek beze změny (R6).
- Náhled prvku píše do pilulky „Náhled prvku · Potvrdit / Zrušit · Esc zruší“. Tečka
  „● Náhled“ podle rámu 3a přijde s kartami nástrojů (P7.54).

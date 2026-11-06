# P7.52 – pravá karta (inspektor) bez posouvání (vydání B, krok 2)

*Součást [plánu nového okna](p7-48-plan-noveho-okna.md); rozhodnutí R1–R7 schválil
autor 6. 11. 2026.*

## Co se změnilo

- **Hlavička každé pravé karty** podle návrhu 1a:
  - malý titulek (11 px, `--fg3`) s ▾ otevře výběr panelů. Při úpravě nebo novém
    prvku ukazuje „Úprava prvku · náhled“ / „Nový prvek · náhled“;
  - velký titulek (15/700) ukazuje kontext, u Úpravy prvku název vybraného prvku
    („Upínání“), jinak název panelu;
  - × zavře panel jako dosud.
- **Karta neposouvá:** pravá karta je vysoká podle skutečného obsahu
  (`floating.ContentScroll`), nejvýš celá výška 3D pohledu.
  - Dřív se každá posuvná oblast ohlašovala nejvýš asi 24 řádky, takže karta zůstala
    malá a obsah se posouval.
  - Výška se počítá pro skutečnou šířku karty, včetně zalomených popisků.
  - Posuvník zůstává jen jako pojistka u malého okna. Self-test hlásí upozornění,
    když se formulář díry při 1440 × 900 nevejde.
- **Formulář prvku je mřížka:** popisek vlevo zarovnaný doprava, pole vpravo, mezery
  8 × 10. Dlouhé položky (nabídky s dlouhým textem, obrysy, vodítka) se zalomí pod
  popisek, aby měly celou šířku. Pole jsou 22 px, `--ctl`, s linkou `--sep2` a modrou
  linkou při fokusu.
- **Patička náhledu:** „Esc zahodí“ · Náhled · Zrušit (vedlejší) · **Potvrdit**
  (primární `--btn`).
  - Hlášení o náhledu je v rámečku `--accentbg`.
  - Vysvětlení Potvrdit/Zrušit je v bublině tlačítka Potvrdit.
  - Popis druhu prvku je v bublině nadpisu formuláře.
  - Díky tomu se formulář díry z ukázky desky vejde při 1440 × 900 bez posouvání.
- **Sbalitelné sekce** (`workspace.Section`) mají linku nahoře, ▶/▼, titulek 600
  a volitelně počet vpravo (`set_count`). Platí i pro sekce okna sestavy.
- Model, výpočty ani formát se nemění. Potvrzení dál přidá jeden krok Zpět.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_inspector_card.py` (4) | posuvná oblast ohlásí celý obsah, běžná ne; posuvník jen v menším pohledu; titulek karty sleduje výběr i náhled; patička v pořadí Esc zahodí · Náhled · Zrušit · Potvrdit a role tlačítek; výška karty = obsah, nejvýš pohled; popisky formuláře vpravo; sekce s počtem a přepínáním |
| testy okna, náhledu a úprav prvků, vodítek, filtrů, sestavy | viz PR |
| self-test „Pravá karta“ (Linux Xvfb, 1440 × 900) | titulek „Upínání“, náhled „Úprava prvku · náhled“, patička vidět ve správném pořadí, skutečné Esc zavře náhled bez změny modelu a historie, formulář díry se vešel (karta 769 px) |

Snímky: [karta náhledu](p7-48-snimky/prava-karta-nahled.png), [celé okno](p7-48-snimky/okno-prava-karta.png).

## Meze

- Návrh 2a ukazuje „Polohy děr · 4“ a „Vlastní průměr“ jako sbalitelné sekce. Formuláře
  se zatím skládají ze schématu prvku bez skupin. Rozdělení do sekcí podle druhu prvku
  je samostatné rozšíření; posuvník je do té doby pojistka.
- Rozbalovací nabídky ve formuláři mají systémový vzhled (Qt nebo macOS), jen pole
  a tlačítka mají styl z návrhu.

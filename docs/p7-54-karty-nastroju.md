# P7.54 – karty Měření, Řez, Mapa tloušťky a náhled prvku (vydání C, krok 1)

*Součást [plánu nového okna](p7-48-plan-noveho-okna.md); rozhodnutí R1–R7 schválil
autor 6. 11. 2026. Pokračování na pokyn autora „ok, pokračuj P7.54“ (7. 11. 2026).
Vzorem jsou rámy 3a (náhled prvku), 3b (měření) a 3c (řez) v
[`p7-48-navrh-okna/obrazovky/`](p7-48-navrh-okna/obrazovky/).*

## Co se změnilo

- **Karta Měření (rám 3b):**
  - nahoře je, co je vybráno („Vybráno: 2 plochy“), bez výběru krátký návod;
  - výsledky jsou **řádky**: popisek vlevo, hodnota vpravo. Řádek, jehož zelená čára je
    ve 3D, má světle zelený podklad a hodnotu zeleně tučně. Seznam se neposouvá, je
    vysoký přesně podle počtu výsledků;
  - pod výsledky jsou v jedné řadě tlačítka **Uložit** (hlavní), Přejmenovat…, Smazat;
  - **Uložená měření** jsou sbalitelná sekce (vpravo zkratka Ctrl+Shift+M) s poznámkou
    „Přepočítají se při každé změně modelu.“, filtrem a řádky „✓ název … hodnota“.
    Bez uložených měření je tam krátká rada. Ctrl+Shift+M sekci rozbalí;
  - **Příprava kót výkresu** je sbalitelná sekce, ve výchozím stavu sbalená. Ovládání
    zůstalo stejné, jen je přeskládané do užších řádků, aby se vešlo do karty 304 px
    (dřív přetékalo vpravo).
- **Karta Řez (rám 3c):** mřížka Řez (zaškrtávátko „zapnutý (klávesa R)“), Rovina,
  Poloha (posuvník a vedle pole v mm), pod ní rozsah „−40.00 až 40.00 mm“. Pak tlačítka
  Otočit stranu a Export DXF/SVG…, linka, řádek **Plocha řezu** se vzorkem barvy
  (cihlová jako ve 3D, pod objemovou mapou pokrytí šedá) a šedý rámeček „Řez je jen
  pohled – model se nemění a do souboru se neukládá…“.
- **Karta Mapa tloušťky** má stejný vzor: mřížka nastavení, tlačítka Zapnout mapu
  (hlavní) / Vypnout mapu a Export CSV…, linka, barevná škála a souhrn.
- **Náhled prvku (rám 3a):**
  - ve stromu je navíc řádek nového prvku (kurzívou, modře, s modrým čárkovaným
    rámečkem a slovem „náhled“ vpravo) na místě, kam se prvek vloží. U úpravy
    existujícího prvku se takto označí jeho řádek. Řádek nejde vybrat a po potvrzení
    nebo zrušení zmizí;
  - plovoucí paleta příkazů je během náhledu neaktivní (šedá);
  - pilulka ukazuje „● Náhled · Sražení 1 | Potvrzení přidá jeden krok Zpět · Esc zruší“.
- **Pilulka** ukazuje vlevo místo „✓ Spočítáno“ to, co je právě ve 3D:
  - náhled prvku (modře),
  - hlavní hodnotu měření „Rozteč os 40.00 mm“ (zeleně, jen s otevřeným panelem Měření;
    zpráva vedle pak hodnotu neopakuje, ale říká „Zelená čára ukazuje, odkud kam se
    měřilo“),
  - polohu řezu „Řez · Y = 0 mm“.

  Chyba modelu a přepočet mají přednost.
- Model, výpočty, formát souborů (34) ani zkratky se nemění. Všechna tlačítka spouští
  tytéž akce jako nabídky a klávesy.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_tool_cards.py` (8) | rozdělení „popisek: hodnota“; řádky měření (výška = počet řádků, bez posuvníku), tlačítka Uložit/Přejmenovat…/Smazat a jejich role, pilulka s hodnotou jen v panelu Měření a bez zdvojení ve zprávě, skutečné kliknutí Uložit a Smazat, stav uloženého měření ✓; Ctrl+Shift+M rozbalí sbalenou sekci; sekce kót sbalená, pole nerozšíří kartu; karta Řez (zaškrtávátko, plocha, rozsah, šedý rámeček, pilulka i s jiným panelem, Otočit stranu); karta Mapa (Zapnout/Vypnout mapu, Export CSV); náhled nového prvku (řádek na konci stromu bez id, nejde vybrat, přežije obnovu stromu, pilulka, paleta neaktivní, po zrušení vše zpět); náhled úpravy označí existující řádek, Potvrdit označení zruší |
| `tests/test_gui.py` – řez | upraveno: plocha je ve vlastním řádku se vzorkem `#d16154`, pilulka „Řez · Y = 0 mm“ / „Y = 40 mm“, vypnutí a zapnutí zaškrtávátkem v kartě |
| testy okna, pozadí, filtrů, hledání, oblíbených, náhledů, skicáře, NDT oken a sestavy (25 souborů, Linux) | 597 úspěšných, 0 chyb; `ruff check src tests` bez nálezů |
| self-test „Karty nástrojů“ (Linux Xvfb, 1440 × 900, skutečné 3D) | „Rozteč os: 40.00 mm“ v pilulce; skutečné kliknutí Uložit a Smazat; řez zaškrtávátkem 1 493.91 mm² s pilulkou; náhled „● Náhled · Sražení 1“ s řádkem ve stromu a neaktivní paletou; skutečné Esc zruší náhled bez změny modelu a historie; obsah karet Měření (i s rozbalenými kótami), Řez a Mapa je nejvýš tak široký jako karta (288/302/302 px) |

Snímky (Linux Xvfb, `examples/deska.json`, 1440 × 900):
[měření](p7-48-snimky/karta-mereni.png), [měření s kótami výkresu](p7-48-snimky/karta-mereni-koty.png),
[řez](p7-48-snimky/karta-rez.png), [náhled prvku](p7-48-snimky/nahled-prvku.png),
[mapa tloušťky](p7-48-snimky/karta-mapa.png).

## Meze

- **Popisek hodnoty ve 3D** zůstává zelený text bez zeleného štítku z rámu 3b. Podklad
  pod popiskem (`Aspect_TODT_SUBTITLE`) shazuje základní ovladač OpenGL ve Windows
  (viz Známé pasti – měření).
- **Hrany v náhledu sražení** popisuje formulář dál významem („hrany na horní ploše,
  poloměr …“), ne krátce „Obvod horní plochy“ jako v rámu 3a. Krátký popis výběru je
  samostatné rozšíření editoru prvků.
- Desetinná čísla jsou dál s tečkou („40.00 mm“), jako v celé aplikaci; rámy návrhu
  mají čárku.
- Řádek „Osy rovnoběžné“ z rámu 3b ukáže karta, až ho vrátí výpočet měření (jádro se
  v P7.54 nemění).
- Zapnutí řezu je v kartě zaškrtávátko, protože tři tlačítka v řadě se do 304 px
  nevejdou. Rám 3c ukazuje kartu už se zapnutým řezem.
- Rozbalená sekce kót výkresu je delší než výška okna 900 px; tam karta použije
  posuvník jako pojistku (pravidlo P7.52). Ve výchozím stavu je sbalená.

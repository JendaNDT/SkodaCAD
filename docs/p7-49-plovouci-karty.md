# P7.49 – plovoucí karty nad 3D (vydání A, krok 2)

*Součást [plánu nového okna](p7-48-plan-noveho-okna.md); rozhodnutí R1 (neprůhledné
karty) schválil autor 6. 11. 2026.*

## Co se změnilo

- **3D pohled zabírá celou šířku okna.** Levý panel (strom a parametry) a pravé panely
  (Úprava prvku, Měření, Mapa tloušťky, Řez, NDT, NDT audit, Konstrukční návrh,
  AI asistent) už nejsou boční docky. Jsou to **plovoucí karty nad 3D** v místech podle
  návrhu 1a: odstup 14 px od okraje, levá karta široká 268 px končí 60 px nad spodkem
  pohledu, pravá karta je široká 304 px (NDT, audit a návrh 320 px). Rohy jsou zaoblené
  (12 px) a okraj tvoří linka `--sep2`.
- **Pravá karta je jen tak vysoká, kolik má obsahu**, nejvýš celá výška pohledu. Delší
  obsah se zatím posouvá uvnitř karty. Pravidlo „karta nikdy neposouvá“ zavede P7.52.
- **„Celý díl“ počítá s kartami.** Díl se zmenší a posune do volného místa mezi kartami,
  aby nebyl schovaný pod panelem. Přepnutí nebo zavření panelu 3D pohled nezmenší ani
  neposune. Kamera se změní až při dalším „Celý díl“.
- **Osový kříž** vlevo dole je menší (0,055 místo 0,08), aby se vešel do 60px pruhu pod
  levou kartou.
- Ovládání zůstává: F9 strom, F4 Úprava prvku, Zobrazení → Panely, menu v titulku karty,
  × zavře panel, Obnovit rozložení. Karta umí tu část rozhraní dřívějšího docku, kterou
  okno používá, takže ostatní kód se neměnil.

Pás nahoře a stavový řádek dole jsou zatím původní (P7.50 a P7.53). Model, výpočty
ani formát souborů se nemění.

## Ověření

| Kontrola | Výsledek |
|---|---|
| `tests/test_floating.py` (3) | poloha a rozměry podle návrhu, výška podle obsahu a mez výšky pohledu, přesun při změně velikosti, volné místo pro 3D, rozhraní jako dock, signál viditelnosti, maska rohů |
| `tests/test_viewer_surface.py::test_fit_all_shrinks_and_shifts_part_into_space_between_cards` | „Celý díl“ s kartami: měřítko × 640/240, posun do středu volného místa; bez karet beze změny |
| `tests/test_gui.py::test_panels_are_floating_cards_over_3d_view` | v okně žádný QDockWidget, všech 9 panelů jsou karty nad 3D, vždy jen jedna pravá, 3D se při přepínání nezmenší, F9 uvolní místo |
| testy okna, hledání, oblíbených, zkratek, filtrů, sestavy a pozadí | viz PR |
| self-test „Karty nad 3D“ (Linux Xvfb, skutečné OCCT) | bez překryvu při 1440/1024/960 (3D 840, 706 a 642 px volné šířky), karta je nad 3D, všech 8 rohů obálky dílu po „Celý díl“ leží mezi kartami, skutečný klik vedle karty vybral horní plochu desky |

Snímek: [okno s kartami](p7-48-snimky/okno-karty.png).

## Meze

- Karta je neprůhledná a bez měkkého stínu (R1). Okraj zaoblení je bez vyhlazení masky.
- Na Windows a macOS ověří kreslení karet nad nativní plochou až self-test na GitHubu.
- Šířky karet jsou pevné podle návrhu. Uložené šířky z dřívějších docků se nepoužívají
  (klíče v `okno.json` zůstávají kvůli verzi 1).

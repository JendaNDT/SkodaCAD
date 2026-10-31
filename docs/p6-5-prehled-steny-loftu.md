# P6 – přehled vzorkovaných tlouštěk přechodu

Rozhodnutí 31. 10. 2026 po autorově „ok, udělej to“: u vybraného dutého
přechodu zobrazit naměřenou normálovou délku materiálem, souřadnice a nejistoty.
Přehled je dočasný pohled. Nemění geometrii, formát 33 ani nastavení NDT.

## Význam čísel

Zdroj bodů je původní vnější plášť loftu sestavený ze stejných umístěných skic,
se stejnou volbou rovných stěn. Koncová čela jsou vyloučena. Na každé boční ploše
se zkouší 5 × 5 parametrických bodů 0,15 / 0,325 / 0,5 / 0,675 / 0,85.
Nejde o rovnoměrnou síť v milimetrech. Bod mimo oříznutou plochu nebo do 0,0001 mm
od hrany se vynechá; počet se ukáže. Plocha bez použitelného bodu má nejistý záznam.
Limit 2 000 bodů je výslovně označen, pokud se další část pláště už neměřila.

Paprsek vede proti vnější normále do **aktuálního dokončeného dílu**, včetně
následujících operací. Původní bod musí být na povrchu, kousek dovnitř musí být
materiál a kousek ven volno. Odstraněný či zakrytý povrch je nejistý, nikoli 0 mm.
`ndt.geometry.PartGeometry.cast` ověří přesné průsečíky a materiál klasifikací
bodu. Výsledkem je délka prvního souvislého úseku od zdroje, nikoli součet
všech dalších stěn na paprsku. Chybějící vstup/výstup, hrana či tečnost znamenají
nejistý bod s českým důvodem. NDT filtr protější stěny do 60° se nepoužívá;
původní mapa tloušťky a UT pravidla se nemění.

Rozsah min–max platí pouze pro jisté vzorky. Srovnání se zadanou stěnou používá
číselnou mez `max(0,00002 mm, wall × 10⁻⁶)`:

- **Pod zadáním**: kratší normálový průchod. V režimu v rovinách skic běžný výsledek.
- **U zadání**: shoda v číselné mezi.
- **Delší průchod**: může jít o zesílený roh nebo později přidaný materiál.
- **Nejisté**: bez číselné tloušťky; výslovný důvod.

Nejde o globální minimum, důkaz konstantní tloušťky, výrobní toleranci, přejímku
ani potvrzení UT měřitelnosti. Mezi body může existovat užší místo.

## Provedení a platnost

`loft_inspection.py` vrací neměnné datové záznamy bez nativních tvarů.
`ModelSession.inspect_loft_wall` kontroluje úplný aktuální model a kladnou stěnu.
V okně běží výpočet v samostatném procesu úlohou `loft_wall`, s novým přepočtem
kopie receptu. Výsledek přijme jen odpovídající job, otisk a id prvku; nezamění
jej za BuildResult, takže nezmění výběr ani zobrazenou geometrii.

Úprava, Zpět/Znovu, otevření a nový přepočet smažou dosavadní zprávu. Zastavení
měření nemění recept, historii ani neuložený stav. Po chybě lze výpočet zopakovat.
Zpráva se neukládá do JSON. Uložení samo ji nezneplatňuje.

Panel je pod formulářem loftu: tlačítko, souhrn a tabulka Bod / mm / Výsledek.
Výběr řádku ukáže polohu a měřicí úsečku ve 3D; nejistý řádek jen bod a důvod.
Při změně zprávy se zachovávají existující buňky tabulky, protože přístupnost
macOS může držet jejich odkazy. GUI nepočítá geometrii, vše jde přes session.

## Reference a ověření

Kužel Ø80→Ø40 × 60 se stěnou 3 mm má 25 jistých hodnot:
`normal` 3 mm; `sections` 3/√(1+1/9) = 2,846049894 mm.
Válec i rovný a zaoblený obdélníkový profil dávají 3 mm. Šikmé rovinné stěny
v režimu skic odpovídají projekci 3/√1,25 a 3/√1,0625.
Starší výsypka: 120 jistých bodů 2,608802645–2,769230769 mm a 5 nejistých paprsků
přes hranu. Receptu nepřibude `wall_mode`.

Regrese zahrnuje dodatečné ztenčení a odstranění pláště, hranu, delší průchod,
limit vzorků, neúplný/stará geometrie, nezměněný recept i těleso, historii,
uložení/otevření, proces, zastavení, opožděný výsledek, chybu a opakování.
GUI test a self-test balíčku procházejí tlačítko, tabulku, značku a zneplatnění.
Úplné lokální a obě systémové kontroly i skutečné okno jsou podmínkou sloučení;
konkrétní výsledky jsou v implementačním PR.

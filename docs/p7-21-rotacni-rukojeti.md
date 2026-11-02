# P7.21 – rotační rukojeti ve 3D

Datum: **2. 11. 2026**. Navazuje na P7.19 a P7.20. Formát a závislosti beze změny.

## Ovládání

Vyber více komponent a v panelu **Společné otočení [°]** zapni **Rotační rukojeti
ve 3D**. Posouvací rukojeti se vypnou; jejich zapnutí naopak vypne prstence.
Oba druhy rukojetí lze také vypnout. Volba se pamatuje v otevřeném okně.

Červený prstenec **X**, zelený **Y** a modrý **Z** otáčejí kolem globálních os sestavy
vedených společným geometrickým těžištěm. Táhni oblouk nebo jeho kulový úchop.
Osa se vybírá uchopením prstence; číselná osa a úhel v panelu zůstávají zadáním
pro tlačítko a tažením se nepřepisují. Při tahu stavový řádek ukazuje skutečný
úhel náhledu. **Puštění** ověří a potvrdí pohyb, **Esc** jej zruší.

**Krok otáčení** je výchozí 15°, rozsah 0–180° se třemi desetinnými místy;
0 = Volně. Přichycení počítá celý úhel od začátku tahu, poloviny od nuly.
Přechod přes ±180° je plynulý a lze obkroužit i více otáček. Klik bez tahu,
pohyb pod půlkrok a celé otáčky nepřidávají historii a neruší Znovu.

Prstence téměř natočené hranou ke kameře se nezobrazují. U nerozlišitelného
křížení se tah nespustí; uchop jiný oblouk, kuličku nebo natoč pohled.
Průjezd středem, kde je úhel neurčitý, náhled zruší. Běžné otáčení kamery,
Shift + tažení a Alt pro sondu zůstávají mimo uchopení rukojeti dostupné.

## Střed, omezení a historie

Střed i potvrzení používají P7.20: geometrické těžiště všech vybraných větví,
vážené objemem. Zahrnuje také skryté díly a díly mimo izolaci, ale náhled je
neodkrývá. Je-li celý výběr skrytý, žádné prstence se nekreslí. Pevný díl blokuje
celý příkaz; vnitřní díly podsestav vyžadují výběr celého rodiče. U natočení
zadaného výrazem je dostupný jen Z. Vazby musí dovolit přesně zadaný pohyb
bez pohybu nevybraného okolí. Při odmítnutí se obnoví původní poloha všech dílů.

Při tažení se mění pouze prezentace AIS, nikoli recept nebo geometrie. Puštění
pošle jeden návrh s tokenem výběru, receptu a identity výsledku. Okno ověří
také aktivní režim a povolenou osu a použije atomické `turn_many_around`.
Úspěšný pohyb tvoří jeden krok Zpět/Znovu. Výrazy poloh, zdrojové soubory,
výběr, kamera, viditelnost, izolace, průhlednost a rozepsaná pole zůstávají.

Esc, ztráta fokusu, skrytí/resize plochy, změna kroku či režimu, výběru nebo
prezentace tah zruší a obnoví původní materiály a zvýraznění. Kamera se při
aktivním tahu kolečkem nemění. Prstence se nepočítají do obálky při Vměstnat.

## Ověření

Čistá matematika ověřuje pravotočivost XYZ, obě strany pohledu, téměř boční
paprsky, neurčitý střed, přichycení, křížení a více otáček. Interakční regrese
používají skutečné AIS transformace v měřítkách 1/1,25/2, kontrolují pevný střed,
materiály a zvýraznění, žádný příkaz před puštěním, jedno přijetí a přerušení.
Regrese okna kontrolují výlučnost režimů, skryté díly, celé podsestavy, pevnost,
výrazy, vazby, zastaralý tah a zachování polí a preferencí.

Nativní self-test skutečně táhne všechny prstence včetně zpracování událostí Qt.
Z tahu přibližně 32° při kroku 15° vznikne 30°, náhled nepoškodí model, obě kopie
se otočí včetně skryté, okolí zůstane. Ověří kameru, objem, 35/85 % průhlednost,
jeden krok Zpět/Znovu a zrušení Esc/krok/režim/fokus/resize i celou otáčku bez historie.
Běží také ve stažených balíčcích Windows a macOS. Místní protokoly a snímky:
`out/p7-rotation-handles/`; úplné výsledky před sloučením patří do implementačního PR.

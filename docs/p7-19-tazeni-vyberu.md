# P7.19 – tažení celého výběru myší

Datum: **2. 11. 2026**. Navazuje na P7.17 a P7.18, bez změny formátu a závislostí.

## Ovládání

Vyber více komponent ve stromu nebo ve 3D. Barevné konce os **X (červená),
Y (zelená), Z (modrá)** posouvají celý výběr po osách celé sestavy, nezávisle
na otočení jednotlivých dílů. Klik bez tahu není změna modelu. Otočení pohledu
a Shift + tažení pro posun kamery zůstávají dostupné mimo uchopení rukojeti.

Volby **Rukojeti ve 3D** a **Krok tažení** jsou v panelu **Společný posun [mm]**.
Výchozí krok je 1 mm, rozsah 0–1000 mm se třemi desetinnými místy; 0 = Volně.
Přichycení počítá celkový posun od začátku tahu, poloviny kroku od nuly.
Volby platí pro otevřené okno, přežijí změnu výběru a historii, do receptu se neukládají.
Rukojeti se kotví do středu obálky viditelných vybraných dílů; zaniklé osy se nekreslí.
Při překrytí úchopů je nutné natočit pohled. Při úplně skrytém výběru úchopy nejsou.

Při tažení je vidět pouze **náhled** a velikost posunu ve stavovém řádku.
Vazby se ověřují při puštění. Pokud pohyb dovolí, celý přesun je jeden krok
**Zpět/Znovu**. Jestliže by pohyb porušil vazby nebo přitáhl nevybraného souseda,
nepřijme se nic. Pevná komponenta blokuje celý výběr, vnitřní komponenty podsestav
se přesouvají prostřednictvím celých rodičů, stejně jako při číselném posunu.
Vybraný rodič s potomkem se zpracuje jednou. Pohyb zahrne i skryté vybrané větve.

**Esc**, ztráta fokusu, skrytí či změna velikosti plochy, změna výběru, geometrie,
průhlednosti, kroku nebo vypnutí rukojetí tah zruší. Původní model, historie i
větev Znovu zůstávají. Kamera, viditelnost, izolace, průhlednost a rozepsaný
číselný posun se potvrzením nemění. Zdrojové soubory se nezapisují.

## Provedení a ověření

Prohlížeč používá nejbližší bod světové osy vůči paprsku kamery a převod
logických souřadnic myši podle skutečného rozlišení OCCT (Retina). Náhled tvoří
samostatná nevybíratelná prezentace se zachovanými materiály; původní části
jsou jen dočasně skryté. Posouvá se také zvýraznění a rukojeti. Kamera nevměstnává
rukojeti do obálky modelu. Při zrušení se odstraní náhled a obnoví prezentace.

Okno ověřuje token výběru, receptu a identity výsledku. Poté volá existující
atomický `AssemblySession.move_many_by`, který kontroluje polohy, otočení,
nevybrané komponenty a otisky zdrojů po řešiči před zápisem do historie.

`tests/test_selection_drag.py` ověřuje nezávislé řešení projekce XYZ, myš v měřítkách
1/1,25/2, skutečné AIS transformace a materiály, jeden požadavek po puštění,
nulový krok a přerušení. Regrese okna kontrolují i skryté díly, zastaralý tah,
vazby, pevnost, celé podsestavy, preference a rozepsaná pole.

Nativní self-test skutečně táhne oba parametrické díly ve všech osách,
kontroluje fyzické středy všech kopií, platnost těles, nezměněnou kameru,
materiály 35/85 %, náhled bez úprav a jeden krok Zpět/Znovu. Zkouší Esc,
změnu kroku a odchod z plochy včetně zachování Znovu. Běží i ve stažených
balíčcích Windows a macOS. Místní protokoly a snímky jsou v
`out/p7-selection-drag/`; úplné výsledky kontrol před sloučením patří do PR.

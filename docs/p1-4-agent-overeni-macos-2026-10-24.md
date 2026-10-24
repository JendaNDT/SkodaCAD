# P1.4 — ověření okna agentem na Macu, 24. 10. 2026

Součást [implementačního PR #39](https://github.com/JendaNDT/SkodaCAD/pull/39),
podle [schválených E1–E9](p1-4-navrh-exportu-a-ndt-pri-chybe.md).
Autor již dříve požádal, aby zkoušky převzal agent; tento protokol není novým
autorovým ručním potvrzením ani odborným ověřením NDT.

## Způsob

Skutečné okno `MainWindow`, `OccViewer` a Cocoa na macOS arm64, Python 3.12.14,
PySide6 6.11.2, skutečný pomocný proces spuštěný přes `spawn`.
Akce Qt a změna parametru byly vyvolány programově; souborové dialogy dostaly
předem určené cesty. Nebyl testován fyzický klik myší ani celý nativní souborový
dialog. Čekání na výpočet mělo mez 90 sekund, celý průchod 240 sekund.
Zachytávaly se také výjimky slotů Qt a nečekaná chybová hlášení.

Snímky skutečného okna byly otevřeny a vizuálně zkontrolovány. Nejde o náhradní
prohlížeč z testů `offscreen`. Testuje se zdrojová aplikace; self-test konečného
staženého balíčku na obou systémech dokládají samostatně úlohy v PR.

## Provedené kroky

1. Platný kvádr 20 × 30 × 40 mm: export přes obsluhu okna do STEP, STL, 3MF,
   GLB a SVG. STEP znovu načten: platná geometrie, 1 těleso, 24 000 mm³,
   rozměry 20 × 30 × 40 mm. Řez Z = 20 má plochu 600 mm²; export DXF i SVG.
2. Stejný kvádr s posledním zaoblením R50: chyba prvku `bad`, poslední dobré
   těleso 24 000 mm³ zůstává viditelné. Trvalá příčina pod stromem, vlastnosti
   výslovně jako diagnostický náhled. Studie UT/PT/MT/RT nedostupné kvůli modelu.
3. Přímé vyvolání pěti exportů a exportu řezu: šest odmítnutí s `bad`/R50
   ještě před souborovým dialogem. Řez přitom zůstává jako diagnostický pohled.
4. Uložit chybný recept jako novou JSON kopii a znovu ji otevřít: chyba zachovaná,
   původní soubor byte shodný. Není vytvořen nový formát ani výsledek vydávaný
   za opravený model.
5. V poli parametru změnit R50 na R2: všechny prvky platné, objem přibližně
   23 702 mm³, export dostupný. Studie po změně zůstávají zastaralé.
6. Akce Zpět vrátí chybu a zamkne export; Znovu obnoví úspěšnou opravu.
7. Vybrat PT a výslovně technicky potvrdit pro aktuální díl: studie platná,
   stále **Neověřeno**. Nebyl zadán smyšlený odborný ověřovatel.
8. Opravený díl exportován do všech pěti formátů, jeho řez do DXF a SVG.
9. Akcí okna nově spočítat mapu PT a vyexportovat CSV. Skutečná barevná mapa
   ve 3D, původní povinné vymezení PT zachované.
10. Audit se zahrnutou PT studií dokončen na pozadí; akcí okna exportovat HTML,
    CSV a PDF. PDF má platnou hlavičku. Toto není tvrzení o úplné vizuální
    kontrole všech stran PDF nebo o odborné správnosti NDT postupu.

Výsledkem úspěšného průchodu je `VÝSLEDEK: OK`, bez nečekaných hlášení
a bez výjimek slotů. Očekávaná odmítnutí ze třetího kroku jsou evidována zvlášť.

## Podklady a meze

Pracovní složka tohoto úkolu obsahuje `outputs/p1-4-zkouska/`:
`00-platny-kvadr.json`, `01-chyba-modelu.json`, `02-pracovni-kopie.json`,
výstupy dílu/řezu, `pt-pristupnost.csv`, `audit/` a snímky
`okno-chyba-modelu.png`, `okno-opraveny-model.png`, `okno-mapa-pt.png`.
Spouštěcí skript, průběžný JSON protokol a log jsou ve
`work/p14-implementation-evidence/` mimo sledované zdroje repozitáře.

Při prvním průchodu skončil pomocný zapisovač evidence po exportu SVG kvůli
výchozímu kódování ASCII. Nebyla to chyba modelu ani aplikace. Zapisovač nyní
používá výslovně UTF-8; průchod se následně zopakoval celý. Neúplný pokus
se nepočítá jako úspěšné ověření.

Fyzické ovládání konečného balíčku na Windows, široká matice zařízení,
historická identita odkazů R04, atomické ukládání R03 a odborná NDT-17
zůstávají mimo tento protokol. Vydání z `main` se do autorova dalšího pokynu nemění.

## Krátký postup pro autora

V balíčku z PR otevři `01-chyba-modelu.json`. Zkontroluj červenou příčinu R50,
označení diagnostického náhledu a nedostupný export. Změň `r` na `2` a potvrď
Enter: chyba má zmizet, těleso se zaoblí a export bude dostupný. Zpět obnoví
chybu, Znovu opravu. Ulož kopii pod novým názvem a znovu ji otevři.
U PT je po opravě potřeba vlastní kontrola oblasti a technické potvrzení;
nový výpočet se neoznačuje jako odborné ověření.

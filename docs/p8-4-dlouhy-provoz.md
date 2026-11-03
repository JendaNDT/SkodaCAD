# P8.4 — dlouhý provoz a měření paměti

Zadání autora 3. 11. 2026: „P8.4 dlouhý provoz s měřením paměti“.
Výchozí vydání je P8.3, `16b760c3a24924b8a5ccd384f2cdd8265fddb799`.
P8.5 autorská přejímka a rozpočty paměti/odezvy tím nejsou schválené ani provedené.

## Co zkouška skutečně provádí

`tests/soak_p8.py` spustí jeden dlouho žijící proces se skutečnými Qt/OCCT okny.
Ve výchozím běhu následují **2 zahřívací a 20 měřených cyklů**; aplikace se mezi
cykly nerestartuje a nevynucuje se GC ani testový úklid oken. Každý cyklus:

1. Otevře historii 122 skutečných prvků (60 slepých kapes), ověří platné těleso,
   1 solid, 126 ploch, 122 položek před prvky a analytický objem.
2. Změní tloušťku v poli okna, použije Zpět/Znovu a ověří t=10/t=11.
3. Uloží pracovní kopii, znovu ji otevře a zkontroluje geometrii.
4. Skutečnou akcí Zastavit zruší worker, ověří zánik procesu a poslední geometrii;
   Znovu dokončí změnu na t=12.
5. Řízeně ukončí pouze aktuální vlastněný worker, převezme a potvrdí skutečný
   chybový dialog a obnoví správný výsledek pomocí Zpět. Nevyvolává pád jádra.
6. Exportuje STEP. V samostatném STEP procesu otestuje záměrně nedostatečný
   rozpočet 1 bajt podle skutečného RSS, ověří jeho ukončení; nový proces
   s běžným produkčním limitem úspěšně načte a přenese platnou geometrii.
7. Otevře sestavu 800 kopií, vybere c799, ověří izolaci a průhlednost, otevře skutečný
   editor a nativní 3D náhled, zruší jej beze změny modelu/výsledku/historie a zavře okno.
8. Po zpracování běžných Qt událostí zaznamená srovnatelný koncový bod paměti a prostředků.

Historie má objem `248×20×t−180π` mm³: pro t=10 je 49034,513322 mm³,
pro t=11 je 53994,513322 a pro t=12 je 58954,513322. Sestava má 800000 mm³.
Konečný stav každého cyklu je stejný, historie úprav se načtením znovu ohraničí.
Nejde tedy o zkoušku neomezeně rostoucí historie Zpět v jediném dokumentu.

## Co se měří a co čísla neznamenají

RSS rodiče a všech jeho živých CAD pomocných procesů se čte v každém kontrolním
bodě a průběžným dohledem, který mezi čteními čeká 500 ms. Doba samotného čtení
se přičítá, nejde o přesně dvouhertzový odběr. Souhrn drží jen čítače a maxima na PID; body se průběžně zapisují
do JSONL na disk, aby měřič sám neuchovával rostoucí seznam vzorků v měřeném procesu.
Analýzu celé evidence a trendu provádí až rodič měřiče po skončení GUI procesu.

Každý koncový bod musí mít úplné kladné RSS, přesný součet aktuálního vzorku,
žádná zavřená okna sestav ani parametrické dialogy. Přepočet dílu a otevřené sestavy
mají každý nejvýše 2 připravené procesy. Po zrušení posledního vlastněného okna
sestavy se její pool uzavře; další otevření vytvoří nový. Na konci každého cyklu
proto musejí zůstat **pouze 2 konkrétní PID poolu hlavního dílu** a žádný STEP nebo
další cizí worker. Zaznamenají se i PID zavíraného poolu a ověří se jejich skutečný
zánik. Po běžném zavření hlavního okna nezůstane žádný worker.

Teprve po posledním primárním cyklu následují oddělené body před/po `gc.collect()`
a běžné zavření aplikace. Měřič si ponechá Qt smyčku pro zaznamenání stavu po close;
následný nouzový úklid vlastních testovacích objektů není součástí důkazu uvolnění
oken během cyklů. Aplikace běží v hlavním `QApplication.exec()`; mezi operacemi
generátor vrátí řízení této smyčce a další krok naplánuje po 50 ms. Asynchronní
čekání a modální náhledy používají vnořené Qt smyčky. Po zavření sestavy se řízení
vrátí hlavní smyčce před měřením úklidu, takže se DeferredDelete může doručit
ve smyčce, v níž bylo naplánované. Měřič nevolá testový `sendPostedEvents`.

RSS je rezidentní pracovní sada, nikoli Python heap nebo GPU paměť; sdílené stránky
se mohou započítat do více procesů. Součet se čte postupně a není unikátní fyzická
paměť celého stroje. Maxima jednotlivých PID se **nesčítají** jako současná špička.
Krátká špička mezi vzorky může chybět. Na Windows čte měřič skutečný WorkingSetSize
ve [struktuře PROCESS_MEMORY_COUNTERS](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters),
na Macu existující čtečku RSS procesu. Nepřidává novou závislost.

První a poslední třetina koncových bodů a medián párových sklonů jsou popis trendu.
Samotný růst RSS neprokazuje únik: alokátor a nativní knihovny si mohou ponechat
již vyhrazenou paměť. Ani rovný trend neprokazuje neexistenci všech úniků.
Ochranný rozpočet měřiče 3 GiB součtu vzorkovaných RSS a timeout 40 minut chrání
zkoušku; nejsou novým limitem produktu nebo schváleným rozpočtem P8.5.
Jednobajtový STEP pokus testuje řízené odmítnutí a obnovu, nikoli skutečné vyčerpání
RAM celého stroje. Počet cyklů nenahrazuje pracovní den ani modely autora.

## Prokázané zadržování zavřených oken

Diagnostický pilot nad původním produkčním zdrojem P8.3 dokončil 2 celé cykly
za 55,69 s. Po cyklech zůstalo 1 a 2 zavřená okna sestav; počet Qt widgetů
1189→1426. Zůstala i po odděleném GC. RSS rodiče 933,6 → 1116,2 MiB (+182,7 MiB).
Nárůst všech bajtů nepřisuzujeme pouze oknům, ale živé zavřené objekty jsou
přímo prokázané, nezávisle na interpretaci RSS. Tři nové regresní zkoušky nad
původním kódem selhaly na stále platných Qt objektech, čtvrtá kontrola chybného
otevření prošla.

Příčina: aplikací vytvořená okna sestav používala běžné `close()`, které okno
po přijetí události skryje. Podle [Qt6.11 QWidget::close](https://doc.qt.io/qt-6.11/qwidget.html#close)
se objekt automaticky zruší až s WA_DeleteOnClose. Průběžné odfiltrování seznamu
viditelných oken v MainWindow nezrušilo již vytvořené Qt objekty.

Oprava v produkční třídě MainWindow označí jím vlastněná okna sestav
pro zrušení po **přijatém** close a na destroyed odstraní obálku ze seznamu vlastníka
bez volání Qt metod zrušeného objektu. Zrušení zavírání u neuložené sestavy stále
zachová okno/model/historii; potvrzené zavření uvolní i child widgets prohlížeče.
Ostatní otevřená okna pokračují a opakované otevření nemá neplatné obálky v seznamu.
Po posledním zrušeném okně MainWindow také ukončí a odloží vlastní pool sestav.
Při přeživším okně nebo zrušeném zavírání pool zůstává. Příští otevření vytvoří nový
pool, což znovu zaplatí spuštění a načtení jádra; úsporu paměti nevydáváme za
bezplatné zrychlení opakovaného otevření. Pool hlavního dílu se tím nemění.
Jádro, přepočet, objemové kontroly, formát a závislosti se nemění.

Původní testový Qt cleanup z #115 zůstává beze změny. Zde jde o životnost
**produkčních oken sestav**, nikoli opakování opravy testových oken nebo důkaz
opravy všech příčin růstu paměti či pozdních pádů Qt.

## Evidence a vydání

První dva odmítnuté piloty měřiče byly neúplné: jeden nevyčkal na asynchronní
sestavení zdroje sestavy, druhý nesprávně předpokládal jediný dvouprocesový pool.
Zůstávají v ignored out/p8-4-long-run, nejsou vydávacími výsledky. Úplný dvoucyklový
pilot dokládá zadržené objekty; nejde o srovnatelnou dlouhou baseline nebo celodenní provoz.

Další diagnostický běh s původní obsluhou měřiče pouze vnořenými smyčkami dosáhl
ochranného součtu 3 GiB po pěti celých cyklech. Neprošel a neprokazuje únik
konkrétní knihovny. Opakovaný přenos téže historie bez GUI (41 dekódování) držel
RSS přibližně 450 MB; diagnostika počtů Python objektů neukázala hromadění
výsledků přepočtu mezi cykly. Kontrolní běhy s vynechaným kreslením i s běžnou
hlavní Qt smyčkou měly odlišný průběh RSS. Tyto izolace nejsou vydávací měření.

Experiment s dodatečným `V3d_View.Remove()` na signálu QWidget destroyed byl
odmítnut: nativní pilot skončil SIGSEGV při dalším kreslení v GLEngine /
OpenGl_PrimitiveArray::drawArray. Přesný nejnižší mechanismus prokázán nebyl.
Změna ani její experimentální testy nejsou součástí dávky; viewer.py je přesně
shodný s výchozím vydáním. Měřič navíc nesmí držet silné nativní handle zavřených
pohledů jen kvůli kontrole, protože by tím sám měnil jejich životnost.
První snímek historického místního běhu pouze s opravou oken částečně překrývá systémové hlášení tohoto
staršího pilotu: viditelná 3D scéna a číselné kontroly jsou doložené, čistý snímek
celého rozhraní tím netvrdíme. Snímky se neupravují ani nenahrazují upraveným obrazem.

## Zachovaný úplný místní běh po první opravě oken

[Neupravený JSON](baselines/p8-4-macos-arm64.json) dokončil **2 zahřívací + 20 měřených
cyklů**, 180 kontrolních bodů, za **578,965 s**, s normálním koncem procesu **0**.
Apple M4, macOS 27.2 arm64, Python 3.12.14, build123d 0.13.0,
OCP 8.0.1.1.0, PySide6 6.11.3. Proces ani aplikace se mezi cykly nerestartovaly.

| Ukazatel | Naměřeno |
|---|---:|
| Koncové RSS rodiče ve 20 měřených cyklech | 809,3–1036,2 MiB |
| Medián první / poslední třetiny | 950,9 / 891,5 MiB |
| Rozdíl těchto mediánů | −59,5 MiB |
| Medián párových sklonů | −1,77 MiB/cyklus |
| Vzorkované maximum rodiče včetně operací | 1184,0 MiB |
| Vzorkované současné maximum součtu procesů | 2973,6 MiB |
| Zavřená okna sestav / parametrické dialogy na konci cyklů | 0 / 0 |
| Počet Qt widgetů na konci všech 22 cyklů | 952 |
| Vlastněné klidové workery na konci cyklu / po zavření aplikace | 4 / 0 |

Po posledním cyklu bylo RSS rodiče 953,4 MiB, po odděleném diagnostickém GC
942,8 MiB a po běžném zavření 942,7 MiB. Průběžný růst měl opakované samovolné
poklesy; během měřených cyklů nebylo vynucené GC. Klesající souhrnný trend tohoto
běhu nedokazuje absenci všech úniků. Bez srovnatelného dlouhého běhu před opravou
z něj nevyvozujeme procentní úsporu RAM způsobenou opravou oken.

Dohled zaznamenal 1205 odběrů; 3 průběžné odběry neměly RSS některého živého PID.
Nejsou nahrazené nulou ani použité jako úplný součet. **Všech 180 kontrolních bodů
mělo úplná kladná RSS**. Ochranná mez 3072 MiB zůstala beze změny.
Geometrie, původní vstupy, náhled beze změny modelu, zrušení/pád workeru,
jednobajtový STEP limit a následný platný přenos geometrie prošly ve všech cyklech.

Raw JSON je bajtově shodná kopie místního výstupu, SHA-256
`4ac76750072402d7a02f16e08c9bec3bd7f861ad0f9fb508894d0a8c066dd295`.
Uvádí commit `16b760c`, protože změna MainWindow i nové měřiče byly při měření
ještě necommitnuté. Identitu skutečných zdrojů dokládá úplná mapa 148 SHA-256:
146 původních zdrojů/ukázek/měřičů a oba nové skripty. Z původní mapy se změnil
jen main_window.py (LF `dd1ed3bf7b873929bcaad9690b2a081149087486f75b47362840c7b5d34d305e`).
Tento historický report ještě zachovává oba klidové pooly, tedy 4 workery.
Není měřením navazujícího ukončování poolu sestav. Zůstává beze změny;
nová výsledná baseline bude samostatný soubor. Viewer, jádro, měřiče P8.1/P8.2
i dřívější raw baselines zůstaly beze změny.

Konečná cílená sada GUI, assembly GUI, viewer surface, guide drag, workerů,
STEP dohledu a Qt cleanup prošla: **372 testů**, 165,65 s, normální konec.
Sedm případů ověřujících úplný raw report se v této sadě před jeho uložením vynechalo.
Po uložení reportu prošla samostatná sada všech nových guardů, regresí vlastnictví
a fyzikálních referencí: **27 testů**, 2,45 s, normální konec. Celé Ruff src/tests
a diff check prošly. Tato první verze měla **2894 testů** (2872 výchozích + 22 nových).

## Odmítnutý CI běh a životnost poolu sestav

macOS job `126248901468` v běhu `41731257425` nad headem `e452b4a` dokončil
21 celých cyklů (2 zahřívací + 19 měřených). Ve 22. cyklu při posledním načtení
STEP překročil vzorkovaný součet RSS ochrannou mez o **4 259 840 bajtů**:
3 225 485 312 proti 3 221 225 472. Skončil řádně odmítnutím zkoušky, exit 1;
nejde o úspěch celého dlouhého testu. Všech 148 otisků odpovídalo očekávání.

V koncových bodech nezůstávala zavřená Qt okna (0, stále 952 widgetů), ale stále
běžely oba připravené pooly, i když žádná sestava nebyla otevřená. Jejich odstranění
je konkrétní oprava životnosti prostředků. Samotné dosažení ochranné meze ani
růst RSS rodiče neprokazuje neomezený únik CAD jádra. Zdroj nejnižšího nativního
mechanismu dalšího růstu nebyl doložen. Limity paměti a času ani geometrické
případy se kvůli tomu nemění.

Tři další regrese před opravou ukončování poolu selhaly (původní čtyři prošly).
Po opravě všech **7 regresí vlastnictví** prošlo za 2,65 s. Ověřují zachování poolu
pro přeživší a neuložené okno, jeho konec až po posledním zrušeném okně, vytvoření
nového poolu při dalším otevření a úklid po chybě prvního otevření.

Navazující úplné měření používá schema `skodacad-p8.4-v2`: stejné operace,
stejný rozsah 2 + 20, beze změny 3072 MiB / 2400 s, navíc důkaz skutečného
zániku PID poolu sestav a jen 2 PID hlavního poolu na konci cyklu.

## Úplný místní běh konečné opravy včetně poolu

[Nový neupravený JSON](baselines/p8-4-macos-arm64-pool-release.json) dokončil
**2 zahřívací + 20 měřených cyklů**, 180 úplných kontrolních bodů, za **601,091 s**,
s normálním koncem procesu **0**. Měřil na stejném M4 a stejných verzích knihoven;
celkový čas zahrnuje i opakované nové spouštění poolu sestav.

| Ukazatel konečné opravy | Naměřeno |
|---|---:|
| Koncové RSS rodiče ve 20 měřených cyklech | 757,4–898,8 MiB |
| Medián první / poslední třetiny | 786,5 / 820,4 MiB |
| Rozdíl mediánů | **+33,9 MiB** |
| Medián párových sklonů | **+2,73 MiB/cyklus** |
| Vzorkované maximum rodiče včetně operací | 1032,4 MiB |
| Vzorkované současné maximum součtu procesů | 2638,3 MiB |
| Vlastněné workery na konci každého cyklu / po zavření aplikace | **2 / 0** |
| Zavřená okna sestav / parametrické dialogy na konci cyklů | **0 / 0** |

V každém cyklu se oba zaznamenané PID sestav skutečně ukončily a zůstal pouze
pool hlavního dílu. Opětovné otevření úspěšně vytvořilo nový pool a správnou
geometrii. Sampler měl 1269 odběrů bez chybějícího RSS, všech 180 bodů bylo úplných.
Před diagnostickým GC bylo RSS rodiče 898,8 MiB, poté 888,2 MiB; po běžném zavření
888,2 MiB a žádný worker. Během primárních cyklů nebylo vynucené GC ani restart GUI.
**Kladný trend rodiče nezamlčujeme**; ukončení konkrétních nepotřebných procesů
není důkaz opravy všech zdrojů růstu RSS. Jde o omezenou zkoušku, nikoli rozpočty
P8.5 nebo záruku celodenního provozu. Nevyvozujeme procentní úsporu RAM ani obecné
zrychlení z dvojice jednotlivých běhů.

Raw je bajtově shodná kopie výstupu, SHA-256
`e9609973b8dc9af3cbefd176f946a9f822332fb5ed89928567ef3cd4765c84ad`.
Uvádí tehdejší HEAD `e452b4a`; dodatečná oprava poolu při měření ještě nebyla
commitnutá. Celá mapa 148 otisků odpovídá skutečným místním zdrojům,
MainWindow LF `be8cded81d838547cebfae126c71ee49a2354584fa9de84c8b36d0835114f39a`.
Všechny původní vstupy zůstaly beze změny. Čtyři nové nativní snímky sestavy
a historie z prvního a posledního cyklu byly prohlédnuté; scény odpovídají
800 kopiím a historii s 60 kapsami, bez překryvu starým systémovým hlášením.

Konečná cílená sada dotčených modulů prošla: **376 testů**, 163,40 s, normální konec;
8 guardů úplného nového raw se tehdy ještě vynechalo. Po jeho uložení prošla
samostatná sada všech P8.4 guardů, regresí oken/poolů a fyzikálních referencí:
**32 testů**, 3,13 s, normální konec. Celé Ruff src/tests a diff check prošly.
Celá nová sada má **2899 testů** (2872 výchozích + 27 nových).

Stejných 2 + 20 cyklů ověří nové workflow p84-long-run.yml na
Windows i macOS. Před sloučením navíc musejí projít úplné standardní testy,
buildy a self-testy stažených aplikací obou OS i STEP. Po sloučení se ověří nové
skutečné vydání z main, oba dlouhé běhy a nové tagy/ZIPy. Časy CI se necommitují.

# P3.3 — průzkum importní služby

**Stav: průzkum, importní služba není hotová.** Podklad k návrhu P3.2;
vzorky P3.1 jsou zatím v [PR #46](https://github.com/JendaNDT/SkodaCAD/pull/46).
P3.3 musí číst mimo Qt, rozlišit jednotky, počet a platnost těles, umožnit
zrušení a neprovádět tiché opravy.

## Ověřené skutečnosti na místním Macu

- V současném prostředí `STEPControl_Reader.FileUnits` u vzorku 01 vrátil
  `millimetre`, u 04 `INCH`. `NbRootsForTransfer` vrátil 1 u jednoho tělesa,
  2 u samostatných dvou těles a 1 u sestavy. Počet kořenů **není** počet těles.
- Po převodu do mm měl vzorek 01 rozměry 40 × 30 × 20 mm; palcový vzorek 04
  měl 50,8 × 25,4 × 12,7 mm. Otevřená plocha měla 40 × 20 × 0 mm, jednu
  plochu a žádné objemové těleso; syntakticky poškozený 06 čtečka odmítla.
- Projekt má pomocný proces v `worker.py`, který lze ukončit; jeho současné
  úlohy však nejsou STEP import a samotné ukončení ještě nedokládá omezení
  paměti ani správné chování při všech selháních nové služby.

## Důležitý nález: automatická oprava

[Dokumentace OCCT](https://github.com/Open-Cascade-SAS/OCCT/blob/master/dox/user_guides/step/step.md)
uvádí, že STEP čtečka ve výchozím nastavení může po převodu spustit `ShapeFix`.
Běžné úspěšné načtení proto samo o sobě nedokazuje, že se tvar neupravoval.

V místním prostředí se po vytvoření čtečky parametr `FromSTEP.exec.op` zobrazil
jako `FixShape`; jeho nastavení na prázdný text bylo přijato a následně se takto
načetly tři jednoduché vzorky 01, 04 a 05 s výše uvedenými rozměry a počty.
**To není důkaz, že se ve všech situacích a verzích jádra vypnuly všechny
opravné zásahy.** Přímé API `GetShapeProcessFlags` navíc v tomto Python balíku
vrátilo chybu převodu typu `bitset`, takže ho nelze bez dalšího využít jako
ověření nastavení. Parametry `Interface_Static` jsou globální pro proces; při
experimentu byly nastaveny pouze v krátce žijícím samostatném procesu.

## Doporučený postup P3.3

1. Rozšířit níže uvedený referenční vstup o další druhy vad a ověřit na
   podporované verzi jádra, které zásahy lze spolehlivě zakázat či zachytit
   a uživateli oznámit. Opakovat na Windows a macOS. Úspěch na nepoškozených
   vzorcích ani jediný případ ohlášené opravy nestačí.
2. Navrhnout přenos výsledku z odděleného procesu, lhůtu, ukončení a skutečný
   způsob omezení paměti na obou OS; velikost STEP 16 MiB sama neomezuje paměť
   potřebnou pro jeho zpracování. Přerušení ani selhání nesmí změnit dokument.
3. Jednoznačně určit podporovanou podmnožinu: pro první verzi navrhnout jedno
   platné uzavřené těleso, známé jednotky a úplný převod. Sestavu, více těles,
   volné plochy, neúplný převod a pochybné jednotky odmítnout se srozumitelnou
   zprávou, dokud pro ně nebude schváleno bezpečné chování. Jediný kořen sám
   nerozlišuje jedno těleso a sestavu.
4. Ověřit kontroly včetně všech zpráv o převodu, platnosti a uzavřenosti každé
   složky, zachování zdroje a správného přepočtu jednotek. Žádná část nesmí být
   potichu vynechána. Přidat reálné vzorky z jiných CAD programů.
5. Poté implementovat a otestovat službu mimo Qt; uložení do modelu, GUI a
   potvrzení uživatelem řešit podle samostatně navazujících kroků plánu.

Přesné chování čtečky pro složité zdroje, více jednotek, vložené sestavy,
pády a nedostatek paměti zatím nebylo prokázáno. Tento průzkum nemění formát
ani aplikaci a není důkazem podpory importu.

## Reprodukovatelný případ opravy orientace

Na Macu byl 27. 10. 2026 vytvořen [referenční kvádr](../tests/fixtures/step-p33/puvodni-kvadr.step)
z P3.1 a jeho [upravená kopie](../tests/fixtures/step-p33/obracena-plocha.step).
Jediná záměrná změna je přepnutí orientace jedné `ADVANCED_FACE` z `.F.` na `.T.`;
originální soubor je zachován. SHA-256 originálu je
`c326fffbe82273617c8e009f9992f04080e615b6863f686a9bea9e7216cce812`, upraveného
souboru `16ff0b22432178a0afa401b7cb1d45a6a10441a8a534d37a53b751b60bfc8de3`.
Oba mají očekávané vnější rozměry 40 × 30 × 20 mm.

[Test](../tests/test_p33_step_repair_probe.py) spouští každé čtení v samostatném
procesu a zachycuje hlášení z načtení i převodu. Místní výsledek:

| Vstup | Nastavení následného `FromSTEP.exec.op` | Zpráva převodu | Výsledek kontroly |
|---|---|---|---|
| Původní kvádr | `FixShape` i prázdné | Bez hlášení. | Jedno platné těleso, 6 ploch, objem 24 000 mm³. |
| Obrácená plocha | `FixShape` | Jádro hlásí chybně orientované plochy a jejich opravu. | Jedno platné těleso, 6 ploch, objem 24 000 mm³. |
| Obrácená plocha | prázdné | Stejné hlášení o opravě. | Jedno platné těleso, 6 ploch, objem 24 000 mm³. |

Upravený vstup tedy vyvolá **ohlášený zásah i při prázdném nastavení následného
`ShapeFix`**. To je důkaz hlášení jádra pro tento konkrétní případ, nikoli důkaz,
že tato zpráva zachycuje všechny možné opravy nebo že všechny změny lze vypnout.
Platnost a stejné rozměry výsledku nezaručují shodu se zamýšleným původním dílem.
Jádro samo ve zprávě uvádí, že orientaci opravilo; experiment nezávisle nesledoval
každý vnitřní krok převodníku.

Doporučení pro budoucí službu: číst diagnostiku **načítání i převodu**, přeložit
ji uživateli a jako bezpečný výchozí postup soubor s hlášenou opravou nepřijmout;
neinterpretovat nepřítomnost hlášení jako důkaz, že žádná úprava nenastala.
Zachovat celý originální STEP a při nejednoznačném či neúplném výsledku hlásit
odmítnutí. Případné přijetí opravovaného tvaru vyžaduje samostatný návrh a
ověření. Další druhy vad a chování na Windows zůstávají neověřené.

Místní příkaz `.venv/bin/pytest -q tests/test_p33_step_repair_probe.py`:
**3 testy prošly**; kontrola Ruff daného testu také prošla. Celá testovací sada
ani Windows v tomto průzkumu spuštěny nebyly. P3.3 tím zatím není implementována.

## Rozpracovaný základ P3.3

Na větvi navazující na PR #46 vznikl experimentální kód, zatím nepřipojený
k aplikaci: `step_probe.py` odmítá zprávy z čtení a převodu, sestavy, jiný
počet než jedno těleso, neplatnou geometrii a jiné než jednoznačné jednotky mm
či palec; `step_source.py` ověřuje vložené bajty, velikost a SHA-256;
`step_task.py` spouští diagnostiku odděleně a umožňuje zrušení, hlídá čas a
průběžně měří rezidentní paměť. Kontrolu vykonává pomocné vlákno nezávisle na
dotazování okna; výsledek přijímá další vlákno. Přenos tvaru probíhá přes binární
zápis OCCT.

**Průběžné měření paměti není pevný limit operačního systému:** mezi dvěma
kontrolami může proces limit překročit a jeho chování na Windows dosud nebylo
ověřeno. Proto tento kód
zatím nesplňuje ochranu prostředků pro uživatelský import. `probe_step` je
blokující a nastavení jádra je globální v procesu: nesmí se volat přímo z GUI
ani souběžně s jinou úlohou OCCT. V této podobě nejde o dokončené P3.3, natož
P3.4 či P3.5; přístup do okna ani změna formátu zatím nejsou zavedeny.

Průběžná úplná sada na místním Macu: **1 665 testů prošlo**, Ruff prošel.
Zahrnuje sadu P3.1 z nesloučené větve; nově přidaný kontrolní případ hlášené
opravy v pomocném procesu byl navíc ověřen samostatně. Nejde o přijetí P3.5.

Po zavedení samostatného dohledu nad procesem prošla na místním Macu další
úplná sada: **1 667 testů**, Ruff bez chyby. Další cílené testy ověřily také
selhání měření paměti a dvě předběžná opětovná načtení po exportu. Předběžné
zkoušky nenahrazují přijetí aplikace ani přenos mezi dvěma systémy.

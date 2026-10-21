# P1.2B — návrh přijetí celého výpočetního kontextu prvku

**Stav: B1–B7 schválené autorem 21. 10. 2026; implementace B.1–B.3 probíhá.**
Podklad: `main / edf9b8ec74b7bdbfa98101796564f22624d45532`, sloučené
[P1.2A / PR #33](https://github.com/JendaNDT/SkodaCAD/pull/33).
Navazuje na [D5 smlouvy P1.1](p1-1-navrh-smlouvy-geometrickych-operaci.md),
[hranici P1.2A](p1-2a-navrh-spolecne-kontroly-geometrie.md#4-zapojení-bez-částečného-přijetí-kandidáta)
a R05 v [auditu P0](p0-audit-a-overeni.md#2-registr-rizik-a-omezení).

## 1. Schválený rozsah

Cíl: při chybě jednoho prvku nezůstane ve výpočtu ani část jeho tělesa, ani
nepřijatá skica či záznam operace. Teprve úspěšný celý prvek předá všechny své
změny dalším prvkům. Například když pole nejprve odebere první kopii díry a druhá
kopie selže, obnoví se stav před celým polem, včetně podkladů pro další opakování.

Chybný prvek **zůstane v receptu červený k opravě** a další prvky se přeskočí.
P1.2B automaticky nevrací uživatelskou editaci ani poslední celý úspěšný dokument.
Obnovuje přijatý výpočetní stav před prvkem v právě počítané verzi receptu.
Zpět/Znovu zůstane samostatným ovládáním historie.

| Bod | Schválený rozsah |
|---|---|
| **B1 Hranice prvku** | Jedna transakce kolem celého `_run_feature`, pro všechny současné typy včetně skici. Zahrne všechny podoperace díry se závitem, pole a zrcadlení i závěrečnou objemovou kontrolu P1.2A. |
| **B2 Oddělený kandidát** | Pracovní `BuildContext` s vlastními kontejnery parametrů, skic a operací; samostatná kopie každého seznamu operací a nové `recording`. Původní kontext se mění až po úspěchu. |
| **B3 Vlastnictví geometrie** | Přijaté `Part`, `Sketch` a `Plane` se mohou sdílet pouze pro čtení. Případná změna existujícího objektu na místě vyžaduje předem vlastní kopii. Bez plošného hlubokého kopírování celé historie a bez nové závislosti. Tuto podmínku doloží audit a regrese současných cest. |
| **B4 Parametry a recept** | Prvek nemění vyčíslené parametry ani vstupní JSON. Pro jeho práci použít kopie; změna těchto vstupů při jinak úspěšném návratu je interní chyba, kandidát se nepřijme. |
| **B5 Výsledek a kompatibilita** | Zachovat české chyby, stavy `ok/error/skipped`, zprávy počtu těles, `parts_before`, historii, worker a dosavadní formát 22. Neplatný kandidát ani jeho pomocná data se nepředají do `BuildResult`. |
| **B6 Důkazy** | Splnit T01–T14 níže: skutečné analytické případy, řízené chyby, aliasy seznamů, skici, přenos, historie, kompatibilita a srovnání výkonu. Současné regrese se zachovají. |
| **B7 Předání** | Jedna implementační větev se třemi malými kroky B.1–B.3, po každém Ruff a celý pytest před commitem. Potom oba kompletní workflow a ruční přijetí konkrétního balíčku. Sloučení vyžaduje další souhlas autora. |

Autor po předložení B1–B7 a žádosti o souhlas se sloučením návrhového PR odpověděl
**„ok, schvaluji“**. [PR #34](https://github.com/JendaNDT/SkodaCAD/pull/34) je sloučené
(`cbf19b1`). Tím jsou povolené kroky B.1–B.3 v samostatném implementačním PR.
[Evidence P1.2B](p1-2b-overeni.md) rozlišuje výsledky jednotlivých kroků a zbývající
přijetí. Sloučení implementace vyžaduje další samostatný souhlas autora.

## 2. Skutečný výchozí stav

P1.2A je implementované a sloučené. Autor 21. 10. 2026 potvrdil sedm vedených
zkoušek na Macu M4 / macOS 27.0.1, včetně obou chybných úprav trubek a opravy.
[Protokol P1.2A](p1-2a-rucni-overeni-macos-2026-10-21.md) rozlišuje potvrzení autora
od technické evidence. Testovaná hlava `8852a6b` má stejný Git strom jako `edf9b8e`.
Místně i v obou cílových systémech prošlo 1 266 testů; oba stažené balíčky mají
úspěšný self-test. Výsledky nejsou ověřením dosud neexistujícího P1.2B.

| Místo na výchozím SHA | Dnes / důvod zásahu |
|---|---|
| `features.BuildContext` | Pět polí: `params`, `part`, `sketches`, `operations`, `recording`. Seznamy v `operations` jsou měnitelné; samotná kopie vnějšího slovníku nestačí. |
| `BuildContext.apply` | Validuje kandidáta a teprve pak mění těleso a připojí podoperaci do `recording`. Úspěch jedné podoperace však není úspěchem celého prvku. |
| `rebuild._run_feature` | Při známé i neočekávané výjimce vrací jen `ctx.part`; `finally` nastaví `recording=None`. Při úspěchu zapíše zaznamenané operace. Ostatní části kontextu neobnovuje. |
| `build_sketch` | Aktuálně zapisuje skicu až po jejím sestavení. Musí zůstat chráněný i případ budoucí chyby po zápisu skici do kandidáta. |
| `build_hole`, `_repeat` | Díra může nejdřív vyvrtat jádro a až pak tvořit závit; pole/zrcadlení může mít několik skupin podoperací. Celá skupina patří do jedné transakce. |
| `rebuild`, `worker`, `session` | Výsledné skici se předávají v `BuildResult`; operace jsou interní podklad opakování. Po chybě se již dnes vyhodnocují měření/NDT nad zachovaným tělesem. P1.2B toto pravidlo nemění. |

Řízené ověření na `edf9b8e`: náhradní builder změnil parametr `t` ze 40 na 41,
přidal skicu a připojil operaci do existujícího seznamu, pak vyvolal `FeatureError`.
Těleso se správně vrátilo na **24 000 mm³**, parametr 41, nová skica a druhá
operace však v kontextu zůstaly. Je to **uměle vyvolaná chyba pro ověření smlouvy**,
nikoli tvrzení o běžné ztrátě dat v současném okně.

Existující `test_late_pattern_failure_restores_geometry_before_the_whole_feature`
již dokládá správnou obnovu tělesa při skutečné pozdní chybě pole. P1.2B rozšíří
důkaz o celý kontext; nebude tuto geometrickou regresi nahrazovat.
Při přípravě tohoto návrhu byly na `edf9b8e` ověřené také skutečné reference
T06/T07: při chybě **79 874.33629385641 mm³**, po opravě **79 748.67258771283 mm³**,
vždy jedno těleso; kontrolní skica se při chybě přeskočí a po opravě projde.
To dokládá použitelnost referenčních receptů, nikoli hotovou implementaci transakce.

## 3. Navržené provedení a přesná smlouva

### 3.1 Průběh jednoho prvku

1. Vyhledat typ prvku. Neznámý typ vrátí dosavadní českou chybu beze změny stavu.
2. Připravit místního kandidáta z přijatého `BuildContext`. Selhání přípravy
   kandidáta nesmí změnit přijatý stav.
3. Spustit builder jen nad kandidátem a pracovní kopií JSON prvku. Všechny jeho
   podoperace zaznamenat do nového seznamu kandidáta.
4. Zachovat závěrečný `inspect_volume` pro všech 11 objemových typů, nezávisle na
   identitě výsledku. Skica sama může úspěšně ponechat `part=None`.
5. Ověřit neměnnost parametrů a JSON zadání. Připravit úplný záznam úspěšného
   prvku v `operations`, včetně prázdného seznamu u neopakovatelných typů.
6. Teprve nyní předat těleso, mapu skic a mapu operací kandidáta přijatému kontextu.
   `recording` rodiče ponechat v původním stavu; v běžném přepočtu je `None`.
7. Při jakékoli dosud zachytávané výjimce zahodit kandidáta a vrátit chybu.
   Původní kontext a jeho dříve uložené aliasy zůstaly nedotčené, není nutná
   dodatečná obnova již přepsaných slovníků.

Jde o krátkou interní pomocnou funkci/metodu v `features.py` a zapojení v
`rebuild.py`, nikoli nový veřejný transakční framework. Názvy pomocných metod
jsou implementační detail. `ctx.apply` zůstane operací jedné podoperace;
přijetí celého prvku bude mít právě jednu hranici v `_run_feature`.
Vnořené transakce ani volání `_run_feature` z builderů se nezavádějí.

### 3.2 Co se kopíruje a co musí zůstat zachováno

| Pole / vstup | Pracovní vlastnictví | Po chybě / při úspěchu |
|---|---|---|
| `params` | Nový slovník čísel; původní slovník není pracovní prostor builderu. | Původní hodnoty i objekt zůstanou. Změna parametrů kandidátem je chyba i při jinak úspěšném návratu. |
| `part` | Kandidát nejprve čte přijatý tvar; operace vytvářejí nové tvary. | Po chybě původní geometrie, poloha, počet a identita přijatého objektu. Při úspěchu validovaný výsledek. |
| `sketches` | Nový slovník se zachovaným pořadím; uložené dvojice rovina/skica jsou jen pro čtení. | Po chybě původní klíče, pořadí, roviny a geometrie; nic z odmítnutého prvku. Při úspěchu nová přijatá mapa. |
| `operations` | Nový slovník **a nový seznam pro každý existující klíč**. Dvojice nástroj/režim sdílejí jen čtený tvar. | Po chybě původní klíče, pořadí, režimy, délky seznamů a nástroje. Zápis odmítnutého prvku nepřibude; existující záznam se nezmění. |
| `recording` | Nový seznam pouze pro tento kandidát. | Při chybě nic neunikne. Při úspěchu jeho obsah uložit jednou jako operace celého prvku; původní `recording` rodiče se nemění ani v přímém interním testu. |
| JSON prvku | Hluboká kopie čistých JSON dat; není to kopie OCCT geometrie. | Vstupní recept se nemění. Zápis builderu do kopie se rozpozná a odmítne, nepoužije se jako skrytá změna zadání. |

Nekopírovat celou `ModelSession`, `BuildResult`, historii, NDT výsledky ani celý
graf nativních tvarů při každém prvku. Přehled musí výslovně pokrývat všechna
pole `BuildContext`; regrese upozorní, pokud budoucí pole nebude ve smlouvě uvedené.

### 3.3 Důležitá mez sdílení tvarů

Kopie slovníku neopraví nativní tvar, který někdo změnil na místě. Lokálně
instalovaný build123d 0.13.0 potvrzuje, že `move` a `locate` mění objekt, zatímco
`moved` a `located` pracují s kopií. Dnešní lineární pole používá `moved`.
Před implementací projít také rotaci, zrcadlení, roviny a pomocné funkce builderů.

Všechny podporované cesty musí zachovat přijaté tvary a jejich vstupní polohu.
Potřebuje-li cesta skutečně měnit starý objekt na místě, musí nejprve vytvořit
vlastní ověřenou kopii. Regrese zkontroluje geometrii původního tělesa, skic,
nástrojů i `parts_before` po úspěchu a selhání. Samotná shoda `id()` nestačí.

Tento návrh není paměťovou izolací libovolného kódu, který by porušil zákaz
zápisu do sdílených nativních objektů. Ani neobnovuje proces po pádu OCCT,
nedostatku paměti či ukončení systému. Tyto meze se nesmějí zaměnit za úplnou
obnovu pěti popsaných polí v podporovaných cestách. Pokud některá dnešní cesta
vyžaduje širší změnu architektury či plošné kopírování historie, předložit dopad
a úpravu návrhu; nerozšiřovat rozsah ani oslabit smlouvu bez rozhodnutí autora.

## 4. Regrese po schválení

Tolerance pro analytickou geometrii zůstávají podle P1.1; seznamy, pořadí klíčů,
režimy, parametry a JSON se porovnávají přesně. Pozorované objekty si test uloží
před voláním, aby případná změna původního seznamu neunikla porovnání se stejným aliasem.

| ID | Případ a nezávislý důkaz |
|---|---|
| **T01** | Řízený builder změní všechna pracovní pole, existující seznam operací, odstraní/zamění skicu a pak selže. Původní kontext i předem uložené aliasy mají stejné hodnoty, pořadí, tvary a polohy. |
| **T02** | T01 parametrizovat pro `FeatureError`, `ExpressionError`, `SelectionError`, `GeometryValidationError` a neočekávanou `RuntimeError`. Zachovat dosavadní druh české chyby; chybu nepřevést na úspěch. |
| **T03** | Úspěšný složený prvek přijme všechny své operace právě jednou a v pořadí. Následné pole/zrcadlení používá jen úplné přijaté záznamy; stav dřívějších uložených seznamů není měněn dodatečně. |
| **T04** | Skica po vytvoření pracovního záznamu řízeně selže: její id se neobjeví v `BuildResult.sketches`, původní skici včetně rovin zůstanou. Platný dokument jen ze skic má nadále `ok=True`, `part=None`. |
| **T05** | Builder vrátí úspěch a změní pracovní metadata, ale závěrečná pojistka odmítne prázdný/smíšený/nevhodný tvar. Nic se nepřijme; žádná falešná zpráva o počtu těles. Zachovat P1.2A test i pro stejnou identitu tvaru. |
| **T06** | Skutečná pozdní chyba pole: deska 100×80×10, dva slepé otvory Ø4 do hloubky 5 na X=−20 a 45. Pole po X s roztečí +20: první kopie řeže, druhá je mimo díl. Výsledek **80 000−40π mm³**, 1 těleso; v bodě (0,0,7.5) zůstane materiál, původní otvory zůstanou. Zachovat i celý kontext. |
| **T07** | Skutečná pozdní chyba zrcadlení stejných otvorů, vytvořených v pořadí X=45 a −20, přes rovinu `YZ` s `offset=20`: první kopie na X=−5 řeže, druhá na X=60 mine díl. Stejný původní objem a čisté záznamy. Po opravě offsetu na 0 mají čtyři otvory **80 000−80π mm³**. |
| **T08** | Díra se závitem: řízené selhání přípravy závitové drážky po úspěšném vyvrtání jádra. Obnoví se stav před celou dírou, ne stav s částečným vrtáním. Platný skutečný závit musí nadále projít existujícími geometrickými testy. |
| **T09** | Neznámý typ, selhání přípravy kandidáta, první chybný prvek a prázdný počáteční kontext: nic se nezmění. Přímý interní test zachová i původní neprázdné `recording`; neznamená to zavedení vnořených transakcí. |
| **T10** | Pokus builderu změnit parametry nebo vnořená JSON data: po chybě i po jinak úspěšném návratu původní vstup nezměněn; neoprávněná změna nezíská status úspěchu. |
| **T11** | Aktuální buildery nemění sdílené původní tvary, roviny, nástroje ani `parts_before`; ověřit objem, obálku, umístění a materiál. Samostatná změna vlastní kopie tvaru následovaná chybou se nesmí projevit na originálu. |
| **T12** | BinTools/pickle a skutečný worker se `spawn`: shodný částečný výsledek, pouze přijaté skici, chyba a přeskočený konec. `operations/recording` nepřidávat do protokolu. Zachovat existující zrušení a zahození starého výsledku. |
| **T13** | Session a okno: pozdní chyba → oprava → Zpět → Znovu → uložení/otevření kopie. Správná geometrie a stavy; originál nezměněn. CLI a offline AI mají stejné počty a chyby, bez síťových volání. |
| **T14** | Zachovat všech 1 266 výchozích případů a rozšířit je o transakční důkazy. Rekurzivně všech 26 ukázek a jednoduché recepty v1–22; stejné objemy, polohy, počty, zprávy a JSON po uložení kopie. Test zahrnutí všech polí kontextu. |

Řízená chyba je důkaz chování konkrétní větve selhání, nikoli náhrada skutečného
modelování. V ručních souborech T06/T07 bude jako následující prvek nezávislá
kontrolní skica, aby po opravě neměnila porovnávaný objem. Reprodukce T06/T07
pro návrh proběhla na výchozím SHA; při implementaci ji zachovat jako výchozí důkaz.
Při odlišnosti jádra doložit příčinu a upravit referenci, nikoli jen změnit číslo,
aby prošel test. Sady umístit především do nového `tests/test_feature_transactions.py`
a existujících testů pole, zrcadlení, workeru, historie a okna.

## 5. Pořadí implementace a výstupy

| Krok | Závislost a změna | Výstup / dokončení |
|---|---|---|
| **B.1 Vlastnictví dat** | Schválení B1–B7; audit pěti polí a čtení/zápisů do tvarů. Interní tvorba kandidáta, izolace kontejnerů a čistého JSON, malé testy T01/T09/T10/T11. | Jednoznačné vlastnictví bez úniku změn přes aliasy; žádné nové veřejné API/formát. Ruff a celý pytest před commitem. |
| **B.2 Hranice přijetí** | B.1; přepojit `_run_feature` na kandidáta a přesunout přijetí až za závěrečnou pojistku. | T02–T08, stejné české chyby a zprávy, skutečné pole/zrcadlení a selhání závitu. Ruff a celý pytest před commitem. |
| **B.3 Přenos a předání** | B.2; T12–T14, měření níže, doplnit dokumentaci a návod. | Ruff a celý pytest; oba cílové workflow na konečné hlavě, self-test skutečně stažených balíčků, ruční protokol, PR ke sloučení až po souhlasu autora. |

B.1 lze ověřovat přímo nad interním kandidátem ještě před přepojením hranice
v B.2. Průběžný commit se nevydává za dokončenou etapu. Nová závislost, změna
formátu, nový typ prvku nebo přesah do sousedních etap vyžadují změnu schválení.

## 6. Výkon a cílové sestavení

Před B.1 znovu změřit stejným `tests/benchmark_p0.py` výchozí `edf9b8e` a po
B.3 kandidáta: zahřátí + 3 opakování, stejný stroj a knihovny, vstupní SHA,
podpisy geometrie/NDT, časy a procesové maximum paměti. Nekopírovat čísla P1.2A
jako nové měření. Žádné časové prahy v pytest ani nové tolerance.

Vedle stávajících scénářů samostatně změřit krátkou historii a pevnou historii
30 drobných oddělených přídavků, vždy s ověřením počtu a součtu analytických objemů.
Zachytit i odmítnutí posledního prvku a opakované přepočty. Tím zviditelnit cenu
kopírování rostoucích slovníků a seznamů; nezaměňovat procesové maximum paměti
za přírůstek jedné transakce. Nezrychlovat výsledek vynecháním izolace nebo kontrol.

Na konečné implementační hlavě musí projít obě úlohy každého workflow Windows
i macOS: Ruff, celý pytest, baseline, sestavení, kontrola stažení a self-test OK.
Při nezměněném vzhledu stačí doložit skutečný nativní průchod chybou a opravou;
případná změna vzhledu vyžaduje snímek skutečného okna. Publikace Releases má
zůstat vázaná na `main`, žádné automatické sloučení.

## 7. Ruční přijetí po implementaci

Použít balíček konečné hlavy implementačního PR a zapsat sestavení, OS, zařízení,
datum a skutečný výsledek. Připravit soubory pro autora, bez nutnosti editovat JSON.

1. Pozdně chybující pole T06: původní dva otvory, žádná částečná nová díra,
   zobrazený objem přibližně **79 874 mm³**, jedno těleso a přeskočený další prvek.
2. Změnit rozteč z +20 na −20: čtyři otvory, zobrazený objem přibližně **79 749 mm³**, úspěch.
   Zpět vrátí chybu a původní dva otvory, Znovu vrátí čtyři otvory.
3. Zrcadlení T07: chyba při offsetu 20, oprava na 0; stejné původní/opravné objemy,
   žádná částečná kopie; oprava i Zpět/Znovu fungují.
4. Na kopii příruby změnit rozměr, uložit pod jiným jménem a znovu otevřít.
   Ověřit geometrii, počty, zprávy a nezměněný originál.
5. Otevřít tři trubky: všechny tři části zůstávají úspěchem. Zopakovat chybu
   a opravu úpravy hrany, porovnat zprávy s přiloženým CLI/offline souhrnem.
6. Přepočítat na pozadí a vyzkoušet Zastavit; původní fungování historie a zahození
   nedokončeného výsledku zůstane. Průchod na Macu nezastupuje ruční Windows test.

Skryté mapy operací nelze spolehlivě přijmout pouhým pohledem na 3D.
Jejich obnovu musí doložit T01–T12; ruční průchod je doplňuje.

## 8. Dokončení a hranice

P1.2B je hotové až po B.1–B.3, T01–T14, zveřejnění výkonu a omezení,
obou zelených cílových kontrolách a ručním přijetí konkrétního balíčku.
R05 lze označit za vyřešené **pro popsaná pole, vlastnictví a podporované cesty**,
nikoli za záruku obnovy po jakékoli nativní havárii nebo chybě neznámého budoucího builderu.
Sloučení implementace je samostatný pokyn autora.

Mimo tento rozsah zůstávají: R01/P1.4 export a NDT při chybném receptu,
R03 atomické ukládání, R04/P1.3 sémantické reference, R12 popis formátu pro AI,
P2 přímé modelování, nový průnik, formát 23, STEP import a odborná NDT-17.
NDT-16 se neprovádí. P1.2B nemění rozhodnutí o více tělesech, tolerance,
objemové podmínky ani upozornění NDT.

## 9. Rozsah původního návrhového PR #34

Pouze dokumentace návrhu, doložení přijetí/sloučení P1.2A a odkazy.
Žádné změny `src/`, testů, ukázkových receptů, závislostí nebo workflow.
README oddíl „Formát modelu“ předávaný AI zůstává byte shodný s výchozím main.
Povinný místní Ruff a celý pytest před dokumentačním commitem ověří výchozí kód;
nejsou výsledkem budoucích T01–T14. Dokumentační diff podle stávajících filtrů
cest nespustí sestavení aplikací. Nové Windows/macOS sestavení je brána budoucí
implementace, nikoli tvrzení tohoto návrhového PR.

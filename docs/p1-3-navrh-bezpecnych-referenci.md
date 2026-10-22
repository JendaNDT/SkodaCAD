# P1.3 — návrh bezpečného vyhodnocování geometrických odkazů

**Stav: návrh ke schválení, 22. 10. 2026. Implementace není schválená ani zahájená.**
Podklad: `main / 3a8deffca360da6ba412cd808837bff8f3ad1d10`, po sloučení
[P1.2B / PR #35](https://github.com/JendaNDT/SkodaCAD/pull/35).
Navazuje na [roadmapu](roadmapa-vyvoje.md#p1--bezpečná-geometrie),
[smlouvu P1.1](p1-1-navrh-smlouvy-geometrickych-operaci.md),
[transakce P1.2B](p1-2b-navrh-transakce-kontextu.md) a R04 v
[auditu P0](p0-audit-a-overeni.md#2-registr-rizik-a-omezení).

## 1. Cíl a rozhodnutí ke schválení

Při změně rozměru se odkaz buď vyhodnotí podle svého výslovného geometrického
předpisu, nebo skončí českým vysvětlením. Rovnocenné možnosti nesmí rozhodnout
pořadí ploch a hran v jádře. Neplatný odkaz nesmí vzniknout tím, že se jeho zadaná
podmínka potichu vynechá. Například zaoblení uprostřed mezi dvěma stejnými hranami
ohlásí nejednoznačný výběr; nezaoblí náhodně jednu z nich.

| Bod | Navržené rozhodnutí |
|---|---|
| **C1 Význam odkazu** | Rozlišit skupinový předpis a požadavek na jediný výsledek. `all`, `face`, `between`, `parallel`, `type`, `radius` mohou záměrně označovat více hran. `near` znamená jedinou nejbližší hranu po filtrech; `find_face` jedinou plochu. Projekce a uložené měření vyžadují právě jednu hranu i bez `near`. |
| **C2 Nejednoznačnost** | Shromáždit všechny rovnocenné kandidáty, odstranit pouze opakovaný výskyt téhož topologického tvaru. Při více rozdílných kandidátech pro jedno místo vrátit chybu; žádné první `min/max/next`, třídění podle indexu ani největší plocha jako náhradní rozhodnutí. |
| **C3 Vstupy a filtry** | Ověřit strukturu, konečná čísla, podporovaný druh a smysluplný poloměr/směr. Zadaný `type` a `radius` jsou závazné. Odstranit fallback `same or faces` u zadaného poloměru a u směru zadané rovinné plochy. Chybějící shoda není důvod oslabit předpis. |
| **C4 Plochy a roviny** | Zachovat pojmenované směry a jejich skupiny; rovina `top` označuje krajní rovinu, nikoli identitu jednoho jejího kusu. Bodový odkaz vyhodnotit podle pravidel v oddílu 4, včetně odmítnutí shody vzdálenosti a normály. Zachovat ověřené sledování průměru hřídele u odkazu bez pevného poloměru. |
| **C5 Vytváření a přenos výběru** | Ověřit každý nově vytvořený předpis zpětným vyhodnocením proti skutečně kliknutému tvaru, včetně záložního popisu. Přenos do dřívějšího stavu a z řezu musí mít jediný geometricky doložený protějšek; jinak se odmítne. |
| **C6 Jednotné použití** | Stejné rozhodnutí použít pro prvky, promítání, uložená měření, plochové NDT cíle a odpovídající výběry v řezu. Zachovat stávající stavy a výjimkové hranice, historii, worker a ochrany P1.2. Vadná NDT reference se nesmí potvrzením studie přepsat na náhodně vybranou plochu. |
| **C7 Kompatibilita a meze** | Formát zůstává 22, bez nových uložených polí, identifikátorů ploch, závislostí a změny IPC. Záměrné změny výsledku starých předpisů jsou vyjmenované v oddílu 6. Nejde o úplné vyřešení topologické identity. |
| **C8 Předání** | Tři kroky C.1–C.3, matice S01–S20, po každém Ruff a celý pytest před commitem; poté oba celé cílové workflow a ruční přijetí balíčku. Implementační PR se sloučí až na samostatný pokyn autora. |

Požadavek „připravit návrh“ opravňuje k tomuto dokumentačnímu PR. Není souhlasem
s C1–C8, implementací ani sloučením tohoto návrhu. Schválení musí uvést, zda povoluje
C1–C8 a kroky C.1–C.3; sloučení návrhového PR se rovněž výslovně potvrdí.

## 2. Ověřený výchozí stav

P1.2B je dokončené: [protokol autora](p1-2b-rucni-overeni-macos-2026-10-22.md)
zaznamenává 17 ručních kontrol a samostatné povolení sloučení. Strom `main`
`c197eb0bdc7c10a1d2913d7a21f2fe807220fcad` je shodný s otestovanou hlavou PR #35
`c30dd09`; sada má 1 311 testů. Toto číslo není počet nových regresí P1.3.

| Místo současného kódu | Nález a důsledek |
|---|---|
| `selectors.select_edges` | `near` používá jediný `min`; stejně vzdálené hrany nerozlišuje. Skupinové výběry a sjednocení seznamů jsou již podporované a musí zůstat. |
| `selectors.find_face` | Má pásmo vzdálenosti 10⁻⁴ mm a volí `max` shody normály. Další shodu skóre nezjišťuje. Neznámý `type` se chová jako nepřítomný; zadaný poloměr může při nenalezení ignorovat. |
| `selectors.select_faces/face_plane` | Pojmenovaná plocha vrací všechny krajní rovinné kusy stejného směru. To je záměrná skupina; použití první položky pro společnou úroveň samo není důkaz chybné identity. |
| `picking.edge_selector/_face_reference_at` | Hrany se zpětně kontrolují, ale poslední záložní popis už samostatnou závěrečnou kontrolu nemá. U šikmé/zakřivené plochy se porovnává poloha počátku, nikoli totožnost znovu nalezené plochy. |
| `picking.map_edges` | Bere první hranu stejného druhu, jejíž geometrie prochází středem zdrojové hrany. Pro obecné křivky `_same_curve` vrací pouze shodu typu. |
| `projection.refresh`, `measure.resolve` | Již odmítají počet hran odlišný od 1. Skrytá volba v `near` však může více možností zredukovat ještě před touto kontrolou. |
| `measure.evaluate`, `ndt.study.evaluate/refresh_target`, `ndt.geometry.faces_of` | Sdílejí hledání ploch. Měření již umí chybu bez hodnoty, studie stav `broken`; PT/MT/RT odmítají seznam problémů cíle. Zachovat tyto hranice a ověřit všechny spotřebitele. |
| `session._model_shapes` | Pro plochu z řezu vybírá jediný nejbližší protějšek a následně kontroluje vzdálenost a normálu; další rovnocenné možnosti neověřuje. |

### Průzkum na nezměněném `main`

Jednorázové místní výpočty používají skutečnou geometrii a obal, který pouze
obrátí pořadí vrácených hran/ploch. Nemění jádro, souřadnice ani recept. Jsou
podkladem návrhu, **ne nově implementovanými regresními testy**:

| Případ | Pozorovaný výsledek |
|---|---|
| Kvádr 20×30×40 se středem v počátku; `parallel=Z`, `near=[0,-15,0]` | Bez změny geometrie se výsledek obrácením pořadí změní z hrany se středem `[-10,-15,0]` na `[10,-15,0]`. Obě jsou 10 mm od bodu. |
| Dva kvádry 20×20×10 se středy `[-20,0,0]` a `[20,0,0]`; bod `[0,0,5]`, normála +Z, typ `plane` | Stejně vzdálené horní plochy se stejnou normálou: nalezený střed se změní z `[-20,0,5]` na `[20,0,5]`. Objem 8 000 mm³, 2 solidy. |
| Válec R5, výška 10; bod `[5,0,0]`, typ `cylinder`, uložený `radius=99` | Vrátí plochu R5 místo odmítnutí neshody poloměru. |
| Kvádr, typ `not-a-face-type` | Vrátí rovinnou plochu místo chyby neznámého typu. |
| Deska 60×30×10 se dvěma průchozími dírami R3 v X=−10 a +10; odkaz na stěnu levé díry v `[-7,0,0]` | Po odstranění levé díry stejný předpis vrátí stěnu pravé díry v `[7,0,0]`. Dokládá zbytkovou mez identity popsanou v oddílu 6; samotná kontrola shod tuto záměnu nepozná. |

## 3. Co musí a nemusí být jednoznačné

**Skupina:** `{"face":"top","radius":"D/2"}` pro zaoblení znamená všechny
odpovídající kruhové hrany; změna počtu je dovolena významem předpisu. Také `all`,
seznam výběrů a několik kusů krajní horní plochy zůstávají legitimní.

**Jedna věc:** `{"parallel":"Z","near":[0,-15,0]}` musí po filtrech určit
jedinou nejbližší hranu. Projekce a uložené měření potřebují jedinou hranu i tehdy,
když jejich předpis nemá `near`. Každá položka seznamu ploch NDT cíle potřebuje
jednu plochu; seznam je záměrná skupina těchto jednotlivých odkazů.

Opakovaný výskyt **téhož** tvaru lze sloučit přes `is_same`; dvě různé plochy
se stejnou polohou, obsahem nebo normálou nelze tímto způsobem prohlásit za jednu.
Výsledek nebo důvod odmítnutí musí být nezávislý na pořadí kandidátů.

`top + offset` je výslovně rovina v určité vzdálenosti od krajní plochy. Není to
odkaz na identitu dna kapsy. Když kapsa zanikne, samotná rovina může nadále existovat.
P1.3 tento starý význam bez změny formátu nepřejmenuje na vazbu k jedné ploše.

## 4. Navržená pravidla vyhodnocení

### Hrany a číselné vstupy

1. Nejdřív ověřit strukturu celého předpisu, i když dřívější filtr nenajde nic.
   Body mají přesně 3 složky; každé vyčíslené číslo je konečné. Neznámý klíč,
   druh nebo osa je chyba. Výrazy v dosavadních číselných polích hran zůstávají.
2. Aplikovat všechny zadané filtry. Poloměr je konečný a kladný, nezmění se
   automaticky na poloměr jiné hrany. Seznam je sjednocení bez duplicit; neplatná
   položka se nevynechává.
3. Pro `near` spočítat vzdálenost všech zbývajících rozdílných hran. Do množiny
   rovnocenných patří každá s `d <= dmin + εd`. Jedna projde, více znamená chybu.
   Bez `near` se vrací celá vyhovující skupina; požadavek na 1 kontroluje spotřebitel.
4. Odkaz se sám neaktualizuje na novou hodnotu a nevrací uložené souřadnice
   projekce jako náhradu za nenalezenou hranu.

### Plochy podle bodu, druhu a normály

1. `at` musí být konečný 3D bod. Nepřítomná `normal` ponechává odkaz bez směrové
   preference; pokud je zadaná, musí být konečná, 3D a nenulová. Normalizovat pro
   porovnání, nikoli přepisovat recept. Nepřítomný `type` zůstává podporovaný.
2. Zadaný `type` patří mezi stávající `plane/cylinder/cone/sphere/torus` a je tvrdý
   filtr. Zadaný `radius` má smysl jen u současných typů s jedním poloměrem
   `cylinder/sphere`; je kladný a musí souhlasit v mezích tabulky níže.
   Nevhodná kombinace se odmítne. Bez shody se nezkouší jiný poloměr.
3. Pro `type=plane` se zadanou normálou požadovat stejný orientovaný směr
   (`dot > 1−10⁻⁶`). Při chybě shody se nevracet ke všem rovinám. Pro ostatní
   odkazy zachovat dosavadní význam normály: rozhoduje v pásmu vzdálenosti;
   u nevolných typů zůstane navíc stávající odmítnutí `dot < 0.5`.
   U válce, koule a kužele normála neurčuje pevnou globální orientaci celé plochy.
4. Ze zbylých ploch spočítat `dmin`, vzít pásmo `d <= dmin + εd` a porovnat
   normály v nejbližších bodech. Pokud mají alespoň dvě rozdílné plochy shodu
   skóre s nejlepším do `εdot` včetně, odmítnout. Bez směrové preference musí být
   v pásmu právě jedna plocha. Pořadí nesmí do výsledku vstoupit.
5. Pojmenovaná rovina zůstane určena směrem a krajní úrovní. Rozkouskování stejné
   roviny nesmí vytvářet falešnou chybu. Rozdílné úrovně v dosavadním pásmu
   `select_faces` posoudit zvlášť: rovinu neurčit náhodnou první položkou,
   použít skutečnou krajní úroveň podle směru.

| Mez | Návrh a význam |
|---|---|
| `εd = 10⁻⁴ mm` | Nerozlišitelnost vzdáleností při volbě jedné hrany/plochy; vychází ze současného pásma `find_face`. Není to největší dovolený posun odkazu. |
| `εdot = 10⁻⁶` | Nerozlišitelnost normalizovaného směrového skóre; bezrozměrné. |
| Poloměr `10⁻⁶ × max(1 mm, abs(r))` | Zachovat současnou délkovou mez příslušného výběru; nevydávat ji za přesnost výrobku. Hraniční `<`/`<=` doložit pro každou cestu, neměnit je potichu při sjednocování. |
| Přenos hran `10⁻⁵ mm` | Dosavadní `_ON_EDGE` pro geometrický protějšek; není to náhradní mez pro obecné hledání nejbližší hrany. |

Tyto meze jsou součástí návrhu ke schválení. Změna proti návrhu nebo zvyšování
tolerance kvůli neprocházející regresi se vrátí k rozhodnutí autora. Objemové meze
P1.1/P1.2 a tolerance NDT algoritmů se nemění. Případy těsně u hranice testovat
na řiditelných vzdálenostech i skutečné geometrii, ne na náhodě numerického šumu.

### Zpětné ověření a přenos z jiného stavu

- `edge_selector` musí po konečné volbě včetně fallbacku znovu získat přesně
  kliknutou množinu. Zpětné ověření se provede i pro odkazy promítnutých hran.
  Zaokrouhlený `near` nesmí vytvořit falešně jednoznačný výběr; pokud je třeba,
  použít více číslic stávajícího pole a opět ověřit, jinak požádat o jiný výběr.
- U bodové reference plochy porovnat skutečně nalezený tvar s kliknutou plochou
  aktuálního dílu, ne jen shodu počátku roviny. `is_same` zde slouží k ověření
  aktuálního výběru, není ukládanou identitou pro budoucí přepočet.
- `map_edges`: nejdřív totožný tvar v cíli; jinak geometrický přenos úsečky nebo
  kružnice/oblouku. Požadovat shodu nosné přímky či kružnice (včetně středu,
  roviny a poloměru) a obsažení celého zdrojového úseku/oblouku, ne jen středu.
  Delší původní hrana je dovolená. Dva vyhovující protějšky jsou chyba.
  U ostatních křivek bez totožného cílového tvaru se přenos výslovně odmítne;
  samotný stejný druh spline není důkaz stejné křivky.
- Plocha z řezu: hledat mezi původními plochami jediný protějšek stejné nosné
  geometrie a orientace, který obsahuje vybraný fragment. Umělá plocha řezu nebo
  více protějšků se odmítne. Není přípustné přenést celý fragment pouze podle
  jednoho jeho bodu. Konkrétní použití API jádra se ověří na zamčené instalaci
  před implementací a doloží S11; nelze-li obsažení spolehlivě doložit,
  bezpečný výsledek je odmítnutí s vysvětlením a možností vypnout řez.

## 5. Chyba, historie, měření a NDT

Navržené vzory českých zpráv (podrobnost s předpisem lze doplnit):

- „Výběr hrany není jednoznačný: stejně blízko jsou 2 hrany. Upřesni výběr
  nebo ji vyber znovu ve 3D.“
- „Plocha odpovídající zadanému druhu a poloměru už na dílu není. Vyber ji znovu.“
- „Vybranou hranu nelze v tomto stavu dílu jednoznačně najít. Vyber jinou hranu
  nebo přidej nový prvek z aktuálního výběru.“

Modelovací prvek při chybě zůstane `error`, následné prvky `skipped`; celý
nepřijatý výpočetní kontext zahodí již hotová P1.2B. Recept zůstane k opravě,
Zpět/Znovu funguje; nevytváří se nová automatická oprava dokumentu.
Projekce nepoužije staré body jako platný vstup do řešiče.
Uložené měření vrátí stávající výsledek s chybou a bez číselné hodnoty.
Chyba samostatného měření/NDT cíle nemusí zneplatnit jinak úspěšnou geometrii.

NDT studie s chybějící/nejednoznačnou plochou má `broken`; nesmí se spočítat
pouze zbývající část požadovaných ploch bez chyby. „Potvrdit studii“ nesmí
neplatnou vazbu automaticky přepsat. Explicitní nový výběr oblasti přes
`ModelSession` zůstává cestou opravy a má historii. Změna receptu dál vytváří
`stale` a ruší platnost starého odborného ověření podle současných pravidel.
Úspěšná reference není odborné ověření NDT. Zpřísnění hledání cíle není nové
pravidlo exportu či výpočtu nad chybnou historií; to zůstává P1.4/R01.

## 6. Kompatibilita a přiznané meze

Záměrně se změní případy, které dnes projdou díky první položce při shodě,
ignorovanému neznámému typu, ignorovanému uloženému poloměru/směru nebo
nedoloženému přenosu obecné křivky. Stejný JSON se nadále načte; jeho reference
ale může nově ohlásit chybu. To je změna chování ke schválení, nikoli migrace formátu.

**Pevné uložené R není živý parametr.** Například uložené měření válcové plochy
s `radius=5` po změně díry na R6 nově vyžádá výběr znovu. V podporovaných
výrazových polích hran lze použít `radius="D/2"`; výrazy do bodových plochových
odkazů se tímto nezavádějí. Odkaz tečné roviny bez pevného poloměru musí nadále
projít dosavadním testem hřídele D20 → D30; kliknuté pojmenované hrany a roviny
dále sledují rozměry podle významu předpisu. Všech 26 ukázek i dosavadní testy
sledování parametrů mají zůstat; případná kolize s C1–C7 se předloží autorovi,
nikoli skryje přepsáním očekávání.

**Bez trvalé identity nelze rozpoznat všechny záměny.** `near` a `at` jsou
geometrické dotazy v aktuálním stavu, nikoli doklad, který prvek původně vytvořil
danou plochu. Když původní díra zanikne a jiná zůstane jediným nejbližším
vyhovujícím kandidátem, starý předpis může nově označit ji. Také rozdělení/splynutí
s jediným vyhovujícím kusem, geometricky shodná náhrada a `top+offset` nemohou
zaručit původní konstrukční záměr. `εd` není limit největšího přemístění;
nový libovolný limit by rozbil sledování parametrů a sám by identitu neprokázal.

P1.3 tedy odstraňuje rozpoznatelné shody a oslabení předpisu, **neslibuje zákaz
všech historických záměn**. R04 lze uzavřít jen pro tuto vymezenou matici;
zbytkové riziko identity se ponechá otevřené. Pokud autor požaduje záruku původu
jednotlivé plochy i po odstranění, rozdělení a znovuotevření souboru, nejdřív
samostatný návrh ukládané identity/provenience, kompatibility a případné změny
formátu. Takové rozšíření není automaticky schválené tímto návrhem.

## 7. Budoucí regresní matice S01–S20

**Specifikace pro následnou implementaci, nikoli výsledky nových testů.**
U chyby prvku ověřit českou příčinu, `error/skipped`, původní geometrii i kontext;
u měření/NDT zvlášť jejich stavy a absenci zdánlivě platného výsledku.

| ID | Vstup / změna | Kritérium přijetí |
|---|---|---|
| S01 | Jednoznačná hrana mezi `front/right` kvádru, změna šířky 20 → 50. | Zachovat existující zaoblení R3: objem `w×30×40−(3²−π×3²/4)×40`, správný upravený roh, 1 validní solid. |
| S02 | Skupiny `all`, `face=top`, seznam se společnými hranami, 2 coplanární horní kusy. | Všechny předepsané hrany právě jednou; skupinu neodmítnout kvůli počtu. Roviny/krajní úroveň nezávislé na pořadí. |
| S03 | Kvádr 20×30×40, `parallel=Z`, `near=[0,-15,0]`. | Dvě stejně vzdálené přední svislé hrany: chyba pro obě pořadí; žádné náhodné zaoblení. |
| S04 | Rozdíl vzdáleností 0, 0.5εd, εd, 2εd; 2 i 3 kandidáti. | Do εd včetně odmítnutí, nad εd jediný vítěz. Ověřit i prohozené pořadí a duplicitní výskyt téhož tvaru. |
| S05 | Dva kvádry z průzkumu, plochový odkaz v mezeře. | Shodná vzdálenost a normála: chyba nezávislá na pořadí; původně 8 000 mm³ / 2 solidy zůstane. |
| S06 | Bod na hraně kvádru se dvěma různými normálami; bod bez normály. | Jasný směrový vítěz projde, shoda do εdot odmítnuta. Bez preference více stejně blízkých ploch je chyba. |
| S07 | Žádná plocha zadaného druhu; válec R5 s předpisem R99; změna uloženého R5 → skutečné R6. | Chyba bez náhrady jiným typem/poloměrem; uložené měření bez hodnoty, NDT `broken`. Nový explicitní výběr R6 obnoví správný průměr 12 mm. |
| S08 | Nesprávný/nesmyslný typ, rozměr bodu, nulová normála, nekladné R, NaN/∞ ve všech číselných cestách. | Konkrétní české odmítnutí, i když by jiný filtr nenašel kandidáta. Žádná nezachycená výjimka pro uživatele. |
| S09 | Konečný popis kliknuté hrany: běžná i fallback větev, blízké hrany a zaokrouhlené `near`. | Přesně původní kliknutá množina, jinak chyba; totéž plochová bodová reference. Pozice sama nestačí. |
| S10 | Zkrácená hrana po R3 proti delší původní; dva protějšky; různé oblouky stejného R. | Správný jediný původní úsek/oblouk; nesouhlas středu/osy/rozsahu nebo více možností se odmítne. Obecná křivka bez totožnosti se odmítne vysvětlením. |
| S11 | Výběr skutečného fragmentu při zapnutém řezu, umělá řezná plocha/hrana, fragment přes hranici rozdělených ploch. | Jediný doložený protějšek projde; umělý nebo nejednoznačný nepozmění recept ani historii. Řez zůstane jen pohledem. |
| S12 | Projekce `r1`: 1 hrana → více rovnocenných / žádná / jiný promítnutý druh. | Chyba projekce před řešením skici; uložené staré body se nepřijmou jako aktuální. Oprava a objem navázaného prstence se ověří fyzicky. |
| S13 | Rozdělit původní horní plochu kapsou tak, aby bodový odkaz byl mezi dvěma stejně vzdálenými kusy. | Bodový odkaz odmítnut, pojmenovaná krajní rovina a záměrná skupina zůstane podle C1/C4 platná. |
| S14 | Uložená měření desky/děr při změnách t, x1, x2; referenční nejednoznačnost. | Dosavadní očekávané tloušťky/rozteče zachovat. Při nejednoznačnosti bez hodnoty, bez převzetí jiného čísla jako úspěchu. |
| S15 | Plocha NDT cíle: shoda, zmizení, nejednoznačnost, změna receptu a „Potvrdit studii“. | `ok/stale/broken` dle příčiny; odmítnuté potvrzení nepřepíše cíl/ověření. Jedna špatná plocha zabrání tichému výpočtu podmnožiny; nové ruční ukotvení má historii. |
| S16 | Nejednoznačná reference v prvku, skutečný worker, GUI, CLI a offline nástroj AI. | Stejná příčina/stav bez síťového volání; BinTools/pickle zachová stavy/měření/NDT, žádná opuštěná dílčí operace v přijatém kontextu. |
| S17 | Chyba → oprava výběru → Zpět/Znovu → Uložit jako → nové otevření. | Správná geometrie, měření i NDT stav v každém kroku; původní soubor byte shodný, chybné předpisy se potichu nemigrují. |
| S18 | Všech 26 ukázek, formáty 1–22, dosavadní testy skic/hřídele/uložených měření/sloupků. | Zachovat fyzické výsledky a sledování parametrů; žádné vypuštění testu či toleranční ústupek. Nový rozpor proti návrhu má předem rozhodnutí autora. |
| S19 | Stejné dotazy nad vícesolidovým dílem, krátkou/dlouhou historií, opakované odmítnutí. | Žádná volba největšího tělesa ani únik nepřijatého stavu. Samostatné srovnání výkonu před/po se stejnými vstupy a geometrií, bez časového prahu v pytest. |
| S20 | Zánik díry s jinou jedinou vyhovující dírou; shodná náhrada; zánik kapsy s `top+offset`. | Charakterizační zkouška prokáže meze oddílu 6. Neslibovat automatické rozpoznání identity ani tyto případy vykázat jako bezpečně odmítnuté. Zbytkové R04 zůstane výslovně otevřené. |

Vedle parametrizovaných mezních kontrol přidat fyzické případy: objem, poloha
díry/zaoblení, materiál v konkrétních bodech, počet validních solidů, směr roviny
a skutečná měřená hodnota. Pro invariantnost pořadí je dovolen obal nad skutečnou
geometrií; sám nenahrazuje analytické kontroly. Počet nových testů se stanoví
podle výsledné parametrizace, ne předem vymyšleným cílovým číslem.

## 8. Malé implementační kroky a závislosti

| Krok | Rozsah po schválení | Výstup / dokončení |
|---|---|---|
| **C.1 Selektory a pravidla** | Po C1–C8: `selectors.py`, jasné rozlišení skupiny/1 výsledku, konečnost/struktura, tvrdé filtry, odmítnutí shod; S01–S08 a S13. | Žádná volba podle pořadí; dokumentovaná záměrná zpřísnění. Cílené testy, Ruff a celý pytest před commitem. |
| **C.2 Výběr a spotřebitelé** | Po C.1: audit a nutné změny `picking.py`, `projection.py`, `measure.py`, `session.py`, `ndt/study.py`, `ndt/geometry.py`; existující cesty NDT ověřit bez přepracování metod. S09–S15. | Zpětně ověřené nové reference, bezpečně odmítnutý přenos, žádné maskování chyby v měření/cíli. Zachované P1.2. Ruff a celý pytest před commitem. |
| **C.3 Historie, přenos a předání** | Po C.2: S16–S20, reálný worker a okno, kompatibilita, aktualizovaná evidence R04 a srovnání výkonu, ruční modely. | Kompletní matice se skutečnými výsledky/mezerami; Ruff a celý pytest před commitem. Samostatné implementační PR; oba celé CI běhy včetně stažení balíčku a ruční přijetí konečné verze. |

Před C.1 zaznamenat zdrojový/vstupní otisk a srovnávací měření; použít existující
P0 baseline a pevné dotazy nad ukázkami + dvěma případy z průzkumu. Zahřátí a
alespoň 3 měření, uvést jednotlivé časy, prostředí a fyzické podpisy. Nový index,
cache geometrie či plošné hluboké kopie nejsou součástí. Výkon se hodnotí před/po
na téže sadě; nesplnění smlouvy nelze omluvit rychlostí.

## 9. Ruční přijetí budoucí implementace

Testovací JSON a hodnoty připravit až z implementační verze, porovnat s CLI/offline
souhrnem a uvést označení konkrétního staženého balíčku. Vést autora po jednotlivých
zkouškách; zaznamenat pouze skutečně potvrzené kroky:

1. Otevřít přírubu, změnit rozměr a ověřit, že platná skupina hran i navázané prvky
   dále fungují. Uložit kopii a otevřít ji; původní soubor zachovat.
2. Kvádr s výběrem stejně blízko dvěma hranám: česká chyba, žádné náhodné zaoblení.
   Upřesnit výběr na přední pravou hranu; správný roh, objem, Zpět/Znovu.
3. Dvě stejně vzdálené plochy: měření nemá číslo, NDT studie má chybnou vazbu;
   potvrzení ji neopraví náhodným přiřazením. Vybrat oblast výslovně znovu.
4. Změnit průměr díry s uloženým pevným R: měření ohlásí nesoulad. Po novém
   výběru vrátí správný průměr, kopie po otevření zachová výsledek.
5. Promítnutá hrana a výběr v řezu: platný výběr se zachová, umělý nebo
   nejednoznačný se odmítne s návodem; oprava a historie fungují.

Skryté kandidáty a přesnou hranici tolerancí prokazují automatické zkoušky,
nikoli pouhý pohled. Mac nenahrazuje ruční průchod na Windows; odborná NDT-17
validace zůstává samostatná. Případnou nedostupnou platformu přiznat.

## 10. Brána dokončení a rozsah tohoto návrhového PR

P1.3 v popsaném rozsahu je dokončené až po C.1–C.3, S01–S20, obou celých cílových
workflow, vizuální kontrole skutečného okna a ručním přijetí konkrétního balíčku.
Evidence musí odlišit chybějící a nejednoznačnou vazbu, záměrnou skupinu a stále
neřešenou historickou identitu. Přijetí nezavírá zbytkové R04, R01/P1.4, R03,
R12 ani odbornou NDT-17. Další rozsah identity má vlastní rozhodnutí autora.

Tento návrhový PR obsahuje pouze dokumentaci a odkazy, včetně doplnění doloženého
dokončení P1.2B. Nemění `src/`, testy, ukázky, závislosti, formát, workflow ani
README oddíl „Formát modelu“ předávaný AI. Místní Ruff a celý pytest ověří stávající
kód před dokumentačním commitem; neprohlašují S01–S20 za implementované.
Dokumentační diff podle současných filtrů nespustí Windows/macOS sestavení;
nové balíčky jsou až branou budoucí implementace.

**Ke schválení: C1–C8, pravidla a meze oddílu 4, záměrná zpřísnění a omezení
oddílu 6, kroky C.1–C.3 a matice S01–S20.** P1.4/P1.5, P2, nová identita/formát,
STEP import, přepracování NDT algoritmů a NDT-16 tím schválené nejsou.
Sloučení implementace bude vyžadovat další samostatný pokyn.

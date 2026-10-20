# P1.1 — schválená smlouva geometrických operací

**Stav: schváleno autorem 20. 10. 2026, bez implementace.**
Autor v tomto rozhovoru potvrdil předložená rozhodnutí D1–D7 a matici testů slovy
„ok, schvaluji“. Schválení se týká smlouvy P1.1; implementace P1.2–P1.5 vyžaduje
samostatně schválený konkrétní rozsah. Modelový formát zůstává ve verzi 22.
Vychází z `main` / `e58d6283a69b51c2e19c9fece2de0e7977ce07f6`, po sloučení
[PR #30](https://github.com/JendaNDT/SkodaCAD/pull/30). Navazuje na
[roadmapu P1](roadmapa-vyvoje.md#p1--bezpečná-geometrie-čeká-na-schválení-implementace)
a [rizika P0](p0-audit-a-overeni.md#2-registr-rizik-a-omezení).

## 1. Schválená rozhodnutí autora

Cíl: určit, co se smí považovat za úspěšnou geometrickou operaci, jak poznat její
selhání a co musí zůstat zachováno. Tento dokument obsahuje schválené volby D1–D7
a konkrétní matici budoucích testů. Tento PR zaznamenává dohodnutá pravidla;
aplikace se chová jako dosud.

| Rozhodnutí | Schválená varianta | Důsledek / alternativa |
|---|---|---|
| **D1 Počet těles** | Zachovat podporu jednoho i více oddělených objemových těles; jejich počet a změnu počtu vždy výslovně uvést ve výsledku. | Existující test pole trubek požaduje 3 tělesa. Plošné pravidlo „vždy právě jedno“ by zrušilo již podporované použití; tuto alternativu nedoporučujeme bez samostatného rozhodnutí o kompatibilitě. |
| **D2 Platnost a účinek** | Úspěšný 3D výsledek musí obsahovat platné, uzavřené objemové složky, konečná čísla a rozlišitelný objem. Přidání/odebrání bez rozlišitelného účinku je chyba. | Prázdný výsledek ani povrch nejsou hotový díl. Tělesa se nesmějí potichu zahazovat. |
| **D3 Tolerance** | Použít níže vymezené tolerance v mm/mm³, bez automatického zvětšování nebo dodatečného opravování geometrie. | Výsledky těsně pod rozlišením jádra nejsou důkazem fyzického spojení; NDT tolerance zůstávají samostatné. |
| **D4 Úpravy hran a skořepina** | Zaoblení/sražení mohou materiál přidat i ubrat; musí zachovat počet složek. Skořepina v první implementační sadě vyžaduje alespoň jednu vybranou otevřenou plochu. | Skořepina bez otevřených ploch dnes pouze zmenší plný díl. Doporučujeme ji srozumitelně odmítnout; správné vytváření uzavřených dutin je samostatné rozšíření. |
| **D5 Selhání a historie** | Chybný prvek zůstane viditelný v receptu s chybou; pro náhled se zachová poslední platná geometrie. Neúspěšný výpočet nesmí zanechat částečné změny kontextu. | Zachová se dosavadní možnost opravit parametr nebo použít Zpět. Automaticky se nezahazuje zadaný recept. |
| **D6 Průnik** | Zde vymezit jeho smlouvu a referenční případy, ale zatím jej nepřidávat jako novou modelovací operaci. | Dnes jsou volby `new`, `add`, `cut`. Nová volba průniku v receptu/GUI potřebuje samostatně schválený rozsah a rozhodnutí o kompatibilitě formátu. |
| **D7 Rozsah schválení** | Schválit pravidla a matici P1.1; implementační změny rozdělit do samostatných kroků P1.2–P1.5. | Schválení tohoto návrhu samo nespouští P1.2/P2 ani nový formát. Dokumentační PR se neslučuje bez souhlasu autora. |

Více těles zde znamená více oddělených objemových složek v jednom receptu, nikoli
sestavu P5: nevznikají samostatné dokumenty, vazby ani pozice součástí.

## 2. Co potvrzuje současný kód

- `BuildContext.apply` podporuje jen `new/add/cut`. `add` bez dosavadního tělesa
  smí vytvořit první těleso; `new` při existujícím dílu je chyba. Tato pravidla zachovat.
- Kontrola `is_valid` sama nestačí: prázdný `Part()` vrací `True`, ale má 0 solidů
  a objem 0. Platný sjednocený výsledek také může obsahovat více oddělených solidů.
- `tests/test_sweep_loft.py::test_pattern_repeats_a_sweep` výslovně očekává
  **3 solidy**. R02 je proto otázka očekávání a viditelnosti počtu těles, nikoli
  důkaz, že každý výsledek s více solidy je vadný.
- Zaoblení, sražení a skořepina zapisují `ctx.part` přímo; ochrana tedy musí zahrnout
  i závěr celého prvku, ne pouze `BuildContext.apply`.
- `_run_feature` dnes při chybě vrací pouze `ctx.part`; úplnost obnovy skic, operací
  a rozpracovaného záznamu je téma P1.2 (R05).
- `ModelSession.export` zatím nekontroluje `result.ok` (R01). P1.1 tento nález
  neřeší a nesmí označit částečný náhled za hotový exportovatelný díl.

### Ověřené průzkumné případy

Místně na nezměněném zdrojovém kódu uvedeného main, Python 3.12.14, build123d 0.13.0,
proběhly jednorázové výpočty. Jde o podklad návrhu, nikoli implementované nové regrese.

| Případ | Pozorování | Důsledek pro smlouvu |
|---|---|---|
| Kvádr 20×30×40 + oddělený 5×5×10 na X=100 | Platné, 24 250 mm³, **2 solidy**. | Hlásit skutečný počet; neprohlašovat jeden souvislý díl. |
| Stejný přídavek s plošným dotykem na X=20 | Platné, přibližně 24 250 mm³, **1 solid**. | Nulový překryv objemu sám neznamená chybu přidání. |
| Dotyk pouze hranou / bodem | Platné, přibližně 24 250 mm³, **2 solidy**. | Vzdálenost 0 sama nedokazuje jeden solid. |
| Přídavek s mezerou 10⁻⁵ mm | **2 solidy**. | Zaznamenat oddělení, nepřidávat vlastní slučování mezer. |
| Přídavek s mezerou 10⁻⁸ mm | Jádro vrátí vzdálenost 0 a **1 solid**. | Pod numerickým rozlišením nelze slibovat rozlišení fyzické mezery. |
| Řez kvádru pásem X=9…11 přes celou výšku/šířku | Platné, 21 600 mm³, **2 solidy**. | I odebrání může zvýšit počet složek. |
| Vnitřní roh půdorysu L, výška 10, zaoblení R2 | 3 000 → **3 008,584073464 mm³**. | Zaoblení nemusí zmenšit objem. |
| Stejný vnitřní roh, sražení 2 mm | 3 000 → **3 020 mm³**. | Totéž platí pro sražení. |
| Skořepina kvádru 50×30×20, t=2, otevřený vršek | **8 472 mm³**, rozměry 50×30×20. | Referenční podporovaný případ. |
| Stejná skořepina, `open_faces=[]` | **19 136 mm³**, plný kvádr 46×26×16. | Bez dalšího rozlišení nejde o vydlabání původního dílu; D4 stanovuje odmítnutí v následné implementaci. |
| Všech 26 JSON ukázek, včetně podsložek | Všechny se přepočítaly úspěšně; výsledky i existující tělesa před prvky mají 1 solid. | Ukázky neodhalí podporované vícesolidové pole; musí zůstat i samostatný test pole. |

## 3. Společná smlouva 3D operace

**Vstup:** dosavadní geometrie A (nebo žádná), nástroj B / vybrané hrany či plochy,
vyhodnocené parametry, významové reference a popis operace. Jednotky jsou mm, mm²,
mm³; úhly ve stupních. Číselné hodnoty, rozměry a meze musí být konečné.
Nejednoznačná reference se nemá hádat; rozpoznávání takových vazeb dodá P1.3.

**Před přijetím:**

1. Vypočítat kandidáta mimo přijatý stav. Výjimku jádra převést na českou chybu.
2. Rozlišit nepřítomný/prázdný tvar, povrch a objemové těleso. Když operace slibuje
   3D výsledek, musí být počet solidů alespoň 1; nesmí zůstat volné plochy/hrany mimo
   tyto solidy ani prázdné složky vydávané za díl.
3. Ověřit platnost tvaru i jeho objemových složek, uzavřenost jejich hraničních
   shellů, konečné souřadnice/mezní rozměry a kladný rozlišitelný objem každé složky.
   Počet shellů nemusí být 1: vnitřní dutina nebo průchozí otvor nejsou samy o sobě chyba.
4. Ověřit postpodmínky konkrétní operace a její pravidlo počtu složek.
5. Přijmout celý výsledek, nebo jej celý odmítnout. Nevybírat největší solid,
   neodmazávat drobné části, nepřesouvat vstupy a nezkoušet větší toleranci jen kvůli úspěchu.

**Nástroj B není výsledný díl.** Nástroj pro několik děr smí mít několik oddělených
validních objemových částí. Nesmí se na něj omylem uplatnit pravidlo „právě jeden solid“.
Platnost objemových nástrojů se ověří také; jeden vadný nástroj se nesmí potichu vynechat.
Kontrola účinku `add/cut` se vztahuje na celý předaný nástroj, ne na zaručené zasažení
každé jeho dílčí části. Úplnost všech děr/poloh vyžaduje příslušný referenční test.

**Počet složek:** schválená D1 dovoluje `N ≥ 1`. `new/add/cut` a opakování nesmějí
tento počet zatajit; při změně se uvede `N před → N po`, např. „Řez vytvořil 2 oddělená
tělesa (předtím 1).“ U zaoblení, sražení a skořepiny se požaduje zachování počtu.
Jeden solid je závazný pouze pro konkrétní referenční případ, který jej očekává.
Neexistuje nová trvale ukládaná volba režimu ani automatické odhadování úmyslu autora.

**Výsledek a chyba:** zachovat stavy `ok/error/skipped`. Informace o více tělesech
je doprovodná informace k platnému výsledku; nezavádí nový stav modelu. P1.2 musí
zajistit její dostupnost v GUI, CLI a nástrojích AI stejnou cestou, odvozením z
geometrie / existující zprávy prvku; nový uložený formát ani IPC protokol nejsou předepsané.
Úspěch geometrické smlouvy není odborná validace NDT ani záruka splnění konstrukčního záměru.
P1.1 zejména nedokládá správnost NDT algoritmů nad několika solidy; takové případy
musí mít vlastní referenční ověření v NDT-17 před tvrzením jejich ověřené podpory.

Skica a dokument tvořený jen skicami mohou mít `part=None` a být platné. Tato smlouva
nepřevádí běžné mezikroky 2D modelování na chybu.

## 4. Numerické meze navržené ke schválení (D3)

| Veličina | Návrh | Použití a omezení |
|---|---|---|
| Délka | `εL = 10⁻⁶ mm` | Kontroly rozměrů v analytických případech. Není to příkaz pro posun/sloučení vstupů ani záruka rozpoznání libovolné malé mezery. |
| Objem | `εV = 10⁻⁹ × max(1 mm³, abs(VA), abs(VR))` | Rozlišitelnost celkového objemu a účinku přidání/odebrání. `VA=0` při prvním tělese; velikost řezacího nástroje se do této meze nezahrnuje. |
| Jednotlivá složka | `εVi = 10⁻⁹ × max(1 mm³, abs(Vi))` | Každá složka musí mít `Vi > εVi`; menší se nesmaže, odmítne se celý kandidát jako nerozlišitelný. |

Objemová mez vychází z řádu současných kontrol v `BuildContext.apply`, nikoli z nové
metrologické přesnosti. Průzkum instalovaného OCCT vrací `Precision.Confusion_s() = 10⁻⁷`
v jednotkách modelu; neznamená to, že všechny algoritmy mají totožnou přesnost.
Tolerance skic, výběru ploch a NDT se v tomto kroku nesjednocují a nemění.

U `add/cut` je účinek do `εV` včetně hranice odmítnut s vysvětlením, že jej nelze
spolehlivě rozlišit. Meze nezakládají obecnou podporu libovolně malých dílů nebo všech
velikostí modelu. Před implementací se doplní případy `0`, `0,5 εV`, `εV`, `2 εV`
a různá měřítka; pokud kontrola nevyhoví dohodnutému rozsahu, nejdřív se upraví návrh,
nikoli potichu zvýší tolerance.

## 5. Postpodmínky jednotlivých operací

Význam výsledku R je `new: R=B`, `add: R=A∪B`, `cut: R=A∖B`, budoucí průnik
`R=A∩B`, vždy v přiznaném numerickém modelu. V referenčních testech kontrolovat také
zachování původního materiálu u add a polohu/rozsah odebraného materiálu u cut.
Povinné kontroly kandidáta popsané níže nejsou formálním důkazem správnosti jádra.

| Operace | Předpoklady | Úspěšný výsledek | Odmítnout |
|---|---|---|---|
| `new` | Dosud není těleso; objemový nástroj je platný. | Celý nástroj splňuje společnou smlouvu; pravdivě uveden počet solidů. | Existující díl, prázdný/povrchový/vadný či nerozlišitelný nástroj. |
| `add` | A může chybět jako dnes; jinak platné A a B. | Bez A jako `new`; jinak `VR − VA > εV`, `VR ≤ VA + VB + εV`, platné všechny složky a zveřejněný počet. | Žádný rozlišitelný přírůstek, ztráta původního materiálu nad toleranci, neplatné složky. Samotné oddělení není dle D1 chyba. |
| `cut` | Existující A, platný objemový nástroj B. | `VA − VR > εV`, `VR > εV`, platné všechny složky; při rozdělení zveřejnit změnu počtu. | Bez A, řez mimo materiál / jen dotyk, odebrání celého dílu, numericky nerozlišitelný zbytek nebo neplatný výsledek. |
| Zaoblení | Existující díl, konečné `radius > 0`, nalezené hrany. | Platný objemový výsledek, stejný počet složek; referenční test doloží poloměr a očekávanou změnu. | Nenalezené hrany, neproveditelný poloměr, neplatný výsledek nebo změna počtu složek. Objem nemusí klesnout. |
| Sražení | Existující díl, konečné `distance > 0`, nalezené hrany. | Totéž jako zaoblení; na referenčním dílu odpovídá velikost sražení. | Totéž; objem nemusí klesnout. Nula zde není přepínač vypnutí prvku. |
| Skořepina | Existující díl, konečné `thickness > 0`, alespoň jedna nalezená otevřená plocha. | Platný materiál stěn, stejný počet složek, `0 < VR < VA − εV`; referenční případy zachovají vnější obálku a správnou tloušťku. | Chybějící otevřené plochy, příliš silná stěna, rozpad/neplatnost. Neukládat plný zmenšený díl jako vydlabaný. |
| Loft / přechod | Alespoň dvě existující skici v pořadí, vždy jedna plocha bez vnitřních smyček jako dnes; konečné parametry. | Vytvořený objemový nástroj splní smlouvu a následně `new/add/cut`. | Chybějící/degradované/nevhodně ležící profily, vadný objem, porušení navazující booleovské operace. |
| Průnik, pouze návrh | Dva platné objemové vstupy. | `εV < VR ≤ min(VA,VB)+εV`; počet složek podle D1. Úplné ponechání A při obsažení A v B je platný průnik. | Prázdný průnik, jen plocha/hrana/bod, vadná objemová část. Žádné nové `operation` se tímto nezavádí. |

Objemové nerovnosti jsou nutné kontroly, nikoli důkaz správného prostorového
výsledku. Sada referencí proto vždy přidává rozměry, polohu, průřezy nebo konkrétní
významové plochy. Objemové součty nesmějí nahradit ověření požadovaného úbytku/přírůstku
v referenčním místě. Stejný objem dvou tvarů také nedokazuje, že jsou stejné.

U dutého loftu zachovat výslovně existující význam: kruh→kruh má tloušťku kolmo
k plášti, fallback kruh↔hranatý profil ji měří v rovinách skic. P1.1 neslibuje
konstantní kolmou tloušťku všude a neschvaluje přepracování tohoto algoritmu.

## 6. Matice budoucích regresních případů

**Toto je specifikace testů pro následnou implementaci. Níže nejsou nově přidané testy.**
U každého odmítnutí ověřit českou zprávu, původní geometrii i kontext a přeskočení
následných prvků. Nepřepisovat starý test pouhým novým očekáváním bez schválení změny.

Základní kvádr 20×30×40 zabírá `[0,20]×[0,30]×[0,40]` mm. Přídavek 5×5×10
na X=x zabírá `[x,x+5]×[0,5]×[0,10]`. U půdorysu L mají oba kvádry společný roh
v počátku; upravovaná vnitřní hrana vede z `[10,10,0]` do `[10,10,10]`.

| ID | Operace / vstup | Očekávání doporučené varianty |
|---|---|---|
| G01 | Prázdný `Part()` s `is_valid=True`. | Chyba, 0 solidů není 3D výsledek. |
| G02 | Solid sestavený z otevřeného shellu; v průzkumu má i kladný objem 19 200 mm³. | Chyba neplatnosti/uzavřenosti. Kladný objem nestačí. |
| G03 | Nekonečná/NaN hodnota, nulový nebo záporný rozměr; vadná dílčí objemová složka. | Odmítnout, žádné vynechání složky. |
| G04 | Tvar s jedním validním solidem a volnou plochou mimo něj. | Odmítnout smíšený neobjemový zbytek; samotné N=1 a kladný objem nestačí. |
| N01 | První kvádr 20×30×40, explicitní `new` i dnešní `add` bez A. | 24 000 mm³, 20×30×40, 1 solid. |
| N02 | Druhé `new` nad existujícím dílem. | Chyba a zachovaný předchozí díl. |
| N03 | Dvě kružnice Ø10 se středy [−15,0] a [15,0], vysunutí 10. | `500π` mm³, 2 platné solidy, oba zachované a oznámené podle D1; nesloučit či nevybrat jeden potichu. |
| A01 | Kvádr + stejný kvádr posunutý o 10 mm v X. | 36 000 mm³, obálka 30×30×40, 1 solid. |
| A02 | Přídavek 5×5×10 plošným dotykem na X=20. | Přibližně 24 250 mm³, 1 solid. Není vyžadován objemový překryv. |
| A03 | Stejný přídavek na X=100. | 24 250 mm³, 2 solidy a výslovná informace 1→2. |
| A04 | Přídavek se společnou hranou / bodem. | 2 solidy, neprohlašovat za jeden; odpovídající objem a poloha. |
| A05 | Nástroj zcela uvnitř existujícího kvádru / totožný kvádr. | Nově navržená chyba nerozlišitelného účinku; původní objem 24 000 mm³. |
| C01 | Kapsa 5×5×10 z horní plochy základního kvádru. | 23 750 mm³, 1 solid, skutečná otevřená kapsa ve správné poloze. |
| C02 | Nástroj mimo díl nebo pouze tečný. | Chyba bez odebrání materiálu. |
| C03 | Nástroj odebere celý kvádr. | Chyba, původní díl 24 000 mm³. |
| C04 | Řez pásem X=9…11 přes celý kvádr. | 21 600 mm³, 2 solidy, informace 1→2. |
| C05 | Deska 40×40×10 se středem XY v počátku, dvě řezačky Ø4 skrz, středy [−10,0] a [10,0]. | `16 000−80π` mm³, obě díry ve správných polohách, konečný 1 solid; nástroj smí mít 2 solidy. |
| F01 | Kvádr 20×30×40, všechny svislé hrany R3. | `24 000 − (4−π)×3²×40` mm³, 1 solid; zachovat existující test. |
| F02 | Vnitřní roh L: sjednocení 20×10×10 a 10×20×10, R2. | `3 000 + (4−π)×10` mm³; platná přidaná výplň, ne falešná chyba růstu objemu. |
| F03 | R50 na kvádru; prázdný výběr; R=0 a R<0. | Odmítnout; žádná nová tichá interpretace nuly. |
| H01 | Kvádr 20×30×40, čtyři svislé hrany s=2. | `24 000 − 4×(2²/2)×40` mm³, správné sražené rohy, 1 solid. |
| H02 | Vnitřní svislý roh uvedeného L, s=2. | 3 020 mm³, platná výplň; zachovaný počet složek. |
| H03 | Neproveditelné sražení s=50; záporná hodnota. | Odmítnout a zachovat poslední platný díl. |
| S01 | Kvádr 50×30×20, otevřený vršek, t=2. | `30 000 − 46×26×18 = 8 472` mm³; obálka 50×30×20, 1 solid. |
| S02 | Prázdné/vynechané `open_faces`; neproveditelná tloušťka; nenalezená plocha. | Odmítnout; žádný plný zmenšený kvádr jako úspěch skořepiny. |
| L01 | Souosé čtverce 40×40 a 20×20, výška 30, rovné stěny. | `30/3 × (1 600+400+800) = 28 000` mm³, výška 30, 1 solid. |
| L02 | Kruhy Ø40 a Ø20, výška 30. | `7 000π` mm³; odpovídající průměry a výška, 1 solid. |
| L03 | Jen jedna skica / chybějící skica / skica s dírou / degradované profily. | Odmítnout; zachovat již existující kontroly a referenční chyby. |
| L04 | Existující dutý kužel a přechod kruh↔čtverec. | Zachovat testy tloušťky kolmo, resp. v rovinách skic; bez změny významu. |
| M01 | Existující `test_pattern_repeats_a_sweep`. | Nadále 3 validní solidy a trojnásobný analytický objem; přidat kontrolu oznámení počtu. |
| M02 | Pole děr / zrcadlení výřezu, včetně několika podoperací a chyby poslední. | Správná geometrie; při chybě obnoven celý stav před prvkem, nikoli část pole. |
| T01 | Přídavek s mezerou 10⁻⁵ mm. | 2 validní složky a pravdivá informace; bez dodatečného sloučení. |
| T02 | Přídavek s mezerou 10⁻⁸ mm u základního kvádru. | Povolené N∈{1,2}; všechny složky platné/uzavřené, objem 24 250 mm³ v εV, obálka 25×30×40 v εL a pravdivě uvedené N. V hraničním pásmu neslibovat fyzické spojení; neprovádět vlastní opravu. |
| T03 | Účinek add/cut v bodech 0, 0,5 εV, εV, 2 εV; různé velikosti. | Do εV odmítnutí; nad εV jen při splnění všech dalších podmínek. |
| X01–X03 | Budoucí průnik: překryv kvádrů; B obsahuje A; jen plošný dotyk / prázdno. | Objem a rozměry analyticky; A beze změny je platné při obsažení; neobjemový výsledek odmítnout. Pouze budoucí specifikace, ne nová funkce. |

T02 záměrně nemá tvrzení „tato fyzická mezera je bezpečně rozpoznatelná“. Testuje
přiznané meze numerického modelu a pravdivost výsledku, nikoli libovolně přesný CAD.
Referenční tolerance pro složitější povrchy musí zůstat u konkrétního testu s důvodem;
nesmí se plošně zvětšit `pytest.approx`, aby zmizela regrese.

## 7. Selhání, kontext a navazující bezpečnost

Na úrovni výpočtu prvku se při selhání musí obnovit přijatý tvar, slovník skic,
slovník již přijatých operací a rozpracovaný záznam operací. P1.2 ověří také to,
že se původní objekt geometrie nezměnil nepřímo; samotná shoda ukazatele nestačí.
Další prvky se označí jako přeskočené, selhaný prvek má česky příčinu a možnost nápravy.

Na úrovni session může zůstat nový, právě neproveditelný recept v historii. Náhled
posledního platného tělesa musí být označen jako částečný/chybný výsledek. Zpět,
Znovu a ruční oprava parametru zůstanou možné; recept se sám nepřepíše starou verzí.

Nepřekládat splnění této smlouvy do tvrzení „NDT studie je platná“. Změny receptu
nadále zastarávají studie. Vazby a jednoznačnost patří do P1.3, export/NDT při chybě
do P1.4. Dokud není dokončeno P1.4, zůstává otevřený R01; nelze deklarovat hotovou P1
jen proto, že se začaly kontrolovat booleovské výsledky.

## 8. Navazující implementační kroky k samostatnému schválení

| Krok | Rozsah | Výstup a podmínka přijetí |
|---|---|---|
| P1.2A | Společná validace kandidáta, pravidla počtu složek a české zprávy; propojení `apply` i přímých úprav hran/stěn. | G/N/A/C/F/H/S případy; více těles a změna počtu jsou vidět v GUI/CLI/AI. Nezavádí se průnik ani nový formát. |
| P1.2B | Přijetí celého prvku a obnova celého kontextu, složené pole/díra/závit. | Chyba poslední podoperace nezmění tvar, skici ani operace; historie a pracovní proces mají regrese. |
| P1.3 | Jednoznačnost významových referencí podle samostatně rozpracované matice. | Chybějící/nejednoznačný výběr není nahrazen odhadem jiné plochy. |
| P1.4 | Samostatně schválené pravidlo exportů, náhledů a NDT při chybném/částečném výsledku. | Stejné chování GUI/CLI/AI; uzavření R01 doložené testem. |
| P1.5 | Celá referenční sada, kompatibilita, oba systémy a ruční přijetí. | Ruff, celý pytest, Windows/macOS sestavení i test stažených balíčků, ruční protokol; vypsané zbývající meze. |

Konkrétní změny, pořadí, testy a kritéria přijetí jsou rozpracované
v [návrhu P1.2A ke schválení](p1-2a-navrh-spolecne-kontroly-geometrie.md).
Implementace tohoto návrhu zatím nezačala. Schválená smlouva nepředepisuje novou
architekturu tříd ani nový přenášený či uložený datový formát.

## 9. Kompatibilita a kritéria dokončení P1.1

- Model zůstává ve verzi **22**; načítání verzí 1–22 a všechny recepty v `examples/`
  musí zůstat dohledatelné. Načtení receptu a úspěšnost jeho nově přísnějšího přepočtu
  jsou odlišné věci: např. prázdná volba otevřených ploch skořepiny se podle D4 nově odmítne.
- Zachovat výslovně podporované vícesolidové pole. Přidání bez účinku a skořepina
  bez otevřených ploch jsou schválená pravidla pro následné zpřísnění chování;
  implementační krok musí mít vlastní schválený rozsah, srozumitelnou chybu
  a test obnovy. Žádná tichá migrace nebo přepis souboru.
  Zpřísnění D2 se týká také neplatných, otevřených nebo podrozlišovacích složek;
  žádná se nesmí jen odstranit, aby zbytek kandidáta prošel.

- Způsob volby hran/ploch, NDT upozornění, knihovny a jejich verze se tímto nemění.
  P2, STEP import, sestavy, nové souborové formáty, bezpečné ukládání R03 a NDT-16
  nejsou součástí této smlouvy.
- **P1.1 je dokončeno: autor 20. 10. 2026 schválil konkrétní volby D1–D7 a matici.**
  Schválení nezaručuje provedení nebo úspěch dosud nenapsaných testů a nenahrazuje
  NDT-17. P1.2–P1.5 zůstávají bez implementace.

## 10. Zdroje a ověření smlouvy

Stav kódu je uvedený commit main. Podstatné zdroje:
[operace a úpravy](../src/skodacad/features.py),
[přepočet a stavy](../src/skodacad/rebuild.py),
[session a export](../src/skodacad/session.py),
[volby modelu](../src/skodacad/schema.py),
[základní fyzikální testy](../tests/test_features.py),
[tažení, loft a vícesolidové pole](../tests/test_sweep_loft.py),
[pole a zrcadlení](../tests/test_pattern.py),
[obnova po chybě](../tests/test_rebuild_errors.py).

Průzkumné výpočty nepozměnily `src/`, modely ani testy. Sérii 26 ukázek a
samostatné případy je nutné odlišit od plánované nové matice; veškeré výsledky
budoucí P1 se budou zapisovat až po skutečném spuštění příslušné implementace.

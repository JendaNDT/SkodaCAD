# NDT – návrh etapy 07B: geometrické pokrytí cílového objemu

Stav: **autor schválil implementaci 17. 10. 2026; provedeno ve vývojové větvi
`codex/ndt-etapa-07b`, před sloučením do `main`**.
Výchozí stav: `main`, commit `0dea6f8`, [sloučené PR #16](https://github.com/JendaNDT/SkodaCAD/pull/16).
Navazuje na [Etapu 07 a provedený krok 07A](12-navrh-etapa-07.md),
[Etapu 06](11-navrh-etapa-06.md) a [závazné vymezení UT](04-zavazne-vymezeni-ut.md).
V otázkách podrobností výpočtu 07B tento dokument upřesňuje obecný návrh Etapy 07.

## Co tento krok přinese

Program spočítá, jaká část **zadaného objemu svaru nebo jiné kontrolované oblasti**
je geometricky pokrytá, nepokrytá nebo nejistá. Výsledek uvede v **mm³ a procentech
objemu**. Nezamění jej za pokrytí vnějšího povrchu dílu.

07B přidá výpočet, textový souhrn, CSV a ověření citlivosti na krok. Příklady
z 07A již obsahují zadání cíle; pro tento krok je bude možné vyhodnotit příkazovou
řádkou. Příkazy při předání spustí vývojář a ukáže autorovi výsledný souhrn a CSV.
Autor nemusí ručně upravovat JSON ani pracovat s příkazovou řádkou.

**Nový editor, tlačítka pro objemový výpočet a barevný náhled uvnitř dílu patří až do
07C.** Po 07B tedy nebude možné celý nový postup obsloužit běžným klikáním v okně.
Plochy a jednotlivé kontrolované body budou dál fungovat dosavadním způsobem.

## 1. Hranice rozsahu a současný základ

07A již umí vytvořit a ověřit cíle `volume` a `weld` v souboru verze 16:
rovný V svar bez otupení, koutový svar a hranol z jednoduchého polygonu.
`ndt/welds.resolve_target` vrací skutečné cílové těleso a jeho objem.
Obecný hranol se protíná s materiálem dílu; nominální svar se musí do dílu vejít.
Tyto významy 07B zachová. Nominální oblast není automaticky rozpoznaná hranice natavení.

Výchozí `ndt/coverage.py` z 07A počítal plochy a body. `CoverageMap.areas` znamená mm²;
`ModelSession._coverage_inputs` a CLI objemový cíl výslovně odmítají.
`visible_ndt_coverage` předpokládalo plošnou síť. Nestačí tedy jen odstranit zákaz
nebo poslat objem do dosavadního seznamu ploch.

V rozsahu 07B je jedna studie, jeden cíl, jedna pojezdová plocha nebo přímá dráha,
jedna sonda a její zadaná orientace; odrazy a lom podle dosavadních výslovných
předpokladů. Více oddělených kusů jednoho účinného cíle musí být zahrnuto celé.
Slučování různých studií nebo pojezdových ploch, hledání optimální dráhy,
zakřivené svary a automatické rozpoznávání svaru se nepřidávají.

**Výrobní geometrie, hmotnost a STEP se nemění. Formát zůstává 16, nové knihovny
nejsou potřeba a výsledky se do souboru modelu neukládají.**
Ruční zkouška vydání Etapy 06 po sloučení zůstává samostatným neuzavřeným úkolem.

## 2. Rozdělení objemu a zachování jeho velikosti

1. Na aktuálně přepočteném dílu se znovu ověří platná UT studie a zavolá
   `resolve_target`. Jmenovatelem je jeho **účinný objem v materiálu**, nikoli
   objem celého dílu nebo samotného ohraničujícího kvádru. Prázdný cíl je chyba.
2. Cíl se rozdělí pravidelnou 3D mřížkou ve vlastním souřadném systému.
   Osy jsou `across`, `across × axis` a `axis`. Začátek mřížky je minimum
   průřezu a podélná souřadnice 0; krok cíle určuje hranu buňky v mm.
   Poslední buňky se zkrátí přesně na konec rozsahu. Otočení celého modelu
   tedy samo nezmění rozdělení cíle.
3. Každá buňka se geometricky protne s účinným cílem. Každý oddělený objemový
   kus průniku tvoří samostatný vzorek s vahou rovnou skutečnému objemu v mm³.
   Vzduch, otvor a část buňky mimo cíl nenesou váhu. Čistý dotyk bez objemu
   nevytváří objemový vzorek. Platná buňka prokazatelně celá uvnitř cíle může
   použít objem kvádru bez zbytečného geometrického průniku.
4. Bod vzorku musí ležet spolehlivě uvnitř příslušného kusu **i materiálu dílu**.
   Nejprve se zkusí těžiště, potom deterministické dělení místního kvádru
   (nejvýše 4 úrovně, celkem nejvýše 4 680 dalších kandidátů na kus).
   Prosté těžiště konkávního tělesa nebo střed původní buňky nejsou důkazem.
   Když vhodný bod nelze najít, známý objem kusu zůstane jako **nejistý**.
5. Žádný kladný objem se nesmí zahodit jen proto, že je malý. Chyba geometrického
   průniku, neplatné těleso nebo neznámá váha znamenají ukončení výpočtu s českým
   vysvětlením; takovou chybu nelze zamaskovat nulovou vahou ani hotovým procentem.
6. Před vyhodnocením zásahů se ověří součet vah proti objemu `resolve_target`.
   Navržená dovolená numerická odchylka je
   `max(0,000001 mm³; 0,000001 × účinný objem)`.
   Větší rozdíl výpočet odmítne. Váhy se nepřepočítají poměrem tak, aby se
   ztracený objem skryl. Přípustná odchylka se zapíše do předpokladů výsledku.

Postup výběru vnitřního bodu je omezený záměrně: velmi tenké nebo složité části
mohou zůstat nejisté. Nesmějí zvýšit pokryté procento tím, že ze součtu zmizí.
Limit kandidátů se počítá také do celkového pracovního limitu podle oddílu 7.

## 3. Co znamená zásah objemového vzorku

Zásahy převezmou společnou logiku Etapy 06: skutečné přiložení sondy,
otisk, přesah, kolize, manipulační rezervu, dosah, odrazy a jistotu ramene.
Pouhá numerická blízkost osy paprsku není důkaz geometrického pokrytí.
Na rovinném pojezdu se mezilehlé přiložení znovu ověří a paprsek znovu trasuje,
včetně opravených odrazů od boční stěny. Na zakřivené ploše samotná numerická
blízkost zůstává nejistá. Tolerance nesmí prodloužit rameno za skutečný konec.

Pro každý vzorek platí právě jeden stav:

| Stav | Podmínka |
|---|---|
| Geometricky pokryto | Ověřený vnitřní bod zasahuje alespoň jeden jistý geometrický paprsek z platného přiložení. |
| Geometricky nepokryto | Vnitřní bod je spolehlivě určený a nezasahuje jej žádný platný ani nejistý paprsek v daném výpočtu. |
| Nelze spolehlivě vyhodnotit | Je známý objem, ale chybí spolehlivý vnitřní bod, nebo bod zasahuje jen nejisté přiložení/rameno či numerická blízkost na zakřivené ploše. |

Jistý zásah má přednost před nejistým z jiné polohy. Nejistotu samotného vzorku
však žádný paprsek nepřepíše na pokryto. Tentýž kus se nezapočítá vícekrát.

**Stav jednoho bodu zastupuje stav jeho objemového kusu. Je to aproximace,
nikoli důkaz zásahu každého místa buňky.** Hraniční buňka může obsahovat pokrytou
i nepokrytou část. Proto se uvádí krok a porovnání s hrubší mřížkou.
Nejistota geometrie a odhad chyby vzorkování nejsou totéž: třetí stav označuje
první z nich, citlivost na krok sleduje druhou. Suma tří stavů nedokazuje přesnost.

Výchozí rozevření zůstává 0°. Numerická tolerance je vyhledávací pomůcka,
nevytváří fyzickou šířku paprsku. Pro objem se výchozí tolerance odvodí jen
z kroku pojezdu: `krok × sqrt(0,5)` pro plochu, `krok × 0,6` pro přímku.
To odpovídá pojezdové složce tolerance Etapy 06; krok cíle ji nebude zvětšovat.
Výslovně zadaná tolerance se zachová a vždy uvede ve výstupu.
Zadané nenulové rozevření používá dosavadní zjednodušený geometrický model svazku;
07B nepřidává model intenzity, útlumu ani detekce vad.

Při pojezdu **po ploše** může rodina osových paprsků pokrýt trojrozměrnou oblast.
Při pojezdu **jen po přímce**, pevném směru a nulovém rozevření tvoří ideální osy
v tomto modelu oblast s nulovým objemem. Konečná mřížka by přesto mohla vykázat
nenulový odhad, pokud její body náhodou leží na této oblasti. **Objemový výpočet
proto kombinaci `line` a nulového rozevření odmítne ještě před vzorkováním**:
„Pojezd po čáře bez rozevření svazku nevymezuje pokrytý objem. Pro objem zvol
pojezd po ploše; pro čáru lze samostatně vyhodnotit body nebo plochy.“
Nenulové rozevření lze zadat pouze jako vědomý předpoklad, nesmí se doplnit
automaticky kvůli získání procenta. Tento případ musí mít vlastní regresní test.
Jde o upřesnění první objemové verze; dosavadní čárový výpočet ploch/bodů se nemění.

## 4. Výsledek, jednotky a CSV

Navrhuje se samostatný `VolumeCoverageMap` v `ndt/volume_coverage.py`.
Dosavadní `CoverageMap` zachová význam a plošnou síť. Společné vyhodnocení zásahů
se vyčlení v `ndt/coverage.py`; oba výsledky použijí stejné `CoverageHit`, názvy
stavů a ochrany přiložení. Objemy se nesmějí ukládat do `CoverageMap.areas`.

Každý objemový vzorek ponese identifikaci buňky/kusu, místní meze buňky,
ověřený světový bod (nebo výslovně žádný bod), objem, stav, důvod a první zásah.
Číslování buněk slouží jen výpočtu, není odkazem na plochu nebo hranu dílu.
Výsledek ponese souřadný systém mřížky, požadovaný i účinný objem, součet vah,
odchylku, počty poloh sondy, dobu a předpoklady. Mezi procesy se předají jen
čísla, texty a datové struktury; žádné OCCT těleso. Meze buňky samy nebudou
vydávány za přesný tvar jejího oříznutého kusu. Vykreslení se vyřeší v 07C.

Veřejné metody výsledku: `total_volume`, `volume(state)`, `percent(state)`,
`summary()`, `write_csv(path)`. `total_volume` je účinný objem z geometrie;
součet vzorků a jeho odchylka jsou dohledatelné samostatně.

`procento stavu = 100 × objem vzorků daného stavu / účinný objem cíle`.
Součet tří objemů odpovídá součtu vah a v numerické toleranci účinnému cíli.
Drobný numerický rozdíl se uvede, nevyrobí se skrytou úpravou vah.
Zaokrouhlená procenta nemusejí dát přesně 100,00 %.
Souhrn oddělí mm³ od počtů vzorků; počet zásahů není procentem objemu.

Povinná metadata zahrnou identifikátor a otisk studie/cíle/dílu, parametry dílu,
algoritmus objemového vzorkování a zásahů, oba kroky, toleranci, rozevření,
pojezd, sondu, orientaci, dosah, odrazy a případné rychlosti pro lom.
Změna algoritmu dostane dohledatelnou novou identifikaci; staré výstupy se
nesmějí tvářit jako výsledky nového výpočtu.

CSV zachová UTF-8 s BOM, středník a desetinnou čárku. Hlavička výslovně uvede
**objem [mm³]**; řádek obsahuje buňku/kus, bod X/Y/Z, objem, stav, důvod,
rameno, celkovou dráhu a polohu sondy. U neurčeného bodu jsou souřadnice prázdné,
nikoli vymyšlené nuly. Přesnost čísel musí zachovat i malé kladné váhy a umožnit
ověřit součet; nepřebírat bez rozmyslu zaokrouhlení ploch na šest desetinných míst.
Hlavička obsahuje jmenovatel, součet vah, odchylku a úplné předpoklady.
Je-li vyžádané porovnání kroků, přidá se jeho nastavení i výsledky do metadat CSV.

Název je vždy **Mapa geometrického pokrytí UT**, dále plné `UT_DISCLAIMER`
ze `skodacad.ndt` a `PERCENT_NOTE` z `ndt.coverage`, bez zkracování v souhrnu a CSV:

> ŠkodaCAD provádí pouze geometrické posouzení přístupnosti ultrazvukové sondy a pokrytí kontrolované oblasti na základě zjednodušeného modelu ultrazvukového svazku. Nevyhodnocuje fyzikální prozvučitelnost materiálu ani detekovatelnost vad. Výsledky nenahrazují kvalifikovaný NDT postup ani odborné posouzení.

> Procento vyjadřuje pouze geometrický podíl zasažené oblasti, nikoli pravděpodobnost nalezení vady.

## 5. Zapojení do aplikace a příkazové řádky

- `compute_volume(geo, placement, target=..., ...)` vyhodnotí ověřený objemový cíl;
  nesmí přijmout současně konkurenční plochy nebo body. Volby paprsku a pojezdu
  zachovají význam stávajícího `coverage.compute`.
- `ModelSession.compute_ndt_coverage` vybere výpočet podle druhu cíle.
  Dosavadní volání pro plochy zůstanou kompatibilní; přibudou volitelné klíčové
  parametry `target_step_mm` a `tolerance_mm`. Bez kroku cíle se použije krok pojezdu.
- `start_ndt_coverage` použije stávající pomocný proces a možnost zastavení.
  Mezipaměť přijme oba typy výsledku. Změna dílu, cíle, sondy nebo přiložení
  zneplatní výsledek; odpověď starého či zrušeného výpočtu se nesmí zobrazit.
- `visible_ndt_coverage` vrátí pro objem prázdnou kresbu, dokud nebude provedeno
  07C. Nevytvoří falešnou povrchovou mapu a nebude volat neexistující `mesh()`.
  Ovládací prvky objemového výpočtu zůstanou v panelu nedostupné.
  `export_ndt_coverage` bude umět CSV obou typů výsledku.
- `skodacad pokryti ... --studie s1` převezme z platné studie také `volume`/`weld`.
  `--plocha` dál označuje výchozí přiložení, ne cílovou oblast.
  `--krok` je krok pojezdu, `--krok-cile` hrana objemové buňky.
  Výslovné `--cil`/`--cil-plocha` dál přepíšou cíl podle dnešního chování;
  výstup uvede skutečný druh vyhodnoceného cíle, aby bod nebyl zaměněn za objem studie.
  Neplatná nebo zastaralá objemová studie se nesmí potichu použít.

Příkaz pro implementaci 07B, spouštěný z kořene repozitáře:

```powershell
skodacad pokryti examples/ndt/cilove_objemy/tupy_svar_objem.json --studie s1 --plocha 50,0,12 --smer 180 --sklon 70 --odrazy 0 --rezim face --krok 5 --krok-cile 2 --konvergence --csv out/tupy-svar-07b.csv
```

Adresář `out` musí před exportem existovat. Příkaz je v této vývojové větvi provedený:
účinný objem i součet vah **14 613,843876 mm³**, jemný běh 5/2 mm dal **12,22 %**,
hrubý 10/4 mm **5,59 %**, rozdíl **6,63 p. b.**. Tolerance zůstala 3,535534 mm,
rozevření 0°, odrazy 0, sklon 70°, pojezd po pravé horní ploše.
Jemný běh trval při místní zkoušce přibližně 42 s (4 000 kandidátních buněk,
2 700 objemových kusů, 609 poloh, z toho 340 platných).
**Výsledek není stabilní odhad; souhrn i CSV doporučují zjemnit krok.**
Čísla platí pouze pro tuto jednu konfiguraci, ne pro všechny možné polohy a sondy.

## 6. Citlivost na krok a význam čísel

Pro objem bude samostatné `check_volume_convergence`, se stejným pravidlem jako
Etapa 06: porovnat `(krok pojezdu, krok cíle)` s `(2× krok pojezdu, 2× krok cíle)`.
Počátek a orientace mřížky se zachovají. Tolerance i rozevření budou v obou bězích
stejné; tolerance se převezme z jemnějšího běhu a podruhé se neodvodí z hrubého kroku.
Oba běhy zahrnou tentýž celý účinný objem a všechny tři stavy.

Souhrn uvede procenta všech tří stavů v obou bězích, největší rozdíl v procentních
bodech a oba kroky. Rozdíl nejvýše **1 procentní bod** znamená pouze nízkou
pozorovanou citlivost této dvojice mřížek; není to garantovaná chyba do 1 %.
Větší rozdíl doporučí zjemnit krok. Bez porovnání se výsledek označí jako
**citlivost na krok neověřena**. Nelze-li dokončit hrubší běh, nesmí se uvést stabilita.

Jemnější krok, stejná tolerance, stejný cíl a stejné fyzikální předpoklady jsou
podmínkou smysluplného porovnání. Hrubé buňky mohou přehlédnout úzké slepé místo;
ani úspěšná kontrola součtu objemu to sama neodhalí.

## 7. Omezení práce a reakce na chybu

Před průniky se z místního rozsahu vypočítá počet kandidátních buněk a počet
poloh sondy. Výchozí ochrany pro 07B: nejvýše **20 000 kandidátních buněk**,
**20 000 objemových kusů**, dosavadních **20 000 poloh sondy** a
**80 000 000 porovnání vzorek–rameno**. Odhad porovnání použije počet vzorků,
poloh a nejvýše zadaný počet ramen; po rozdělení buněk se ověří znovu.
Nesmí se začít drahé ořezávání, když už hrubý odhad zjevně překračuje limit.

Hledání vnitřních bodů má navíc celkový limit **1 000 000 klasifikací bodů**.
Jeho vyčerpání označí zbývající známé kusy jako nejisté se srozumitelným důvodem;
nesmí změnit jejich váhy. Překročení limitu buněk, kusů nebo porovnání výpočet
odmítne a doporučí zvětšit příslušný krok. Automatické zhrubnutí bez vědomí autora
se nepřidává. Chyba nesmí ponechat starý výsledek jako nový.

Limity jsou ochrany první verze, nikoli slib doby výpočtu. Při implementaci se
změří počet buněk, průniků a skutečný čas na referenčních dílech; při neúnosném
čase se nejprve zlevní bezpečné případy a zvolí hrubší ukázkové nastavení.
Nezvyšovat limity jen proto, aby prošel příklad. Výpočet i přípravu vzorků půjde
zastavit ukončením pomocného procesu. CLI lze přerušit obvyklým způsobem.

## 8. Ověření před předáním

Následující tabulka uvádí **požadované budoucí testy**, nikoli výsledky hotové 07B.
U geometrických příkladů musí být konstrukce platná a očekávání nezávisle odvozené
ze vzorce; u pokrytí nestačí pouze ověřit, že součet procent vyšel na 100.

| Scénář | Podmínka převzetí |
|---|---|
| Hranol 10 × 20 × 30 mm uvnitř materiálu | Jmenovatel 6 000 mm³, zachovaný součet i při kroku, který nedělí rozměry. |
| Otočení a posun stejného dílu, cíle i sondy | Shodné váhy a stavy v numerické toleranci; mřížka není ukotvená ve světě. |
| Částečně vyčnívající hranol, otvor a více kusů v buňce | Jen skutečný materiál; všechny oddělené kusy mají váhu. Prázdný průnik je chyba. |
| Konkávní a tenký kus, nenalezený vnitřní bod | Žádný bod ve vzduchu nesmí získat pokryto; známá váha zůstává nejistá. |
| Chyba průniku nebo součet mimo toleranci | Česká chyba bez hotového procenta; žádná normalizace zakrývající ztracený objem. |
| Koutový svar 7 × 7 mm, délka 100 mm | 2 450 mm³ pro každou ze dvou samostatných studií. |
| V svar z `tupy_svar_objem.json` | 14 613,843876 mm³ včetně převýšení a podkořene; celý výrobní díl není jmenovatel. |
| Přímá sonda nad rovným kvádrem; cíl bezpečně uvnitř dovoleného pojezdu a dosahu | 100 % jistých objemových vzorků; mimo dosah 0 % jistých zásahů. |
| Deska 200 × 100 × 20 mm, přímá sonda Ø10, celý rovný pojezd | Analytická mez souvislého pojezdu osy je `190 × 90 × 20 = 342 000 mm³` z `400 000 mm³`, tedy 85,5 %. Odhad se k ní musí blížit při zjemnění; hrubé mřížce nepředepsat falešnou přesnou shodu. |
| Stejná deska, jen omezený dosah a část povoleného pojezdu | Nezávisle odvodit pokrytý hranol; ověřit objemovou váhu i nepokrytý zbytek, včetně různě velkých hraničních buněk. |
| Přímá dráha bez rozevření | Objemový výpočet ji odmítne s vysvětlením ještě před vzorkováním; záměrně zarovnaná mřížka nesmí vytvořit falešné kladné procento. Plochy/body zůstávají podporované. |
| Kolize, rezerva, odraz od boční stěny a více odrazů | Zachovat regrese Etapy 06, žádné pokrytí díky pouhé toleranci nebo za koncem ramene. |
| Nejistý zásah a pozdější jistý zásah | Jedna váha, jistý zásah vyhraje; nejistý vzorek bez vnitřního bodu zůstane nejistý. |
| Porovnání kroků | Stejná tolerance a jmenovatel, maximum rozdílu ze všech tří stavů, nikoli jen zeleného. |
| Souhrn a CSV, včetně velmi malých vah | mm³, správný jmenovatel, stav/důvod, předpoklady, plná upozornění, ověřitelný součet po exportu. |
| Session, pomocný proces, změna a zastavení | Stejná data synchronně i na pozadí; zrušený či zastaralý výsledek se nevrátí, výrobní geometrie se nemění. |
| Dosavadní body, plochy a panel | Zachované referenční výsledky, mm²/body, plošná kresba i ochrana objemového ovládání do 07C. |

Před commitem implementace musí projít `ruff check src tests` a celá sada
`pytest -q`. Před předáním projdou sestavení a automatické zkoušky skutečných
balíčků Windows i macOS; doplní se malý objemový výpočet také do balíčkového
self-testu, aby se prověřilo přibalení nového modulu a ukázkových dat.
Vývojové výpočty nedokazují ruční funkčnost na autorově MacBooku.

Autor dostane konkrétní souhrn a CSV V svaru, tabulku obou kroků, dobu výpočtu
a jednoznačný seznam provedených kontrol. Samotná bodová reference 45°/60°/70°
u kořene neurčuje procento celého svaru; toto procento se nyní neslibuje.

## 9. Pořadí práce a rozhodnutí autora

| Krok po schválení 07B | Hotový výstup |
|---|---|
| 07B.1 – vzorkování a váhy | Mřížka, průniky, ověřené vnitřní body, zachování objemu, limity a analytické testy. |
| 07B.2 – společné zásahy | `VolumeCoverageMap`, sdílení logiky Etapy 06, tři stavy, oddělené jednotky a regrese. |
| 07B.3 – propojení a předání | Session/proces, CLI, CSV, citlivost, balíčkové zkoušky a předvedený výsledek. |

**Autor schválil pouze implementaci 07B v uvedeném rozsahu:** vážené objemové
vzorkování nad skutečným cílem, sdílené ověřování zásahů, mm³/procenta, souhrn,
CSV a porovnání kroků, bez změny formátu a bez nových knihoven.
07C, slučování studií a sloučení implementace do `main` vyžadují další pokyn.
Souhlas autora ze 17. 10. 2026 navazuje na předložení tohoto návrhu.

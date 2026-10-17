# NDT – návrh etapy 07: svar a cílový objem

Stav: **07A schváleno autorem 17. 10. 2026 a sloučeno do `main` v PR #16 (`0dea6f8`);
07B schváleno 17. 10. 2026 a sloučeno do `main` v PR #17 (`35f1507`);
07C schváleno 17. 10. 2026 a implementováno ve vývojové větvi**.

Podrobné návrhy kroků: [07B – geometrické pokrytí cílového objemu](13-navrh-etapa-07b.md),
[07C – cílový objem a jeho pokrytí v okně](14-navrh-etapa-07c.md).

Provedení 07A: `ndt/welds.py`, cíle `volume`/`weld` v JSON 16, normalizace směrů,
ověření skutečných objemů, stavy a historie studií, metody `ModelSession`, ukázkové
soubory v `examples/ndt/cilove_objemy/`. Objemové ověření se váže také na otisk cíle
`verified.target`. Stávající panel umí ukázat číselný objem; nový editor ani zobrazení
pomocného tělesa se zatím nepřidává. 07B vyhodnocuje objem samostatně v mm³,
nikdy přes plošné váhy; ovládání objemového výpočtu v okně zůstává až pro 07C.

Navazuje na [plán](03-implementacni-plan.md), [Etapu 06](11-navrh-etapa-06.md)
a [závazné vymezení UT](04-zavazne-vymezeni-ut.md). Etapa 06 je sloučená v
[PR #15](https://github.com/JendaNDT/SkodaCAD/pull/15), commit `9007054`;
na Windows i macOS prošlo 723 testů, sestavení a zkouška staženého balíčku.
Autor odložil ruční zkoušku vydání po sloučení na později. Tato zkouška se nepovažuje
za provedenou; příprava tohoto návrhu ji nenahrazuje.

## Co bude vidět pro uživatele

Ve studii půjde místo povrchových ploch zvolit **svar** nebo **kontrolovaný objem**.
Uživatel zadá polohu, směr, délku a rozměry; ve 3D uvidí pomocnou oblast uvnitř dílu.
Mapa geometrického pokrytí UT pak ukáže podíl této oblasti v **mm³ a procentech objemu**.
Stávající plochy zůstanou v mm² a jednotlivé body v počtech bodů.

Příklad: v tupém svaru lze odděleně posoudit celý zadaný objem svaru a úzkou oblast
kořene. Hodnocení samotného povrchu převýšení už nebude vydáváno za pokrytí svaru.
Stávající studie ploch se ale samy na objemové studie nepřevedou.

## 1. Doporučený rozsah první verze

- **Rovný tupý svar V** v plechu: tloušťka, rozevření úkosu, kořenová mezera,
  převýšení a podkořen, délka. První průřez je bez otupení kořene; jiné přípravy hran
  půjdou zadat pomocným polygonem. Jde o uživatelem zadanou nominální geometrii svaru.
- **Rovný koutový svar** s trojúhelníkovým průřezem: dvě ramena, délka a strana.
  Oboustranný svar budou dva samostatně definované cíle/studie.
- **Pomocný kontrolovaný objem**: hranol z jednoduchého rovinného polygonu
  a délky. Umožní zadat kořen nebo přilehlou oblast, i když CAD neobsahuje hranici svaru.
- Jedna studie má jeden cíl. Pro svar a další oblast lze založit nebo duplikovat studii.
  Jejich procenta se nesčítají; překrývající se objemy nesmějí zvětšit společný výsledek.
- Přilehlé oblasti se zadají ručně jako samostatné objemy. Program z rozměrů svaru
  neodhadne skutečnou tepelně ovlivněnou oblast ani rozsah podle normy.

Obvodový svar trubky a zakřivená trasa jsou navazující rozšíření. Starší návrh v0.2
je uváděl jako referenční scénář; tento návrh je **výslovně odkládá**. Bez tohoto
rozhodnutí by byl rozsah první verze podstatně větší.

## 2. Uložení a vazba na díl – navržená verze JSON 16

Rozšíří se existující `study.target`; nové objekty nebudou konstrukční prvky
v `features`. Nebudou měnit objem, hmotnost ani exportovaný STEP výrobního dílu.

- Dosavadní `kind: "faces"` zůstane zachovaný.
- `kind: "volume"`: místní souřadný systém, délka a jednoduchý uzavřený polygon.
- `kind: "weld"`: tentýž souřadný systém, délka, typ svaru a jeho rozměry;
  průřezy vygeneruje `ndt/welds.py`. Nebude se současně ukládat jiný konkurenční polygon.
- Každý cíl patří své studii. Sdílená knihovna svarů a odkazy mezi více studiemi
  nejsou pro první verzi nutné.
- Rozměry budou konečná čísla v mm a °. Výrazy odkazující na parametry modelu lze
  doplnit později; první verze nebude slibovat automatické přizpůsobení rozměrů svaru.

Příklad pomocné oblasti kořene, pouze navržený formát:

```json
{
  "kind": "volume",
  "frame": {
    "origin": [0, -50, 0],
    "axis": [0, 1, 0],
    "across": [1, 0, 0]
  },
  "length_mm": 100,
  "profile_mm": [[-1, 0], [1, 0], [1, 2], [-1, 2]]
}
```

Průřez používá souřadnice `(napříč, výška)`. `axis` je podélná osa; výška má směr
`across × axis`. Ve výše uvedeném příkladu tedy výška míří do +Z. Vektory musí
být nenulové a kolmé, při načtení se normalizují. Koncové body, profil a délka
nesmějí připustit záporný nebo nulový objem ani samoprotínající se polygon.

Pomocný objem znamená **materiál dílu uvnitř zadaného hranolu**: jeho účinným cílem je
průnik s dílem. Panel uvede objem zadaného hranolu i skutečný objem v materiálu;
vzduch se nezapočte do pokrytí. Prázdný průnik je neplatné zadání, nikoli 0 % pokrytí.
Nominální svar se naopak musí do dílu vejít; chybějící materiál vyvolá vysvětlenou
neplatnou vazbu, nesmí se potichu oříznout a tím změnit zadaný svar.

První verze používá souřadnice v modelu a existující otisk receptu dílu. Po změně
geometrie je cíl zastaralý, i když má stejný objem. Uživatel musí zkontrolovat náhled
a znovu jej potvrdit. Program nesmí přesunout cíl na „nejbližší svar“.
Chybějící materiál, prázdný průnik či chyba konstrukce cíle znamenají neplatnou vazbu.

Načtení verzí 1–15 zůstane zachované. Uložení novou aplikací zapisuje verzi 16,
kterou starší aplikace odmítne s dosavadním vysvětlením o novější verzi.
Původní soubory se bez výslovného uložení nepřepisují. Výsledky pokrytí se neukládají.
Úprava cíle, typu nebo rozměrů svaru zruší mapu i odborné ověření studie; musí fungovat
Zpět/Znovu, duplikace, uložení a opětovné načtení.

## 3. Výpočet objemu a jeho geometrického pokrytí

1. `ndt/welds.py` vytvoří pomocné těleso cíle a ověří vazbu vůči skutečnému dílu.
2. Cíl se rozdělí pravidelnou 3D mřížkou v jeho místním souřadném systému.
   Hraniční buňky se oříznou skutečným cílovým tělesem; jejich váhou je **objem v mm³**.
3. Každý oddělený kus buňky dostane kontrolovaný bod uvnitř materiálu. Není-li možné
   určit spolehlivý bod, objem zůstane ve výsledku jako **nejistý**, nesmí zmizet ze jmenovatele.
   Těžiště konkávního kusu nelze bez kontroly považovat za bod uvnitř.
4. Zásah bodu využije ověřený geometrický výpočet Etapy 06, včetně kolizí sondy,
   odrazů a ověření mezilehlých přiložení. Samotný zásah jednoho bodu je aproximací
   pokrytí jeho buňky, nikoli důkazem zásahu každého místa této buňky.
5. Procento stavu je `100 × součet objemů buněk daného stavu / účinný cílový objem`.
   Součet tří stavů musí pokrýt celý jmenovatel. Budou výslovně oddělené mm², mm³ a body;
   dnešní pole `CoverageMap.areas` se nesmí naplnit objemy bez změny významu výstupu.
6. Citlivost se porovná při kroku a dvojnásobném kroku, se stejným geometrickým
   rozevřením a numerickou tolerancí. Krok pojezdu a krok cíle budou dohledatelné zvlášť.
   Při hrubém rozlišení se nesmí prezentovat stabilita nebo přesnost bez porovnání.

Na začátku se omezí počet buněk i porovnání, ještě před drahým ořezáváním.
Příliš jemné zadání dostane české vysvětlení a návrh zvětšit krok. Výpočet poběží
v dosavadním pomocném procesu, půjde zastavit a do GUI se přenesou jen data pro kreslení.

V okně se zobrazí pomocný obrys cíle a barevné buňky v řezu modelem. Řez nemění
jmenovatel ani celkové procento: slouží k prohlížení výsledku uvnitř dílu. Samotný
obarvený vnější povrch nesmí být jediným zobrazením objemového výsledku.
CSV obsahuje objem buňky, jednotku mm³, stav, zásah, souřadnice a předpoklady.

Název zůstává **Mapa geometrického pokrytí UT**; plné `UT_DISCLAIMER` a význam procent
budou v panelu, příkazové řádce i exportu. Žádné automatické rozpoznávání svarů,
signály, tvrzení o detekovatelnosti nebo zásahy do konstrukční geometrie.

## 4. Referenční výsledky a podmínky převzetí

| Scénář | Nezávislá očekávaná hodnota nebo chování |
|---|---|
| Hranol 10 × 20 × 30 mm uvnitř materiálu | 6 000 mm³, shodná suma vah buněk; otočení v prostoru objem nezmění |
| Pomocná oblast částečně vně dílu | jmenovatel tvoří jen průnik s materiálem; prázdný průnik je chyba |
| Koutový svar s rameny 7 mm, délka 100 mm | 2 450 mm³ na každé straně; dvě samostatné studie, ne smíchaná procenta |
| Tupý V, tloušťka 12 mm, mezera 2 mm, úkos 60°, délka 100 mm | tělo svaru `(2·12 + 12²·tan 30°)·100 = 10 713,843876 mm³` |
| Tentýž V v `tupy_svar.json`, včetně zadaného převýšení a podkořene | navíc `(20+14)/2·2·100 + (6+4)/2·1·100 = 3 900 mm³`, celkem **14 613,843876 mm³** |
| Kořen V svaru a dosavadní úhlová sonda | zachovat referenční bodové výsledky 45° a 60° nepokryto, 70° pokryto; neurčuje to automaticky procento celého svaru |
| Odraz a překážka u sondy | zachovat opravy Etapy 06; tolerance nesmí zakrýt kolizi, rezervu či nedostatečný dosah |
| Změna polohy/rozměrů dílu nebo cíle | mapa zanikne, ověření neplatí; neplatná vazba se nesmí změnit na „pokryto“ |
| Uložení/načtení a Zpět/Znovu | geometricky shodný cíl, studie i stavy; původní plochové studie fungují dál |

V svar je **nominální zadaná oblast**, ne rozpoznaná hranice natavení. Dnešní CAD
model hranici úkosu neobsahuje; přesný cílový objem proto nelze z výrobního tělesa
automaticky vyčíst. Hranice kořene, přilehlých oblastí a skutečná geometrie svaru
musí pocházet ze zadání autora, případně z odborného ověření.

## 5. Malé implementační kroky po schválení

| Krok | Výstup | Ověření |
|---|---|---|
| **07A – datový základ a pomocné objemy** | `ndt/welds.py`, rozšíření `ndt/study.py`, JSON 16 a metody `ModelSession`; bez nového ovládání | analytické objemy, vazby, migrace, uložení a Zpět/Znovu |
| **07B – objemové pokrytí bez GUI** | vzorkování, objemové váhy, společný výpočet zásahů, souhrn, CSV a CLI | součet objemů, tři stavy, citlivost na krok, zachování plošných a bodových výsledků |
| **07C – ovládání a demonstrace** | editor cíle ve studii, náhled, objemová mapa v řezu a výpočet na pozadí | offscreen testy, skutečné 3D okno, zastavení výpočtu, Windows/macOS balíčky |

Nové knihovny se nepředpokládají. Geometrii obstará stávající build123d/OCCT,
GUI jen volá `ModelSession`. Každý krok má vlastní ověření a kontrolu změn;
do `main` se nová etapa nebude slučovat bez dalšího pokynu autora.

Praktická demonstrace: otevřít kopii `tupy_svar.json`, založit objemovou UT studii,
zvolit rovný V svar podle tabulky, prohlédnout jeho průřez a objem, přiložit sondu,
spočítat pokrytí a posunout řez. Poté změnit rozměr dílu: starý výsledek musí zmizet
a zadání si vyžádat kontrolu. Původní výrobní díl zůstane geometricky stejný.

## 6. Konkrétní rozhodnutí autora

**Schváleno autorem 17. 10. 2026 pro krok 07A:** rovné V a koutové svary + pomocný polygonální hranol,
rozšíření formátu na verzi 16 se zachováním načítání starých modelů, bez nových knihoven.
Provést pouze krok **07A**; výpočet objemového pokrytí a nové ovládání následují odděleně.

Tím se neschvaluje automatické rozpoznávání svarů, obvodové/zakřivené svary,
odhad skutečné tepelně ovlivněné oblasti, změna geometrie výrobního dílu ani sloučení
nové etapy do hlavní větve.

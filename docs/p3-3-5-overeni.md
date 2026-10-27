# P3.3–P3.5 — evidence vývoje a ověřování

**Stav: rozpracováno, bez přijetí a bez sloučení.** Rozsah je záměrně omezen na
jeden platný uzavřený díl se známou jednotkou milimetr nebo palec, velikost
zdroje nejvýš 16 MiB. Sestavy, více těles, volné plochy, neznámé jednotky,
poškozené vstupy a hlášené opravy se odmítají. Neexistuje záruka, že OCCT
nahlásí každou změnu interní reprezentace; referenční vstupy a analytické
kontroly nejsou testem všech STEP souborů.

Zdroj je vložen v JSON modelu verze 24; starší verze 1–23 se načítají, stará
aplikace verzi 24 nepřečte. Při změně zdroje je chráněna identita SHA-256;
obnova nabízí jen totožné bajty. Uložení zapisuje nejprve do pomocného souboru
ve stejné složce a poté nahrazuje cíl. Při selhání nahrazení se v testu původní
obsah nezměnil. Přenositelnost neznamená důkaz identity jednotlivých ploch;
bezpečnost odkazů z P1 a omezení P2 zůstávají v platnosti.

Diagnostika probíhá v samostatném procesu, zrušení jej ukončí; opětovné otevření
zdroje při přepočtu probíhá ve stávajícím pomocném procesu a jeho rodič sleduje
během převodu čas a paměť. Měření paměti je **průběžné**, není pevnou hranicí
OS a může být překročeno mezi odečty. Limit i chování na obtížných vstupních
modelech vyžadují další ověření. Nepřítomnost varování sama nedokazuje, že
k žádné změně jádra při převodu nedošlo.

## Automatické průběžné zkoušky

Testy `test_p33_step_probe`, `test_p33_step_task`, `test_p33_step_source`,
`test_p33_step_repair_probe`, `test_p34_step_model`, `test_p34_step_gui` a
`test_p35_step_preliminary` pokrývají jednotky, počet těles, syntaktickou chybu,
ohlášenou opravu, integritu dat, zrušení, limity, obnovu shodného zdroje,
vložení, náhled, vrácení, přímou úpravu, uložení a opětovné načtení. Zkouška
exportu a opětovného importu používá zatím syntetické zdroje z P3.1. Při
chybě jádra nelze výsledek považovat za hotový díl. Výsledky konečné plné
sady a CI jsou zaznamenány samostatně až po jejich doběhnutí.

## Místní zkouška skutečné aplikace 28. 10. 2026

Zkušební lokální sestavení `.app` bylo otevřeno na Macu a ovládáno agentem,
nikoli autorem. Palcový soubor `04-palce.step` v novém modelu:

- dialog ukázal 50,8 × 25,4 × 12,7 mm, objem 16 387,1 mm³ a jedno těleso;
- po potvrzení se díl vykreslil ve skutečném 3D a vlastnosti zobrazily stejné
  rozměry; Zpět a Znovu odebraly a znovu přidaly těleso;
- uložení a opětovné otevření testovacího JSON fungovalo, vložený zdroj měl
  shodné bajty i SHA-256 s původním vzorkem;
- výběr horní plochy ukázal tloušťku 12,70 mm;
- vzorek s obrácenou plochou zobrazil hlášení o upozornění/opravě a byl odmítnut,
  prázdný model zůstal beze změny.

Jde o agentovu zkoušku na Macu, ne o autorovo ruční přijetí. Zatím zde není
prokázáno běžné použití ve Windows, přenos mezi dvěma operačními systémy ani
přijetí uživatelových skutečných souborů z jiných CADů.

Plná místní sada: **1 684 testů prošlo**, Ruff prošel. Následně byla samostatně
ověřena také nová položka horní lišty a skript přenosu: vytvoření a otevření obou
modelů a zpětné čtení exportu na Macu prošly. Zkouška na druhém OS zatím čeká
na běh CI. Mac `.app` prošla kontrolou podpisu a stávajícím self-testem.

Orientační zátěž: syntetický jednoduchý kvádr doplněný mezerami přesně na
16 MiB zpracován na tomto Macu za 1,39 s; nejvyšší při vzorkování naměřená
rezidentní paměť pomocného procesu 435,1 MiB. Nejde o geometricky složitý
model ani o horní mez spotřeby, vzorkování nemusí zachytit vrchol. Skript je
`tests/benchmark_p35_step.py`; běh pro Windows je připraven v CI.

CI skript `tests/p35_cross_os.py` vytváří modely na jednom systému a ověřuje je
na druhém; po načtení porovnává otisky, rozměry, objemy a počet těles a provede
export a opětovné čtení. Přenos běží v obou směrech v samostatném workflow.
**Dokud workflow neprojde, přenos mezi OS není potvrzen.**

Po plné sadě byl samostatně doplněn a ověřen test, že běžná úprava prvku využívaná také AI nemůže potichu nahradit SHA-256 či
data zdroje; test nevolá vzdálené AI API. Další změny
před odevzdáním tvoří skripty pro přenos mezi OS, dokumentace a tato cílená
regrese. Ověření na Windows dosud nebylo dokončeno.

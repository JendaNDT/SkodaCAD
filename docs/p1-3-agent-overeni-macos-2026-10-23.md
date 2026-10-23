# P1.3 — převzetí zbývajících zkoušek agentem, 23. 10. 2026

Autor požádal: „Nemůžeme tyto ruční testy přeskákat? Nebo nemůžeš je udělat ty sám?“
Zbývající kontroly proto přebírá agent. Nejde o potvrzení jednotlivých případů
autorem ani o pokyn ke sloučení [PR #37](https://github.com/JendaNDT/SkodaCAD/pull/37).

## Co skutečně potvrdil autor

Na staženém Mac sestavení **76891b9783ba (2026-10-22)** autor potvrdil spuštění
a údaj sestavení, přírubu `t = 18 → 20`, odpovídající objemy přibližně
311 093 → 345 784 mm³, jedno těleso a platné prvky, Zpět/Znovu, uložení
upravené kopie a její nové otevření. Samostatně potvrdil původní obsah originálu.
Poslední bod je kontrola obsahu, nikoli porovnání bajtů.

Případy hran, ploch, poloměru, projekce a řezu autor nepotvrdil. Jeho starší
potvrzení P1.2B se sem nepřenášejí. Výše uvedené sestavení předchází opravě
skicáře popsané níže; nejde o přijetí nového sestavení po této opravě.

## Pokus o přímé ovládání stažené aplikace

Agent připojil skutečnou novou aplikaci přes nástroj ovládání počítače, prohlédl
otevřenou přírubu a přes nativní Uložit jako zachoval její pracovní stav v nové
kopii `00-pred-prevzetim.json` (formát 22, `t = 20`). Kontrolní otevření této kopie
ve zdrojovém integračním testu potvrdilo 345 783,584208 mm³ a jedno platné těleso.

Po zavření nativního dialogu přestalo ovládání okna odpovídat chybou
`-10005: timeoutReached`. Finder dál odpovídal. Po jednom restartu potvrzeném
autorem se připojení obnovilo, ale stejný problém nastal po otevření dalšího
modelu. Diagnostický vzorek procesu ukazoval čekání v běžné smyčce AppKit;
zamrznutí samotné aplikace tím prokázané není. Agent toto nepovažuje za úspěšný
průchod zbývajících případů skutečnými kliky ve staženém balíčku.

## Automatizované doplnění a nalezená chyba

Samostatný testovací průchod používá Qt **offscreen**, náhradní prohlížeč,
programově předané skutečné tvary OCCT a skutečný pomocný proces. Ovládá
existující akce okna/skicáře; dialogům předává zkušební cesty. Není to zkouška
nativních dialogů, GPU, fyzického výběru myší ani samotného staženého balíčku.

První průchod odhalil chybu na návratu ze skicáře: `FieldsForm._build_profile`
přenášel body, segmenty a vazby, ale vynechal slovník `references`. Samotná
oprava promítnuté hrany se tak do modelu nepropsala. V rámci schváleného S12/S17
je doplněn přenos tohoto stávajícího volitelného pole; jeho nepřítomnost se
zachová. Formát 22, závislosti, algoritmy NDT ani ovládání se nemění.

Nový `test_reference_sketcher_roundtrip` ověřuje nahrazení vadné projekce,
její smazání a přidání první projekce do existující skici. Stiskne skutečné
tlačítko formuláře, použije akce Smazat/Promítnout ve skicáři, ověří přesný
přenesený obrys, fyzický váleček a objem, Zpět/Znovu, uloženou kopii a byte shodný
originál. Tři nové případy prošly za 2,66 s. Při obnovení pouze původního
přenosu v paměti všechny tři selhaly; potvrzují tedy právě tuto regresi.
Ruff prošel a celý pytest dokončil **1 451 případů / 429,85 s**, bez chyb
a přeskočení. Obě nová CI sestavení jsou při vzniku tohoto záznamu rozpracovaná.

Po opravě prošlo **6 doplňkových scénářů / 7,96 s** (36 zaznamenaných stavů):

| Scénář | Ověřený výsledek |
|---|---|
| Zachovaná pracovní příruba | Kopie se znovu načte, `t = 20`, 1 těleso, 345 783,584208 mm³. |
| Hrany | Česká nejednoznačnost a přeskočený prvek; nově vybraná hrana opraví pouze správný roh, 23 922,743339 mm³; historie a kopie zachované. |
| Plochy | Dva kvádry / 8 000 mm³; vadné měření bez čísla, potvrzení chybné PT oblasti zakázané. Nová oblast je nejprve zastaralá, samostatné potvrzení ji opraví. Nové měření 400 mm², historie a kopie v pořádku. |
| Poloměr | Válec Ø 12 × 10 / 1 130,973355 mm³; starý pevný R5 nemá platné číslo. Nový výběr uloží průměr 12 mm, oblast vyžaduje samostatné potvrzení; historie a kopie v pořádku. |
| Projekce | Smazání vadné a nové promítnutí ve skicáři se po opravě přenese do modelu, kružnice R1 zůstane; objem 24 006,283185 mm³, historie a kopie v pořádku. |
| Řez | Y = 0 má 320 mm². Skutečný fragment horní plochy vytvoří PT oblast na původní ploše; umělá stěna řezu se odmítne bez změny receptu či historie. Nové sezení načte kopii bez řezu. |

NDT studie ve všech těchto kontrolách zůstaly odborně **„Neověřeno.“**
Všech šest původních receptů zůstalo byte shodných. Současné sezení smí po
opětovném otevření zachovat svůj pohled řezu; nepřítomnost řezu v uloženém
receptu se ověřuje novým sezením, nikoli požadavkem na jeho automatické vypnutí.

## Přiznané zbývající meze

Nové úplné místní testy po opravě prošly; zbývají obě celé CI včetně self-testu
staženého balíčku. Původní úspěšné běhy 39864017429/39864017473 zůstávají důkazem
pro původní hlavu `6fdd337`, nikoli pro novou opravu. Konečné identity a výsledky
patří do popisu PR a aktuální přílohy předání.

Úplné ruční přijetí konečného balíčku na Macu, ruční průchod Windows a odborná
NDT-17 se neprohlašují za hotové. Autor nemusí opakovat dlouhý vedený postup;
případné přijetí s těmito výslovně uvedenými mezerami a pokyn ke sloučení jsou
jeho samostatná rozhodnutí. Zbytková historická identita R04 zůstává otevřená.

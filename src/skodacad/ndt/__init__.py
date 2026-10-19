"""NDT – předběžné posouzení proveditelnosti nedestruktivní kontroly (UT, PT, MT, RT).

Samostatná analytická vrstva nad modelem: nikdy nemění geometrii dílu. Plán vývoje je
v ``docs/ndt/03-implementacni-plan.md``, rozhodnutí etap 00–01 v ``04-navrh-etapa-00-01.md``.
Rozsah UT závazně vymezuje ``docs/ndt/04-zavazne-vymezeni-ut.md`` (má přednost před plánem):
jen přístupnost sondy a geometrické pokrytí – ne prozvučitelnost materiálu ani detekovatelnost
vad. ``UT_DISCLAIMER`` je povinné upozornění v přesném znění z tohoto dokumentu. Rozsah PT
vymezuje ``docs/ndt/20-vymezeni-pt.md`` (jen geometrická přístupnost povrchu – ne smáčivost,
vzlínání, citlivost ani detekovatelnost vad), povinné upozornění je ``PT_DISCLAIMER``. Rozsah MT
vymezuje ``docs/ndt/22-vymezeni-mt.md`` (jen geometrie zkoušky jhem – ne intenzita ani rozložení
pole, citlivost ani detekovatelnost vad), povinné upozornění je ``MT_DISCLAIMER``. Rozsah RT
vymezuje ``docs/ndt/24-vymezeni-rt.md`` (jen geometrie projekce – ne dávka ani radiační ochrana,
expozice, kvalita obrazu, citlivost ani detekovatelnost vad), povinné upozornění je
``RT_DISCLAIMER``.
"""

DISCLAIMER = ("Předběžné posouzení proveditelnosti NDT. Nenahrazuje kvalifikovaný postup, "
              "normové vyhodnocení ani reálnou kontrolu.")
UT_DISCLAIMER = ("ŠkodaCAD provádí pouze geometrické posouzení přístupnosti ultrazvukové sondy "
                 "a pokrytí kontrolované oblasti na základě zjednodušeného modelu ultrazvukového "
                 "svazku. Nevyhodnocuje fyzikální prozvučitelnost materiálu ani detekovatelnost "
                 "vad. Výsledky nenahrazují kvalifikovaný NDT postup ani odborné posouzení.")
UT_ACCESS = "Přístupnost UT sondy"  # doporučené názvy v okně a protokolech
UT_COVERAGE = "Mapa geometrického pokrytí UT"
PT_DISCLAIMER = ("ŠkodaCAD provádí pouze geometrické posouzení přístupnosti povrchu pro "
                 "jednotlivé kroky kapilární zkoušky (nanesení, čištění a odstranění přebytku, "
                 "vývojka, prohlídka) na základě zjednodušených modelů nástrojů a výhledu. "
                 "Nevyhodnocuje smáčivost, vzlínání ani odstranitelnost penetrantu, citlivost "
                 "zkoušky ani detekovatelnost vad. Výsledky nenahrazují kvalifikovaný NDT postup "
                 "ani odborné posouzení.")
PT_ACCESS = "Přístupnost povrchu pro PT"  # doporučené názvy v okně a protokolech
PT_MAP = "Mapa geometrické přístupnosti PT"
MT_DISCLAIMER = ("ŠkodaCAD provádí pouze geometrické posouzení magnetické práškové zkoušky "
                 "jhem: kam lze přiložit zjednodušený model jha, kterým orientačním směrem by "
                 "mezi póly vedlo magnetické pole, zda lze místo pokrýt dvěma směry magnetizace "
                 "a zda je místo přístupné pro nanesení detekčního prostředku a prohlídku. "
                 "Nevyhodnocuje intenzitu ani skutečné rozložení magnetického pole, vliv "
                 "materiálu, mezery pod póly a tvaru dílu na pole, citlivost zkoušky ani "
                 "detekovatelnost vad. Výsledky nenahrazují kvalifikovaný NDT postup ani "
                 "odborné posouzení.")
MT_ACCESS = "Přiložení jha a směry magnetizace pro MT"  # doporučené názvy v okně a protokolech
MT_MAP = "Mapa geometrické proveditelnosti a směrového pokrytí MT"
RT_DISCLAIMER = ("ŠkodaCAD provádí pouze geometrické posouzení radiografické zkoušky: kam lze "
                 "umístit zjednodušený model zdroje a detektoru, kudy vedou přímé paprsky "
                 "z ohniska dílem, jakou tloušťku materiálu prozařují, kam se oblast promítne "
                 "na detektor a jaké je geometrické zvětšení a geometrická neostrost z rozměru "
                 "ohniska. Nevyhodnocuje dávku ani radiační ochranu, expoziční parametry, "
                 "rozptýlené záření, kontrast, zčernání ani kvalitu obrazu, viditelnost "
                 "indikátorů kvality obrazu, citlivost zkoušky ani detekovatelnost vad. Výsledky "
                 "nenahrazují kvalifikovaný NDT postup, odborné posouzení ani posouzení radiační "
                 "ochrany.")
RT_ACCESS = "Geometrie projekce RT"  # doporučené názvy v okně a protokolech
RT_MAP = "Mapa geometrického promítnutí oblasti RT"
RT_PREVIEW = "Náhled prozařované tloušťky – není radiografický snímek"

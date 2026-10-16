"""NDT – předběžné posouzení proveditelnosti nedestruktivní kontroly (UT, PT, MT, RT).

Samostatná analytická vrstva nad modelem: nikdy nemění geometrii dílu. Plán vývoje je
v ``docs/ndt/03-implementacni-plan.md``, rozhodnutí etap 00–01 v ``04-navrh-etapa-00-01.md``.
Rozsah UT závazně vymezuje ``docs/ndt/04-zavazne-vymezeni-ut.md`` (má přednost před plánem):
jen přístupnost sondy a geometrické pokrytí – ne prozvučitelnost materiálu ani detekovatelnost
vad. ``UT_DISCLAIMER`` je povinné upozornění v přesném znění z tohoto dokumentu.
"""

DISCLAIMER = ("Předběžné posouzení proveditelnosti NDT. Nenahrazuje kvalifikovaný postup, "
              "normové vyhodnocení ani reálnou kontrolu.")
UT_DISCLAIMER = ("ŠkodaCAD provádí pouze geometrické posouzení přístupnosti ultrazvukové sondy "
                 "a pokrytí kontrolované oblasti na základě zjednodušeného modelu ultrazvukového "
                 "svazku. Nevyhodnocuje fyzikální prozvučitelnost materiálu ani detekovatelnost "
                 "vad. Výsledky nenahrazují kvalifikovaný NDT postup ani odborné posouzení.")
UT_ACCESS = "Přístupnost UT sondy"  # doporučené názvy v okně a protokolech
UT_COVERAGE = "Mapa geometrického pokrytí UT"

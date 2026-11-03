# P7.34 — bezpečné přejmenování parametru sestavy

V editoru **Parametry sestavy…** vyber řádek a použij **Přejmenovat**, případně
uprav přímo buňku názvu. Enter dokončí název a přepíše odpovídající odkazy:

- ve výrazech ostatních parametrů;
- v osách X/Y/Z polohy a otočení komponent, včetně nadřazených podsestav;
- ve vzdálenostních vazbách této úrovně sestavy.

Přehled použití ihned ukáže nový název i nové výrazy. Jde o pracovní změnu;
teprve **Použít změny** přijme celou dávku jako jeden krok Zpět. **Zrušit** ponechá
model, výsledek a historii beze změn. Opakované přejmenování funguje i pro nový
parametr; názvy lze prohodit přes volný dočasný název. Obsazený či neplatný název
vrátí buňku k původnímu názvu a nepřepíše žádný odkaz.

## Provedení a meze

`assembly_parameter_rename.py` určuje přesné odkazy pomocí AST a nahrazuje jejich
UTF-8 rozsahy od konce. Zachovává okolní zápis výrazu, komentáře, matematické funkce
a podobné názvy (`d` není `delsi`). Nevkládá ani nespouští uživatelský kód.
Podporuje české znaky i víceřádkové výrazy včetně CR/LF. Nečitelný výraz se odmítne
s místem chyby; nelze bezpečně hádat, zda obsahuje odkaz. Rezervované názvy a
nekanonické kompatibilní znaky Unicode se jako nový název nepřijímají, aby se název
při vyhodnocení nezaměnil za jiný identifikátor.

`AssemblySession.rename_parameter` přejmenuje parametr a odkazy jednou transakcí.
Editor může spojit přejmenování s dalšími pracovními úpravami: předá finální
parametry a seřazený seznam přejmenování do `set_parameters`. Session v kopii
přehraje přepis poloh a vazeb a ověří parametry, jejich použití i případný nový
spor vazeb před přijetím. Změny hodnot zůstávají samostatným záměrem autora;
samotné přejmenování zachovává skutečnou geometrii.

Nepřepisují se popisy, názvy/id komponent a vazeb, cesty souborů ani vnitřní
parametry zdrojových dílů nebo podsestav. Zdrojové soubory se nemění, formát,
geometrické jádro a závislosti zůstávají stejné.

## Ověření

`tests/test_assembly_parameter_rename.py` ověřuje přesné tokeny, komentáře, české
znaky, UTF-8 rozsahy, různé konce řádků, kolize a neplatné názvy, odmítnutí
nečitelného výrazu i nulovou změnu při chybě. Porovnává skutečné vrcholy, objemy
a platnost těles před/po přejmenování a po Zpět/Znovu, uložení a otevření. Vazba
po přejmenování dál reaguje na změnu hodnoty. Testuje také oddělení podsestav,
neměnné zdrojové soubory, zachování existujícího Znovu, přehled použití, stabilní
buňky, zrušení a prohození názvů v jedné dávce.

Nativní self-test **Přejmenování parametru sestavy** používá skutečné tlačítko
a Enter. Přejmenuje `mezera` na `vule_vicka` v odvozeném parametru, posunu,
otočení i vzdálenostní vazbě, ověří přehled, geometrii, kameru, sedm splněných
vazeb, jeden krok Zpět/Znovu, odmítnutou kolizi názvů a zrušení bez změn.
Scénář je součástí self-testů stažených aplikací Windows i macOS. Místní evidence
a snímek jsou v `out/assembly-parameter-rename/`; úplné kontroly v implementačním PR.

# Pracovní výkres s řezem a exportem

Výkres může obsahovat jeden osový řez. Osa, poloha v milimetrech a směr se
ukládají do projektu a podporují Zpět/Znovu. Na listu je poloha řezu napsaná
u pohledu a řezová rovina i směr pohledu jsou vyznačeny v odpovídajícím
původním pohledu. Pokud
řez míjí díl, není platný nebo se nevejde na stránku, náhled ani export se
nevydávají za dokončené.

Export je jednostránkový PDF nebo DXF; rozměry na listu jsou v mm. PDF používá
vektorové úsečky; kružnice aproximuje s maximálním průhybem 0,005 mm na listu.
Přímé B-spliny prvního stupně převádí přesně podle uzlů. Ostatní nepodporované
křivky PDF výslovně odmítne; DXF používá geometrický převod build123d. Kóty,
pohledy, skryté hrany a šrafy se exportují společně. Popisek uvádí název,
materiál a měřítko; není to úplné popisové pole ani prohlášení o shodě s normou.

Export se zastaví při neplatné kótě, starém přepočtu, změněném řezu nebo chybě
geometrie. Při chybě zůstává případný existující soubor nedotčený. Oba výstupy
obsahují kontrolní úsečku 50 mm a upozornění na kontrolu před výrobou. Tisk je
nutné nastavit na skutečnou velikost a kontrolní úsečku fyzicky změřit.

Ověřeno otevření PDF nezávislou čtečkou, rozměr stránky, text a měřítko
kontrolní úsečky; DXF zkontrolován čtením entit, jednotek a hladin. Otevření DXF
v nezávislé CAD aplikaci a fyzický tisk zatím nejsou ověřené. Automatické hlídání
všech kolizí kót, strojírenské tolerance, drsnosti, a úplné popisové pole zatím chybí. Jde proto o pracovní výkres,
nikoli automaticky schválený podklad pro výrobu.

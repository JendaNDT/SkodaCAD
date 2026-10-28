# Upozornění na možné překrytí kót

Kontrola před exportem hledá překrytí textů kót, textu s jinou kótovací čarou,
vnitřní křížení či souběh kótovacích čar a dotyk textu nebo kótovací čáry
s promítnutými hranami. Zohledňuje také označení řezu a popisové pole. Text
posuzuje podle konzervativní obálky v mm na listu, takže může upozornit i na
situaci, která je vizuálně čitelná. Záměrný kontakt v krajním bodě dvou
kótovacích čar se sám o sobě za kolizi nepovažuje.

Upozornění obsahuje identifikátory kót v náhledu. Před uložením se objeví ve
stavovém řádku a názvu ukládacího okna; po uložení zůstane ve stavovém řádku
a ve výsledném PDF/DXF. Export se bez dalšího potvrzování nezastavuje, protože
jde o odhad, ne o jistotu. Pokud kontrola selže nebo překročí mez složitosti,
upozorní, že není úplná. Naopak neplatné vazby, změněný model a nepodporované
křivky nadále export zastavují a nepřepíší stávající soubor.

Kontrola nerozpoznává všechny kolize ani sama nezajišťuje čitelnost nebo shodu
s výkresovou normou. Uživatel musí zkontrolovat výkres, výrobní údaje a tisk.
Formát modelu se nemění; výsledky kontroly se do modelu neukládají.
